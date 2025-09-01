from __future__ import annotations

from bisect import bisect_right
from typing import List, Tuple

from ui.types import Row
from ui.layout import measure_row_height

class LayoutIndex:
    """
    Immutable per-build layout index of cumulative row offsets and heights.

    - offsets[i] == pixel Y of the top of row i in content coordinates.
    - heights[i] == pixel height of row i.
    - total_height == sum(heights).
    """

    __slots__ = ("offsets", "heights", "total_height")

    def __init__(self) -> None:
        self.offsets: List[int] = []
        self.heights: List[int] = []
        self.total_height: int = 0

    def rebuild(self, view, rows: List[Row]) -> None:
        """
        Recompute offsets/heights using the current wrap width of `view`.

        This is O(N) and should be called after:
        - rows change (flatten),
        - or the available text width changes (window resize).
        """
        heights = []
        for r in rows:
            # measure_row_height will populate/consume wrap cache as needed.
            ht = measure_row_height(view, r)
            heights.append(max(0, ht))

        offsets = []
        acc = 0
        for ht in heights:
            offsets.append(acc)
            acc += ht

        self.heights = heights
        self.offsets = offsets
        self.total_height = acc

    def row_top(self, i: int) -> int:
        """Get the top Y coordinate of row i."""
        if 0 <= i < len(self.offsets):
            return self.offsets[i]
        return 0

    def row_height(self, i: int) -> int:
        """Get the height of row i."""
        if 0 <= i < len(self.heights):
            return self.heights[i]
        return 0

    def find_row_at_y(self, y: int) -> Tuple[int, int]:
        """
        Given a content Y (0 = very top), return: (row_index, y_into_row)

        If y is above first row, returns (0, y).
        If y is beyond end, returns (last_index, last_row_height-1) as a clamp.
        """
        if not self.offsets:
            return (-1, 0)

        i = bisect_right(self.offsets, y) - 1
        if i < 0:
            return (0, y)

        if i >= len(self.heights):
            last = len(self.heights) - 1
            last_h = self.heights[last] if last >= 0 else 0
            return (last, max(0, last_h - 1))

        return (i, y - self.offsets[i])

    def content_height(self) -> int:
        """Get the total content height."""
        return self.total_height

    def insert_row(self, view, insert_idx: int, new_row: Row):
        """Insert a single row and update layout incrementally."""
        if not (0 <= insert_idx <= len(self.heights)):
            # Out of bounds, trigger full rebuild
            self.rebuild(view, view._rows)
            return

        # Measure the new row
        new_height = measure_row_height(view, new_row)

        # Insert height at the correct position
        self.heights.insert(insert_idx, new_height)

        # Recalculate offsets from insertion point onward
        if insert_idx == 0:
            new_offset = 0
        else:
            new_offset = self.offsets[insert_idx - 1] + self.heights[insert_idx - 1]

        # Insert the new offset
        self.offsets.insert(insert_idx, new_offset)

        # Update all subsequent offsets
        for i in range(insert_idx + 1, len(self.offsets)):
            self.offsets[i] += new_height

        # Update total height
        self.total_height += new_height
