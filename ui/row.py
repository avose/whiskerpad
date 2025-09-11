# ui/row.py – cache-free Row implementation

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List
import wx

from core.tree import entry_dir
from ui.types import Row
from ui.image_loader import load_thumb_bitmap
from ui.notebook_text import rich_text_from_entry
from ui.cursor import CursorRenderer
from ui.icons import wpIcons

# Import functions that were moved to row_utils
from ui.row_utils import has_children, caret_hit, item_rect

# Drawing constants
SELECTION_PEN_WIDTH = 2
SELECTION_OUTLINE_WIDTH = 1
DATE_GUTTER_PADDING = 6

__all__ = ["RowPainter", "RowMetrics"]

@dataclass(frozen=True)
class RowMetrics:
    DATE_COL_W: int
    INDENT_W: int
    GUTTER_W: int
    PADDING: int

def _date_str(ts: int | None) -> str:
    if not ts:
        return ""
    return time.strftime("%Y-%m-%d", time.localtime(int(ts)))

class RowPainter:
    """
    Draw a single row (date gutter + content) using wx.GraphicsContext.

    All layout / wrap information is retrieved from
    ``view.cache.layout(row.entry_id)`` – no per-row cache dict.
    """

    def __init__(self, view: wx.Window, metrics: RowMetrics) -> None:
        self.view = view
        self.m = metrics
        self.cursor_renderer = CursorRenderer()

    def _get_collapsed_state(self, entry_id: str) -> bool:
        """Get collapse state, respecting read-only transient state"""
        # Check transient state in read-only mode
        if self.view.is_read_only():
            return self.view.flat_tree._transient_collapsed.get(entry_id, False)

        # Normal persistent state
        try:
            entry = self.view.cache.entry(entry_id)
            return entry.get("collapsed", False)
        except:
            return False

    # ------------------------------------------------------------------ #

    def draw(
            self,
            gc: wx.GraphicsContext,
            rect: wx.Rect,
            row: Row,
            entry: dict,
            *,
            selected: bool = False,
    ) -> None:
        """
        Paint a row.  `rect` is in window coordinates.
        """
        if rect.width <= 0 or rect.height <= 0:
            return

        gc.PushState()
        gc.Clip(rect.x, rect.y, rect.width, rect.height)

        base_bg = self.view.GetBackgroundColour() or wx.SystemSettings.GetColour(
            wx.SYS_COLOUR_WINDOW
        )
        gc.SetBrush(wx.Brush(base_bg))
        gc.SetPen(wx.Pen(base_bg))
        gc.DrawRectangle(rect.x, rect.y, rect.width, rect.height)

        # Check if this row is cut (should always show red outline)
        is_cut_row = (hasattr(self.view, '_cut_entry_id') and 
                      self.view._cut_entry_id == row.entry_id)

        # Draw cut outline (red) if row is cut, regardless of selection
        if is_cut_row:
            cut_color = wx.Colour(220, 20, 20)  # Red color
            gc.SetPen(wx.Pen(cut_color, SELECTION_PEN_WIDTH))
            gc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 0)))  # Transparent brush

            # Draw red outline rectangle
            outline_x = rect.x + self.m.DATE_COL_W
            outline_y = rect.y
            outline_w = max(0, rect.width - self.m.DATE_COL_W)
            outline_h = rect.height
            gc.DrawRectangle(outline_x, outline_y, outline_w, outline_h)

        # Check if this row is marked as bookmark source
        elif self.view._bookmark_source_id and self.view._bookmark_source_id == row.entry_id:
            bookmark_color = wx.Colour(20, 220, 20)  # Green color
            gc.SetPen(wx.Pen(bookmark_color, SELECTION_PEN_WIDTH))
            gc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 0)))  # Transparent brush
            # Draw green outline rectangle
            outline_x = rect.x + self.m.DATE_COL_W
            outline_y = rect.y
            outline_w = max(0, rect.width - self.m.DATE_COL_W)
            outline_h = rect.height
            gc.DrawRectangle(outline_x, outline_y, outline_w, outline_h)

        # Draw selection outline (blue) if row is selected AND not cut
        elif selected:
            sel_color = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
            gc.SetPen(wx.Pen(sel_color, SELECTION_PEN_WIDTH))
            gc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 0)))  # Transparent brush

            # Draw blue outline rectangle
            outline_x = rect.x + self.m.DATE_COL_W
            outline_y = rect.y
            outline_w = max(0, rect.width - self.m.DATE_COL_W)
            outline_h = rect.height
            gc.DrawRectangle(outline_x, outline_y, outline_w, outline_h)

        # date gutter (bg + YY-MM-DD + outline)
        entry = self.view.cache.entry(row.entry_id)
        self._draw_date_gutter(gc, rect, entry, selected)

        # caret glyph
        level = int(row.level)
        x0 = rect.x + self.m.DATE_COL_W + self.m.PADDING + level * self.m.INDENT_W
        y_text_top = rect.y + self.m.PADDING

        has_kids = any(it.get("type") == "child" for it in entry.get("items", []))
        collapsed = self._get_collapsed_state(row.entry_id)
        caret_glyph = "▶" if (has_kids and collapsed) else ("▼" if has_kids else "•")

        gc.SetFont(self.view._bold if has_kids else self.view._font,
                   wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
        gc.DrawText(caret_glyph, x0, y_text_top)

        # ------------------------------------------------------------------
        # content (image or rich text)
        # ------------------------------------------------------------------
        layout = self.view.cache.layout(row.entry_id) or {}
        content_x = x0 + self.m.GUTTER_W

        if layout.get("is_img"):
            self._draw_image_token(gc, row, layout, content_x, y_text_top)
        else:
            self._draw_rich_text(gc, row, layout, content_x, y_text_top, selected)

        # cursor (if editing this row)
        edit_state = self.view._edit_state
        if (edit_state.active and
            edit_state.row_idx == self._row_index(row) and
            edit_state.cursor_visible
        ):
            self._draw_cursor(gc, row, layout, content_x, y_text_top)

        gc.PopState()

    # ------------------------------------------------------------------ #
    # image rows
    # ------------------------------------------------------------------ #

    def _draw_image_token(
        self,
        gc: wx.GraphicsContext,
        row: Row,
        layout: dict,
        x: int,
        y: int,
    ):
        fname = layout.get("img_file")
        sw = int(layout.get("img_sw") or 0)
        sh = int(layout.get("img_sh") or 0)
        if fname and sw > 0 and sh > 0:
            try:
                bmp_dir = entry_dir(self.view.notebook_dir, row.entry_id)
                bmp, _, _ = load_thumb_bitmap(bmp_dir, fname)
                gc.DrawBitmap(bmp, x, y, sw, sh)
                return
            except Exception:
                pass  # fall through to token text

        gc.SetFont(self.view._font, wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
        gc.DrawText(f'{{{{img "{fname or "MISSING"}"}}}}', x, y)

    # ------------------------------------------------------------------ #
    # rich-text rows
    # ------------------------------------------------------------------ #

    def _draw_rich_text(self, gc, row, layout, x, y, selected):
        """Draw rich text with simple selection highlighting."""
        lines = layout.get("rich_lines") or []
        if not lines:
            self._draw_plain_text_fallback(gc, row, x, y, selected)
            return

        # Draw text normally (no complex per-line selection logic needed)
        cur_y = y
        for line_idx, line in enumerate(lines):
            self._draw_rich_text_line(gc, line, x, cur_y)
            cur_y += line["height"]

        # Draw selection highlight after drawing text
        selection_range = self._get_selection_range_for_row(row)
        if selection_range:
            start_pos, end_pos = selection_range
            self._draw_selection_highlight(gc, row, start_pos, end_pos, x, y)

    def _draw_plain_text_fallback(self, gc, row, x, y, selected):
        """Draw plain text when no rich text layout is available."""
        plain = rich_text_from_entry(self.view.cache.entry(row.entry_id)).to_plain_text()
        if plain.strip():
            color_key = wx.SYS_COLOUR_HIGHLIGHTTEXT if selected else wx.SYS_COLOUR_WINDOWTEXT
            gc.SetFont(self.view._font, wx.SystemSettings.GetColour(color_key))
            gc.DrawText(plain, x, y)

    def _get_selection_range_for_row(self, row):
        """Get selection range if this row is being edited, None otherwise."""
        edit_state = self.view._edit_state
        if (edit_state.active and
            edit_state.row_idx == self._row_index(row) and
            edit_state.has_selection()):
            return edit_state.get_selection_range()
        return None

    def _draw_rich_text_line(self, gc, line, x, cur_y):
        """Draw a single line of rich text without selection complexity."""
        cur_x = x

        # Draw all segments
        for seg in line.get("segments", []):
            txt = seg.get("text", "")
            if not txt:
                continue

            # Draw segment background
            self._draw_segment_background(gc, seg, cur_x, cur_y, line["height"])

            # Create appropriate font (with underlining for links)
            base_font = self.view._bold if seg.get("bold") else self.view._font
            if seg.get("link_target"):
                font = wx.Font(base_font)
                font.SetUnderlined(True)
            else:
                font = base_font

            color = self._get_segment_color(seg)
            gc.SetFont(font, color)
            gc.DrawText(txt, cur_x, cur_y)

            cur_x += seg["width"]

    def _draw_segment_background(self, gc, seg, x, y, height):
        """Draw background color for a text segment if specified."""
        bg = seg.get("bg")
        if bg and self._is_valid_color(bg):
            bgc = wx.Colour(bg)
            width = seg["width"]
            gc.SetBrush(wx.Brush(bgc))
            gc.SetPen(wx.Pen(bgc))
            gc.DrawRectangle(x, y, width, height)

    def _get_segment_color(self, seg):
        """Get the color for a text segment, handling links with validation."""
        # Check if this is a link
        if seg.get("link_target"):
            target_id = seg.get("link_target")

            # Check if the target still exists
            try:
                self.view.cache.entry(target_id)
                # Target exists - use blue for working links
                return wx.Colour("#0000ff")
            except Exception:
                # Target doesn't exist - use red for broken links
                return wx.Colour("#ff0000")

        # Regular color handling for non-links
        color_str = seg.get("color")
        if color_str and self._is_valid_color(color_str):
            return wx.Colour(color_str)

        return wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)

    def _draw_selection_highlight(self, gc, row, selection_start, selection_end, x_text, y_text):
        """Draw selection highlight as black outline only (no fill)."""
        if selection_start == selection_end:
            return

        # Normalize selection range
        start_pos = min(selection_start, selection_end)
        end_pos = max(selection_start, selection_end)

        # Get layout and use actual line height (not ROW_H which includes padding)
        layout = self.view.cache.layout(row.entry_id) or {}
        line_height = layout.get('line_h', self.view.ROW_H)

        # Get pixel positions
        start_x, start_y = self.view.cache.char_to_pixel(row, start_pos, x_text, y_text)
        end_x, end_y = self.view.cache.char_to_pixel(row, end_pos, x_text, y_text)

        # Set black outline, no fill
        gc.SetPen(wx.Pen(wx.Colour(0, 0, 0), 1))
        gc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 0)))

        if start_y == end_y:
            # Single line selection - use line_height, not ROW_H
            width = end_x - start_x
            gc.DrawRectangle(start_x, start_y, width, line_height)
        else:
            # Multi-line selection
            rich_lines = layout.get('rich_lines', [])

            for line_idx, line in enumerate(rich_lines):
                line_start_char = line['start_char']
                line_end_char = line['end_char']

                # Skip lines outside selection
                if end_pos <= line_start_char or start_pos >= line_end_char:
                    continue

                # Calculate this line's portion of the selection
                line_sel_start = max(start_pos, line_start_char)
                line_sel_end = min(end_pos, line_end_char)

                # Convert to pixels
                line_start_x, _ = self.view.cache.char_to_pixel(row, line_sel_start, x_text, y_text)
                line_end_x, _ = self.view.cache.char_to_pixel(row, line_sel_end, x_text, y_text)

                line_y = y_text + line_idx * line_height

                # Draw rectangle outline using line_height
                gc.DrawRectangle(line_start_x, line_y, line_end_x - line_start_x, line_height)

    def _is_valid_color(self, color_str):
        """Check if color string is valid for wx.Colour."""
        if not color_str or not isinstance(color_str, str):
            return False
        # Basic validation - should start with # and be hex
        return color_str.startswith('#') and len(color_str) == 7

    # ------------------------------------------------------------------ #
    # cursor
    # ------------------------------------------------------------------ #

    def _draw_cursor(
        self,
        gc: wx.GraphicsContext,
        row: Row,
        layout: dict,
        x_text: int,
        y_text: int,
    ):
        st = self.view._edit_state
        rich_text = st.rich_text

        if not rich_text:
            return

        # Use cache for cursor positioning
        cx, cy = self.view.cache.char_to_pixel(row, st.cursor_pos, x_text, y_text)

        # Use actual line height, not ROW_H which includes padding
        line_height = layout.get('line_h', self.view.ROW_H)

        self.cursor_renderer.draw_cursor(gc, cx, cy, line_height, True)

    # ------------------------------------------------------------------ #
    # date gutter
    # ------------------------------------------------------------------ #

    def _draw_date_gutter(
        self, gc: wx.GraphicsContext, rect: wx.Rect, entry: dict, selected: bool
    ):
        gutter_bg = wx.Colour(240, 240, 240)
        gc.SetBrush(wx.Brush(gutter_bg))
        gc.SetPen(wx.Pen(gutter_bg))
        gc.DrawRectangle(rect.x, rect.y, self.m.DATE_COL_W, rect.height)

        ts = entry.get("last_edit_ts") or entry.get("created_ts")
        ds = _date_str(ts)
        if ds:
            gc.SetFont(self.view._font, wx.Colour(120, 120, 120))
            tw, _ = gc.GetTextExtent(ds)
            dx = rect.x + self.m.DATE_COL_W - DATE_GUTTER_PADDING - tw
            dy = rect.y + self.m.PADDING
            gc.DrawText(ds, dx, dy)

        # Check if this row is cut (always show red gutter if cut)
        is_cut_row = (hasattr(self.view, '_cut_entry_id') and 
                      self.view._cut_entry_id == entry.get("id"))

        # Check if this row is bookmark source
        is_bookmark_source = (self.view._bookmark_source_id and
                              self.view._bookmark_source_id == entry.get("id"))

        # Draw gutter outline for cut rows (red) or selected rows (blue)
        if is_cut_row:
            # Red outline for cut rows (regardless of selection)
            sel = wx.Colour(220, 20, 20)
            gc.SetPen(wx.Pen(sel, 1))
            gc.StrokeLine(rect.x, rect.y, rect.x, rect.y + rect.height - 1)
            gc.StrokeLine(rect.x, rect.y, rect.x + self.m.DATE_COL_W, rect.y)
            gc.StrokeLine(
                rect.x,
                rect.y + rect.height - 1,
                rect.x + self.m.DATE_COL_W,
                rect.y + rect.height - 1,
            )
        elif is_bookmark_source:
            # Green outline for bookmark source rows
            sel = wx.Colour(20, 220, 20)
            gc.SetPen(wx.Pen(sel, 1))
            gc.StrokeLine(rect.x, rect.y, rect.x, rect.y + rect.height - 1)
            gc.StrokeLine(rect.x, rect.y, rect.x + self.m.DATE_COL_W, rect.y)
            gc.StrokeLine(
                rect.x,
                rect.y + rect.height - 1,
                rect.x + self.m.DATE_COL_W,
                rect.y + rect.height - 1,
            )
        elif selected:
            # Blue outline for selected (non-cut) rows
            sel = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
            gc.SetPen(wx.Pen(sel, 1))
            gc.StrokeLine(rect.x, rect.y, rect.x, rect.y + rect.height - 1)
            gc.StrokeLine(rect.x, rect.y, rect.x + self.m.DATE_COL_W, rect.y)
            gc.StrokeLine(
                rect.x,
                rect.y + rect.height - 1,
                rect.x + self.m.DATE_COL_W,
                rect.y + rect.height - 1,
            )

    # ------------------------------------------------------------------ #
    # helper
    # ------------------------------------------------------------------ #

    def _row_index(self, row: Row) -> int:
        for i, r in enumerate(self.view._rows):
            if r.entry_id == row.entry_id:
                return i
        return -1
