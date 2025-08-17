from __future__ import annotations

import os
from pathlib import Path
from typing import Union, Tuple

import wx

Pathish = Union[str, Path]

__all__ = [
    "thumb_name_for",
    "make_thumbnail_file",
]


def thumb_name_for(image_filename: str) -> str:
    """
    Derive thumbnail name from the imported image filename:
      "<UUID>_<sanitized>.<ext>" -> "<UUID>_thumb.jpg"
    """
    prefix = image_filename.split("_", 1)[0] if "_" in image_filename else image_filename
    return f"{prefix}_thumb.jpg"


def _fit_within(w: int, h: int, max_px: int) -> Tuple[int, int]:
    """
    Return (tw, th) scaled to fit within max_px x max_px, preserving aspect.
    """
    if w <= 0 or h <= 0:
        return (max_px, max_px)
    if w <= max_px and h <= max_px:
        return (w, h)
    if w >= h:
        tw = max_px
        th = max(1, int(round(h * (max_px / float(w)))))
    else:
        th = max_px
        tw = max(1, int(round(w * (max_px / float(h)))))
    return (tw, th)


def _ensure_wx_app() -> None:
    """
    Ensure a wx.App exists (safe if already created).
    Image operations generally work without Show(), but require app init on some platforms.
    """
    if not wx.App.IsMainLoopRunning():
        # Try to get existing; if none, create a hidden one.
        app = wx.App.GetInstance()
        if app is None:
            wx.App(False)


def make_thumbnail_file(
    entry_dir: Pathish,
    image_filename: str,
    *,
    max_px: int = 256,
    jpeg_quality: int = 85,
) -> Path:
    """
    Create/overwrite the thumbnail JPEG for the given image inside the same entry directory.
    Returns the absolute Path of the thumbnail.

    - Reads:  <entry_dir>/<image_filename>
    - Writes: <entry_dir>/<UUID>_thumb.jpg
    """
    _ensure_wx_app()

    entry = Path(entry_dir)
    src = entry / image_filename
    if not src.is_file():
        raise FileNotFoundError(f"source image not found: {src}")

    thumb_path = entry / thumb_name_for(image_filename)

    img = wx.Image(str(src))
    if not img.IsOk():
        raise RuntimeError(f"failed to load image: {src}")

    tw, th = _fit_within(img.GetWidth(), img.GetHeight(), max_px)
    if img.GetWidth() != tw or img.GetHeight() != th:
        img = img.Scale(tw, th, wx.IMAGE_QUALITY_HIGH)

    # Set JPEG quality if supported
    try:
        img.SetOptionInt(wx.IMAGE_OPTION_QUALITY, int(jpeg_quality))
    except Exception:
        pass

    # Save via a same-directory temp, then atomic replace + fsync of the directory
    tmp = thumb_path.with_name(f".{thumb_path.name}.tmp")
    try:
        if not img.SaveFile(str(tmp), wx.BITMAP_TYPE_JPEG):
            raise RuntimeError(f"failed to save thumbnail to temp: {tmp}")
        os.replace(tmp, thumb_path)
        # fsync directory to persist metadata
        fd = os.open(str(thumb_path.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass

    return thumb_path

