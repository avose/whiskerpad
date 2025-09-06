# ui/keys.py

from __future__ import annotations

import wx

from ui.scroll import visible_range
from ui.select import select_row, select_entry_id
from ui.row import has_children
from ui.notebook_text import rich_text_from_entry
from ui.edit_state import find_word_boundaries

# ------------ Multi-line text navigation helpers ------------

def _move_cursor_up_line(edit_state, plain_text):
    """Move cursor up one line, preserving column position when possible."""
    cursor_pos = edit_state.cursor_pos
    lines = plain_text.split('\n')
    current_line, current_col = _get_line_col_from_position(plain_text, cursor_pos)

    if current_line <= 0:
        return None

    prev_line = lines[current_line - 1]
    target_col = min(current_col, len(prev_line))
    new_pos = _get_position_from_line_col(lines, current_line - 1, target_col)
    return new_pos

def _move_cursor_down_line(edit_state, plain_text):
    """Move cursor down one line, preserving column position when possible."""
    cursor_pos = edit_state.cursor_pos
    lines = plain_text.split('\n')
    current_line, current_col = _get_line_col_from_position(plain_text, cursor_pos)

    if current_line >= len(lines) - 1:
        return None

    next_line = lines[current_line + 1]
    target_col = min(current_col, len(next_line))
    new_pos = _get_position_from_line_col(lines, current_line + 1, target_col)
    return new_pos

def _get_line_col_from_position(text, pos):
    """Get line and column numbers from character position."""
    lines = text.split('\n')
    current_pos = 0
    for line_idx, line in enumerate(lines):
        line_end = current_pos + len(line)
        if pos <= line_end:
            col = pos - current_pos
            return line_idx, col
        current_pos = line_end + 1

    return len(lines) - 1, len(lines[-1]) if lines else 0

def _get_position_from_line_col(lines, line_idx, col):
    """Get character position from line and column numbers."""
    if line_idx < 0 or line_idx >= len(lines):
        return None

    pos = 0
    for i in range(line_idx):
        pos += len(lines[i]) + 1

    pos += min(col, len(lines[line_idx]))
    return pos

def _get_cursor_line_and_column(text: str, cursor_pos: int) -> tuple[int, int]:
    """Get the line index and column position of the cursor."""
    lines = text.split('\n')
    current_pos = 0
    for line_idx, line in enumerate(lines):
        line_end = current_pos + len(line)
        if cursor_pos <= line_end:
            col = cursor_pos - current_pos
            return line_idx, col
        current_pos = line_end + 1

    return len(lines) - 1, len(lines[-1]) if lines else 0

def _handle_single_line_arrow_navigation(view, key_code) -> bool:
    """Handle up/down arrows for single-line entries - move between rows."""
    current_row = view._rows[view._sel]
    current_layout = view.cache.layout(current_row.entry_id) or {}

    if current_layout.get("is_img"):
        if key_code in (wx.WXK_UP, wx.WXK_NUMPAD_UP):
            return _move_to_previous_row(view)
        elif key_code in (wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN):
            return _move_to_next_row(view)

    if key_code in (wx.WXK_UP, wx.WXK_NUMPAD_UP):
        return _move_to_previous_row(view)
    elif key_code in (wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN):
        return _move_to_next_row(view)

    return False

def _move_to_previous_row(view) -> bool:
    """Move selection to previous row, entering edit mode only if not an image row."""
    if view._sel > 0:
        view.exit_edit_mode(save=True)
        select_row(view, view._sel - 1)

        prev_row = view._rows[view._sel]
        layout = view.cache.layout(prev_row.entry_id) or {}
        if layout.get("is_img"):
            return True

        prev_entry = view._get(prev_row.entry_id)
        prev_rich_text = rich_text_from_entry(prev_entry)
        cursor_pos = prev_rich_text.char_count()
        view.enter_edit_mode(view._sel, cursor_pos)
        return True

    return False

