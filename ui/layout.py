from __future__ import annotations

from typing import Tuple, List

import wx

from ui.notebook_text import rich_text_from_entry, measure_rich_text_wrapped
from ui.types import Row
from utils.img_tokens import parse_img_token_line
from ui.image_loader import load_thumb_bitmap
from core.tree import entry_dir

def client_text_width(view, level: int) -> int:
    """Calculate available text width for a given indentation level."""
    w = view.GetClientSize().width
    left = view.DATE_COL_W + view.PADDING + level * view.INDENT_W + view.GUTTER_W + 4
    right_pad = view.PADDING + 4
    return max(10, w - left - right_pad)

def ensure_wrap_cache(view, row: Row) -> None:
    """Update row.cache with rich text layout information if width or source changed."""
    level = int(row.level)
    curw = client_text_width(view, level)

    wkey = int(row.cache.get("_wrap_w") or -1)

    # Get entry and rich text
    e = view._get(row.entry_id)
    rich_text = rich_text_from_entry(e)
    
    # Convert to plain text for comparison and image token detection
    plain_text = rich_text.to_plain_text()
    src_trim = (plain_text or "").strip()
    token_fname = parse_img_token_line(src_trim)  # None unless it's exactly a block token line

    if (wkey != curw or 
        row.cache.get("_wrap_src") != plain_text or 
        "_wrap_h" not in row.cache):

        # Image-only row?
        if token_fname:
            ed = entry_dir(view.nb_dir, row.entry_id)
            try:
                _bmp, tw, th = load_thumb_bitmap(ed, token_fname)
                
                # Scale down to fit content width; never scale up
                if tw > curw:
                    scaled_w = curw
                    scaled_h = max(1, int(round(th * (curw / float(tw)))))
                else:
                    scaled_w, scaled_h = tw, th

                row.cache["_is_img"] = True
                row.cache["_img_file"] = token_fname
                row.cache["_img_w"] = tw
                row.cache["_img_h"] = th
                row.cache["_img_sw"] = scaled_w
                row.cache["_img_sh"] = scaled_h
                total_h = scaled_h + 2 * view.PADDING

                # Clear rich text cache for image rows
                row.cache["_rich_lines"] = []
                row.cache["_wrap_h"] = total_h
                
            except Exception:
                # Image loading failed - treat as text
                row.cache["_is_img"] = False
                _cache_rich_text_layout(view, row, rich_text, curw, plain_text)
        else:
            # Rich text row
            row.cache["_is_img"] = False
            _cache_rich_text_layout(view, row, rich_text, curw, plain_text)

        row.cache["_wrap_w"] = curw
        row.cache["_wrap_src"] = plain_text

def _cache_rich_text_layout(view, row: Row, rich_text, curw: int, plain_text: str) -> None:
    """Cache rich text layout information for a text row."""
    # Create device context for text measurement
    dc = wx.ClientDC(view)
    
    # Handle completely empty text
    if not plain_text.strip() and rich_text.char_count() == 0:
        # Empty text - create minimal layout
        dc.SetFont(view._font)
        line_height = dc.GetTextExtent("Ag")[1]
        total_h = line_height + 2 * view.PADDING
        
        row.cache["_rich_lines"] = [{
            'segments': [],
            'height': line_height
        }]
        row.cache["_wrap_h"] = total_h
        row.cache["_wrap_lh"] = line_height
        return
    
    # Measure rich text with wrapping
    line_segments, line_height, total_h = measure_rich_text_wrapped(
        rich_text, curw, dc, view._font, view._bold, view.PADDING
    )
    
    # Cache the layout information
    row.cache["_rich_lines"] = line_segments
    row.cache["_wrap_h"] = total_h
    row.cache["_wrap_lh"] = line_height

def measure_row_height(view, row: Row) -> int:
    """Get the height of a row, ensuring wrap cache is up to date."""
    ensure_wrap_cache(view, row)
    return max(view.ROW_H, int(row.cache.get("_wrap_h") or view.ROW_H))
