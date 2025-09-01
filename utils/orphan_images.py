from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple, Union

from utils.img_tokens import referenced_images

Pathish = Union[str, Path]

__all__ = [
    "find_orphans",
    "cleanup_orphans",
]


def _extract_uuid_from_filename(filename: str, pattern: re.Pattern) -> str | None:
    """Extract UUID from filename using the given regex pattern."""
    match = pattern.match(filename)
    return match.group("uuid") if match else None


# UUID is 32 lowercase hex from our filename scheme.
UUID_RE = r"(?P<uuid>[0-9a-f]{32})"
IMAGE_EXT = r"(?:png|jpg|jpeg|gif|webp|bmp|tif|tiff)"

IMG_FILE_RE = re.compile(rf"^{UUID_RE}_.+?\.{IMAGE_EXT}$")
THUMB_RE = re.compile(rf"^{UUID_RE}_thumb\.jpg$")


def _uuid_of_image_filename(filename: str) -> str | None:
    return _extract_uuid_from_filename(filename, IMG_FILE_RE)


def _uuid_of_thumb(filename: str) -> str | None:
    return _extract_uuid_from_filename(filename, THUMB_RE)


def find_orphans(entry_dir: Pathish, entry_text: str) -> Tuple[Set[str], Set[str]]:
    """
    Return (image_files_to_delete, thumb_files_to_delete) as filename sets (not paths).
    A file is considered orphaned if:
      - For images: its filename is NOT referenced by any token in entry_text.
      - For thumbs: its UUID does NOT appear among referenced images' UUIDs.
    """
    d = Path(entry_dir)
    if not d.exists():
        return set(), set()

    # Referenced image filenames exactly as they appear in tokens
    ref_images: Set[str] = referenced_images(entry_text)
    ref_image_uuids: Set[str] = set(filter(None, (_uuid_of_image_filename(f) for f in ref_images)))

    imgs_to_delete: Set[str] = set()
    thumbs_to_delete: Set[str] = set()

    for path in d.iterdir():
        if not path.is_file():
            continue
        filename = path.name
        u_img = _uuid_of_image_filename(filename)
        if u_img is not None:
            if filename not in ref_images:
                imgs_to_delete.add(filename)
            continue
        u_th = _uuid_of_thumb(filename)
        if u_th is not None:
            if u_th not in ref_image_uuids:
                thumbs_to_delete.add(filename)
            continue
        # Other files (entry.json, temp files, etc.) are ignored.

    return imgs_to_delete, thumbs_to_delete


def cleanup_orphans(entry_dir: Pathish, entry_text: str, *, dry_run: bool = False) -> Dict[str, List[str]]:
    """
    Delete orphaned image files and thumbnails from the entry directory.
    Returns a dict with lists of deleted filenames and those kept/referenced.
    Set dry_run=True to only report without deleting.
    """
    d = Path(entry_dir)
    imgs_to_delete, thumbs_to_delete = find_orphans(d, entry_text)

    deleted: List[str] = []
    errors: List[str] = []

    if not dry_run:
        for filename in list(imgs_to_delete) + list(thumbs_to_delete):
            try:
                (d / filename).unlink(missing_ok=True)
                deleted.append(filename)
            except Exception as e:
                errors.append(f"{filename}: {e}")

    # Report referenced items (kept)
    ref_images = sorted(list(referenced_images(entry_text)))
    ref_thumbs = sorted([f"{u}_thumb.jpg" for u in set(filter(None, (_uuid_of_image_filename(f) for f in ref_images)))])

    return {
        "deleted": sorted(list(deleted if not dry_run else (list(imgs_to_delete) + list(thumbs_to_delete)))),
        "kept_images": ref_images,
        "kept_thumbs": ref_thumbs,
        "errors": errors,
    }