def _move_to_next_row(view) -> bool:
    """Move selection to next row, entering edit mode only if not an image row."""
    if view._sel < len(view._rows) - 1:
        view.exit_edit_mode(save=True)
        select_row(view, view._sel + 1)

        next_row = view._rows[view._sel]
        layout = view.cache.layout(next_row.entry_id) or {}
        if layout.get("is_img"):
            return True

        view.enter_edit_mode(view._sel, 0)
        return True

    return False

def _update_cursor_position(view, new_pos: int):
    """Update cursor position and refresh display."""
    view._edit_state.cursor_pos = new_pos
    view._edit_state.clear_selection()
    view._edit_state.update_format_from_cursor()
    view._refresh_edit_row()

# ------------ Key event handlers ------------

def handle_key_event(view, evt: wx.KeyEvent) -> bool:
    """Centralized key routing for GCView."""
    if evt.ControlDown():
        code = evt.GetKeyCode()
        if code in (ord('C'), ord('V'), ord('X')):
            return _handle_clipboard_keys(view, evt)

    if view._edit_state.active:
        return handle_edit_mode_keys(view, evt)

    return handle_navigation_keys(view, evt)

# ------------ Edit key handlers ------------

def handle_edit_mode_keys(view, evt: wx.KeyEvent) -> bool:
    """Handle all keyboard input during text editing."""
    code = evt.GetKeyCode()

    if code == wx.WXK_ESCAPE:
        return _handle_escape_key(view)

    if code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
        return _handle_enter_key(view, evt)

    if code == wx.WXK_TAB:
        return _handle_tab_key(view, evt)

    if code in (wx.WXK_LEFT, wx.WXK_RIGHT):
        return _handle_cursor_keys(view, evt)

    if code in (wx.WXK_UP, wx.WXK_NUMPAD_UP, wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN):
        return _handle_vertical_keys(view, evt)

    if code in (wx.WXK_HOME, wx.WXK_END):
        return _handle_home_end_keys(view, evt)

    if code in (wx.WXK_BACK, wx.WXK_DELETE):
        return _handle_delete_keys(view, evt)

    return _handle_text_input(view, evt)

def _handle_escape_key(view) -> bool:
    """Handle Escape key - cancel editing."""
    view.exit_edit_mode(save=False)
    return True

def _handle_enter_key(view, evt) -> bool:
    """Handle Enter key using FlatTree."""
    if evt.ShiftDown():
        # Add line break - may change row height
        view.insert_text_at_cursor("\n")
        view.SetVirtualSize((-1, view._index.content_height()))
        from ui.scroll import soft_ensure_visible
        soft_ensure_visible(view, view._edit_state.row_idx)
        return True
    else:
        # Create new sibling using FlatTree
        current_entry_id = view._edit_state.entry_id
        view.exit_edit_mode(save=True)
        
        # Use FlatTree for sibling creation
        new_id = view.flat_tree.create_sibling_after(current_entry_id)
        
        if new_id:
            # Find and start editing the new node immediately
            for i, row in enumerate(view._rows):
                if row.entry_id == new_id:
                    view.enter_edit_mode(i, 0)
                    from ui.scroll import soft_ensure_visible
                    soft_ensure_visible(view, i)
                    break
        
        return True

def _handle_tab_key(view, evt) -> bool:
    """Handle Tab key using FlatTree."""
    current_entry_id = view._edit_state.entry_id
    current_cursor_pos = view._edit_state.cursor_pos

    # Save the current edit content
    if view._edit_state.rich_text:
        rich_data = view._edit_state.rich_text.to_storage()
        view.cache.set_edit_rich_text(current_entry_id, rich_data)

        # CRITICAL: Force immediate persistence to disk
        from core.tree import commit_entry_edit
        commit_entry_edit(view.notebook_dir, current_entry_id, rich_data)

    # Perform indent/outdent using FlatTree
    success = False
    if evt.ShiftDown():
        success = view.flat_tree.outdent_entry(current_entry_id)
    else:
        success = view.flat_tree.indent_entry(current_entry_id)

    if success:
        # Find the entry in its new position and re-enter edit mode
        for i, row in enumerate(view._rows):
            if row.entry_id == current_entry_id:
                view.enter_edit_mode(i, current_cursor_pos)
                view.select_entry(current_entry_id, ensure_visible=True)
                break

    return True

