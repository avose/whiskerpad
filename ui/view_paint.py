from __future__ import annotations
from typing import Any, Dict, List
import wx

from ui.notebook_text import text_from_entry, measure_wrapped, flatten_ops


def _client_text_width(view, level: int) -> int:
    w = view.GetClientSize().width
    left = view.DATE_COL_W + view.PADDING + level * view.INDENT_W + view.GUTTER_W + 4
    right_pad = view.PADDING + 4
    return max(10, w - left - right_pad)


def _ensure_wrap_cache(view, row: Dict[str, Any]):
    """Populate wrapping cache on the row if width or source changed."""
    level = int(row["level"])
    curw = _client_text_width(view, level)
    wkey = int(row.get("_wrap_w") or -1)

    if row["kind"] == "node":
        e = view._get(row["entry_id"])
        text = text_from_entry(e)
        src = row.get("_wrap_src")
        if wkey != curw or src != text or "_wrap_h" not in row:
            dc = wx.ClientDC(view)
            lines, lh, th = measure_wrapped(text, curw, dc, view._font, view.PADDING)
            row["_wrap_lines"] = lines
            row["_wrap_lh"] = lh
            row["_wrap_h"] = th
            row["_wrap_w"] = curw
            row["_wrap_src"] = text
    else:
        # Legacy rich block
        src_text = flatten_ops(row.get("ops", []))
        src = row.get("_wrap_src")
        if wkey != curw or src != src_text or "_wrap_h" not in row:
            dc = wx.ClientDC(view)
            lines, lh, th = measure_wrapped(src_text, curw, dc, view._font, view.PADDING)
            row["_wrap_lines"] = lines
            row["_wrap_lh"] = lh
            row["_wrap_h"] = th
            row["_wrap_w"] = curw
            row["_wrap_src"] = src_text


def measure_item(view, row: Dict[str, Any]) -> int:
    _ensure_wrap_cache(view, row)
    return max(view.ROW_H, int(row.get("_wrap_h") or view.ROW_H))


def draw_item(view, dc: wx.DC, rect: wx.Rect, row: Dict[str, Any], selected: bool):
    level = int(row["level"])

    # selection background
    if selected:
        bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        fg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT)
        dc.SetBrush(wx.Brush(bg))
        dc.SetPen(wx.Pen(bg))
        dc.DrawRectangle(rect)
        dc.SetTextForeground(fg)
    else:
        dc.SetTextForeground(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))

    x0 = rect.x + view.DATE_COL_W + view.PADDING + level * view.INDENT_W
    y = rect.y + view.PADDING

    if row["kind"] == "node":
        e = view._get(row["entry_id"])
        has_children = any(it.get("type") in ("child",) for it in e.get("items", []))
        collapsed = bool(e.get("collapsed", False))
        caret = "▶" if (has_children and collapsed) else ("▼" if has_children else "•")

        # date gutter (YYYY-MM-DD), aligned to top of row
        ts = e.get("last_edit_ts") or e.get("created_ts")
        if ts:
            import time as _t
            datestr = _t.strftime("%Y-%m-%d", _t.localtime(ts))
            tw, _th = dc.GetTextExtent(datestr)
            dx = rect.x + view.DATE_COL_W - 6 - tw
            dy = rect.y + view.PADDING
            old_fg = dc.GetTextForeground()
            dc.SetTextForeground(wx.Colour(120, 120, 120))
            dc.DrawText(datestr, dx, dy)
            dc.SetTextForeground(old_fg)

        dc.SetFont(view._bold if has_children else view._font)
        dc.DrawText(caret, x0, rect.y + view.PADDING)

        # wrapped node text
        x_text = x0 + view.GUTTER_W
        lines: List[str] = row.get("_wrap_lines") or []
        lh = row.get("_wrap_lh") or dc.GetTextExtent("Ag")[1]
        y_text = y
        dc.SetFont(view._font)
        for line in lines:
            dc.DrawText(line, x_text, y_text)
            y_text += lh
        return

    # Legacy rich block
    x_text = x0 + view.GUTTER_W
    dc.SetFont(view._font)
    lines: List[str] = row.get("_wrap_lines") or []
    lh = row.get("_wrap_lh") or dc.GetTextExtent("Ag")[1]
    y_text = y
    for line in lines:
        dc.DrawText(line, x_text, y_text)
        y_text += lh
