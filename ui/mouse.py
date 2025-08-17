from __future__ import annotations

import wx

from ui.row import caret_hit, item_rect, has_children
from ui.scroll import soft_ensure_visible
from ui.select import select_row
from ui.cursor import char_pos_from_pixel
from ui.notebook_text import rich_text_from_entry
from core.tree_utils import toggle_collapsed

def row_at_window_y(view, ywin: int) -> int:
    """
    Robust hit-test: find row index from window Y.
    Map window Y to content Y and ask the index.
    """
    if not view._rows:
        return -1

    ywin = int(ywin)

    unit_x, unit_y = view.GetScrollPixelsPerUnit()
    scroll_xu, scroll_yu = view.GetViewStart()  # units, not pixels
    scroll_y_px = scroll_yu * unit_y

    idx, _y_into = view._index.find_row_at_y(scroll_y_px + ywin)
    return int(idx)

def char_pos_from_click(view, row_idx: int, click_pos: wx.Point) -> int:
    """Convert mouse click coordinates to character position in row text."""
    
    if not (0 <= row_idx < len(view._rows)):
        return 0
    
    row = view._rows[row_idx]
    entry = view._get(row.entry_id)
    
    # Get rich text for this entry
    rich_text = rich_text_from_entry(entry)
    
    # Convert window coordinates to content coordinates
    scroll_x, scroll_y = view.GetViewStart()
    scroll_y_px = scroll_y * view.GetScrollPixelsPerUnit()[1]
    
    # Adjust click position for scroll offset
    content_click_x = click_pos.x
    content_click_y = click_pos.y + scroll_y_px
    
    # Get the text area rectangle for this row (in content coordinates)
    row_rect = item_rect(view, row_idx)
    level = int(row.level)
    
    # Calculate text area position
    text_area_x = row_rect.x + view.DATE_COL_W + view.PADDING + level * view.INDENT_W + view.GUTTER_W
    text_area_y = row_rect.y + view.PADDING
    
    # Calculate available width for text
    available_width = (view.GetClientSize().width - 
                      view.DATE_COL_W - view.PADDING - 
                      level * view.INDENT_W - view.GUTTER_W - 4)
    
    # Use cursor positioning logic with corrected coordinates
    dc = wx.ClientDC(view)
    char_pos = char_pos_from_pixel(
        rich_text,
        content_click_x,  # Now in content coordinates
        content_click_y,  # Now in content coordinates
        text_area_x,
        text_area_y,
        max(10, available_width),
        dc,
        view._font,
        view._bold,
        view.ROW_H
    )
    
    return char_pos

def handle_left_down(view, evt: wx.MouseEvent) -> bool:
    """Handle left mouse button down - enter edit mode or toggle caret."""
    pos = evt.GetPosition()
    idx = row_at_window_y(view, pos.y)

    if idx < 0 or idx >= len(view._rows):
        # Click in empty space - save current edit, exit edit mode, and clear selection
        if view._edit_state.active:
            view.exit_edit_mode(save=True)
        
        # Clear selection and refresh to remove highlight
        old_sel = view._sel
        view._sel = -1
        if old_sel >= 0:
            view.Refresh()  # Full refresh to clear old highlight
        return True

    rect = item_rect(view, idx)
    row = view._rows[idx]

    # Handle caret clicks (existing tree navigation logic)
    if caret_hit(view, row, rect, pos):
        if has_children(view, row):
            # Save current edit before tree operation
            if view._edit_state.active:
                view.exit_edit_mode(save=True)
            
            # Update selection and refresh before tree operation
            old_sel = view._sel
            view._sel = idx
            if old_sel != idx:
                view.Refresh()
            
            toggle_collapsed(view.nb_dir, row.entry_id)
            view.invalidate_cache(row.entry_id)
            view.rebuild()
        return True

    # Check if this is an image row
    if row.cache.get("_is_img"):
        # Image rows can't be edited - just select them
        if view._edit_state.active:
            view.exit_edit_mode(save=True)
        
        # Update selection and refresh
        old_sel = view._sel
        view._sel = idx
        if old_sel != idx:
            view.Refresh()  # This is why images work - we call Refresh here
        
        view.SetFocus()
        return True

    # Click on text - enter edit mode at click position
    char_pos = char_pos_from_click(view, idx, pos)
    
    # Update selection to match the row being edited
    old_sel = view._sel
    view._sel = idx
    
    # If already editing this row, just move cursor
    if (view._edit_state.active and view._edit_state.row_idx == idx):
        view.set_cursor_position(char_pos)
    else:
        # Enter edit mode for this row
        if old_sel != idx and old_sel >= 0:
            # Refresh to clear old selection highlight before entering edit mode
            view.Refresh()
        view.enter_edit_mode(idx, char_pos)
    
    view.SetFocus()
    return True

def handle_left_dclick(view, evt: wx.MouseEvent) -> bool:
    """Double-click toggles collapse if row has children."""
    pos = evt.GetPosition()
    idx = row_at_window_y(view, pos.y)

    if idx < 0 or idx >= len(view._rows):
        return False

    row = view._rows[idx]

    if has_children(view, row):
        # Save current edit before tree operation
        if view._edit_state.active:
            view.exit_edit_mode(save=True)
            
        toggle_collapsed(view.nb_dir, row.entry_id)
        view.invalidate_cache(row.entry_id)
        view.rebuild()
        return True

    return False

def handle_left_up(view, evt: wx.MouseEvent) -> bool:
    # Placeholder in case you later add drag-select; currently no-op.
    return False

def handle_motion(view, evt: wx.MouseEvent) -> bool:
    # Placeholder for hover/drag feedback; currently no-op.
    return False

def handle_mousewheel(view, evt: wx.MouseEvent) -> bool:
    """
    Give each wheel-notch a bigger bite:
    − native unit-height ≈1 px
    − we scroll 24px per notch → ~8-12 text lines depending on font
    """
    unit_x, unit_y = view.GetScrollPixelsPerUnit()  # (px per scroll unit)
    rotation = evt.GetWheelRotation()  # raw delta
    delta = evt.GetWheelDelta() or 120  # platform constant (≈120)
    notches = rotation / float(delta)  # +/-1, +/-2 ...

    pixels = -1 * int(notches * 48)

    start_x, start_y_units = view.GetViewStart()  # in scroll units

    new_y_units = max(0, start_y_units + pixels // unit_y)

    view.Scroll(start_x, new_y_units)
    return True
