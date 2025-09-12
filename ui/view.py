# ui/view.py

from __future__ import annotations

import wx
import os
import tempfile
from typing import Dict, Any, List, Optional

from ui.decorators import check_read_only

# -----------------------------------------------------------------------------
# project imports
# -----------------------------------------------------------------------------

from core.log import Log
from core.tree import (
    commit_entry_edit,
    cancel_entry_edit,
)

from ui.cache import NotebookCache
from ui.constants import (
    INDENT_W,
    GUTTER_W,
    PADDING,
    DATE_COL_W,
    DEFAULT_ROW_H,
    DEFAULT_BG_COLOR,
)
from ui.icons import wpIcons
from ui.types import Row
from ui.model import flatten_tree
from ui.layout import measure_row_height
from ui.row import RowPainter, RowMetrics
from ui.mouse import (
    handle_left_down,
    handle_left_up,
    handle_left_dclick,
    handle_motion,
    handle_mousewheel,
)
from ui.keys import handle_key_event
from ui.paint import paint_background, paint_rows
from ui.scroll import soft_ensure_visible
from ui.index import LayoutIndex
from ui.drag_drop import ImageDropTarget
from ui.edit_state import EditState, RichText
from ui.notebook_text import rich_text_from_entry
from ui.cursor import CursorRenderer
from ui.clipboard import Clipboard
from ui.row_utils import is_image_row, get_image_file_path, item_rect
from ui.flat_tree import FlatTree

