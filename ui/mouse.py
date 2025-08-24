# ui/mouse.py  – rewritten for unified NotebookCache
from __future__ import annotations

import wx

from ui.row import caret_hit, item_rect, has_children
from ui.scroll import soft_ensure_visible
from ui.select import select_row
from ui.cursor import char_pos_from_pixel
from ui.notebook_text import rich_text_from_entry
from core.tree_utils import toggle_collapsed


# ---------------------------------------------------------------------------
# row hit-testing helpers
# ---------------------------------------------------------------------------


def row_at_window_y(view, ywin: int) -> int:
    """
    Map a window-Y coordinate to a row index via LayoutIndex.
    Returns −1 if outside any row.
    """
    if not view._rows:
        return -1

    unit_x, unit_y = view.GetScrollPixelsPerUnit()
    scroll_xu, scroll_yu = view.GetViewStart()  # scroll units
    scroll_y_px = scroll_yu * unit_y

    idx, _ = view._index.find_row_at_y(scroll_y_px + int(ywin))
    return int(idx)


# ---------------------------------------------------------------------------
# click → character-offset helper (unchanged)
# ---------------------------------------------------------------------------


def char_pos_from_click(view, row_idx: int, click_pos: wx.Point) -> int:
    if not (0 <= row_idx < len(view._rows)):
        return 0

    row = view._rows[row_idx]
    entry = view._get(row.entry_id)
    rich_text = rich_text_from_entry(entry)

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

    available_w = (
        view.GetClientSize().width
        - view.DATE_COL_W
        - view.PADDING
        - level * view.INDENT_W
        - view.GUTTER_W
        - 4
    )

    dc = wx.ClientDC(view)
    return char_pos_from_pixel(
        rich_text,
        content_click_x,
        content_click_y,
        text_area_x,
        text_area_y,
        max(10, available_w),
        dc,
        view._font,
        view._bold,
        view.ROW_H,
    )


# ---------------------------------------------------------------------------
# event handlers
# ---------------------------------------------------------------------------


def handle_left_down(view, evt: wx.MouseEvent) -> bool:
    """
    • caret click  → collapse/expand
    • text click   → enter edit mode
    • image row    → just select
    • empty space  → clear selection / save edit
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

    # ---------- caret gutter click ----------
    if caret_hit(view, row, rect, pos) and has_children(view, row):
        if view._edit_state.active:
            view.exit_edit_mode(save=True)
        view.toggle_collapsed_fast(row.entry_id)
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

    # ---------- text click → edit mode ----------
    char_pos = char_pos_from_click(view, idx, pos)
    old_sel = view._sel
    view._sel = idx

    if view._edit_state.active and view._edit_state.row_idx == idx:
        view.set_cursor_position(char_pos)
    else:
        if old_sel != idx and old_sel >= 0:
            view.Refresh()  # clear old highlight
        view.enter_edit_mode(idx, char_pos)
    view.SetFocus()
    return True


def handle_left_dclick(view, evt: wx.MouseEvent) -> bool:
    pos = evt.GetPosition()
    idx = row_at_window_y(view, pos.y)
    if idx < 0 or idx >= len(view._rows):
        return False

    row = view._rows[idx]
    if has_children(view, row):
        if view._edit_state.active:
            view.exit_edit_mode(save=True)
        toggle_collapsed(view.nb_dir, row.entry_id)
        view.invalidate_cache(row.entry_id)
        view.rebuild()
        return True
    return False


def handle_left_up(view, evt: wx.MouseEvent) -> bool:
    return False  # placeholder


def handle_motion(view, evt: wx.MouseEvent) -> bool:
    return False  # placeholder


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
