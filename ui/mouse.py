# ui/mouse.py

from __future__ import annotations

import wx
from core.log import Log
from ui.row import caret_hit, item_rect, has_children
from ui.row_utils import date_gutter_hit, caret_hit, item_rect, has_children
from ui.scroll import soft_ensure_visible
from ui.select import select_row
from ui.notebook_text import rich_text_from_entry
from ui.edit_state import find_word_boundaries

# ---------------------------------------------------------------------------
# row hit-testing helpers
# ---------------------------------------------------------------------------

def row_at_window_y(view, ywin: int) -> int:
    """Map a window-Y coordinate to a row index via LayoutIndex."""
    if not view._rows:
        return -1

    unit_x, unit_y = view.GetScrollPixelsPerUnit()
    scroll_xu, scroll_yu = view.GetViewStart()
    scroll_y_px = scroll_yu * unit_y

    idx, _ = view._index.find_row_at_y(scroll_y_px + int(ywin))
    return int(idx)

# ---------------------------------------------------------------------------
# click → character-offset helper
# ---------------------------------------------------------------------------

def char_pos_from_click(view, row_idx: int, click_pos: wx.Point) -> int:
    if not (0 <= row_idx < len(view._rows)):
        return 0

    row = view._rows[row_idx]
    
    scroll_x, scroll_y = view.GetViewStart()
    scroll_y_px = scroll_y * view.GetScrollPixelsPerUnit()[1]

    content_click_x = click_pos.x
    content_click_y = click_pos.y + scroll_y_px

    row_rect = item_rect(view, row_idx)
    level = int(row.level)

    text_area_x = (
        row_rect.x
        + view.DATE_COL_W
        + view.PADDING
        + level * view.INDENT_W
        + view.GUTTER_W
    )

    text_area_y = row_rect.y + view.PADDING

    # Use cache for coordinate conversion
    return view.cache.pixel_to_char(row, content_click_x, content_click_y, text_area_x, text_area_y)

# ---------------------------------------------------------------------------
# Link helpers
# ---------------------------------------------------------------------------

def _get_text_run_at_char_pos(view, row_idx: int, char_pos: int):
    """Get the TextRun that contains the given character position."""
    if not (0 <= row_idx < len(view._rows)):
        return None

    row = view._rows[row_idx]
    entry = view._get(row.entry_id)
    rich_text = rich_text_from_entry(entry)

    if not rich_text or char_pos < 0:
        return None

    current_pos = 0
    for run in rich_text.runs:
        run_end = current_pos + len(run.content)
        if current_pos <= char_pos < run_end:
            return run
        current_pos = run_end

    return None

def _handle_link_click(view, row_idx: int, char_pos: int) -> bool:
    """Check if click was on a link and handle navigation."""
    text_run = _get_text_run_at_char_pos(view, row_idx, char_pos)
    if text_run and text_run.link_target:
        # This is a link click - first exit edit mode if active
        if view._edit_state.active:
            view.exit_edit_mode(save=True)

        # Now navigate to the target
        success = view.navigate_to_entry(text_run.link_target)
        if success:
            view.SetStatusText("Navigated to linked entry")
            Log.debug(f"Link jump to {text_run.link_target=}.", 1)
        else:
            view.SetStatusText("Link target not found (may have been deleted)")
            Log.debug(f"Link target DNE: {text_run.link_target=}.", 0)
        return True

    return False

# ---------------------------------------------------------------------------
# event handlers
# ---------------------------------------------------------------------------

