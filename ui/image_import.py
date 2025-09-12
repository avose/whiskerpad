'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''
from __future__ import annotations

from pathlib import Path
from typing import Dict, Union

from utils.paths import ensure_entry_dir, image_uuid_and_filename
from utils.fs_atomic import atomic_copy
from utils.img_tokens import make_img_token
from ui.image_utils import make_thumbnail_file, thumb_name_for
from utils.image_types import is_supported_image_path

Pathish = Union[str, Path]

__all__ = ["import_image_into_entry"]

def import_image_into_entry(notebook_dir: Pathish, entry_id: str, src_path: Pathish) -> Dict[str, str]:
    """
    Import an image file into the entry directory:
      - ensure entry dir exists (sharded layout)
      - build UUID-prefixed sanitized filename
      - atomic copy into entry dir
      - generate 256px JPEG thumbnail
      - return dict with filenames and token

    Returns:
      {
        "filename": "<UUID>_<sanitized>.<ext>",
        "thumb": "<UUID>_thumb.jpg",
        "token": '{{img "<UUID>_<sanitized>.<ext>"}}',
        "abs_path": "/abs/path/to/<UUID>_<sanitized>.<ext>"
      }
    """
    src = Path(src_path)
    if not src.is_file():
        raise FileNotFoundError(f"Source image not found: {src}")
    if not is_supported_image_path(src):
        raise ValueError(f"Unsupported image type: {src.suffix}")

    entry = ensure_entry_dir(notebook_dir, entry_id)
    _uuid, filename = image_uuid_and_filename(src.name)
    dst = entry / filename

    atomic_copy(src, dst)

    # Create/overwrite the thumbnail
    make_thumbnail_file(entry, filename, max_px=256)
    thumb = thumb_name_for(filename)

    token = make_img_token(filename)
    return {
        "filename": filename,
        "thumb": thumb,
        "token": token,
        "abs_path": str(dst.resolve()),
    }

