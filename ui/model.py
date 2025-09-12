'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''
from __future__ import annotations

from typing import List, Optional

from core.tree import load_entry
from ui.types import Row

def _is_collapsed(notebook_dir: str, entry_id: str, view=None) -> bool:
    """
    Check if entry is collapsed, respecting read-only transient state.
    
    In read-only mode: Check transient state first, fall back to persistent
    In normal mode: Check persistent state only
    """
    # If we have a view and it's in read-only mode, check transient state
    if view and view.is_read_only():
        if entry_id in view.flat_tree._transient_collapsed:
            return view.flat_tree._transient_collapsed[entry_id]
        # Fall through to persistent check if not in transient state
    
    # Normal persistent check
    try:
        if view:
            entry = view.cache.entry(entry_id)
        else:
            entry = load_entry(notebook_dir, entry_id)
        return entry.get("collapsed", False)
    except:
        return False

def _gather_children(notebook_dir: str, parent_id: str, level: int, out: List[Row], view=None) -> None:
    """Recursively gather children entries into the output list."""
    out.append(Row(kind="node", entry_id=parent_id, level=level))

    # Skip children if this node is collapsed (check transient state in read-only mode)
    if _is_collapsed(notebook_dir, parent_id, view):
        return

    # Add all child entries
    try:
        if view:
            entry = view.cache.entry(parent_id)
        else:
            entry = load_entry(notebook_dir, parent_id)
            
        for item in entry.get("items", []):
            if item.get("type") == "child" and isinstance(item.get("id"), str):
                _gather_children(notebook_dir, item["id"], level + 1, out, view)
    except:
        pass

def flatten_tree(notebook_dir: str, root_id: str, view=None) -> List[Row]:
    """
    Flatten a hierarchical tree structure into a linear list of rows, excluding the root.
    
    Args:
        notebook_dir: Path to notebook directory
        root_id: ID of root entry
        view: Optional view instance for read-only transient state checking
    """
    rows: List[Row] = []

    try:
        # Load the root entry but don't add it to the display
        if view:
            root_entry = view.cache.entry(root_id)
        else:
            root_entry = load_entry(notebook_dir, root_id)

        # Start with the root's children at level 0 (instead of the root at level 0)
        for item in root_entry.get("items", []):
            if item.get("type") == "child" and isinstance(item.get("id"), str):
                _gather_children(notebook_dir, item["id"], 0, rows, view)
    except:
        pass

    return rows

def update_tree_incremental(notebook_dir: str, rows: List[Row], changed_entry_id: str, view=None) -> List[Row]:
    """
    Update flattened tree incrementally when one node's collapse state changes.
    
    Args:
        notebook_dir: Path to notebook directory
        rows: Current list of rows
        changed_entry_id: ID of entry whose collapse state changed
        view: Optional view instance for read-only transient state checking
    """
    # Find the changed row
    changed_idx = -1
    for i, row in enumerate(rows):
        if row.entry_id == changed_entry_id:
            changed_idx = i
            break

    if changed_idx == -1:
        # Entry not found in current view - full rebuild needed
        root_id = rows[0].entry_id if rows else ""
        return flatten_tree(notebook_dir, root_id, view)

    # Check new collapse state (respecting transient state in read-only mode)
    is_collapsed = _is_collapsed(notebook_dir, changed_entry_id, view)

    # Remove old subtree from rows
    rows_before = rows[:changed_idx + 1]  # Include the changed row itself

    # Skip over old subtree
    i = changed_idx + 1
    target_level = rows[changed_idx].level
    while i < len(rows) and rows[i].level > target_level:
        i += 1
    rows_after = rows[i:]

    # If now expanded, insert new subtree
    if not is_collapsed:
        new_subtree = []
        _gather_children(notebook_dir, changed_entry_id, target_level, new_subtree, view)
        
        # Remove the root since it's already in rows_before
        if new_subtree and new_subtree[0].entry_id == changed_entry_id:
            new_subtree = new_subtree[1:]
        
        return rows_before + new_subtree + rows_after
    else:
        # If collapsed, just combine before and after
        return rows_before + rows_after
