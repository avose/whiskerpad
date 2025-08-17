from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Union

Pathish = Union[str, Path]

__all__ = ["fsync_dir", "atomic_write_bytes", "atomic_copy"]


def fsync_dir(dir_path: Pathish) -> None:
    """
    Fsync a directory to persist metadata updates (e.g., renames).
    Safe no-op if the directory doesn't exist.
    """
    d = Path(dir_path)
    if not d.exists():
        return
    fd = os.open(str(d), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_tmp_and_replace(
    dst_path: Path, write_fn, *, tmp_suffix: str = "", mode_from: Path | None = None
) -> None:
    """
    Internal helper:
      - create a temp file in dst directory
      - write via write_fn(fileobj)
      - fsync temp
      - (optional) chmod from mode_from
      - os.replace -> dst
      - fsync directory
    """
    dst_dir = dst_path.parent
    dst_dir.mkdir(parents=True, exist_ok=True)
    tmp_name = f".{dst_path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}{tmp_suffix}"
    tmp_path = dst_dir / tmp_name

    try:
        with open(tmp_path, "wb") as f:
            write_fn(f)
            f.flush()
            os.fsync(f.fileno())
        if mode_from is not None:
            try:
                os.chmod(tmp_path, mode_from.stat().st_mode & 0o777)
            except Exception:
                # Permissions best-effort; don't fail atomicity on chmod
                pass
        os.replace(tmp_path, dst_path)
        fsync_dir(dst_dir)
    except Exception:
        # Best-effort cleanup
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        raise


def atomic_write_bytes(dst: Pathish, data: bytes) -> None:
    """
    Atomically write bytes to dst path (same-dir temp + replace + fsync).
    """
    dst_path = Path(dst)

    def _writer(fobj):
        fobj.write(data)

    _write_tmp_and_replace(dst_path, _writer)


def atomic_copy(src: Pathish, dst: Pathish, *, chunk_size: int = 1 << 20) -> None:
    """
    Atomically copy a file from src to dst using a same-directory temp file,
    fsyncing data and directory metadata.
    """
    src_path = Path(src)
    dst_path = Path(dst)
    if not src_path.is_file():
        raise FileNotFoundError(f"Source not found or not a file: {src_path}")
    if src_path.resolve() == dst_path.resolve():
        # Nothing to do; treat as success
        return

    def _writer(fobj):
        with open(src_path, "rb") as r:
            shutil.copyfileobj(r, fobj, length=chunk_size)

    _write_tmp_and_replace(dst_path, _writer, mode_from=src_path)

