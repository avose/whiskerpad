# ui/layout.py  – rewritten for unified cache
from __future__ import annotations

import wx
from typing import Tuple, List

from ui.notebook_text import rich_text_from_entry, measure_rich_text_wrapped
from ui.types import Row
from utils.img_tokens import parse_img_token_line
from ui.image_loader import load_thumb_bitmap
from core.tree import entry_dir

# ---------------------------------------------------------------------------

def client_text_width(view, level: int) -> int:
    """Pixels available for wrapped text at a given indent level."""
    w = view.GetClientSize().width
    left = (
        view.DATE_COL_W
        + view.PADDING
        + level * view.INDENT_W
        + view.GUTTER_W
        + 4
    )
    right_pad = view.PADDING + 4
    return max(10, w - left - right_pad)


# ---------------------------------------------------------------------------

def ensure_wrap_cache(view, row: Row) -> None:
    """
    Guarantee that layout (wrap) info for *row* exists in view.cache.

    If the cached layout is stale for the current text-width it is
    recomputed and stored; otherwise no work is done.
    """
    cache = view.cache
    eid = row.entry_id
    width = client_text_width(view, row.level)

    # fast-path: already valid → nothing to do
    if cache.layout_valid(eid, width):
        return

    # expensive path – recompute
    entry = cache.entry(eid)
    rich_text = rich_text_from_entry(entry)
    plain_text = rich_text.to_plain_text().strip()

    # Check for image-token row
    token_fname = parse_img_token_line(plain_text)
    if token_fname:
        _store_image_layout(cache, view, row, entry, token_fname, width)
        return

    _store_text_layout(cache, view, row, rich_text, width)


def _store_image_layout(
    cache, view, row: Row, entry: dict, fname: str, width: int
) -> None:
    """Compute scaled thumbnail metrics and cache them."""
    try:
        bmp_dir = entry_dir(view.notebook_dir, row.entry_id)
        _bmp, tw, th = load_thumb_bitmap(bmp_dir, fname)

        # scale down to fit width (never scale up)
        if tw > width:
            sw = width
            sh = max(1, int(round(th * (width / float(tw)))))
        else:
            sw, sh = tw, th

        #!!avose: Hack to allow images to be larger than width.
        #sw, sh = tw, th

        layout = {
            "is_img": True,
            "img_file": fname,
            "img_sw": sw,
            "img_sh": sh,
            "wrap_h": sh + 2 * view.PADDING,
        }
        cache.store_layout(row.entry_id, width, layout)
    except Exception:
        # fallback: treat as plain text
        _store_text_layout(cache, view, row, rich_text_from_entry(entry), width)


def _store_text_layout(
    cache, view, row: Row, rich_text, width: int
) -> None:
    """Wrap rich text, measure it, and cache the result."""
    dc = wx.ClientDC(view)
    line_segments, line_height, total_h = measure_rich_text_wrapped(
        rich_text, width, dc, view._font, view._bold, view.PADDING
    )

    layout = {
        "is_img": False,
        "rich_lines": line_segments,
        "line_h": line_height,
        "wrap_h": total_h,
    }
    cache.store_layout(row.entry_id, width, layout)


# ---------------------------------------------------------------------------

def measure_row_height(view, row: Row) -> int:
    """
    Cheap accessor used *everywhere*.

    Ensures layout is present (calling ensure_wrap_cache if needed) and
    then returns the cached row height.
    """
    ensure_wrap_cache(view, row)
    h = view.cache.row_height(row.entry_id)
    return max(view.ROW_H, h if h is not None else view.ROW_H)