# =============================================================================
class GCView(wx.ScrolledWindow):
    """
    GraphicsContext-based, variable-row-height view of the entry tree
    with inline rich-text editing.
    
    Now uses FlatTree for all tree/row operations.
    """

    def __init__(self, parent: wx.Window, notebook_dir: str, root_id: str, on_image_drop=None):
        super().__init__(parent, style=wx.BORDER_SIMPLE | wx.WANTS_CHARS)

        self.notebook_dir = notebook_dir
        self.root_id = root_id
        self.main_frame = wx.GetApp().GetTopWindow()

        # central cache
        self.cache = NotebookCache(notebook_dir, self)
        self._read_only = False

        # flattened rows + selection
        self._rows: List[Row] = []
        self._sel: int = -1
        self._cut_entry_id: Optional[str] = None
        self._bookmark_source_id: Optional[str] = None

        # layout index
        self._index: LayoutIndex = LayoutIndex()

        # rich-text editing state
        self._edit_state = EditState()
        self._cursor_renderer = CursorRenderer()
        self._cursor_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_cursor_blink)

        # Selection state for drag operations
        self._drag_start_pos = None
        self._is_dragging = False

        # layout constants
        self.INDENT_W = INDENT_W
        self.GUTTER_W = GUTTER_W
        self.PADDING = PADDING
        self.DATE_COL_W = DATE_COL_W

        # row painter
        self._metrics = RowMetrics(
            DATE_COL_W=self.DATE_COL_W,
            INDENT_W=self.INDENT_W,
            GUTTER_W=self.GUTTER_W,
            PADDING=self.PADDING,
        )
        self._row_painter = RowPainter(self, self._metrics)

        # appearance + scrolling
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetDoubleBuffered(True)
        self.SetBackgroundColour(DEFAULT_BG_COLOR)
        self.SetScrollRate(0, 1)

        # fonts + default row height
        self._font = self.GetFont()
        self._bold = wx.Font(
            self._font.GetPointSize(),
            self._font.GetFamily(),
            wx.FONTSTYLE_NORMAL,
            wx.FONTWEIGHT_BOLD,
        )

        dc = wx.ClientDC(self)
        dc.SetFont(self._font)
        lh = dc.GetTextExtent("Ag")[1]
        self.ROW_H = max(lh + 2 * self.PADDING, DEFAULT_ROW_H)

        # CREATE FLATTREE INSTANCE - This is the key integration point
        self.flat_tree = FlatTree(self)

        # Image scale / pan
        self._img_scale = 1.0
        self._img_pan_x = 0.0
        self._img_pan_y = 0.0

        # event bindings
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEFT_DCLICK, self._on_left_dclick)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_mousewheel)
        self.Bind(wx.EVT_RIGHT_DOWN, self._on_context_menu)

        # Track last client width for cheap resize detection
        self._last_client_w = self.GetClientSize().width

        # Set up drag & drop for images
        if on_image_drop:
            drop_target = ImageDropTarget(self, on_image_drop)
            self.SetDropTarget(drop_target)

        # Build model
        self.rebuild()

    def cleanup(self):
        """Clean up resources before destruction to prevent crashes."""
        # Stop the cursor timer
        if hasattr(self, '_cursor_timer') and self._cursor_timer:
            self._cursor_timer.Stop()

        # Exit edit mode cleanly
        if self._edit_state.active:
            self.exit_edit_mode(save=True)

        # Clear cut state
        self._cut_entry_id = None

        # Clear the image cache to free wx.Bitmap objects
        from ui.image_loader import clear_thumb_cache
        clear_thumb_cache()

    def is_read_only(self) -> bool:
        """Check if in read-only mode"""
        if getattr(self, '_read_only', False):
            return True
        try:
            return self.main_frame.is_read_only()
        except:
            pass
        return False

    # ------------------------------------------------------------------ #
    # cache invalidation wrappers
    # ------------------------------------------------------------------ #

    def invalidate_cache(self, entry_id: Optional[str] = None) -> None:
        if entry_id:
            self.cache.invalidate_entry(entry_id)
        else:
            self.cache.invalidate_all()

    def invalidate_cache_selective(self, ids: set[str]) -> None:
        self.cache.invalidate_entries(ids)

    # ------------------------------------------------------------------ #
    # selection helpers
    # ------------------------------------------------------------------ #

    def _change_selection(self, new_idx: int):
        if not (0 <= new_idx < len(self._rows)):
            new_idx = -1
        if self._sel == new_idx:
            return
        # Set the new selection.
        self._sel = new_idx
        # Clear any saved image scale / pan state.
        self.set_image_scale_pan(1.0, 0.0, 0.0)
        # Repaint to update highlight
        self.Refresh(False)

    def select_row(self, idx: int, ensure_visible: bool = True, refresh: bool = True) -> bool:
        """Select a row by index."""
        idx = min(max(idx, 0), len(self._rows)-1)

        self._change_selection(idx)
        if ensure_visible:
            soft_ensure_visible(self, idx)

        return True
    
    def select_entry(self, entry_id: str, ensure_visible: bool = True) -> bool:
        """Select a row by entry id."""
        for i, r in enumerate(self._rows):
            if r.entry_id == entry_id:
                return self.select_row(i, ensure_visible=ensure_visible, refresh=True)
        return False

    # ------------------------------------------------------------------ #
    # rebuilding / flattening
    # ------------------------------------------------------------------ #

    def rebuild(self) -> None:
        """Re-flatten tree, keep selection when possible, rebuild index."""
        prev_id = self.current_entry_id()

        self.cache.invalidate_all()
        self._rows = flatten_tree(self.notebook_dir, self.root_id, self)
        self._index.rebuild(self, self._rows)

        total_h = self._index.content_height() if self._rows else 0
        self.SetVirtualSize((-1, total_h))

        if prev_id:
            for i, r in enumerate(self._rows):
                if r.entry_id == prev_id:
                    self._change_selection(i)
                    break
            else:
                self._change_selection(-1)
        else:
            self._change_selection(-1)

        # sync edit-state row index
        if self._edit_state.active:
            new_idx = next(
                (i for i, r in enumerate(self._rows) if r.entry_id == self._edit_state.entry_id),
                -1,
            )

            if new_idx >= 0:
                self._edit_state.row_idx = new_idx
            else:
                self.exit_edit_mode(save=False)

        self.Refresh(False)
        self.Update()

    # ==========================================================================
    # rich-text editing helpers  (unchanged except cache calls)
    # ==========================================================================

    def _on_cursor_blink(self, _evt):
        if self._edit_state.active:
            self._edit_state.cursor_visible = not self._edit_state.cursor_visible
            self._refresh_edit_row()

    def _refresh_edit_row(self):
        if not self._edit_state.active:
            return

        row_rect = item_rect(self, self._edit_state.row_idx)
        # Add a small buffer for cursor visibility
        row_rect.height += 4
        self._refresh_rect_area(row_rect, extend_to_bottom=False)

    # ------------ Edit mode management ------------

    @check_read_only
    def enter_edit_mode(self, row_idx: int, cursor_pos: int = 0):
        # First, properly exit any active edit mode using the dedicated function
        self.exit_edit_mode(save=True)

        # Now handle ONLY entering edit mode for the new row
        if not (0 <= row_idx < len(self._rows)):
            return

        row = self._rows[row_idx]
        entry = self.cache.entry(row.entry_id)
        Log.debug(f"enter_edit_mode({row_idx=}, {cursor_pos=}), {row.entry_id=}", 10)
        rich_text = rich_text_from_entry(entry)

        # Initialize edit state for the NEW row
        self._edit_state.start_editing(row_idx, row.entry_id, rich_text, cursor_pos)
        self._cursor_timer.Start(500)
        self._sel = row_idx
        self.invalidate_cache(row.entry_id)
        self._refresh_edit_row()

    @check_read_only
    def exit_edit_mode(self, save: bool = True):
        if not self._edit_state.active:
            return

        entry_id = self._edit_state.entry_id
        Log.debug(f"exit_edit_mode(), {entry_id=}", 10)
        final_rt = self._edit_state.stop_editing()
        self._cursor_timer.Stop()

        if save and final_rt and entry_id:
            import json

            # Load the stored content from disk
            entry = self.cache.entry(entry_id)
            stored_text = entry.get("text", [])

            # Get the edited content
            current_text = final_rt.to_storage()

            # Only commit if content actually changed
            if stored_text == current_text:
                cancel_entry_edit(self.notebook_dir, entry_id)
            else:
                commit_entry_edit(self.notebook_dir, entry_id, current_text)

        elif entry_id:
            cancel_entry_edit(self.notebook_dir, entry_id)

        if entry_id:
            self.invalidate_cache(entry_id)
            self._index.rebuild(self, self._rows)
            self.SetVirtualSize((-1, self._index.content_height()))

        self.Refresh()

    # used after each keystroke while editing
    def _invalidate_edit_row_cache(self):
        if self._edit_state.active:
            self.cache.invalidate_entry(self._edit_state.entry_id)
            self._index.rebuild(self, self._rows)

    # ------------------------------------------------------------------ #
    # subtree-specific invalidation  (collapse/expand fast path)
    # ------------------------------------------------------------------ #

    def invalidate_subtree_cache(self, root_entry_id: str):
        ids = self._get_subtree_entry_ids(root_entry_id)
        self.cache.invalidate_entries(ids)

    def _get_subtree_entry_ids(self, root_id: str) -> set[str]:
        result = {root_id}
        try:
            entry = self.cache.entry(root_id)
            for item in entry.get("items", []):
                if isinstance(item, dict) and item.get("type") == "child":
                    cid = item.get("id")
                    if isinstance(cid, str):
                        result.update(self._get_subtree_entry_ids(cid))
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------ #
    # Collapse / expand
    # ------------------------------------------------------------------ #

    def toggle_collapsed_fast(self, entry_id: str):
        """Uses FlatTree for consistent incremental updates."""
        self.flat_tree.toggle_collapse(entry_id)

    def navigate_to_entry(self, entry_id: str) -> bool:
        """Uses FlatTree for ancestor expansion."""
        return self.flat_tree.ensure_entry_visible(entry_id)

    # ------------------------------------------------------------------ #
    # partial refresh helpers
    # ------------------------------------------------------------------ #

    def _refresh_rect_area(self, rect: wx.Rect, extend_to_bottom: bool = False):
        """Common refresh logic for rectangular areas."""
        client_size = self.GetClientSize()
        scroll_x, scroll_y = self.GetViewStart()
        scroll_y_px = scroll_y * self.GetScrollPixelsPerUnit()[1]

        # Convert to window coordinates
        window_y = rect.y - scroll_y_px

        if extend_to_bottom:
            height = client_size.height - window_y
        else:
            height = rect.height

        if height > 0 and window_y < client_size.height:
            refresh_rect = wx.Rect(0, max(0, window_y), client_size.width, height)
            self.RefreshRect(refresh_rect)
        else:
            self.Refresh()

    def _refresh_from_row(self, start_idx: int):
        """Refresh from the specified row to the bottom of the view."""
        if start_idx >= len(self._rows):
            return

        start_rect = item_rect(self, start_idx)
        if start_rect.IsEmpty():
            self.Refresh()
            return

        self._refresh_rect_area(start_rect, extend_to_bottom=True)

    def _refresh_from_row_downward(self, start_idx: int):
        """Refresh from the specified row index to the bottom of the view."""
        if start_idx < 0 or start_idx >= len(self._rows):
            self.Refresh()
            return

        start_rect = item_rect(self, start_idx)
        self._refresh_rect_area(start_rect, extend_to_bottom=True)

    def _refresh_changed_area(self, entry_id: str):
        """Refresh the area for a specific entry."""
        idx = next((i for i, r in enumerate(self._rows) if r.entry_id == entry_id), -1)
        if idx < 0:
            self.Refresh()
            return

        rect = item_rect(self, idx)
        if rect.IsEmpty():
            self.Refresh()
            return

        self._refresh_rect_area(rect, extend_to_bottom=True)

    # ==========================================================================
    # keystroke-driven text edit helpers (unchanged except cache calls)
    # ==========================================================================

    @check_read_only
    def insert_text_at_cursor(self, text: str):
        if not self._edit_state.active:
            return

        # Get current formatting and apply it to new text
        current_format = self._edit_state.get_current_format()
        self._edit_state.rich_text.insert_text(
            self._edit_state.cursor_pos,
            text,
            formatting=current_format
        )
        self._edit_state.cursor_pos += len(text)

        rich_data = self._edit_state.rich_text.to_storage()
        self.cache.set_edit_rich_text(self._edit_state.entry_id, rich_data)
        self.invalidate_cache(self._edit_state.entry_id)
        self._invalidate_edit_row_cache()

        # Update virtual size to handle height changes
        new_height = self._index.content_height()
        self.SetVirtualSize((-1, new_height))

        # If inserting newlines, ensure the edited row stays visible
        if '\n' in text:
            self._refresh_from_row_downward(self._edit_state.row_idx)
            # Ensure the current edit position is still visible
            from ui.scroll import soft_ensure_visible
            soft_ensure_visible(self, self._edit_state.row_idx)
        else:
            self._refresh_edit_row()

    @check_read_only
    def delete_char_before_cursor(self):
        if not self._edit_state.active:
            return

        # Check if we're deleting a newline (affects height)
        plain_text = self._edit_state.rich_text.to_plain_text()
        cursor_pos = self._edit_state.cursor_pos
        deleting_newline = (cursor_pos > 0 and 
                           cursor_pos <= len(plain_text) and 
                           plain_text[cursor_pos - 1] == '\n')

        self._edit_state.delete_before_cursor()
        rich_data = self._edit_state.rich_text.to_storage()
        self.cache.set_edit_rich_text(self._edit_state.entry_id, rich_data)
        self.invalidate_cache(self._edit_state.entry_id)
        self._invalidate_edit_row_cache()

        # Update virtual size and scroll if deleting newlines
        self.SetVirtualSize((-1, self._index.content_height()))

        if deleting_newline:
            from ui.scroll import soft_ensure_visible
            soft_ensure_visible(self, self._edit_state.row_idx)
            self._refresh_from_row_downward(self._edit_state.row_idx)
        else:
            self._refresh_edit_row()

    @check_read_only
    def delete_char_after_cursor(self):
        if not self._edit_state.active:
            return

        # Check if we're deleting a newline (affects height)
        plain_text = self._edit_state.rich_text.to_plain_text()
        cursor_pos = self._edit_state.cursor_pos
        deleting_newline = (cursor_pos < len(plain_text) and 
                           plain_text[cursor_pos] == '\n')

        self._edit_state.delete_after_cursor()
        rich_data = self._edit_state.rich_text.to_storage()
        self.cache.set_edit_rich_text(self._edit_state.entry_id, rich_data)
        self.invalidate_cache(self._edit_state.entry_id)
        self._invalidate_edit_row_cache()

        # Update virtual size and scroll if deleting newlines
        self.SetVirtualSize((-1, self._index.content_height()))

        if deleting_newline:
            from ui.scroll import soft_ensure_visible
            soft_ensure_visible(self, self._edit_state.row_idx)
            self._refresh_from_row_downward(self._edit_state.row_idx)
        else:
            self._refresh_edit_row()

    @check_read_only
    def delete_selected_text(self):
        """Delete the currently selected text."""
        if not self._edit_state.active or not self._edit_state.has_selection():
            return

        selection_range = self._edit_state.get_selection_range()
        if selection_range:
            start, end = selection_range

            # Check if we're deleting across multiple lines
            selected_text = self._edit_state.rich_text.to_plain_text()[start:end]
            has_newlines = '\n' in selected_text

            self._edit_state.rich_text.delete_range(start, end)
            self._edit_state.cursor_pos = start
            self._edit_state.clear_selection()

            # Save changes and update display
            rich_data = self._edit_state.rich_text.to_storage()
            self.cache.set_edit_rich_text(self._edit_state.entry_id, rich_data)
            self.invalidate_cache(self._edit_state.entry_id)
            self._invalidate_edit_row_cache()

            # Update virtual size and refresh properly
            self.SetVirtualSize((-1, self._index.content_height()))

            if has_newlines:
                # If we deleted newlines, refresh from this row downward
                self._refresh_from_row_downward(self._edit_state.row_idx)
            else:
                # For single-line changes, just refresh the row
                self._refresh_edit_row()

    @check_read_only
    def move_cursor(self, delta: int):
        if self._edit_state.active:
            self._edit_state.move_cursor(delta)
            self._edit_state.update_format_from_cursor()
            self._refresh_edit_row()

    @check_read_only
    def set_cursor_position(self, pos: int):
        if self._edit_state.active:
            self._edit_state.set_cursor_position(pos)
            self._edit_state.update_format_from_cursor()
            self._refresh_edit_row()

    # ------------------------------------------------------------------ #
    # painting
    # ------------------------------------------------------------------ #

    def _on_paint(self, _evt: wx.PaintEvent):
        dc = wx.AutoBufferedPaintDC(self)
        gc = wx.GraphicsContext.Create(dc)
        ch = self.GetClientSize().height

        paint_background(self, gc, ch)

        sx, sy = self.GetViewStart()
        sy_px = sy * self.GetScrollPixelsPerUnit()[1]
        i0, y_into = self._index.find_row_at_y(sy_px)

        if 0 <= i0 < len(self._rows):
            y = paint_rows(self, gc, i0, -y_into, ch)
        else:
            y = 0

        if y < ch:
            w = self.GetClientSize().width
            bg = self.GetBackgroundColour() or DEFAULT_BG_COLOR
            gc.SetBrush(wx.Brush(bg))
            gc.SetPen(wx.Pen(bg))
            gc.DrawRectangle(self.DATE_COL_W, y, max(0, w - self.DATE_COL_W), ch - y)

    # ------------------------------------------------------------------ #
    # event dispatch
    # ------------------------------------------------------------------ #

    def _on_left_down(self, evt):  # same handlers as before
        if handle_left_down(self, evt):
            return
        evt.Skip()

    def _on_left_up(self, evt):
        if handle_left_up(self, evt):
            return
        evt.Skip()

    def _on_motion(self, evt):
        if handle_motion(self, evt):
            return
        evt.Skip()

    def _on_left_dclick(self, evt):
        if handle_left_dclick(self, evt):
            return
        evt.Skip()

    def _on_mousewheel(self, evt):
        if handle_mousewheel(self, evt):
            return
        evt.Skip()

    def _on_char(self, evt):
        if handle_key_event(self, evt):
            return
        evt.Skip()

    # ------------------------------------------------------------------ #
    # handle resize – invalidate only layout_data
    # ------------------------------------------------------------------ #

    def _on_size(self, _evt: wx.SizeEvent):
        new_w = self.GetClientSize().width
        if new_w != self._last_client_w:
            self._last_client_w = new_w
            self.cache.invalidate_layout_only()
            self._index.rebuild(self, self._rows)
            self.SetVirtualSize((-1, self._index.content_height()))
            self.Refresh(False)
        _evt.Skip()

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    def set_root(self, root_id: str):
        self.root_id = root_id
        self.invalidate_cache()
        self.rebuild()

    def current_entry_id(self) -> Optional[str]:
        # If we have rows and a valid selection, return the selected entry
        if 0 <= self._sel < len(self._rows):
            return self._rows[self._sel].entry_id

        # For empty notebooks, return the root entry ID so operations can work
        if not self._rows:
            return self.root_id

        # No valid selection
        return None

    # dummy stubs for NotePanel
    def edit_entry(self, _eid: str) -> bool:
        return False

    def edit_block(self, _bid: str) -> bool:
        return False

    def SetStatusText(self, text: str):
        """Set status text in main frame."""
        # Get the main frame and set status text
        Log.debug(text, 0)
        self.main_frame.SetStatusText(text)

    # ------------ Clipboard operations ------------

    @check_read_only
    def copy(self):
        """Copy selected text or mark row as bookmark source."""
        try:
            # If we're in edit mode, check if it's an image row
            if self._edit_state.active:
                if is_image_row(self, self._edit_state.row_idx):
                    image_path = get_image_file_path(self, self._edit_state.row_idx)
                    if image_path:
                        Clipboard.copy_image(image_path)
                        self.SetStatusText("Copied image to clipboard")
                    else:
                        self.SetStatusText("Error: Could not find image file")
                    return

                # Handle text copy (existing logic)
                if not self._edit_state.has_selection():
                    self.SetStatusText("No text selected to copy")
                    return

                selected_text = self._edit_state.get_selected_text()
                if selected_text:
                    Clipboard.copy_text(selected_text)
                    self.SetStatusText(f"Copied {len(selected_text)} characters")
                else:
                    self.SetStatusText("No text selected to copy")

            else:
                # Navigation mode - mark row as bookmark source
                if 0 <= self._sel < len(self._rows):
                    # Clear previous bookmark source
                    old_bookmark_id = self._bookmark_source_id
                    if old_bookmark_id:
                        self._refresh_changed_area(old_bookmark_id)

                    # Clear cut state (mutual exclusion)
                    if self._cut_entry_id:
                        old_cut_id = self._cut_entry_id
                        self._cut_entry_id = None
                        self._refresh_changed_area(old_cut_id)

                    # Set new bookmark source
                    self._bookmark_source_id = self._rows[self._sel].entry_id
                    self._refresh_changed_area(self._bookmark_source_id)

                    # Get entry title for status
                    entry = self.cache.entry(self._bookmark_source_id)
                    title = entry.get('text', [{}])[0].get('content', 'Untitled')[:30]
                    self.SetStatusText(f"Row marked as bookmark source: {title}")
                else:
                    self.SetStatusText("No row selected to bookmark")

        except Exception as e:
            error_msg = f"Copy failed: {e}"
            self.SetStatusText(error_msg)

    @check_read_only
    def paste(self):
        """Uses FlatTree for sibling creation."""
        # First check for link insertion when in edit mode with bookmark source
        if (self._edit_state.active and
            self._bookmark_source_id is not None and
            self._insert_link_from_bookmark_source()):
            return

        # Original paste logic
        if self._cut_entry_id and not self._edit_state.active:
            # Use FlatTree for cut/paste operations
            self._move_cut_row()
        elif Clipboard.has_image():
            # Use FlatTree for image paste
            self._paste_image()
        elif self._edit_state.active:
            # Paste text in edit mode (unchanged)
            self._paste_text()
        else:
            self.SetStatusText("Nothing to paste")

    @check_read_only
    def _paste_image(self):
        """Handle pasting image using FlatTree."""
        temp_image_path = Clipboard.get_image()
        if not temp_image_path:
            self.SetStatusText("Failed to get image from clipboard")
            return

        try:
            from ui.image_import import import_image_into_entry
            from core.tree import load_entry, save_entry

            # Determine where to insert
            if self._edit_state.active:
                current_id = self._edit_state.entry_id
                self.exit_edit_mode(save=True)
            else:
                current_id = self.current_entry_id()

            if not current_id:
                # No selection, use root
                from core.tree import get_root_ids
                root_ids = get_root_ids(self.notebook_dir)
                if root_ids:
                    current_id = root_ids[0]
                else:
                    raise RuntimeError("No location to paste image")

            # Use FlatTree to create sibling
            new_id = self.flat_tree.create_sibling_after(current_id)

            # Import the image
            info = import_image_into_entry(self.notebook_dir, new_id, temp_image_path)
            token = info["token"]

            # Set the entry text to the image token
            entry = load_entry(self.notebook_dir, new_id)
            entry["text"] = [{"content": token}]
            entry["edit"] = ""
            save_entry(self.notebook_dir, entry)

            # Select the new image row
            for i, row in enumerate(self._rows):
                if row.entry_id == new_id:
                    self._change_selection(i)
                    soft_ensure_visible(self, i)
                    break

            self.SetStatusText("Pasted image")

            # Clean up temp file if it was created by us
            if temp_image_path and temp_image_path.startswith(tempfile.gettempdir()):
                try:
                    os.unlink(temp_image_path)
                except Exception:
                    pass  # Ignore cleanup errors

        except Exception as e:
            self.SetStatusText(f"Failed to paste image: {e}")

    @check_read_only
    def _paste_text(self):
        """Handle pasting text from clipboard."""
        if not self._edit_state.active:
            self.SetStatusText("Start editing to paste text")
            return

        text = Clipboard.get_text()
        if text:
            if self._edit_state.has_selection():
                self.delete_selected_text()
            self.insert_text_at_cursor(text)
            self.SetStatusText(f"Pasted {len(text)} characters")
        else:
            self.SetStatusText("No text on clipboard")

    @check_read_only
    def _insert_link_from_bookmark_source(self) -> bool:
        """Insert a link to the bookmark source at the cursor position."""
        if not self._bookmark_source_id or not self._edit_state.active:
            return False

        try:
            # Get the source entry to create default link text
            source_entry = self.cache.entry(self._bookmark_source_id)

            # Get default text from the entry (first 30 chars of content)
            text_content = source_entry.get('text', [{}])
            if text_content and text_content[0].get('content'):
                default_text = text_content[0]['content'].strip()[:30]
                if not default_text:
                    default_text = "Untitled"
            else:
                default_text = "Untitled"

            # If the default text is too long, add ellipsis
            if len(default_text) == 30 and len(source_entry.get('text', [{}])[0].get('content', '')) > 30:
                default_text += "..."

            # Show dialog to get custom link text from user
            dlg = wx.TextEntryDialog(
                self,
                "Enter text for the link:",
                "Insert Link",
                default_text
            )

            if dlg.ShowModal() != wx.ID_OK:
                dlg.Destroy()
                return False  # User cancelled

            # Get the user-entered text
            link_text = dlg.GetValue().strip()
            dlg.Destroy()

            if not link_text:
                self.SetStatusText("Link text cannot be empty")
                return False

            # Insert the link using the EditState method
            self._edit_state.insert_link(self._bookmark_source_id, link_text)

            # Update cache and rebuild layout (same as insert_text_at_cursor)
            rich_data = self._edit_state.rich_text.to_storage()
            self.cache.set_edit_rich_text(self._edit_state.entry_id, rich_data)
            self.invalidate_cache(self._edit_state.entry_id)
            self._invalidate_edit_row_cache()

            # Update virtual size and refresh
            new_height = self._index.content_height()
            self.SetVirtualSize((-1, new_height))
            self._refresh_edit_row()

            # Clear the bookmark source since we've used it
            self.clear_bookmark_source()

            self.SetStatusText(f"Inserted link: {link_text}")
            return True

        except Exception as e:
            self.SetStatusText(f"Failed to insert link: {e}")
            return False

    @check_read_only
    def cut(self):
        """Cut selected text or mark row for moving."""
        if self._edit_state.active:
            # In edit mode - cut selected text
            if not self._edit_state.has_selection():
                self.SetStatusText("No text selected to cut")
                return

            selected_text = self._edit_state.get_selected_text()
            if selected_text and Clipboard.copy_text(selected_text):
                self.delete_selected_text()
                self.SetStatusText(f"Cut {len(selected_text)} characters")
            else:
                self.SetStatusText("Failed to cut text")
        else:
            # In navigation mode - mark row for moving
            if 0 <= self._sel < len(self._rows):
                # Clear bookmark source state (mutual exclusion)
                if self._bookmark_source_id:
                    old_bookmark_id = self._bookmark_source_id
                    self._bookmark_source_id = None
                    self._refresh_changed_area(old_bookmark_id)

                self._cut_entry_id = self._rows[self._sel].entry_id
                self.SetStatusText("Row marked for moving (use Ctrl+V to move)")
                self.Refresh() # Repaint to show red outline
            else:
                self.SetStatusText("No row selected to cut")

    @check_read_only
    def _move_cut_row(self):
        """Move cut row using FlatTree."""
        if not self._cut_entry_id:
            return

        if not (0 <= self._sel < len(self._rows)):
            self.SetStatusText("Select a target location first")
            return

        target_entry_id = self._rows[self._sel].entry_id

        if self._cut_entry_id == target_entry_id:
            self.SetStatusText("Cannot move row after itself")
            return

        #Use FlatTree for move operation
        if self.flat_tree.move_entry_after(self._cut_entry_id, target_entry_id):
            moved_id = self._cut_entry_id
            self._cut_entry_id = None  # Clear cut state

            # Select the moved row
            for i, row in enumerate(self._rows):
                if row.entry_id == moved_id:
                    self._change_selection(i)
                    soft_ensure_visible(self, i)
                    break

            self.SetStatusText("Row moved")
        else:
            self.SetStatusText("Cannot move row to that location")

    @check_read_only
    def clear_bookmark_source(self):
        """Clear the bookmark source selection."""
        if self._bookmark_source_id:
            old_id = self._bookmark_source_id
            self._bookmark_source_id = None
            self._refresh_changed_area(old_id)


    # ------------ Image scale / pan (view only, not data) ------------

    def set_image_scale_pan(self, scale: float = None, pan_x: float = None, pan_y: float = None):
        change = False

        if scale is not None:
            scale = max(1.0, min(10.0, scale))
            self._img_scale = scale
            change = True

        if pan_x is not None:
            self._img_pan_x = pan_x
            change = True
        if pan_y is not None:
            self._img_pan_y = pan_y
            change = True

        if change:
            self.Refresh(False)

    # ------------ Image zoom operations ------------

    @check_read_only
    def zoom_image_in(self):
        """Zoom in the selected image thumbnail."""
        from ui.image_transform import get_current_thumbnail_max_size, calculate_zoom_in_size, can_zoom_in

        row_idx = self._get_selected_image_row_index()
        if row_idx is None:
            return

        # Get layout and extract current max size
        row = self._rows[row_idx]
        layout = self.cache.layout(row.entry_id) or {}
        current_max = get_current_thumbnail_max_size(layout)

        if current_max is None or not can_zoom_in(current_max):
            return

        new_max_size = calculate_zoom_in_size(current_max)
        self._regenerate_thumbnail(row_idx, new_max_size)

    @check_read_only
    def zoom_image_out(self):
        """Zoom out the selected image thumbnail."""
        from ui.image_transform import get_current_thumbnail_max_size, calculate_zoom_out_size, can_zoom_out

        row_idx = self._get_selected_image_row_index()
        if row_idx is None:
            return

        # Get layout and extract current max size
        row = self._rows[row_idx]
        layout = self.cache.layout(row.entry_id) or {}
        current_max = get_current_thumbnail_max_size(layout)

        if current_max is None or not can_zoom_out(current_max):
            return

        new_max_size = calculate_zoom_out_size(current_max)
        self._regenerate_thumbnail(row_idx, new_max_size)

    @check_read_only
    def zoom_image_reset(self):
        """Reset image thumbnail to natural size (original size or 256px, whichever is smaller)."""
        from ui.image_transform import calculate_reset_size
        from ui.row_utils import get_original_image_dimensions

        row_idx = self._get_selected_image_row_index()
        if row_idx is None:
            return

        # Get original image dimensions
        original_dims = get_original_image_dimensions(self, row_idx)
        if original_dims is None:
            return

        original_width, original_height = original_dims
        reset_size = calculate_reset_size(original_width, original_height)
        self._regenerate_thumbnail(row_idx, reset_size)

    # ------------ Image transform operations ------------

    @check_read_only
    def rotate_image_clockwise(self):
        """Rotate the selected image thumbnail 90 degrees clockwise."""
        from ui.image_transform import rotate_thumbnail_clockwise
        self._apply_thumbnail_transform(rotate_thumbnail_clockwise)

    @check_read_only
    def rotate_image_anticlockwise(self):
        """Rotate the selected image thumbnail 90 degrees anticlockwise."""
        from ui.image_transform import rotate_thumbnail_anticlockwise
        self._apply_thumbnail_transform(rotate_thumbnail_anticlockwise)

    @check_read_only
    def flip_image_vertical(self):
        """Flip the selected image thumbnail vertically."""
        from ui.image_transform import flip_thumbnail_vertical
        self._apply_thumbnail_transform(flip_thumbnail_vertical)

    @check_read_only
    def flip_image_horizontal(self):
        """Flip the selected image thumbnail horizontally."""
        from ui.image_transform import flip_thumbnail_horizontal
        self._apply_thumbnail_transform(flip_thumbnail_horizontal)

    @check_read_only
    def _apply_thumbnail_transform(self, transform_func):
        """Apply a transformation function to the selected image thumbnail."""
        from ui.row_utils import get_image_filename
        from ui.image_loader import clear_thumb_cache_for_entry
        from ui.image_utils import thumb_name_for
        from core.tree import entry_dir

        row_idx = self._get_selected_image_row_index()
        if row_idx is None:
            return

        row = self._rows[row_idx]
        entry_id = row.entry_id

        # Get image filename and thumbnail path
        image_filename = get_image_filename(self, row_idx)
        if not image_filename:
            return

        image_dir = entry_dir(self.notebook_dir, entry_id)
        thumbnail_path = str(image_dir / thumb_name_for(image_filename))

        # Apply transformation
        if transform_func(thumbnail_path):
            # Clear caches and refresh display
            clear_thumb_cache_for_entry(image_dir, image_filename)
            self.cache.invalidate_entry(entry_id)

            # Refresh display (preserves current zoom level)
            self._index.rebuild(self, self._rows)
            self.SetVirtualSize((-1, self._index.content_height()))
            self._refresh_changed_area(entry_id)

    def _get_selected_image_row_index(self) -> Optional[int]:
        """Get the currently selected row index if it's an image row."""
        if not (0 <= self._sel < len(self._rows)):
            return None

        if not is_image_row(self, self._sel):
            return None

        return self._sel

    @check_read_only
    def _regenerate_thumbnail(self, row_idx: int, new_max_size: int):
        """Regenerate thumbnail for image row with new size."""
        from ui.image_utils import make_thumbnail_file
        from ui.image_loader import clear_thumb_cache_for_entry
        from ui.row_utils import get_image_filename
        from core.tree import entry_dir

        row = self._rows[row_idx]
        entry_id = row.entry_id

        # Get image filename and paths
        image_filename = get_image_filename(self, row_idx)
        if not image_filename:
            return

        image_dir = entry_dir(self.notebook_dir, entry_id)

        # Regenerate thumbnail at new size
        make_thumbnail_file(image_dir, image_filename, max_px=new_max_size)

        # Clear caches to force reload
        clear_thumb_cache_for_entry(image_dir, image_filename)
        self.cache.invalidate_entry(entry_id)

        # Refresh display
        self._index.rebuild(self, self._rows)
        self.SetVirtualSize((-1, self._index.content_height()))
        self._refresh_changed_area(entry_id)

    # ------------ Context menu ------------

    @check_read_only
    def _on_context_menu(self, evt):
        """Show context menu with same actions as toolbar"""
        main_frame = wx.GetApp().GetTopWindow()
        if not main_frame:
            return
        # First perform the same action as a left click.
        handle_left_down(self, evt)

        menu = wx.Menu()

        # Define menu items matching toolbar actions (excluding color pickers)
        menu_items = [
            (wx.NewIdRef(), "Add Image(s)", "image_add", "on_action_add_images"),
            (wx.NewIdRef(), "Create Tab", "tab_add", "on_action_add_tab"),
            (wx.NewIdRef(), "Show All", "sitemap", "on_action_show_all"),
            (wx.NewIdRef(), "Lines to Bullets", "text_list_bullets", "on_action_lines_to_rows"),
            (wx.NewIdRef(), "Add Row", "add", "on_action_add_row"),
            (wx.NewIdRef(), "Delete", "delete", "on_action_delete"),
        ]

        # Build menu and collect IDs for context-sensitive enabling
        menu_id_map = {}  # method_name -> menu_id

        for item in menu_items:
            if item is None:
                menu.AppendSeparator()
            else:
                menu_id, label, icon_name, method_name = item

                # Create menu item with icon
                menu_item = wx.MenuItem(menu, menu_id, label)
                icon = wpIcons.Get(icon_name)
                if icon and icon.IsOk():
                    menu_item.SetBitmap(icon)

                menu.Append(menu_item)
                menu_id_map[method_name] = menu_id

                # Bind to MainFrame method
                handler = getattr(main_frame, method_name)
                self.Bind(wx.EVT_MENU, handler, id=menu_id)

        # Context-sensitive enabling/disabling
        self._update_context_menu_state(menu, menu_id_map)

        # Show menu at cursor position
        self.PopupMenu(menu)
        menu.Destroy()

    def _update_context_menu_state(self, menu, menu_id_map):
        """Enable/disable menu items based on current state"""
        # Disable specific actions based on state.
        #has_selection = 0 <= self._sel < len(self._rows)
        #is_image = has_selection and is_image_row(self, self._sel)
        #in_edit_mode = self._edit_state.active
        #has_cut_entry = self._cut_entry_id is not None
        #for action in actions_subset:
        #    if action in menu_id_map:
        #        menu.Enable(menu_id_map[action], False)
