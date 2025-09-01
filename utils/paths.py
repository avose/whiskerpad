from __future__ import annotations

import os
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Tuple, Optional, Union

Pathish = Union[str, Path]

__all__ = [
    "entries_shard_dir",
    "entry_dir",
    "ensure_entry_dir",
    "sanitize_basename",
    "new_uuid",
    "image_uuid_and_filename",
]


def entries_shard_dir(nb_dir: Pathish, entry_id: str) -> Path:
    """
    Return the shard directory for an entry id:
      <nb_dir>/entries/<entry_id[:2]>
    Does not create it.
    """
    nb = Path(nb_dir)
    if len(entry_id) < 2:
        raise ValueError("entry_id must be at least 2 characters")
    return nb / "entries" / entry_id[:2]


def entry_dir(nb_dir: Pathish, entry_id: str) -> Path:
    """
    Return the full entry directory path (not created):
      <nb_dir>/entries/<id[:2]>/<id>
    """
    return entries_shard_dir(nb_dir, entry_id) / entry_id


def ensure_entry_dir(nb_dir: Pathish, entry_id: str) -> Path:
    """
    Ensure the entry directory exists and return it.
    """
    d = entry_dir(nb_dir, entry_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


_SPACE_RE = re.compile(r"\s+")
_SAFE_CHAR_RE = re.compile(r"[^A-Za-z0-9._-]")  # conservative, portable


def _normalize_unicode_and_whitespace(text: str) -> str:
    """Normalize unicode and collapse whitespace to underscores."""
    text = unicodedata.normalize("NFKC", text)
    return _SPACE_RE.sub("_", text)


def _apply_safe_character_restrictions(text: str) -> str:
    """Apply conservative character set restrictions."""
    text = text.replace("/", "_")
    return _SAFE_CHAR_RE.sub("_", text)


def _truncate_preserving_extension(text: str, max_len: int) -> str:
    """Truncate text while trying to preserve file extension."""
    stem, dot, ext = text.partition(".") if text.count(".") == 1 else (text, "", "")

    if ext:
        ext = "." + ext  # restore leading dot
        base_max = max(1, max_len - len(ext))
        stem = stem[:base_max]
        result = stem + ext
    else:
        result = text[:max_len]

    # Avoid empty stems
    if result in ("", ".", ".."):
        result = "file"

    return result


def sanitize_basename(pathlike: Pathish, *, max_len: int = 120) -> str:
    """
    Return a safe basename for storing inside an entry directory.

    Rules:
    - take only the basename (strip any directories)
    - normalize unicode and collapse whitespace
    - apply conservative character set restrictions
    - limit length preserving extension when possible
    """
    # 1) basename only
    text = os.path.basename(str(pathlike)).strip()

    # Windows drive letter edge-case: os.path.basename("C:\\") == "C:\\"
    text = text.replace("\\", "/")
    text = os.path.basename(text)

    if not text:
        text = "file"

    # 2-3) normalize unicode and whitespace
    text = _normalize_unicode_and_whitespace(text)

    # 4-5) apply safe character restrictions
    text = _apply_safe_character_restrictions(text)

    # 6) truncate while preserving extension
    return _truncate_preserving_extension(text, max_len)


def new_uuid() -> str:
    """Return a lowercase hex UUID string (no dashes)."""
    return uuid.uuid4().hex


def image_uuid_and_filename(orig_path: Pathish, uid: Optional[str] = None) -> Tuple[str, str]:
    """
    Build the (uuid, filename) tuple for an imported image:
      - uuid := new_uuid() (or provided uid)
      - filename := "<UUID>_<SANITIZED_ORIG>"
    The caller will place this file into the entry directory.
    """
    u = uid or new_uuid()
    base = sanitize_basename(orig_path)
    return u, f"{u}_{base}"

