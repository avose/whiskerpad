from __future__ import annotations

import wx
import time
from dataclasses import dataclass
from typing import List

from ui.types import Row
from ui.image_loader import load_thumb_bitmap
from ui.notebook_text import rich_text_from_entry, measure_rich_text_wrapped
from ui.cursor import pixel_pos_from_char, CursorRenderer
from core.tree import entry_dir

__all__ = ["caret_hit", "item_rect", "RowPainter", "RowMetrics"]

def has_children(view, row: Row) -> bool:
    e = view._get(row.entry_id)
    items = e.get("items", [])
    return any(isinstance(it, dict) and it.get("type") == "child" for it in items)

def caret_hit(view, row: Row, rect: wx.Rect, pos: wx.Point) -> bool:
    """
    Return True if click is within the caret gutter horizontally.
    Y is intentionally ignored to avoid subtle mismatches with row geometry.
    """
    level = int(row.level)
    x0 = rect.x + view.DATE_COL_W + view.PADDING + level * view.INDENT_W
    return x0 <= pos.x < (x0 + view.GUTTER_W)

def item_rect(view, idx: int) -> wx.Rect:
    """
    Compute row rect in content coords using LayoutIndex.
    """
    if not (0 <= idx < len(view._rows)):
        return wx.Rect(0, 0, 0, 0)

    w = view.GetClientSize().width
    top = int(view._index.row_top(idx))
    h = int(view._index.row_height(idx))
    return wx.Rect(0, top, w, h)

# --------------------- RowPainter and RowMetrics ---------------------

@dataclass(frozen=True)
class RowMetrics:
    DATE_COL_W: int
    INDENT_W: int
    GUTTER_W: int
    PADDING: int

def _date_str(ts: int | None) -> str:
    if not ts:
        return ""
    return time.strftime("%Y-%m-%d", time.localtime(ts))

