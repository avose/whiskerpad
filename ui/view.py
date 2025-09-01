# ui/view.py  – refactored for unified NotebookCache
from __future__ import annotations

import wx
from typing import Dict, Any, List, Optional

# -----------------------------------------------------------------------------
# project imports
# -----------------------------------------------------------------------------
from core.tree import (
    commit_entry_edit,
    cancel_entry_edit,
)
from core.tree_utils import (
    add_sibling_after,
    indent_under_prev_sibling,
    outdent_to_parent_sibling,
    toggle_collapsed,
)

from ui.cache import NotebookCache
from ui.constants import INDENT_W, GUTTER_W, PADDING, DATE_COL_W, DEFAULT_ROW_H
from ui.types import Row
from ui.model import flatten_tree, update_tree_incremental
from ui.layout import measure_row_height
from ui.row import RowPainter, RowMetrics, caret_hit, item_rect
from ui.select import select_entry_id
from ui.mouse import (
    handle_left_down,
    handle_left_up,
    handle_left_dclick,
    handle_motion,
    handle_mousewheel,
)
from ui.keys import handle_key_event
from ui.paint import paint_background, paint_rows
from ui.scroll import soft_ensure_visible, visible_range, clamp_scroll_y
from ui.index import LayoutIndex
from ui.drag_drop import ImageDropTarget
from ui.edit_state import EditState, RichText
from ui.notebook_text import rich_text_from_entry
from ui.cursor import CursorRenderer

