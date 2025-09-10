# ui/cache.py
from __future__ import annotations

import wx
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

    def __init__(self, notebook_dir: str, view=None) -> None:
        self.notebook_dir = notebook_dir
        self.view = view  # Reference to view for cache refresh operations
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._dirty: Set[str] = set()  # unsaved entry_data

    def set_view(self, view):
        """Set view reference after construction if needed"""
        self.view = view

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

    def char_to_pixel(self, row: Row, char_pos: int, text_area_x: int, text_area_y: int) -> Tuple[int, int]:
        """Convert character position to pixel coordinates using cached layout data."""
        from ui.layout import client_text_width, ensure_wrap_cache

        # Ensure we have valid layout data
        width = client_text_width(self.view, row.level)
        if not self.layout_valid(row.entry_id, width):
            ensure_wrap_cache(self.view, row)

        layout = self.layout(row.entry_id)
        if not layout or layout.get("is_img"):
            # Image row or no layout - return start position
            return (text_area_x, text_area_y)

        rich_lines = layout.get("rich_lines", [])
        line_height = layout.get("line_h", self.view.ROW_H)

        if not rich_lines or char_pos <= 0:
            return (text_area_x, text_area_y)

        char_pos = min(char_pos, rich_lines[-1]['end_char'])

        # Find which line contains this character position
        for line_idx, line in enumerate(rich_lines):
            start_char = line['start_char']
            end_char = line['end_char']

            # Normal case: position within line
            if start_char <= char_pos < end_char:
                y = text_area_y + line_idx * line_height

                # Find x position within the line
                chars_into_line = char_pos - start_char
                x = text_area_x
                chars_measured = 0

                for segment in line['segments']:
                    segment_len = len(segment['text'])
                    if chars_measured + segment_len >= chars_into_line:
                        # Character is within this segment
                        chars_in_segment = chars_into_line - chars_measured
                        if chars_in_segment > 0:
                            partial_text = segment['text'][:chars_in_segment]
                            font = self.view._bold if segment.get('bold') else self.view._font
                            dc = wx.ClientDC(self.view)
                            dc.SetFont(font)
                            partial_width = dc.GetTextExtent(partial_text)[0]
                            x += partial_width
                        return (x, y)

                    x += segment['width']
                    chars_measured += segment_len

                return (x, y)

            # Special case: position at end of line (but not the last line)
            elif char_pos == end_char and line_idx < len(rich_lines) - 1:
                y = text_area_y + line_idx * line_height
                x = text_area_x + sum(seg['width'] for seg in line['segments'])
                return (x, y)

        # Fallback: position at end of last line
        if rich_lines:
            last_line = rich_lines[-1]
            y = text_area_y + (len(rich_lines) - 1) * line_height
            x = text_area_x + sum(seg['width'] for seg in last_line['segments'])
            return (x, y)

        return (text_area_x, text_area_y)

    def pixel_to_char(self, row: Row, click_x: int, click_y: int, text_area_x: int, text_area_y: int) -> int:
        """Convert pixel coordinates to character position using cached layout data."""
        from ui.layout import client_text_width, ensure_wrap_cache
        
        # Ensure we have valid layout data
        width = client_text_width(self.view, row.level)
        if not self.layout_valid(row.entry_id, width):
            ensure_wrap_cache(self.view, row)
        
        layout = self.layout(row.entry_id)
        if not layout or layout.get("is_img"):
            # Image row or no layout - return 0
            return 0
        
        rich_lines = layout.get("rich_lines", [])
        line_height = layout.get("line_h", self.view.ROW_H)
        
        if not rich_lines:
            return 0
        
        # Determine which line was clicked
        click_y_in_text = click_y - text_area_y
        if click_y_in_text < 0:
            return rich_lines[0]['start_char']
        
        line_idx = max(0, int(click_y_in_text // line_height))
        if line_idx >= len(rich_lines):
            return rich_lines[-1]['end_char']
        
        line = rich_lines[line_idx]
        click_x_in_line = click_x - text_area_x

        if click_x_in_line <= 0:
            return line['start_char']

        # Find character position within the clicked line
        char_pos = line['start_char']
        x_pos = 0

        for segment in line['segments']:
            segment_width = segment['width']
            if x_pos + segment_width >= click_x_in_line:
                # Click is within this segment
                pos_in_seg = self._find_char_in_segment(segment, click_x_in_line - x_pos)
                result_pos = char_pos + pos_in_seg

                # NEW: Clamp to line boundaries to prevent end-of-line issues
                return min(result_pos, line['end_char'])

            x_pos += segment_width
            char_pos += len(segment['text'])

        # Click was past end of line - return end of this line, not last line
        return line['end_char']

    def _find_char_in_segment(self, segment: dict, click_x_in_segment: int) -> int:
        """Find which character in a segment was clicked."""
        text = segment['text']
        font = self.view._bold if segment.get('bold') else self.view._font
        dc = wx.ClientDC(self.view)
        dc.SetFont(font)
        
        # Binary search would be more efficient, but simple linear search for now
        best_pos = 0
        best_distance = abs(click_x_in_segment)
        
        for i in range(len(text) + 1):
            substr = text[:i]
            width = dc.GetTextExtent(substr)[0]
            distance = abs(width - click_x_in_segment)
            
            if distance < best_distance:
                best_distance = distance
                best_pos = i
        
        return best_pos

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
