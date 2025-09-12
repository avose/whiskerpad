'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
import wx

from core.tree import entry_dir
from ui.types import Row
from ui.image_transform import get_current_thumbnail_max_size


__all__ = [
    "has_children",
    "date_gutter_hit",
    "caret_hit", 
    "item_rect",
    "is_image_row",
    "get_image_file_path",
    "get_image_filename",
]

def has_children(view, row: Row) -> bool:
    """Check if a row has child entries."""
    entry = view.cache.entry(row.entry_id)
    return any(
        item.get("type") == "child"
        for item in entry.get("items", [])
    )

def date_gutter_hit(view, row: Row, rect: wx.Rect, pos: wx.Point) -> bool:
    """
    Return True if click lands in the date gutter area.
    This should just select the row, not start editing.
    """
    # Date gutter spans from left edge to DATE_COL_W
    return rect.x <= pos.x < (rect.x + view.DATE_COL_W)

def caret_hit(view, row: Row, rect: wx.Rect, pos: wx.Point) -> bool:
    """
    Return True if click lands in the entire left margin area (including caret).
    This includes all space from the date column to the start of text content.
    Y is ignored to avoid subtle geometry mismatches.
    """
    level = int(row.level)
    
    # Start of clickable area: right after date column
    left_edge = rect.x + view.DATE_COL_W
    
    # End of clickable area: where text content starts
    text_start = left_edge + view.PADDING + level * view.INDENT_W + view.GUTTER_W
    
    # Entire left margin is clickable for row selection
    return left_edge <= pos.x < text_start

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

def is_image_row(view, row_idx: int) -> bool:
    """Check if the given row displays an image."""
    if not (0 <= row_idx < len(view._rows)):
        return False
    
    row = view._rows[row_idx]
    layout = view.cache.layout(row.entry_id) or {}
    return layout.get("is_img", False)

def get_image_filename(view, row_idx: int) -> Optional[str]:
    """Get the image filename for an image row."""
    if not is_image_row(view, row_idx):
        return None
    
    row = view._rows[row_idx]
    layout = view.cache.layout(row.entry_id) or {}
    return layout.get("img_file")

def get_image_file_path(view, row_idx: int) -> Optional[str]:
    """Get the full path to the original image file for an image row."""
    filename = get_image_filename(view, row_idx)
    if not filename:
        return None
    
    row = view._rows[row_idx]
    image_dir = entry_dir(view.notebook_dir, row.entry_id)
    image_path = image_dir / filename
    
    if image_path.exists():
        return str(image_path)
    
    return None

def get_original_image_dimensions(view, row_idx: int) -> Optional[Tuple[int, int]]:
    """Get the original image width and height from the source file."""
    image_path = get_image_file_path(view, row_idx)
    if not image_path:
        return None
    
    # Load the original image to get its dimensions
    import wx
    if not wx.App.IsMainLoopRunning():
        app = wx.App.GetInstance()
        if app is None:
            wx.App(False)
    
    img = wx.Image(image_path)
    if not img.IsOk():
        return None
        
    return (img.GetWidth(), img.GetHeight())
