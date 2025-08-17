from __future__ import annotations

import wx
from typing import Dict, Any, List, Optional

from core.tree import load_entry, commit_entry_edit, cancel_entry_edit, set_entry_edit_text
from core.tree_utils import (
    add_sibling_after,
    indent_under_prev_sibling,
    outdent_to_parent_sibling,
    toggle_collapsed,
)

from ui.constants import INDENT_W, GUTTER_W, PADDING, DATE_COL_W, DEFAULT_ROW_H
from ui.types import Row
from ui.model import flatten_tree
from ui.layout import measure_row_height
from ui.row import RowPainter, RowMetrics, caret_hit, item_rect
from ui.select import select_entry_id
from ui.mouse import (
    handle_left_down, handle_left_up, handle_left_dclick,
    handle_motion, handle_mousewheel
)
from ui.keys import handle_key_event
from ui.paint import paint_background, paint_rows
from ui.scroll import soft_ensure_visible, visible_range, clamp_scroll_y
from ui.index import LayoutIndex

# NEW: Rich text editing imports
from ui.edit_state import EditState, RichText
from ui.notebook_text import rich_text_from_entry
from ui.cursor import CursorRenderer

class GCView(wx.ScrolledWindow):
    """
    GraphicsContext-based, variable-row-height view of the entry tree with rich text editing.
    """

    def __init__(self, parent: wx.Window, nb_dir: str, root_id: str):
        super().__init__(parent, style=wx.BORDER_SIMPLE | wx.WANTS_CHARS)

        self.nb_dir = nb_dir
        self.root_id = root_id

        # Initialize core data structures - these always exist
        self._entry_cache: Dict[str, Dict[str, Any]] = {}
        self._rows: List[Row] = []
        self._sel: int = -1
        self._wrap_cache_w: int = -1
        self._index: LayoutIndex = LayoutIndex()

        # NEW: Rich text editing state
        self._edit_state = EditState()
        self._cursor_renderer = CursorRenderer()
        
        # NEW: Cursor blinking timer
        self._cursor_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_cursor_blink)

        # Layout constants
        self.INDENT_W = INDENT_W
        self.GUTTER_W = GUTTER_W
        self.PADDING = PADDING
        self.DATE_COL_W = DATE_COL_W

        # RowPainter with explicit metrics
        self._metrics = RowMetrics(
            DATE_COL_W=self.DATE_COL_W,
            INDENT_W=self.INDENT_W,
            GUTTER_W=self.GUTTER_W,
            PADDING=self.PADDING,
        )

        self._row_painter = RowPainter(self, self._metrics)

        # Configure appearance and scrolling
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetDoubleBuffered(True)
        self.SetBackgroundColour(wx.Colour(246, 252, 246))  # ~#F6FCF6
        self.SetScrollRate(0, 1)  # pixel-based vertical scrolling

        # Initialize fonts and calculate row height
        self._font = self.GetFont()
        self._bold = wx.Font(
            self._font.GetPointSize(),
            self._font.GetFamily(),
            wx.FONTSTYLE_NORMAL,
            wx.FONTWEIGHT_BOLD,
        )

        # Calculate row height from font metrics
        dc = wx.ClientDC(self)
        dc.SetFont(self._font)
        lh = dc.GetTextExtent("Ag")[1]
        self.ROW_H = max(lh + 2 * self.PADDING, DEFAULT_ROW_H)

        # Bind events
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEFT_DCLICK, self._on_left_dclick)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_mousewheel)

        # Build initial model
        self.rebuild()

    # ------------------ cache + data ------------------

    def _get(self, eid: str) -> Dict[str, Any]:
        """Get entry from cache or load from disk."""
        e = self._entry_cache.get(eid)
        if e is None:
            e = load_entry(self.nb_dir, eid)
            self._entry_cache[eid] = e
        return e

    def invalidate_cache(self, entry_id: Optional[str] = None) -> None:
        """Invalidate entry and row caches."""
        if entry_id:
            self._entry_cache.pop(entry_id, None)
            for r in self._rows:
                if r.entry_id == entry_id:
                    r.cache.clear()
        else:
            self._entry_cache.clear()
            for r in self._rows:
                r.cache.clear()

    def _change_selection(self, new_idx: int):
        """Change selection and force full refresh to update highlights properly."""
        if not (0 <= new_idx < len(self._rows)):
            new_idx = -1

        if self._sel == new_idx:
            return

        self._sel = new_idx

        # Force full refresh to ensure highlight changes are visible
        self.Refresh(False)

    def rebuild(self) -> None:
        """Re-flatten tree and refresh. Keep selection by entry_id if possible."""
        prev_id = self.current_entry_id()
        old_sel = self._sel  # Store old selection for refresh

        # Clear caches and rebuild model
        self._entry_cache.clear()
        self._rows = flatten_tree(self.nb_dir, self.root_id)
        self._index.rebuild(self, self._rows)

        # Set virtual size for ScrolledWindow
        total_height = self._index.content_height() if self._rows else 0
        self.SetVirtualSize((-1, total_height))

        # Restore selection using the helper method
        if prev_id:
            for i, r in enumerate(self._rows):
                if r.entry_id == prev_id:
                    self._change_selection(i)  # This will refresh both old and new
                    break
        else:
            self._change_selection(-1)  # Clear selection properly

        # Update edit state if editing row changed
        if self._edit_state.active:
            new_idx = -1
            for i, r in enumerate(self._rows):
                if r.entry_id == self._edit_state.entry_id:
                    new_idx = i
                    break

            if new_idx >= 0:
                self._edit_state.row_idx = new_idx
            else:
                self.exit_edit_mode(save=False)

        # Force immediate repaint
        self.Refresh(False)
        self.Update()

    # ------------------ Rich Text Editing ------------------

    def _on_cursor_blink(self, evt):
        """Handle cursor blinking."""
        if self._edit_state.active:
            self._edit_state.cursor_visible = not self._edit_state.cursor_visible
            self._refresh_edit_row()

    def _refresh_edit_row(self):
        """Efficiently refresh just the row being edited."""
        if not self._edit_state.active:
            return

        # Get row rect in content coordinates
        row_rect = item_rect(self, self._edit_state.row_idx)

        # Convert to window coordinates by subtracting scroll offset
        scroll_x, scroll_y = self.GetViewStart()
        scroll_y_px = scroll_y * self.GetScrollPixelsPerUnit()[1]

        # Adjust rect to window coordinates
        window_rect = wx.Rect(
            row_rect.x,
            row_rect.y - scroll_y_px,
            row_rect.width,
            row_rect.height + 4  # Add small margin for cursor
        )

        # Only refresh if the rect is visible in the current window
        client_height = self.GetClientSize().height
        if (window_rect.y < client_height and 
            window_rect.y + window_rect.height > 0):
            self.RefreshRect(window_rect)
        else:
            # Row not visible, no need to refresh
            pass

    def enter_edit_mode(self, row_idx: int, cursor_pos: int = 0):
        """Start editing a row at the specified cursor position."""
        # Save any existing edit first
        self._save_current_edit()

        # Get the row and entry
        if not (0 <= row_idx < len(self._rows)):
            return

        row = self._rows[row_idx]
        entry = self._get(row.entry_id)

        # Get initial rich text
        rich_text = rich_text_from_entry(entry)

        # Start editing
        self._edit_state.start_editing(row_idx, row.entry_id, rich_text, cursor_pos)

        # Start cursor blinking
        self._cursor_timer.Start(500)  # 500ms blink rate

        # Update selection to edited row
        self._sel = row_idx

        # Refresh display
        self.invalidate_cache(row.entry_id)
        self._refresh_edit_row()

    def exit_edit_mode(self, save: bool = True):
        """Stop editing and optionally save changes."""
        if not self._edit_state.active:
            return

        # Get entry_id BEFORE calling stop_editing (which clears it)
        entry_id = self._edit_state.entry_id
        final_rich_text = self._edit_state.stop_editing()
        self._cursor_timer.Stop()

        if save and final_rich_text is not None and entry_id:
            # Commit rich text to storage
            commit_entry_edit(self.nb_dir, entry_id, final_rich_text.to_storage())
        elif entry_id:
            # Cancel: clear the edit field
            cancel_entry_edit(self.nb_dir, entry_id)

        if entry_id:
            self.invalidate_cache(entry_id)

        # Force full refresh to ensure proper redraw of highlights
        self.Refresh()

    def _save_current_edit(self):
        """Save the current edit text to the edit field."""
        if self._edit_state.active and self._edit_state.rich_text and self._edit_state.entry_id:
            # Save plain text to edit field for crash recovery
            plain_text = self._edit_state.get_plain_text()
            set_entry_edit_text(self.nb_dir, self._edit_state.entry_id, plain_text)

    def _invalidate_edit_row_cache(self):
        """Invalidate cache for the row being edited."""
        if self._edit_state.active:
            for r in self._rows:
                if r.entry_id == self._edit_state.entry_id:
                    r.cache.clear()
                    break
            # Rebuild layout for the edited row
            self._index.rebuild(self, self._rows)

    # ------------------ Text Editing Operations ------------------

    def insert_text_at_cursor(self, text: str):
        """Insert text at current cursor position."""
        if not self._edit_state.active:
            return

        self._edit_state.insert_text(text)

        # Immediately save to edit field and invalidate cache
        plain_text = self._edit_state.get_plain_text()
        set_entry_edit_text(self.nb_dir, self._edit_state.entry_id, plain_text)
        self.invalidate_cache(self._edit_state.entry_id)
        self._invalidate_edit_row_cache()
        self._refresh_edit_row()

    def delete_char_before_cursor(self):
        """Delete character before cursor (backspace)."""
        if not self._edit_state.active:
            return

        self._edit_state.delete_before_cursor()

        # Immediately save to edit field and invalidate cache
        plain_text = self._edit_state.get_plain_text()
        set_entry_edit_text(self.nb_dir, self._edit_state.entry_id, plain_text)
        self.invalidate_cache(self._edit_state.entry_id)
        self._invalidate_edit_row_cache()
        self._refresh_edit_row()

    def delete_char_after_cursor(self):
        """Delete character after cursor (delete key)."""
        if not self._edit_state.active:
            return

        self._edit_state.delete_after_cursor()

        # Immediately save to edit field and invalidate cache
        plain_text = self._edit_state.get_plain_text()
        set_entry_edit_text(self.nb_dir, self._edit_state.entry_id, plain_text)
        self.invalidate_cache(self._edit_state.entry_id)
        self._invalidate_edit_row_cache()
        self._refresh_edit_row()

    def move_cursor(self, delta: int):
        """Move cursor by delta characters."""
        if not self._edit_state.active:
            return

        self._edit_state.move_cursor(delta)
        self._refresh_edit_row()

    def set_cursor_position(self, position: int):
        """Set cursor to specific position."""
        if not self._edit_state.active:
            return

        self._edit_state.set_cursor_position(position)
        self._refresh_edit_row()

    # ------------------ painting ------------------

    def _on_paint(self, _evt: wx.PaintEvent):
        """Paint the view using GraphicsContext."""
        dc = wx.AutoBufferedPaintDC(self)
        gc = wx.GraphicsContext.Create(dc)
        ch = self.GetClientSize().height

        paint_background(self, gc, ch)

        # Get scroll position from ScrolledWindow
        scroll_x, scroll_y = self.GetViewStart()
        scroll_y_px = scroll_y * self.GetScrollPixelsPerUnit()[1]

        i0, y_into = self._index.find_row_at_y(scroll_y_px)

        if 0 <= i0 < len(self._rows):
            y = paint_rows(self, gc, first_idx=i0, y0=-y_into, max_h=ch)
        else:
            y = 0

        # Fill any remaining space below content
        if y < ch:
            w = self.GetClientSize().width
            bg = self.GetBackgroundColour()
            if not bg.IsOk():
                bg = wx.Colour(246, 252, 246)
            gc.SetBrush(wx.Brush(bg))
            gc.SetPen(wx.Pen(bg))
            gc.DrawRectangle(self.DATE_COL_W, y, max(0, w - self.DATE_COL_W), ch - y)

    # ------------------ event handlers ------------------

    def _on_left_down(self, evt: wx.MouseEvent):
        if handle_left_down(self, evt):
            return
        evt.Skip()

    def _on_left_up(self, evt: wx.MouseEvent):
        if handle_left_up(self, evt):
            return
        evt.Skip()

    def _on_motion(self, evt: wx.MouseEvent):
        if handle_motion(self, evt):
            return
        evt.Skip()

    def _on_left_dclick(self, evt: wx.MouseEvent):
        if handle_left_dclick(self, evt):
            return
        evt.Skip()

    def _on_mousewheel(self, evt: wx.MouseEvent):
        if handle_mousewheel(self, evt):
            return
        evt.Skip()

    def _on_char(self, evt: wx.KeyEvent):
        if handle_key_event(self, evt):
            return
        evt.Skip()

    def _on_size(self, _evt: wx.SizeEvent):
        """Handle window resize - invalidate wrap cache and rebuild layout."""
        w = self.GetClientSize().width
        if w != self._wrap_cache_w:
            self._wrap_cache_w = w

            # Invalidate wrap cache for all rows
            for r in self._rows:
                r.cache.pop("_wrap_w", None)
                r.cache.pop("_wrap_h", None)
                r.cache.pop("_wrap_lines", None)
                r.cache.pop("_wrap_src", None)

            # Rebuild layout index with new wrap width
            self._index.rebuild(self, self._rows)

            # Update virtual size
            total_height = self._index.content_height() if self._rows else 0
            self.SetVirtualSize((-1, total_height))

            self.Refresh(False)

        _evt.Skip()

    # ------------------ public API ------------------

    def set_root(self, root_id: str):
        """Change the root entry and rebuild the view."""
        self.root_id = root_id
        self.invalidate_cache()
        self.rebuild()

    def current_entry_id(self) -> Optional[str]:
        """Return the currently selected entry ID."""
        if 0 <= self._sel < len(self._rows):
            return self._rows[self._sel].entry_id
        return None

    def select_entry(self, entry_id: str, ensure_visible: bool = True) -> bool:
        """Select an entry by ID."""
        return select_entry_id(self, entry_id, ensure_visible=ensure_visible)

    # Placeholder methods for NotePanel compatibility
    def edit_entry(self, _entry_id: str) -> bool:
        """Edit entry - not implemented in display-only view."""
        return False

    def edit_block(self, _block_id: str) -> bool:
        """Edit block - not implemented in display-only view."""
        return False
