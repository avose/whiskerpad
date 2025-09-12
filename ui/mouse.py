# ui/mouse.py
'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''

from __future__ import annotations

import wx
from typing import Tuple, Optional

from core.log import Log
from ui.row import caret_hit, item_rect, has_children
from ui.row_utils import date_gutter_hit, caret_hit, item_rect, has_children, is_image_row
from ui.scroll import soft_ensure_visible
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
    entry = view.cache.entry(row.entry_id)
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

    # ---------- Empty space click ----------
    if idx < 0 or idx >= len(view._rows):
        if view._edit_state.active:
            view.exit_edit_mode(save=True)
        view.select_row(-1)
        return True

    rect = item_rect(view, idx)
    row = view._rows[idx]

    # ---------- Date gutter click, select row ----------
    if date_gutter_hit(view, row, rect, pos):
        if view._edit_state.active:
            view.exit_edit_mode(save=True)
        view.select_row(idx)
        view.SetFocus()
        return True

    # ---------- Caret gutter click ----------
    if caret_hit(view, row, rect, pos):
        if has_children(view, row):
            # Has children - toggle collapse/expand as usual
            if view._edit_state.active:
                view.exit_edit_mode(save=True)
            # Use FlatTree instead of direct toggle_collapsed
            view.flat_tree.toggle_collapse(row.entry_id)
            view.select_row(idx)
            view.SetFocus()
            return True

        else:
            # No children - just select the row, don't start editing
            if view._edit_state.active:
                view.exit_edit_mode(save=True)
            view.select_row(idx)
            view.SetFocus()
            return True

    # ---------- Image-token row click ----------
    layout = view.cache.layout(row.entry_id) or {}
    if layout.get("is_img"):
        if view._edit_state.active:
            view.exit_edit_mode(save=True)
        view.select_row(idx)
        view.SetFocus()
        return True

    # ---------- Text click, check for links FIRST, then edit mode ----------
    char_pos = char_pos_from_click(view, idx, pos)

    # ALWAYS check for link clicks first, regardless of edit state
    if _handle_link_click(view, idx, char_pos):
        return True

    view.select_row(idx)

    if view._edit_state.active and view._edit_state.row_idx == idx:
        view.set_cursor_position(char_pos)
        view._edit_state.clear_selection() # Clear selection on single click

        # Prepare for potential drag
        view._drag_start_pos = char_pos
        view._is_dragging = False

    else:
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

    # ---------- Caret gutter double-click, toggle collapse ----------
    if caret_hit(view, row, rect, pos) and has_children(view, row):
        if view._edit_state.active:
            view.exit_edit_mode(save=True)

        # Use FlatTree instead of direct toggle_collapsed
        view.flat_tree.toggle_collapse(row.entry_id)

        return True

    # ---------- Date gutter double-click, just select row ----------
    if date_gutter_hit(view, row, rect, pos):
        if view._edit_state.active:
            view.exit_edit_mode(save=True)

        view.select_row(idx)
        view.SetFocus()
        return True

    # ---------- Text area double-click, word selection ----------
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

def get_image_rect_near_point(
        view, x: int, y: int
) -> Optional[Tuple[int, int, int, int]]:
    # Get scroll info
    sx, sy = view.GetViewStart()
    sy_px = sy * view.GetScrollPixelsPerUnit()[1]

    # Get row index
    row_idx, _ = view._index.find_row_at_y(sy_px + y)
    if not (0 <= row_idx < len(view._rows)):
        return None

    # Check if this is an image row
    if not is_image_row(view, row_idx):
        return None

    # Get the row rectangle
    row_rect = item_rect(view, row_idx)
    if row_rect.IsEmpty():
        return None

    # Get image dimensions from layout
    row = view._rows[row_idx]
    layout = view.cache.layout(row.entry_id) or {}
    img_w = int(layout.get("img_sw") or 0)
    img_h = int(layout.get("img_sh") or 0)
    if img_w <= 0 or img_h <= 0:
        return None

    # Calculate image position within the row
    x0 = row_rect.x + view._metrics.DATE_COL_W + view._metrics.PADDING + row.level * view._metrics.INDENT_W
    y_text_top = row_rect.y + view._metrics.PADDING
    img_x = x0 + view._metrics.GUTTER_W
    img_y = y_text_top

    # Convert to screen coordinates by subtracting scroll offset
    img_y -= sy_px
    return (img_x, img_y, img_w, img_h)

def handle_mousewheel(view, evt: wx.MouseEvent) -> bool:
    """
    Scroll ~48 px per wheel notch (≈8-12 text lines, font-dependent).
    """
    rotation = evt.GetWheelRotation()
    delta = evt.GetWheelDelta() or 120

    # Check for image zoom with control key down.
    if evt.ControlDown():
        # Compute scaling from wheel rotation delta
        notches = rotation / float(delta)
        zoom_step = 1.1
        scale_factor = zoom_step if notches > 0 else 1.0 / zoom_step
        old_scale = view._img_scale
        new_scale = old_scale * (scale_factor ** abs(notches))
        new_scale = max(1.0, min(10.0, new_scale))
        f = new_scale / old_scale

        # Get mouse position from the event
        mx, my = evt.GetX(), evt.GetY()

        # Get coordinates of the imge on the window
        img_rect = get_image_rect_near_point(view, mx, my)
        if not img_rect:
            # Scale with no panning
            view.set_image_scale_pan(scale=new_scale)
            return True
        img_x, img_y, img_w, img_h = img_rect

        # Anchor is the same center used in drawing for Translate/Scale
        ax = img_x + img_w / 2.0
        ay = img_y + img_h / 2.0

        # Pointer-anchored pan update for center-anchored scaling:
        # p' = f*p + (1 - f)*(M - A)
        new_pan_x = f * view._img_pan_x + (1.0 - f) * (mx - ax)
        new_pan_y = f * view._img_pan_y + (1.0 - f) * (my - ay)

        # Apply both scale and pan changes
        view.set_image_scale_pan(scale=new_scale, pan_x=new_pan_x, pan_y=new_pan_y)
        return True

    # Regular mouse wheen event.
    unit_x, unit_y = view.GetScrollPixelsPerUnit()
    notches = rotation / float(delta)
    pixels = -int(notches * 48)

    start_x, start_y_units = view.GetViewStart()
    new_y_units = max(0, start_y_units + pixels // unit_y)

    view.Scroll(start_x, new_y_units)
    return True