# =============================================================================
class GCView(wx.ScrolledWindow):
    """
    GraphicsContext-based, variable-row-height view of the entry tree
    with inline rich-text editing.
    """

    # ------------------------------------------------------------------ #
    # construction
    # ------------------------------------------------------------------ #

    def __init__(self, parent: wx.Window, notebook_dir: str, root_id: str, on_image_drop=None):
        super().__init__(parent, style=wx.BORDER_SIMPLE | wx.WANTS_CHARS)

        self.notebook_dir = notebook_dir
        self.root_id = root_id

        # central cache
        self.cache = NotebookCache(notebook_dir)

        # flattened rows + selection
        self._rows: List[Row] = []
        self._sel: int = -1

        # layout index
        self._index: LayoutIndex = LayoutIndex()

        # rich-text editing state
        self._edit_state = EditState()
        self._cursor_renderer = CursorRenderer()
        self._cursor_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_cursor_blink)

        # Selection state.
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
        self.SetBackgroundColour(wx.Colour(246, 252, 246))
        self.SetScrollRate(0, 1)  # pixel vertical scrolling

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

        # event bindings
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEFT_DCLICK, self._on_left_dclick)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_mousewheel)

        # track last client width for cheap resize detection
        self._last_client_w = self.GetClientSize().width

        # Set up drag & drop for images
        if on_image_drop:
            drop_target = ImageDropTarget(self, on_image_drop)
            self.SetDropTarget(drop_target)

        # build model
        self.rebuild()

    # ------------------------------------------------------------------ #
    # thin helper: keep legacy _get(...) usage alive
    # ------------------------------------------------------------------ #

    def _get(self, eid: str) -> Dict[str, Any]:
        return self.cache.entry(eid)

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
        self._sel = new_idx
        self.Refresh(False)  # repaint to update highlight

    # ------------------------------------------------------------------ #
    # rebuilding / flattening
    # ------------------------------------------------------------------ #

    def rebuild(self) -> None:
        """Re-flatten tree, keep selection when possible, rebuild index."""
        prev_id = self.current_entry_id()

        self.cache.invalidate_all()
        self._rows = flatten_tree(self.notebook_dir, self.root_id)
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

    def enter_edit_mode(self, row_idx: int, cursor_pos: int = 0):
        self._save_current_edit()

        if not (0 <= row_idx < len(self._rows)):
            return
        row = self._rows[row_idx]
        entry = self._get(row.entry_id)
        rich_text = rich_text_from_entry(entry)

        self._edit_state.start_editing(row_idx, row.entry_id, rich_text, cursor_pos)
        #self._edit_state.update_format_from_cursor()
        self._cursor_timer.Start(500)
        self._sel = row_idx

        self.invalidate_cache(row.entry_id)
        self._refresh_edit_row()

    def exit_edit_mode(self, save: bool = True):
        if not self._edit_state.active:
            return
        entry_id = self._edit_state.entry_id
        final_rt = self._edit_state.stop_editing()
        self._cursor_timer.Stop()

        if save and final_rt and entry_id:
            commit_entry_edit(self.notebook_dir, entry_id, final_rt.to_storage())
        elif entry_id:
            cancel_entry_edit(self.notebook_dir, entry_id)

        if entry_id:
            self.invalidate_cache(entry_id)
        self.Refresh()

    def _save_current_edit(self):
        if self._edit_state.active and self._edit_state.entry_id and self._edit_state.rich_text:
            rich_data = self._edit_state.rich_text.to_storage()
            self.cache.set_edit_rich_text(self._edit_state.entry_id, rich_data)

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
            entry = self._get(root_id)
            for item in entry.get("items", []):
                if isinstance(item, dict) and item.get("type") == "child":
                    cid = item.get("id")
                    if isinstance(cid, str):
                        result.update(self._get_subtree_entry_ids(cid))
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------ #
    # incremental collapse / expand
    # ------------------------------------------------------------------ #

    def toggle_collapsed_fast(self, entry_id: str):
        toggle_collapsed(self.notebook_dir, entry_id)
        self.invalidate_subtree_cache(entry_id)

        self._rows = update_tree_incremental(self.notebook_dir, self._rows, entry_id)
        self._index.rebuild(self, self._rows)

        self.SetVirtualSize((-1, self._index.content_height()))
        self._refresh_changed_area(entry_id)

    # ------------------------------------------------------------------ #
    # incremental insert (unchanged except cache access)
    # ------------------------------------------------------------------ #

    def add_node_incremental(
        self, parent_entry_id: str, new_entry_id: str, insert_after_id: str | None = None
    ):
        insert_idx = -1
        if insert_after_id:
            for i, row in enumerate(self._rows):
                if row.entry_id == insert_after_id:
                    insert_idx = i + 1
                    break
        if insert_idx == -1:
            self.rebuild()
            return

        try:
            _ = self._get(new_entry_id)  # ensure cached
            level = self._rows[insert_idx - 1].level if insert_after_id else self._rows[
                insert_idx - 1
            ].level + 1
            new_row = Row(kind="node", entry_id=new_entry_id, level=level)

            self._rows.insert(insert_idx, new_row)
            self._index.insert_row(self, insert_idx, new_row)

            self.SetVirtualSize((-1, self._index.content_height()))
            self._refresh_from_row(insert_idx)
        except Exception:
            self.rebuild()

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

        # Update virtual size
        self.SetVirtualSize((-1, self._index.content_height()))

        # If inserting newlines, refresh from this row downward
        if '\n' in text:
            self._refresh_from_row_downward(self._edit_state.row_idx)
        else:
            self._refresh_edit_row()

    def delete_char_before_cursor(self):
        if not self._edit_state.active:
            return

        self._edit_state.delete_before_cursor()
        rich_data = self._edit_state.rich_text.to_storage()
        self.cache.set_edit_rich_text(self._edit_state.entry_id, rich_data)
        self.invalidate_cache(self._edit_state.entry_id)
        self._invalidate_edit_row_cache()
        self._refresh_edit_row()

    def delete_char_after_cursor(self):
        if not self._edit_state.active:
            return

        self._edit_state.delete_after_cursor()
        rich_data = self._edit_state.rich_text.to_storage()
        self.cache.set_edit_rich_text(self._edit_state.entry_id, rich_data)
        self.invalidate_cache(self._edit_state.entry_id)
        self._invalidate_edit_row_cache()
        self._refresh_edit_row()

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

    def move_cursor(self, delta: int):
        if self._edit_state.active:
            self._edit_state.move_cursor(delta)
            self._edit_state.update_format_from_cursor()
            self._refresh_edit_row()

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
            bg = self.GetBackgroundColour() or wx.Colour(246, 252, 246)
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
        return self._rows[self._sel].entry_id if 0 <= self._sel < len(self._rows) else None

    def select_entry(self, entry_id: str, ensure_visible: bool = True) -> bool:
        return select_entry_id(self, entry_id, ensure_visible)

    # dummy stubs for NotePanel
    def edit_entry(self, _eid: str) -> bool:
        return False

    def edit_block(self, _bid: str) -> bool:
        return False

    def SetStatusText(self, text: str):
        """Set status text in main frame."""
        # Get the main frame and set status text
        main_frame = wx.GetApp().GetTopWindow()
        if hasattr(main_frame, 'SetStatusText'):
            main_frame.SetStatusText(text)

    # ------------ Clipboard operations ------------

    def copy(self):
        """Copy selected text to clipboard with Mac compatibility improvements."""
        if not self._edit_state.active or not self._edit_state.has_selection():
            self.SetStatusText("No text selected to copy")
            return

        selected_text = self._edit_state.get_selected_text()

        if not selected_text:
            self.SetStatusText("No text selected to copy")
            return

        try:
            if not wx.TheClipboard.Open():
                self.SetStatusText("Could not open clipboard")
                return

            # Create text data object
            data = wx.TextDataObject(selected_text)

            # Try to set the data
            if not wx.TheClipboard.SetData(data):
                self.SetStatusText("Failed to set clipboard data")
            else:
                # Flush is critical for Mac to ensure data persists
                wx.TheClipboard.Flush()
                self.SetStatusText(f"Copied {len(selected_text)} characters")

        except Exception as e:
            self.SetStatusText(f"Copy failed: {e}")
        finally:
            try:
                wx.TheClipboard.Close()
            except:
                pass  # Ignore close errors

    def paste(self):
        """Paste clipboard text at cursor position."""
        if not self._edit_state.active:
            return

        try:
            if not wx.TheClipboard.Open():
                self.SetStatusText("Could not open clipboard")
                return

            if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_UNICODETEXT)):
                data = wx.TextDataObject()
                success = wx.TheClipboard.GetData(data)

                if success:
                    text_to_paste = data.GetText()
                    if text_to_paste:
                        # Replace selection or insert at cursor
                        if self._edit_state.has_selection():
                            self.delete_selected_text()
                        self.insert_text_at_cursor(text_to_paste)
                        self.SetStatusText(f"Pasted {len(text_to_paste)} characters")
                    else:
                        self.SetStatusText("Clipboard contains empty text")
                else:
                    self.SetStatusText("Failed to retrieve clipboard data")
            else:
                self.SetStatusText("No compatible text format on clipboard")

        except Exception as e:
            self.SetStatusText(f"Paste error: {e}")
        finally:
            try:
                wx.TheClipboard.Close()
            except:
                pass  # Ignore close errors

    def cut(self):
        """Cut selected text to clipboard."""
        if not self._edit_state.active or not self._edit_state.has_selection():
            return

        selected_text = self._edit_state.get_selected_text()
        if selected_text and wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(selected_text))
                self.delete_selected_text()
                self.SetStatusText(f"Cut {len(selected_text)} characters")
            except Exception:
                pass
            finally:
                wx.TheClipboard.Close()
