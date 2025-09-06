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
from ui.cursor import pixel_pos_from_char, CursorRenderer
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
        entry = self.view._get(row.entry_id)
        self._draw_date_gutter(gc, rect, entry, selected)

        # caret glyph
        level = int(row.level)
        x0 = rect.x + self.m.DATE_COL_W + self.m.PADDING + level * self.m.INDENT_W
        y_text_top = rect.y + self.m.PADDING

        has_kids = any(it.get("type") == "child" for it in entry.get("items", []))
        collapsed = bool(entry.get("collapsed", False))
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
        """Draw rich text with proper selection highlighting."""
        lines = layout.get("rich_lines") or []
        if not lines:
            self._draw_plain_text_fallback(gc, row, x, y, selected)
            return

        # Get selection range for this row if editing
        selection_range = self._get_selection_range_for_row(row)

        # Get actual row rectangle for proper selection alignment
        row_idx = self._row_index(row)
        row_rect = None
        if row_idx >= 0:
            row_top = int(self.view._index.row_top(row_idx))
            row_height = int(self.view._index.row_height(row_idx))
            row_rect = wx.Rect(0, row_top, self.view.GetClientSize().width, row_height)
            # Convert to window coordinates
            scroll_x, scroll_y = self.view.GetViewStart()
            scroll_y_px = scroll_y * self.view.GetScrollPixelsPerUnit()[1]
            row_rect.y -= scroll_y_px

        # Draw each line with line-specific selection
        char_pos = 0
        cur_y = y
        total_lines = len(lines)

        for line_idx, line in enumerate(lines):
            is_first_line = (line_idx == 0)
            is_last_line = (line_idx == total_lines - 1)

            char_pos = self._draw_rich_text_line(
                gc, line, x, cur_y, char_pos, selection_range,
                row_rect, is_first_line, is_last_line
            )
            cur_y += line["height"]

    def _draw_plain_text_fallback(self, gc, row, x, y, selected):
        """Draw plain text when no rich text layout is available."""
        plain = rich_text_from_entry(self.view._get(row.entry_id)).to_plain_text()
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

    def _draw_link_icon(self, gc, x, y, seg):
        """Draw a small link icon before link text. Returns icon width."""
        try:
            # Load the link icon
            icon = wpIcons.Get("link")

            if not icon or not icon.IsOk():
                return 0  # No icon available, no extra width needed

            # Your icons are already 16x16, so use them as-is
            icon_size = 16

            # Position icon vertically centered with text
            font_size = self.view._font.GetPointSize()
            icon_y = y + (font_size - icon_size) // 2

            # Draw the icon
            gc.DrawBitmap(icon, x, icon_y, icon_size, icon_size)

            # Return icon width + small padding
            return icon_size + 3  # 16px icon + 3px padding

        except Exception:
            # Fallback if icon loading fails
            return 0


    def _draw_rich_text_line(self, gc, line, x, cur_y, start_char_pos, selection_range,
                             row_rect, is_first_line, is_last_line):
        """Draw a single line of rich text and return updated character position."""
        char_pos = start_char_pos
        cur_x = x

        # Collect selection bounds for this entire line
        line_selection_bounds = None
        if selection_range:
            line_selection_bounds = self._calculate_line_selection_bounds(
                line, char_pos, x, selection_range)

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
                # Create copy of base font and set underlined
                font = wx.Font(base_font)  # Copy constructor
                font.SetUnderlined(True)
            else:
                font = base_font

            color = self._get_segment_color(seg)
            gc.SetFont(font, color)
            gc.DrawText(txt, cur_x, cur_y)

            # Remove the manual underline drawing - font handles it now!

            cur_x += seg["width"]
            char_pos += len(txt)

        # Draw selection outline for this specific line (if any)
        if line_selection_bounds and row_rect:
            self._draw_line_selection_outline(
                gc, line_selection_bounds, cur_y, line["height"],
                row_rect, is_first_line, is_last_line)

        return char_pos

    def _calculate_line_selection_bounds(self, line, line_char_start, line_x_start, selection_range):
        """Calculate the pixel bounds of selection within this line."""
        sel_start, sel_end = selection_range

        char_pos = line_char_start
        cur_x = line_x_start
        selection_left = None
        selection_right = None

        for seg in line.get("segments", []):
            txt = seg.get("text", "")
            if not txt:
                continue

            text_len = len(txt)
            text_start = char_pos
            text_end = text_start + text_len

            # Check if this segment overlaps with selection
            if sel_start < text_end and sel_end > text_start:
                # This segment has selection
                highlight_start = max(0, sel_start - text_start)
                highlight_end = min(text_len, sel_end - text_start)

                if highlight_start < highlight_end:
                    # Measure text to get precise bounds
                    font = self.view._bold if seg.get("bold") else self.view._font
                    dc = wx.ClientDC(self.view)
                    dc.SetFont(font)

                    before_text = txt[:highlight_start] if highlight_start > 0 else ""
                    selected_text = txt[highlight_start:highlight_end]

                    before_width = dc.GetTextExtent(before_text)[0] if before_text else 0
                    selected_width = dc.GetTextExtent(selected_text)[0]

                    seg_selection_left = cur_x + before_width
                    seg_selection_right = seg_selection_left + selected_width

                    if selection_left is None:
                        selection_left = seg_selection_left
                    else:
                        selection_left = min(selection_left, seg_selection_left)

                    if selection_right is None:
                        selection_right = seg_selection_right
                    else:
                        selection_right = max(selection_right, seg_selection_right)

            cur_x += seg["width"]
            char_pos += text_len

        if selection_left is not None and selection_right is not None:
            return (selection_left, selection_right)
        return None

    def _draw_line_selection_outline(self, gc, selection_bounds, line_y, line_height,
                                    row_rect, is_first_line, is_last_line):
        """Draw selection outline for a specific line with proper vertical bounds."""
        selection_left, selection_right = selection_bounds
        selection_width = selection_right - selection_left

        if selection_width <= 0:
            return

        # Calculate selection rectangle Y position and height based on line position
        if is_first_line and is_last_line:
            # Single line - use full row bounds to align with blue outline
            selection_y = row_rect.y
            selection_height = row_rect.height
        elif is_first_line:
            # First line of multi-line - start from row top, end at line bottom
            selection_y = row_rect.y
            selection_height = (line_y - row_rect.y) + line_height
        elif is_last_line:
            # Last line of multi-line - start from line top, end at row bottom
            selection_y = line_y
            selection_height = (row_rect.y + row_rect.height) - line_y
        else:
            # Middle line - just cover this line
            selection_y = line_y
            selection_height = line_height

        # Draw black outline rectangle
        gc.SetPen(wx.Pen(wx.Colour(0, 0, 0), SELECTION_OUTLINE_WIDTH))
        gc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 0)))  # Transparent fill
        gc.DrawRectangle(selection_left, selection_y, selection_width, selection_height)

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
                self.view._get(target_id)
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

        avail_w = (
            self.view.GetClientSize().width
            - self.view.DATE_COL_W
            - self.view.PADDING
            - int(row.level) * self.view.INDENT_W
            - self.view.GUTTER_W
            - 4
        )
        line_h = int(layout.get("line_h") or self.view.ROW_H)

        dc = wx.ClientDC(self.view)
        cx, cy = pixel_pos_from_char(
            rich_text,
            st.cursor_pos,
            x_text,
            y_text,
            avail_w,
            dc,
            self.view._font,
            self.view._bold,
            line_h,
        )
        self.cursor_renderer.draw_cursor(gc, cx, cy, self.view.ROW_H, True)

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
