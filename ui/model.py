from __future__ import annotations

from typing import List

from core.tree import load_entry
from ui.types import Row

def _gather_children(nb_dir: str, parent_id: str, level: int, out: List[Row]) -> None:
    """Recursively gather children entries into the output list."""
    e = load_entry(nb_dir, parent_id)
    out.append(Row(kind="node", entry_id=parent_id, level=level))

    # Skip children if this node is collapsed
    if e.get("collapsed", False):
        return

    # Add all child entries
    for item in e.get("items", []):
        if isinstance(item, dict) and item.get("type") == "child":
            child_id = item.get("id")
            if isinstance(child_id, str):
                _gather_children(nb_dir, child_id, level + 1, out)

def flatten_tree(nb_dir: str, root_id: str) -> List[Row]:
    """Flatten a hierarchical tree structure into a linear list of rows."""
    rows: List[Row] = []
    _gather_children(nb_dir, root_id, 0, rows)
    return rows
