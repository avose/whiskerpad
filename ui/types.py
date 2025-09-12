# ui/types.py
'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Row:
    """
    A single flattened row in the notebook view.

    • kind      – currently always "node" (kept for future block types)
    • entry_id  – UUID of the entry this row represents
    • level     – tree-indent level (root = 0)
    """
    kind: str          # e.g. "node"
    entry_id: str
    level: int
