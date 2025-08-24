# ui/row.py  – cache-free Row implementation
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List

import wx

from ui.types import Row
from ui.image_loader import load_thumb_bitmap
from ui.notebook_text import rich_text_from_entry
from ui.cursor import pixel_pos_from_char, CursorRenderer
from core.tree import entry_dir

__all__ = ["caret_hit", "item_rect", "RowPainter", "RowMetrics"]


# ---------------------------------------------------------------------------
# misc helpers
# ---------------------------------------------------------------------------


def has_children(view, row: Row) -> bool:
    entry = view._get(row.entry_id)  # thin wrapper -> cache.entry()
    return any(
        isinstance(it, dict) and it.get("type") == "child"
        for it in entry.get("items", [])
    )


def caret_hit(view, row: Row, rect: wx.Rect, pos: wx.Point) -> bool:
    """
    Return True if click lands in the caret gutter horizontally.
    Y is ignored to avoid subtle geometry mismatches.
    """
    level = int(row.level)
    x0 = rect.x + view.DATE_COL_W + view.PADDING + level * view.INDENT_W
    return x0 <= pos.x < (x0 + view.GUTTER_W)


def item_rect(view, idx: int) -> wx.Rect:
    """
    Rectangle of row *idx* in **content** coordinates (not window).
    """
    if not (0 <= idx < len(view._rows)):
        return wx.Rect(0, 0, 0, 0)
    w = view.GetClientSize().width
    top = int(view._index.row_top(idx))
    h = int(view._index.row_height(idx))
    return wx.Rect(0, top, w, h)


# ---------------------------------------------------------------------------
# row metrics & painter
# ---------------------------------------------------------------------------

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

        # selection overlay (skip gutter)
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
        if (
            hasattr(self.view, "_edit_state")
            and self.view._edit_state.active
            and self.view._edit_state.row_idx == self._row_index(row)
            and self.view._edit_state.cursor_visible
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
                bmp_dir = entry_dir(self.view.nb_dir, row.entry_id)
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

    def _draw_rich_text(
        self,
        gc: wx.GraphicsContext,
        row: Row,
        layout: dict,
        x: int,
        y: int,
        selected: bool,
    ):
        lines: List[dict] = layout.get("rich_lines") or []

        if not lines:
            # fallback – plain text
            plain = rich_text_from_entry(self.view._get(row.entry_id)).to_plain_text()
            if plain.strip():
                gc.SetFont(
                    self.view._font,
                    wx.SystemSettings.GetColour(
                        wx.SYS_COLOUR_HIGHLIGHTTEXT if selected else wx.SYS_COLOUR_WINDOWTEXT
                    ),
                )
                gc.DrawText(plain, x, y)
            return

        cur_y = y
        for line in lines:
            cur_x = x
            for seg in line.get("segments", []):
                txt = seg.get("text", "")
                if not txt:
                    continue

                font = self.view._bold if seg.get("bold") else self.view._font
                if selected:
                    color = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT)
                elif seg.get("color"):
                    try:
                        color = wx.Colour(seg["color"])
                    except Exception:
                        color = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
                else:
                    color = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)

                gc.SetFont(font, color)

                # background highlight
                bg = seg.get("bg")
                if bg and not selected:
                    try:
                        bgc = wx.Colour(bg)
                        w = seg["width"]
                        h = line["height"]
                        gc.SetBrush(wx.Brush(bgc))
                        gc.SetPen(wx.Pen(bgc))
                        gc.DrawRectangle(cur_x, cur_y, w, h)
                    except Exception:
                        pass

                gc.DrawText(txt, cur_x, cur_y)
                cur_x += seg["width"]

            cur_y += line["height"]

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
            dx = rect.x + self.m.DATE_COL_W - 6 - tw
            dy = rect.y + self.m.PADDING
            gc.DrawText(ds, dx, dy)

        if selected:
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
