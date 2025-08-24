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

def update_tree_incremental(nb_dir: str, rows: List[Row], changed_entry_id: str) -> List[Row]:
    """Update flattened tree incrementally when one node's collapse state changes."""
    
    # Find the changed row
    changed_idx = -1
    for i, row in enumerate(rows):
        if row.entry_id == changed_entry_id:
            changed_idx = i
            break
    
    if changed_idx == -1:
        # Fallback to full rebuild if not found
        return flatten_tree(nb_dir, rows[0].entry_id if rows else "")
    
    # Get the entry to check new collapse state
    entry = load_entry(nb_dir, changed_entry_id)
    is_collapsed = entry.get("collapsed", False)
    
    # Remove old subtree from rows
    rows_before = rows[:changed_idx + 1]  # Include the changed row itself
    rows_after = []
    
    # Skip over old subtree
    i = changed_idx + 1
    target_level = rows[changed_idx].level
    while i < len(rows) and rows[i].level > target_level:
        i += 1
    rows_after = rows[i:]
    
    # If now expanded, insert new subtree
    if not is_collapsed:
        new_subtree = []
        _gather_children(nb_dir, changed_entry_id, target_level, new_subtree)
        # Remove the root since it's already in rows_before
        if new_subtree and new_subtree[0].entry_id == changed_entry_id:
            new_subtree = new_subtree[1:]
        
        return rows_before + new_subtree + rows_after
    else:
        # If collapsed, just combine before and after
        return rows_before + rows_after