def _handle_cursor_keys(view, evt) -> bool:
    """Handle left/right arrow keys."""
    code = evt.GetKeyCode()

    if code == wx.WXK_LEFT:
        if evt.ShiftDown():
            new_pos = max(0, view._edit_state.cursor_pos - 1)
            view._edit_state.extend_selection_to(new_pos)
            view._edit_state.cursor_pos = new_pos
            view._edit_state.update_format_from_cursor()
            view._refresh_edit_row()
        else:
            view._edit_state.clear_selection()
            view.move_cursor(-1)
        return True

    elif code == wx.WXK_RIGHT:
        if evt.ShiftDown():
            max_pos = view._edit_state.rich_text.char_count() if view._edit_state.rich_text else 0
            new_pos = min(max_pos, view._edit_state.cursor_pos + 1)
            view._edit_state.extend_selection_to(new_pos)
            view._edit_state.cursor_pos = new_pos
            view._edit_state.update_format_from_cursor()
            view._refresh_edit_row()
        else:
            view._edit_state.clear_selection()
            view.move_cursor(1)
        return True

    return False

def _handle_vertical_keys(view, evt) -> bool:
    """Handle up/down arrow keys for multi-line text and inter-row navigation."""
    if not view._edit_state.active or not view._edit_state.rich_text:
        return False

    plain_text = view._edit_state.rich_text.to_plain_text()
    cursor_pos = view._edit_state.cursor_pos
    code = evt.GetKeyCode()

    # For single-line text, let it fall through to row navigation
    if '\n' not in plain_text:
        return _handle_single_line_arrow_navigation(view, code)

    # Multi-line text - check if we're at boundary lines
    line_idx, col = _get_cursor_line_and_column(plain_text, cursor_pos)
    lines = plain_text.split('\n')

    if code in (wx.WXK_UP, wx.WXK_NUMPAD_UP):
        if line_idx == 0:
            return _move_to_previous_row(view)
        else:
            new_pos = _move_cursor_up_line(view._edit_state, plain_text)
            if new_pos is not None:
                _update_cursor_position(view, new_pos)
            return True

    elif code in (wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN):
        if line_idx == len(lines) - 1:
            return _move_to_next_row(view)
        else:
            new_pos = _move_cursor_down_line(view._edit_state, plain_text)
            if new_pos is not None:
                _update_cursor_position(view, new_pos)
            return True

    return False

def _handle_home_end_keys(view, evt) -> bool:
    """Handle Home/End keys."""
    code = evt.GetKeyCode()

    if code == wx.WXK_HOME:
        if evt.ShiftDown():
            view._edit_state.extend_selection_to(0)
            view._edit_state.cursor_pos = 0
            view._edit_state.update_format_from_cursor()
        else:
            view._edit_state.clear_selection()
            view.set_cursor_position(0)
        view._refresh_edit_row()
        return True

    elif code == wx.WXK_END:
        if view._edit_state.rich_text:
            end_pos = view._edit_state.rich_text.char_count()
            if evt.ShiftDown():
                view._edit_state.extend_selection_to(end_pos)
                view._edit_state.cursor_pos = end_pos
                view._edit_state.update_format_from_cursor()
            else:
                view._edit_state.clear_selection()
                view.set_cursor_position(end_pos)
            view._refresh_edit_row()
        return True

    return False