def handle_left_down(view, evt: wx.MouseEvent) -> bool:
    """
    • date gutter click → just select row
    • caret click → collapse/expand
    • link click → navigate to target (exit edit mode first)
    • text click → enter edit mode
    • image row → just select
    • empty space → clear selection / save edit
    """
    pos = evt.GetPosition()
    idx = row_at_window_y(view, pos.y)

    # ---------- click in empty space ----------
    if idx < 0 or idx >= len(view._rows):
        if view._edit_state.active:
            view.exit_edit_mode(save=True)

        old_sel = view._sel
        view._sel = -1
        if old_sel >= 0:
            view.Refresh()

        return True

    rect = item_rect(view, idx)
    row = view._rows[idx]

    # ---------- date gutter click → just select row ----------
    if date_gutter_hit(view, row, rect, pos):
        if view._edit_state.active:
            view.exit_edit_mode(save=True)

        old_sel = view._sel
        view._sel = idx
        if old_sel != idx:
            view.Refresh()

        view.SetFocus()
        return True

    # ---------- caret gutter click ----------
    if caret_hit(view, row, rect, pos):
        if has_children(view, row):
            # Has children - toggle collapse/expand as usual
            if view._edit_state.active:
                view.exit_edit_mode(save=True)

            # Use FlatTree instead of direct toggle_collapsed
            view.flat_tree.toggle_collapse(row.entry_id)

            old_sel = view._sel
            view._sel = idx
            if old_sel != idx:
                view.Refresh()

            view.SetFocus()
            return True

        else:
            # No children - just select the row, don't start editing
            if view._edit_state.active:
                view.exit_edit_mode(save=True)

            old_sel = view._sel
            view._sel = idx
            if old_sel != idx:
                view.Refresh()

            view.SetFocus()
            return True

    # ---------- check if this is an image-token row ----------
    layout = view.cache.layout(row.entry_id) or {}
    if layout.get("is_img"):
        if view._edit_state.active:
            view.exit_edit_mode(save=True)

        old_sel = view._sel
        view._sel = idx
        if old_sel != idx:
            view.Refresh()

        view.SetFocus()
        return True

    # ---------- text click → check for links FIRST, then edit mode ----------
    char_pos = char_pos_from_click(view, idx, pos)

    # ALWAYS check for link clicks first, regardless of edit state
    if _handle_link_click(view, idx, char_pos):
        return True

    old_sel = view._sel
    view._sel = idx

    if view._edit_state.active and view._edit_state.row_idx == idx:
        view.set_cursor_position(char_pos)
        view._edit_state.clear_selection() # Clear selection on single click

        # Prepare for potential drag
        view._drag_start_pos = char_pos
        view._is_dragging = False

    else:
        if old_sel != idx and old_sel >= 0:
            view.Refresh() # clear old highlight

        view.enter_edit_mode(idx, char_pos)

        # Prepare for potential drag
        view._drag_start_pos = char_pos
        view._is_dragging = False

    view.SetFocus()
    return True

def handle_left_dclick(view, evt: wx.MouseEvent) -> bool:
    pos = evt.GetPosition()
    idx = row_at_window_y(view, pos.y)

    if idx < 0 or idx >= len(view._rows):
        return False

    row = view._rows[idx]
    rect = item_rect(view, idx)

    # ---------- caret gutter double-click → toggle collapse ----------
    if caret_hit(view, row, rect, pos) and has_children(view, row):
        if view._edit_state.active:
            view.exit_edit_mode(save=True)

        # Use FlatTree instead of direct toggle_collapsed
        view.flat_tree.toggle_collapse(row.entry_id)

        return True

    # ---------- date gutter double-click → just select row ----------
    if date_gutter_hit(view, row, rect, pos):
        if view._edit_state.active:
            view.exit_edit_mode(save=True)

        old_sel = view._sel
        view._sel = idx
        if old_sel != idx:
            view.Refresh()

        view.SetFocus()
        return True

    # ---------- text area double-click → word selection ----------
    # Check if this is a text row (not image)
    layout = view.cache.layout(row.entry_id) or {}
    if layout.get("is_img"):
        return False

    # Get character position of double-click
    char_pos = char_pos_from_click(view, idx, pos)

    # Enter edit mode if not already editing this row
    if not view._edit_state.active or view._edit_state.row_idx != idx:
        view.enter_edit_mode(idx, char_pos)

    # Select word at click position
    if view._edit_state.active and view._edit_state.rich_text:
        plain_text = view._edit_state.rich_text.to_plain_text()
        start, end = find_word_boundaries(plain_text, char_pos)

        view._edit_state.set_selection(start, end)
        view._edit_state.cursor_pos = end # Position cursor at end of selection
        view._refresh_edit_row()

    return True

def handle_motion(view, evt: wx.MouseEvent) -> bool:
    if not evt.LeftIsDown() or not view._edit_state.active:
        return False

    if hasattr(view, '_drag_start_pos') and view._drag_start_pos is not None:
        pos = evt.GetPosition()
        idx = row_at_window_y(view, pos.y)

        if idx == view._edit_state.row_idx:
            char_pos = char_pos_from_click(view, idx, pos)

            if not view._is_dragging and abs(char_pos - view._drag_start_pos) > 0:
                view._is_dragging = True

            if view._is_dragging:
                # Create/extend selection
                view._edit_state.set_selection(view._drag_start_pos, char_pos)
                view._edit_state.cursor_pos = char_pos
                view._refresh_edit_row()
                return True

    return False

def handle_left_up(view, evt: wx.MouseEvent) -> bool:
    if hasattr(view, '_is_dragging') and view._is_dragging:
        view._is_dragging = False
        view._drag_start_pos = None
        return True

    # Clean up drag state
    if hasattr(view, '_drag_start_pos'):
        view._drag_start_pos = None

    return False

def handle_mousewheel(view, evt: wx.MouseEvent) -> bool:
    """
    Scroll ~48 px per wheel notch (≈8-12 text lines, font-dependent).
    """
    unit_x, unit_y = view.GetScrollPixelsPerUnit()
    rotation = evt.GetWheelRotation()
    delta = evt.GetWheelDelta() or 120

    notches = rotation / float(delta)
    pixels = -int(notches * 48)

    start_x, start_y_units = view.GetViewStart()
    new_y_units = max(0, start_y_units + pixels // unit_y)

    view.Scroll(start_x, new_y_units)
    return True
