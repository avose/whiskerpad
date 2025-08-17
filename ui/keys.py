from __future__ import annotations

import wx

from ui.scroll import visible_range
from ui.select import select_row, select_entry_id
from ui.row import has_children
from core.tree_utils import (
    add_sibling_after,
    indent_under_prev_sibling,
    outdent_to_parent_sibling,
    toggle_collapsed,
)

def handle_key_event(view, evt: wx.KeyEvent) -> bool:
    """
    Centralized key routing for GCView.
    Returns True if the event was handled (selection moved, model changed, etc.).
    """
    # Handle edit mode keys first
    if view._edit_state.active:
        return handle_edit_mode_keys(view, evt)
    
    # Handle navigation mode keys
    return handle_navigation_keys(view, evt)

def handle_edit_mode_keys(view, evt: wx.KeyEvent) -> bool:
    """Handle all keyboard input during text editing."""
    code = evt.GetKeyCode()
    
    # Escape - cancel editing
    if code == wx.WXK_ESCAPE:
        view.exit_edit_mode(save=False)
        return True
    
    # Enter key handling
    if code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
        if evt.ShiftDown():
            # Shift+Enter: insert literal newline
            view.insert_text_at_cursor("\n")
        else:
            # Regular Enter: finish editing and create new sibling (empty)
            current_entry_id = view._edit_state.entry_id
            view.exit_edit_mode(save=True)

            # Create new empty sibling after current node
            new_id = add_sibling_after(view.nb_dir, current_entry_id)
            if new_id:
                view.rebuild()
                # Find and start editing the new node
                for i, row in enumerate(view._rows):
                    if row.entry_id == new_id:
                        view._change_selection(i)
                        view.enter_edit_mode(i, 0)
                        break
        return True

    # Tab handling - indent/outdent the current node
    if code == wx.WXK_TAB:
        current_entry_id = view._edit_state.entry_id
        view.exit_edit_mode(save=True)  # Save current edit
        
        if evt.ShiftDown():
            # Shift+Tab: outdent
            if outdent_to_parent_sibling(view.nb_dir, current_entry_id):
                view.rebuild()
                view.select_entry(current_entry_id, ensure_visible=True)
        else:
            # Tab: indent
            if indent_under_prev_sibling(view.nb_dir, current_entry_id):
                view.rebuild()
                view.select_entry(current_entry_id, ensure_visible=True)
        return True
    
    # Cursor movement
    if code == wx.WXK_LEFT:
        view.move_cursor(-1)
        return True
        
    if code == wx.WXK_RIGHT:
        view.move_cursor(1)
        return True
    
    if code == wx.WXK_UP:
        # Move to previous line or exit to navigation mode
        # For now, just move cursor to beginning
        view.set_cursor_position(0)
        return True
        
    if code == wx.WXK_DOWN:
        # Move to next line or exit to navigation mode
        # For now, just move cursor to end
        if view._edit_state.rich_text:
            view.set_cursor_position(view._edit_state.rich_text.char_count())
        return True
    
    # Home/End within current line
    if code == wx.WXK_HOME:
        view.set_cursor_position(0)
        return True
        
    if code == wx.WXK_END:
        if view._edit_state.rich_text:
            view.set_cursor_position(view._edit_state.rich_text.char_count())
        return True
    
    # Backspace and Delete
    if code == wx.WXK_BACK:
        view.delete_char_before_cursor()
        return True
    
    if code == wx.WXK_DELETE:
        view.delete_char_after_cursor()
        return True
    
    # Text input - handle regular characters
    unicode_key = evt.GetUnicodeKey()
    raw_key = evt.GetKeyCode()

    if unicode_key != wx.WXK_NONE and unicode_key > 31:  # Printable characters
        char = chr(unicode_key)

        # Handle case sensitivity and shift characters properly
        if char.isalpha():
            # For letters, manually apply shift state
            if not evt.ShiftDown():
                char = char.lower()
        elif evt.ShiftDown() and raw_key in range(ord('0'), ord('9') + 1):
            # Handle shift+number keys for symbols
            shift_map = {
                ord('1'): '!', ord('2'): '@', ord('3'): '#', ord('4'): '$',
                ord('5'): '%', ord('6'): '^', ord('7'): '&', ord('8'): '*',
                ord('9'): '(', ord('0'): ')'
            }
            char = shift_map.get(raw_key, char)
        elif evt.ShiftDown():
            # Handle other shift combinations
            shift_map = {
                ord(';'): ':', ord('='): '+', ord(','): '<', ord('-'): '_',
                ord('.'): '>', ord('/'): '?', ord('`'): '~', ord('['): '{',
                ord('\\'): '|', ord(']'): '}', ord("'"): '"'
            }
            char = shift_map.get(raw_key, char)

        view.insert_text_at_cursor(char)
        return True
    
    # Let other keys pass through
    return False

