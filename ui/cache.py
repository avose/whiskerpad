# ui/cache.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Set, Tuple

from core.log import Log
from core.tree import (
    load_entry,
    save_entry,
    commit_entry_edit,
    cancel_entry_edit,
    set_entry_edit_rich_text,
)

__all__ = ["NotebookCache"]


class NotebookCache:
    """
    One-stop cache for WhiskerPad.

    • entry_data   – the JSON for a node, loaded from disk once and reused
    • layout_data  – row height / wrapped-text info
                     (recomputed automatically when text-width changes)

    The fast path:

        width = client_text_width(view, row.level)
        if not cache.layout_valid(eid, width):
            layout = expensive_wrap(...)
            cache.store_layout(eid, width, layout)
        h = cache.row_height(eid)        # O(1) dict read

    All other code should go through this class; nothing touches the disk
    directly except the helpers above.
    """

    # ------------------------------------------------------------------ #
    # construction / statistics
    # ------------------------------------------------------------------ #

    def __init__(self, notebook_dir: str) -> None:
        self.notebook_dir = notebook_dir
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._dirty: Set[str] = set()  # unsaved entry_data

    # ------------------------------------------------------------------ #
    # entry-level I/O
    # ------------------------------------------------------------------ #

    def entry(self, entry_id: str) -> Dict[str, Any]:
        """
        Return the entry JSON, loading from disk on first access.
        """
        c = self._cache.setdefault(entry_id, {})
        if "entry_data" not in c:
            c["entry_data"] = load_entry(self.notebook_dir, entry_id)
        return c["entry_data"]

    def save_entry_data(self, entry: Dict[str, Any]) -> None:
        save_entry(self.notebook_dir, entry)
        self._cache.setdefault(entry["id"], {})["entry_data"] = entry
        self._dirty.discard(entry["id"])

    # ------------------------------------------------------------------ #
    # layout-data helpers
    # ------------------------------------------------------------------ #

    def layout_valid(self, entry_id: str, text_width: int) -> bool:
        ld = self._cache.get(entry_id, {}).get("layout_data")
        return bool(ld and ld["computed_for"]["text_width"] == text_width)

    def store_layout(
        self, entry_id: str, text_width: int, layout: Dict[str, Any]
    ) -> None:
        """
        Store freshly-computed layout data.

        `layout` MUST contain at minimum:
            • "wrap_h"  – full row height in px
            • "is_img"  – bool
        You may add keys like "rich_lines", "img_sw", "img_sh", etc.
        """
        self._cache.setdefault(entry_id, {})["layout_data"] = {
            "computed_for": {"text_width": int(text_width)},
            **layout,
        }

    def layout(self, entry_id: str) -> Dict[str, Any] | None:
        return self._cache.get(entry_id, {}).get("layout_data")

    def row_height(self, entry_id: str) -> int | None:
        """
        Fast-path height fetch; returns None if no valid layout is cached.
        """
        ld = self._cache.get(entry_id, {}).get("layout_data")
        return None if ld is None else int(ld.get("wrap_h", 0))

    # ------------------------------------------------------------------ #
    # invalidation
    # ------------------------------------------------------------------ #

    def invalidate_entry(self, entry_id: str) -> None:
        Log.debug(f"invalidate_entry({entry_id=})", 10)
        self._cache.pop(entry_id, None)
        self._dirty.discard(entry_id)

    def invalidate_entries(self, entry_ids: set[str]) -> None:
        """
        Remove many entries from the cache at once.
        Keeps identical semantics with invalidate_entry(), but faster
        for large collapse/expand operations.
        """
        Log.debug(f"invalidate_entries(entry_ids={','.join(entry_ids)})", 10)
        for eid in entry_ids:
            self._cache.pop(eid, None)      # entry_data + layout_data
            self._dirty.discard(eid)        # clear dirty flag if present

    def invalidate_layout_only(self) -> None:
        """
        Called from GCView._on_size when the window width changes:
        keeps entry_data, drops only layout_data.
        """
        Log.debug(f"invalidate_layout_only()", 10)
        for c in self._cache.values():
            c.pop("layout_data", None)

    # ------------------------------------------------------------------ #
    # global invalidation
    # ------------------------------------------------------------------ #
    def invalidate_all(self) -> None:
        """Clear entry_data, layout_data, and dirty sets."""
        Log.debug(f"invalidate_all()", 10)
        self._cache.clear()
        self._dirty.clear()

    # ------------------------------------------------------------------ #
    # edit-helpers (delegates to core.tree and keeps cache coherent)
    # ------------------------------------------------------------------ #

    def commit_edit(self, entry_id: str, rich_text: list[dict]) -> None:
        commit_entry_edit(self.notebook_dir, entry_id, rich_text)
        self.invalidate_entry(entry_id)

    def cancel_edit(self, entry_id: str) -> None:
        cancel_entry_edit(self.notebook_dir, entry_id)
        self.invalidate_entry(entry_id)

    def set_edit_rich_text(self, entry_id: str, rich_text: list[dict]) -> None:
        """Set rich text in edit field during editing."""
        set_entry_edit_rich_text(self.notebook_dir, entry_id, rich_text)
        self._dirty.add(entry_id)

    # ------------------------------------------------------------------ #
    # diagnostics
    # ------------------------------------------------------------------ #

    def stats(self) -> Dict[str, int]:
        entry_cnt = len(self._cache)
        layout_cnt = sum("layout_data" in v for v in self._cache.values())
        return {
            "entries": entry_cnt,
            "layouts": layout_cnt,
            "dirty": len(self._dirty),
        }