class RowPainter:
    """
    Draw a single row (date gutter + content) using wx.GraphicsContext.
    Now supports rich text rendering and cursor drawing.
    """

    def __init__(self, view: wx.Window, metrics: RowMetrics) -> None:
        self.view = view
        self.m = metrics # injected metrics (widths, padding)
        self.cursor_renderer = CursorRenderer()

    def draw(
        self,
        gc: wx.GraphicsContext,
        rect: wx.Rect,
        row: Row,
        entry: dict,
        *,
        selected: bool = False,
    ) -> None:
        # Clip to row rect so a partially visible row renders correctly.
        gc.PushState()
        gc.Clip(rect.x, rect.y, rect.width, rect.height)

        base_bg = self.view.GetBackgroundColour()
        if not base_bg.IsOk():
            base_bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)

        # Row background (clears any selection artifacts)
        gc.SetBrush(wx.Brush(base_bg))
        gc.SetPen(wx.Pen(base_bg))
        gc.DrawRectangle(rect.x, rect.y, rect.width, rect.height)

        level = int(row.level)

        # Selection overlay (content area only; gutter stays grey)
        if selected:
            sel_bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
            gc.SetBrush(wx.Brush(sel_bg))
            gc.SetPen(wx.Pen(sel_bg))
            gc.DrawRectangle(
                rect.x + self.m.DATE_COL_W,
                rect.y,
                max(0, rect.width - self.m.DATE_COL_W),
                rect.height,
            )

        # Date gutter (bg + date text + selection-outline)
        self.draw_date_gutter(gc, rect, entry, selected)

        # Caret glyph
        x0 = rect.x + self.m.DATE_COL_W + self.m.PADDING + level * self.m.INDENT_W
        y = rect.y + self.m.PADDING

        has_kids = any(it.get("type") == "child" for it in entry.get("items", []))
        collapsed = bool(entry.get("collapsed", False))
        caret = "▶" if (has_kids and collapsed) else ("▼" if has_kids else "•")

        gc.SetFont(self.view._bold if has_kids else self.view._font,
                   wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
        gc.DrawText(caret, x0, y)

        # Content: rich text or image token
        x_text = x0 + self.m.GUTTER_W
        
        # Check if this is an image token row
        if row.cache.get("_is_img"):
            self._draw_image_token(gc, rect, row, entry, x_text, y)
        else:
            self._draw_rich_text(gc, rect, row, entry, x_text, y, selected)

        # Draw cursor if this row is being edited
        if (hasattr(self.view, '_edit_state') and 
            self.view._edit_state.active and 
            self.view._edit_state.row_idx == self._get_row_index(row) and
            self.view._edit_state.cursor_visible):
            self._draw_cursor(gc, rect, row, entry, x_text, y)

        gc.PopState()

    def _get_row_index(self, row: Row) -> int:
        """Find the index of this row in the view's row list."""
        for i, r in enumerate(self.view._rows):
            if r.entry_id == row.entry_id:
                return i
        return -1

    def _draw_image_token(self, gc: wx.GraphicsContext, rect: wx.Rect, row: Row, entry: dict, x_text: int, y: int):
        """Draw an image token row."""
        fname = row.cache.get("_img_file")
        sw = int(row.cache.get("_img_sw") or 0)
        sh = int(row.cache.get("_img_sh") or 0)

        if fname and sw > 0 and sh > 0:
            try:
                ed = entry_dir(self.view.nb_dir, row.entry_id)
                bmp, _w, _h = load_thumb_bitmap(ed, fname)
                gc.DrawBitmap(bmp, x_text, y, sw, sh)
            except Exception:
                # Fallback to text display
                gc.SetFont(self.view._font, wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
                gc.DrawText(f'{{{{img "{fname or "MISSING"}"}}}}', x_text, y)
        else:
            gc.SetFont(self.view._font, wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
            gc.DrawText(f'{{{{img "{fname or "MISSING"}"}}}}', x_text, y)

    def _draw_rich_text(self, gc: wx.GraphicsContext, rect: wx.Rect, row: Row, entry: dict, x_text: int, y: int, selected: bool):
        """Draw rich text with formatting."""
        # Get cached rich text layout or compute it
        line_segments = row.cache.get("_rich_lines")
        if not line_segments:
            # Should have been computed in layout phase, fallback to simple text
            rich_text = rich_text_from_entry(entry)
            plain_text = rich_text.to_plain_text()
            
            # If completely empty, don't draw anything (not even a placeholder)
            if not plain_text.strip():
                return
            
            gc.SetFont(self.view._font,
                       wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT) if selected
                       else wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))
            gc.DrawText(plain_text, x_text, y)
            return

        # Draw each line with its segments
        current_y = y
        for line_info in line_segments:
            current_x = x_text
            
            # Skip completely empty lines
            segments = line_info.get('segments', [])
            if not segments:
                current_y += line_info.get('height', self.view.ROW_H)
                continue
            
            for segment in segments:
                text = segment.get('text', '')
                if not text:
                    continue

                # Set font based on formatting
                font = self.view._bold if segment.get('bold', False) else self.view._font
                
                # Set text color
                if selected:
                    color = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT)
                elif segment.get('color'):
                    try:
                        color = wx.Colour(segment['color'])
                    except:
                        color = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
                else:
                    color = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)

                gc.SetFont(font, color)

                # Draw background color if specified
                bg_color = segment.get('bg')
                if bg_color and not selected:
                    try:
                        bg_wx_color = wx.Colour(bg_color)
                        # Measure text to get background rect
                        text_w = segment.get('width', gc.GetTextExtent(text)[0])
                        text_h = line_info.get('height', self.view.ROW_H)
                        
                        gc.SetBrush(wx.Brush(bg_wx_color))
                        gc.SetPen(wx.Pen(bg_wx_color))
                        gc.DrawRectangle(current_x, current_y, text_w, text_h)
                    except:
                        pass  # Invalid color, skip background

                # Draw the text
                gc.DrawText(text, current_x, current_y)
                
                # Advance x position
                current_x += segment.get('width', gc.GetTextExtent(text)[0])

            # Advance to next line
            current_y += line_info.get('height', self.view.ROW_H)

    def _draw_cursor(self, gc: wx.GraphicsContext, rect: wx.Rect, row: Row, entry: dict, x_text: int, y: int):
        """Draw the text cursor at the current position."""
        if not hasattr(self.view, '_edit_state') or not self.view._edit_state.active:
            return

        rich_text = self.view._edit_state.rich_text
        if not rich_text:
            return

        cursor_pos = self.view._edit_state.cursor_pos
        
        # Calculate available width for text
        level = int(row.level)
        available_width = (self.view.GetClientSize().width - 
                          self.view.DATE_COL_W - self.view.PADDING - 
                          level * self.view.INDENT_W - self.view.GUTTER_W - 4)

        # Get cursor pixel position
        dc = wx.ClientDC(self.view)
        cursor_x, cursor_y = pixel_pos_from_char(
            rich_text,
            cursor_pos,
            x_text,
            y,
            available_width,
            dc,
            self.view._font,
            self.view._bold,
            self.view.ROW_H
        )

        # Draw cursor
        self.cursor_renderer.draw_cursor(
            gc, cursor_x, cursor_y, self.view.ROW_H, visible=True
        )

    def draw_date_gutter(self, gc: wx.GraphicsContext, rect: wx.Rect, entry: dict, selected: bool) -> None:
        """Draw the gutter background, date text (right-aligned), and selection outline in the gutter."""
        # Gutter background
        gutter_bg = wx.Colour(240, 240, 240)
        gc.SetBrush(wx.Brush(gutter_bg))
        gc.SetPen(wx.Pen(gutter_bg))
        gc.DrawRectangle(rect.x, rect.y, self.m.DATE_COL_W, rect.height)

        # Date text
        ts = entry.get("last_edit_ts") or entry.get("created_ts")
        ds = _date_str(ts)
        if ds:
            gc.SetFont(self.view._font, wx.Colour(120, 120, 120))
            tw, th = gc.GetTextExtent(ds)
            dx = rect.x + self.m.DATE_COL_W - 6 - tw
            dy = rect.y + self.m.PADDING
            gc.DrawText(ds, dx, dy)

        # Selection outline (hollow rectangle) spanning the gutter height
        if selected:
            sel_col = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
            gc.SetPen(wx.Pen(sel_col, 1))
            path = gc.CreatePath()
            rx = rect.x
            ry = rect.y
            rw = max(0, self.m.DATE_COL_W)
            rh = rect.height - 1
            path.AddRectangle(rx, ry, rw, rh)
            gc.StrokePath(path)
