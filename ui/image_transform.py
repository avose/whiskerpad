'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Optional, Tuple
import wx

__all__ = [
    # Zoom operations (moved from image_zoom.py)
    "get_current_thumbnail_max_size",
    "calculate_zoom_in_size",
    "calculate_zoom_out_size",
    "calculate_reset_size",
    "clamp_thumbnail_size",
    "can_zoom_in",
    "can_zoom_out",
    # Transform operations
    "flip_thumbnail_vertical",
    "flip_thumbnail_horizontal",
    "rotate_thumbnail_clockwise",
    "rotate_thumbnail_anticlockwise",
]

# Constants
ZOOM_SCALE_FACTOR = 1.2  # 20% steps for finer control
MIN_THUMBNAIL_SIZE = 16
MAX_THUMBNAIL_SIZE = 2560
DEFAULT_THUMBNAIL_SIZE = 256


def _ensure_wx_app() -> None:
    """Ensure a wx.App exists for image operations."""
    if not wx.App.IsMainLoopRunning():
        app = wx.App.GetInstance()
        if app is None:
            wx.App(False)


# ============================================================================
# Zoom operations (moved from image_zoom.py)
# ============================================================================

def get_current_thumbnail_max_size(layout: dict) -> Optional[int]:
    """Extract the larger dimension from layout cache as current max size."""
    img_sw = layout.get("img_sw", 0)
    img_sh = layout.get("img_sh", 0)

    if img_sw <= 0 or img_sh <= 0:
        return None

    return max(img_sw, img_sh)


def calculate_zoom_in_size(current_max: int) -> int:
    """Calculate new size when zooming in (larger)."""
    new_size = int(current_max * ZOOM_SCALE_FACTOR)
    return clamp_thumbnail_size(new_size)


def calculate_zoom_out_size(current_max: int) -> int:
    """Calculate new size when zooming out (smaller)."""
    new_size = int(current_max / ZOOM_SCALE_FACTOR)
    return clamp_thumbnail_size(new_size)


def calculate_reset_size(original_width: int, original_height: int) -> int:
    """
    Calculate the natural reset size based on original image dimensions.
    For small images: use original size
    For large images: use default 256px limit
    """
    original_max = max(original_width, original_height)
    return min(original_max, DEFAULT_THUMBNAIL_SIZE)


def clamp_thumbnail_size(size: int) -> int:
    """Ensure size is within valid bounds."""
    return max(MIN_THUMBNAIL_SIZE, min(MAX_THUMBNAIL_SIZE, size))


def can_zoom_in(current_max: int) -> bool:
    """Check if zoom in operation would produce a larger size."""
    new_size = int(current_max * ZOOM_SCALE_FACTOR)
    return new_size > current_max and new_size <= MAX_THUMBNAIL_SIZE


def can_zoom_out(current_max: int) -> bool:
    """Check if zoom out operation would produce a smaller size."""
    new_size = int(current_max / ZOOM_SCALE_FACTOR)
    return new_size < current_max and new_size >= MIN_THUMBNAIL_SIZE


# ============================================================================
# Transform operations (new)
# ============================================================================

def flip_thumbnail_vertical(thumbnail_path: str) -> bool:
    """Flip thumbnail vertically (upside down)."""
    return _apply_thumbnail_transform(thumbnail_path, lambda img: img.Mirror(False))


def flip_thumbnail_horizontal(thumbnail_path: str) -> bool:
    """Flip thumbnail horizontally (left-right mirror)."""
    return _apply_thumbnail_transform(thumbnail_path, lambda img: img.Mirror(True))


def rotate_thumbnail_clockwise(thumbnail_path: str) -> bool:
    """Rotate thumbnail 90 degrees clockwise."""
    return _apply_thumbnail_transform(thumbnail_path, lambda img: img.Rotate90(True))


def rotate_thumbnail_anticlockwise(thumbnail_path: str) -> bool:
    """Rotate thumbnail 90 degrees anticlockwise."""
    return _apply_thumbnail_transform(thumbnail_path, lambda img: img.Rotate90(False))


def _apply_thumbnail_transform(thumbnail_path: str, transform_func) -> bool:
    """Apply a transformation function to thumbnail and save back to disk."""
    _ensure_wx_app()

    path = Path(thumbnail_path)
    if not path.exists():
        return False

    # Load thumbnail
    img = wx.Image(str(path))
    if not img.IsOk():
        return False

    # Apply transformation
    transformed_img = transform_func(img)
    if not transformed_img.IsOk():
        return False

    # Save via atomic replace (same pattern as image_utils.py)
    tmp_path = path.with_name(f".{path.name}.tmp")

    try:
        # Save as PNG (thumbnail format change)
        if not transformed_img.SaveFile(str(tmp_path), wx.BITMAP_TYPE_PNG):
            return False

        # Atomic replace
        os.replace(tmp_path, path)

        # fsync directory
        fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

        return True

    finally:
        # Cleanup temp file if it exists
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except:
                pass
