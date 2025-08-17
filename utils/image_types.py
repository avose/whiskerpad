from __future__ import annotations

from pathlib import Path
from typing import Iterable, Set

__all__ = ["IMAGE_EXTS", "is_supported_image_path", "wx_open_filter_string"]

# Central list of supported raster formats (lowercase, no dots)
IMAGE_EXTS: Set[str] = {
    "png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff",
}


def is_supported_image_path(p: Path | str) -> bool:
    ext = Path(p).suffix.lower().lstrip(".")
    return ext in IMAGE_EXTS


def wx_open_filter_string(extra_all: bool = True) -> str:
    """
    Build a wx.FileDialog filter string for our supported image types.
    Example: "Image files (*.png;*.jpg;...)|*.png;*.jpg;...|All files (*.*)|*.*"
    """
    wildcards = ";".join(f"*.{e}" for e in sorted(IMAGE_EXTS))
    parts = [f"Image files ({wildcards})|{wildcards}"]
    if extra_all:
        parts.append("All files (*.*)|*.*")
    return "|".join(parts)