def _handle_delete_keys(view, evt) -> bool:
    """Handle Backspace/Delete keys."""
    code = evt.GetKeyCode()

    if code == wx.WXK_BACK:
        if view._edit_state.has_selection():
            view.delete_selected_text()
        else:
            view.delete_char_before_cursor()
        return True

    elif code == wx.WXK_DELETE:
        if view._edit_state.has_selection():
            view.delete_selected_text()
        else:
            view.delete_char_after_cursor()
        return True

    return False

def _handle_clipboard_keys(view, evt) -> bool:
    """Handle Ctrl+C/V/X clipboard operations in both edit and navigation modes."""
    code = evt.GetKeyCode()

    if code == ord('C'):
        view.copy()
    elif code == ord('V'):
        view.paste()
    elif code == ord('X'):
        view.cut()

    return True

def _handle_text_input(view, evt) -> bool:
    """Handle regular text character input."""
    unicode_key = evt.GetUnicodeKey()
    raw_key = evt.GetKeyCode()

    if unicode_key == wx.WXK_NONE or unicode_key <= 31:
        return False

    # Delete selection before inserting text
    if view._edit_state.has_selection():
        view.delete_selected_text()

    char = chr(unicode_key)

    # Handle case sensitivity and shift characters
    if char.isalpha():
        if not evt.ShiftDown():
            char = char.lower()
    elif evt.ShiftDown() and raw_key in range(ord('0'), ord('9') + 1):
        shift_map = {
            ord('1'): '!', ord('2'): '@', ord('3'): '#', ord('4'): '$',
            ord('5'): '%', ord('6'): '^', ord('7'): '&', ord('8'): '*',
            ord('9'): '(', ord('0'): ')'
        }
        char = shift_map.get(raw_key, char)
    elif evt.ShiftDown():
        shift_map = {
            ord(';'): ':', ord('='): '+', ord(','): '<', ord('-'): '_',
            ord('.'): '>', ord('/'): '?', ord('`'): '~', ord('['): '{',
            ord('\\'): '|', ord(']'): '}', ord("'"): '"'
        }
        char = shift_map.get(raw_key, char)

    view.insert_text_at_cursor(char)
    return True

# ------------ Navigation key handlers ------------

def handle_navigation_keys(view, evt: wx.KeyEvent) -> bool:
    """Handle keyboard input when not in edit mode (tree navigation)."""
    code = evt.GetKeyCode()

    if code == wx.WXK_ESCAPE:
        return _handle_nav_escape_key(view)

    if code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
        return _handle_nav_enter_key(view)

    if not view._rows:
        return False

    if code == wx.WXK_TAB:
        return _handle_nav_tab_keys(view, evt)

    if code in (wx.WXK_UP, wx.WXK_NUMPAD_UP, wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN):
        return _handle_nav_arrow_keys(view, evt)

    if code in (wx.WXK_PAGEUP, wx.WXK_PAGEDOWN):
        return _handle_nav_page_keys(view, evt)

    if code in (wx.WXK_HOME, wx.WXK_END):
        return _handle_nav_home_end_keys(view, evt)

    if code == wx.WXK_SPACE:
        return _handle_nav_space_key(view)

    if code in (wx.WXK_BACK, wx.WXK_DELETE):
        return _handle_nav_delete_keys(view, evt)

    return False

def _handle_nav_escape_key(view) -> bool:
    """Handle Escape key in navigation mode - clear cut state and bookmark source."""
    cleared_something = False

    if view._cut_entry_id:
        view._cut_entry_id = None
        view.Refresh()
        view.SetStatusText("Cut selection cleared")
        cleared_something = True

    if view._bookmark_source_id:
        view.clear_bookmark_source()
        view.SetStatusText("Bookmark source cleared")
        cleared_something = True

    return cleared_something

