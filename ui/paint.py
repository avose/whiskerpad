'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''
from __future__ import annotations

import wx

from ui.layout import ensure_wrap_cache, measure_row_height
from ui.constants import DEFAULT_BG_COLOR

def paint_background(view, gc: wx.GraphicsContext, client_h: int) -> None:
    """Fill full client area and the date gutter with background colors."""
    w = view.GetClientSize().width

    # Main background
    bg = view.GetBackgroundColour()
    if not bg.IsOk():
        bg = DEFAULT_BG_COLOR

    gc.SetBrush(wx.Brush(bg))
    gc.SetPen(wx.Pen(bg))
    gc.DrawRectangle(0, 0, w, client_h)

    # Date gutter background
    gutter_bg = wx.Colour(240, 240, 240)
    gc.SetBrush(wx.Brush(gutter_bg))
    gc.SetPen(wx.Pen(gutter_bg))
    gc.DrawRectangle(0, 0, view.DATE_COL_W, client_h)

def paint_rows(view, gc: wx.GraphicsContext, first_idx: int, y0: int, max_h: int) -> int:
    """
    Draw rows starting at first_idx, placing that row's top at window Y y0,
    and continue until we reach max_h. Returns the Y coordinate just past
    the last painted row.
    """
    if first_idx < 0 or first_idx >= len(view._rows):
        return max(0, y0)

    w = view.GetClientSize().width
    y = y0
    i = first_idx

    while i < len(view._rows) and y < max_h:
        r = view._rows[i]
        h = measure_row_height(view, r)
        rect = wx.Rect(0, y, w, h)
        ensure_wrap_cache(view, r)
        e = view.cache.entry(r.entry_id)
        
        # Always pass selection state - the row painter will handle cut vs selection priority
        is_selected = (i == view._sel)
        
        view._row_painter.draw(gc, rect, r, e, selected=is_selected)
        
        y += h
        i += 1

    return y
