from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

import wx

from utils.image_types import wx_open_filter_string

Pathish = Union[str, Path]

__all__ = ["choose_image_files", "choose_single_image_file"]


def choose_image_files(
    parent: wx.Window | None,
    *,
    multiple: bool = True,
    default_dir: Pathish | None = None,
) -> Optional[List[str]]:
    """
    Open a file picker for supported image types.
    Returns a list of absolute paths on OK, or None on cancel.
    """
    style = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
    if multiple:
        style |= wx.FD_MULTIPLE
    wildcard = wx_open_filter_string(extra_all=True)
    with wx.FileDialog(
        parent,
        message="Add image(s)…",
        wildcard=wildcard,
        style=style,
        defaultDir=str(default_dir) if default_dir else "",
    ) as dlg:
        if dlg.ShowModal() != wx.ID_OK:
            return None
        if multiple:
            paths = [str(Path(p).resolve()) for p in dlg.GetPaths()]
        else:
            paths = [str(Path(dlg.GetPath()).resolve())]
    return paths


def choose_single_image_file(
    parent: wx.Window | None,
    *,
    default_dir: Pathish | None = None,
) -> Optional[str]:
    """
    Convenience wrapper for a single image selection.
    """
    res = choose_image_files(parent, multiple=False, default_dir=default_dir)
    if not res:
        return None
    return res[0]