def handle_navigation_keys(view, evt: wx.KeyEvent) -> bool:
    """Handle keyboard input when not in edit mode (tree navigation)."""
    if not view._rows:
        return False

    code = evt.GetKeyCode()
    n = len(view._rows)
    sel = view._sel

    # ---------- Indent / Outdent ----------

    # Shift+Tab => outdent one level (move after parent)
    if code == wx.WXK_TAB and evt.ShiftDown():
        if 0 <= sel < n:
            cur_id = view._rows[sel].entry_id
            if outdent_to_parent_sibling(view.nb_dir, cur_id):
                view.rebuild()
                view.select_entry(cur_id, ensure_visible=False)
        return True

    # Tab => indent under previous sibling
    if code == wx.WXK_TAB:
        if 0 <= sel < n:
            cur_id = view._rows[sel].entry_id
            if indent_under_prev_sibling(view.nb_dir, cur_id):
                view.rebuild()
                view.select_entry(cur_id, ensure_visible=False)
        return True

    # ---------- Navigation ----------

    # Up
    if code in (wx.WXK_UP, wx.WXK_NUMPAD_UP):
        if sel > 0:
            select_row(view, sel - 1)
        return True

    # Down
    if code in (wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN):
        if sel < n - 1:
            select_row(view, sel + 1)
        return True

    # PageUp → jump to first fully visible; if already there, go one up
    if code == wx.WXK_PAGEUP:
        first, _ = visible_range(view)
        target = first - 1 if sel == first and first > 0 else first
        if 0 <= target < n and target != sel:
            select_row(view, target)
        return True

    # PageDown → jump to last fully visible; if already there, go one down
    if code == wx.WXK_PAGEDOWN:
        _, last = visible_range(view)
        target = sel + 1 if sel == last and sel < n - 1 else last
        if 0 <= target < n and target != sel:
            select_row(view, target)
        return True

    # Home / End
    if code == wx.WXK_HOME:
        if sel != 0 and n > 0:
            select_row(view, 0)
        return True

    if code == wx.WXK_END:
        if n > 0 and sel != n - 1:
            select_row(view, n - 1)
        return True

    # ---------- Toggle collapse / expand (Space) ----------
    if code == wx.WXK_SPACE:
        if 0 <= sel < n:
            r = view._rows[sel]
            if has_children(view, r):
                toggle_collapsed(view.nb_dir, r.entry_id)
                view.invalidate_cache(r.entry_id)
                view.rebuild()
        return True

    # ---------- Add sibling after (Enter) ----------
    if code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
        if 0 <= sel < n:
            cur_id = view._rows[sel].entry_id
            new_id = add_sibling_after(view.nb_dir, cur_id)
            if new_id:
                view.rebuild()
                # Find and start editing the new empty node
                for i, row in enumerate(view._rows):
                    if row.entry_id == new_id:
                        view.enter_edit_mode(i, 0)
                        break
        return True

    # ---------- Start editing current row (F2 or double-letter key) ----------
    if code == wx.WXK_F2:
        if 0 <= sel < n:
            # Don't edit image rows
            row = view._rows[sel]
            if not row.cache.get("_is_img"):
                view.enter_edit_mode(sel, 0)
        return True

    return False
