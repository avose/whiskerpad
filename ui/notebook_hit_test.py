from __future__ import annotations
import wx
from typing import Tuple, Optional

def item_rect(view: wx.VListBox, idx: int) -> wx.Rect:
    # Deterministic rectangle using our own row heights.
    count = int(view.GetItemCount())
    if idx < 0 or idx >= count:
        return wx.Rect()
    top = 0
    for i in range(idx):
        top += int(view.OnMeasureItem(i))
    h = int(view.OnMeasureItem(idx))
    return wx.Rect(0, top, view.GetClientSize().width, h)

def hit_test(view: wx.VListBox, pos: wx.Point) -> Tuple[int, Optional[wx.Rect]]:
    # Walk rows once; stop when pos.y falls within a row's band.
    count = int(view.GetItemCount())
    w = view.GetClientSize().width
    y = int(pos.y)
    top = 0
    for i in range(count):
        h = int(view.OnMeasureItem(i))
        if top <= y < top + h:
            return i, wx.Rect(0, top, w, h)
        top += h
    return -1, None

def caret_hit(view, row: dict, rect: wx.Rect, pos: wx.Point) -> bool:
    level = int(row.get("level", 0))
    x0 = rect.x + getattr(view, "DATE_COL_W", 0) + getattr(view, "PADDING", 4) + level * getattr(view, "INDENT_W", 16)
    caret_rect = wx.Rect(x0, rect.y, getattr(view, "GUTTER_W", 12), rect.height)
    return caret_rect.Contains(pos)
