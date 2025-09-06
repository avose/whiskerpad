from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple, Union
import time
import wx

from ui.image_utils import thumb_name_for

Pathish = Union[str, Path]

__all__ = ["load_thumb_bitmap", "clear_thumb_cache", "clear_thumb_cache_for_entry"]

# Very small LRU-ish cache for decoded bitmaps keyed by absolute file path.
# We keep access timestamps and drop the oldest when exceeding the limit.
_CACHE: Dict[str, Tuple[wx.Bitmap, Tuple[int, int], float]] = {}
_CACHE_MAX = 256  # number of thumbnails; tweak as needed


def _ensure_wx_app() -> None:
    if not wx.App.IsMainLoopRunning():
        app = wx.App.GetInstance()
        if app is None:
            wx.App(False)


def clear_thumb_cache() -> None:
    """Clear entire thumbnail cache."""
    _CACHE.clear()


def clear_thumb_cache_for_entry(entry_dir: Pathish, image_filename: str) -> None:
    """Clear thumbnail cache for a specific entry's image."""
    entry = Path(entry_dir)
    thumb_path = entry / thumb_name_for(image_filename)
    abs_key = str(thumb_path.resolve())
    _CACHE.pop(abs_key, None)


def _prune_cache() -> None:
    if len(_CACHE) <= _CACHE_MAX:
        return

    # Drop ~10% oldest entries
    to_drop = max(1, _CACHE_MAX // 10)
    for k, _v in sorted(_CACHE.items(), key=lambda kv: kv[1][2])[:to_drop]:
        _CACHE.pop(k, None)


def load_thumb_bitmap(entry_dir: Pathish, image_filename: str) -> Tuple[wx.Bitmap, int, int]:
    """
    Load (and cache) the thumbnail bitmap for an image in `entry_dir`.
    Returns: (bitmap, width, height)
    Raises if the thumb file is missing or cannot be decoded.
    """
    _ensure_wx_app()

    entry = Path(entry_dir)
    thumb_path = entry / thumb_name_for(image_filename)
    abs_key = str(thumb_path.resolve())

    # Cache hit
    hit = _CACHE.get(abs_key)
    if hit is not None:
        bmp, (w, h), _ts = hit
        _CACHE[abs_key] = (bmp, (w, h), time.time())
        return bmp, w, h

    # Load from disk - support both PNG (new) and JPEG (legacy)
    if not thumb_path.is_file():
        # Try legacy JPEG format for backwards compatibility
        legacy_thumb = thumb_path.with_suffix('.jpg')
        if legacy_thumb.is_file():
            thumb_path = legacy_thumb
        else:
            raise FileNotFoundError(f"thumbnail not found: {thumb_path}")

    img = wx.Image(str(thumb_path))
    if not img.IsOk():
        raise RuntimeError(f"failed to decode thumbnail: {thumb_path}")

    w, h = img.GetWidth(), img.GetHeight()
    bmp = wx.Bitmap(img)

    _CACHE[abs_key] = (bmp, (w, h), time.time())
    _prune_cache()

    return bmp, w, h