def _handle_nav_tab_keys(view, evt) -> bool:
    """Handle Tab/Shift+Tab using FlatTree."""
    sel = view._sel
    if not (0 <= sel < len(view._rows)):
        return False

    cur_id = view._rows[sel].entry_id

    if evt.ShiftDown():
        # Outdent - but don't let top-level entries (level 0) outdent further
        current_row = view._rows[sel]
        if current_row.level == 0:
            return False  # Can't outdent children of hidden root

        success = view.flat_tree.outdent_entry(cur_id)
    else:
        success = view.flat_tree.indent_entry(cur_id)

    if success:
        view.select_entry(cur_id, ensure_visible=False)

    return True

def _handle_nav_arrow_keys(view, evt) -> bool:
    """Handle up/down arrow navigation."""
    code = evt.GetKeyCode()
    sel = view._sel
    n = len(view._rows)

    if code in (wx.WXK_UP, wx.WXK_NUMPAD_UP):
        if sel > 0:
            select_row(view, sel - 1)
        return True
    elif code in (wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN):
        if sel < n - 1:
            select_row(view, sel + 1)
        return True

    return False

def _handle_nav_page_keys(view, evt) -> bool:
    """Handle PageUp/PageDown navigation."""
    code = evt.GetKeyCode()
    sel = view._sel
    n = len(view._rows)

    if code == wx.WXK_PAGEUP:
        first, _ = visible_range(view)
        target = first - 1 if sel == first and first > 0 else first
        if 0 <= target < n and target != sel:
            select_row(view, target)
        return True
    elif code == wx.WXK_PAGEDOWN:
        _, last = visible_range(view)
        target = sel + 1 if sel == last and sel < n - 1 else last
        if 0 <= target < n and target != sel:
            select_row(view, target)
        return True

    return False

def _handle_nav_home_end_keys(view, evt) -> bool:
    """Handle Home/End navigation."""
    code = evt.GetKeyCode()
    sel = view._sel
    n = len(view._rows)

    if code == wx.WXK_HOME:
        if sel != 0 and n > 0:
            select_row(view, 0)
        return True
    elif code == wx.WXK_END:
        if n > 0 and sel != n - 1:
            select_row(view, n - 1)
        return True

    return False

def _handle_nav_space_key(view) -> bool:
    """Handle Space key using FlatTree."""
    sel = view._sel
    if not (0 <= sel < len(view._rows)):
        return False

    row = view._rows[sel]
    if has_children(view, row):
        view.flat_tree.toggle_collapse(row.entry_id)
        return True

    return False

def _handle_nav_enter_key(view) -> bool:
    """Handle Enter key using FlatTree."""
    if len(view._rows) == 0:
        # Handle empty notebook case
        from core.tree import get_root_ids, create_node
        root_ids = get_root_ids(view.notebook_dir)
        if root_ids:
            new_id = create_node(view.notebook_dir, parent_id=root_ids[0], title="")
            if new_id:
                view.rebuild()
                if view._rows:
                    view.enter_edit_mode(0, 0)
                return True

    sel = view._sel
    if not (0 <= sel < len(view._rows)):
        return False

    cur_id = view._rows[sel].entry_id
    
    # Use FlatTree for sibling creation
    new_id = view.flat_tree.create_sibling_after(cur_id)
    
    if new_id:
        # Find and start editing the new node immediately
        for i, row in enumerate(view._rows):
            if row.entry_id == new_id:
                view.enter_edit_mode(i, 0)
                from ui.scroll import soft_ensure_visible
                soft_ensure_visible(view, i)
                break

    return True

def _handle_nav_delete_keys(view, evt) -> bool:
    """Handle Delete/Backspace keys to delete current row."""
    code = evt.GetKeyCode()
    if code not in (wx.WXK_DELETE, wx.WXK_BACK):
        return False

    sel = view._sel
    if not (0 <= sel < len(view._rows)):
        return False

    # Get the main frame and call its delete method
    main_frame = wx.GetApp().GetTopWindow()
    if hasattr(main_frame, '_on_delete'):
        main_frame._on_delete()
        return True

    return False
