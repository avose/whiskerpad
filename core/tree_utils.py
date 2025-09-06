from __future__ import annotations

from typing import Optional, List

from core.tree import load_entry, save_entry, create_node, get_root_ids, set_root_ids

__all__ = [
    "add_sibling_after",
    "indent_under_prev_sibling", 
    "outdent_to_parent_sibling",
    "move_entry_after",
    "set_collapsed",
    "toggle_collapsed",
    "get_ancestors",
]

def _find_child_index(items: list, child_id: str) -> int:
    """Find index of child with given ID in items list. Returns -1 if not found."""
    return next(
        (i for i, item in enumerate(items)
         if isinstance(item, dict) and item.get("type") == "child" and item.get("id") == child_id),
        -1
    )

def get_ancestors(notebook_dir: str, entry_id: str) -> List[str]:
    """Get all ancestor entry IDs from target up to root (excluding target itself)."""
    ancestors = []
    current_id = entry_id
    
    while current_id:
        try:
            entry = load_entry(notebook_dir, current_id)
            parent_id = entry.get("parent_id")
            if parent_id:
                ancestors.append(parent_id)
                current_id = parent_id
            else:
                break  # Reached root
        except Exception:
            # Entry doesn't exist or is corrupted
            break
    
    return ancestors  # Returns [parent, grandparent, great-grandparent, ...]

# ---------- Selection-adjacent create ----------

def add_sibling_after(notebook_dir: str, cur_id: str) -> Optional[str]:
    """
    Create a new node at the same level as cur_id, inserted immediately after it.
    Returns the new entry_id, or None on failure.
    Uses fresh snapshots to avoid stale ordering.
    """
    cur = load_entry(notebook_dir, cur_id)
    parent_id = cur.get("parent_id")

    # Child case: insert in parent's items right after cur_id
    if parent_id:
        parent = load_entry(notebook_dir, parent_id)
        items = list(parent.get("items", []))
        idx = _find_child_index(items, cur_id)
        insert_index = (idx + 1) if idx >= 0 else len(items)
        return create_node(notebook_dir, parent_id=parent_id, title="", insert_index=insert_index)

    # Root case: insert after cur among root_ids
    ids = get_root_ids(notebook_dir)
    if cur_id not in ids:
        # Data inconsistency - cur_id should be in root_ids if it has no parent
        return None

    idx = ids.index(cur_id)
    new_id = create_node(notebook_dir, parent_id=None, title="")  # appends by default
    
    # Refresh and reorder
    ids = get_root_ids(notebook_dir)
    if new_id in ids:
        ids.remove(new_id)
        ids.insert(min(idx + 1, len(ids)), new_id)
        set_root_ids(notebook_dir, ids)
    
    return new_id

# ---------- Indent / Outdent / Move ----------

def indent_under_prev_sibling(notebook_dir: str, cur_id: str) -> bool:
    """
    Make cur_id a child of its previous sibling (same parent).
    Root items use previous root as new parent.
    No-op if there is no previous sibling/root.
    """
    cur = load_entry(notebook_dir, cur_id)
    parent_id = cur.get("parent_id")

    if parent_id:
        parent = load_entry(notebook_dir, parent_id)
        items = list(parent.get("items", []))
        idx = _find_child_index(items, cur_id)
        if idx <= 0:
            return False  # no previous sibling

        prev_id = items[idx - 1].get("id")
        if not isinstance(prev_id, str):
            return False

        # Expand prev; move cur from parent -> prev.children
        prev = load_entry(notebook_dir, prev_id)
        if prev.get("collapsed", False):
            prev["collapsed"] = False
            save_entry(notebook_dir, prev)

        items.pop(idx)
        parent["items"] = items
        save_entry(notebook_dir, parent)

        pitems = list(prev.get("items", []))
        pitems.append({"type": "child", "id": cur_id})
        prev["items"] = pitems
        save_entry(notebook_dir, prev)

        cur["parent_id"] = prev_id
        save_entry(notebook_dir, cur)
        return True

    # Root: previous root becomes new parent
    ids = get_root_ids(notebook_dir)
    if cur_id not in ids:
        return False

    idx = ids.index(cur_id)
    if idx <= 0:
        return False  # no previous root to indent under

    prev_id = ids[idx - 1]
    prev = load_entry(notebook_dir, prev_id)
    if prev.get("collapsed", False):
        prev["collapsed"] = False
        save_entry(notebook_dir, prev)

    # Remove from roots; append to prev children
    ids.pop(idx)
    set_root_ids(notebook_dir, ids)

    pitems = list(prev.get("items", []))
    pitems.append({"type": "child", "id": cur_id})
    prev["items"] = pitems
    save_entry(notebook_dir, prev)

    cur["parent_id"] = prev_id
    save_entry(notebook_dir, cur)
    return True

def outdent_to_parent_sibling(notebook_dir: str, cur_id: str) -> bool:
    """
    Move cur_id up one level:
    - If cur has a parent P and P has grandparent G: remove cur from P, insert cur as a sibling
      immediately after P in G's children.
    - If cur has a parent P and P is root-level: remove cur from P, insert cur in root_ids
      immediately after P.
    - If cur has no parent (root): no-op.
    """
    cur = load_entry(notebook_dir, cur_id)
    parent_id = cur.get("parent_id")
    if not parent_id:
        return False  # already at root

    parent = load_entry(notebook_dir, parent_id)

    # If the parent itself is the single root entry (has no grand-parent),
    # Shift-Tab is a no-op. Bail out before doing any modifications.
    grand_id = parent.get("parent_id")
    if grand_id is None:
        return False

    # Remove cur from parent (normal out-dent case only).
    pitems = list(parent.get("items", []))
    idx = _find_child_index(pitems, cur_id)
    if idx < 0:
        return False  # cur not found in parent's items

    pitems.pop(idx)
    parent["items"] = pitems
    save_entry(notebook_dir, parent)

    # Insert as sibling after parent in grand-parent's items
    grand = load_entry(notebook_dir, grand_id)
    gitems = list(grand.get("items", []))
    pidx = _find_child_index(gitems, parent_id)
    insert_index = pidx + 1 if pidx >= 0 else len(gitems)

    gitems.insert(insert_index, {"type": "child", "id": cur_id})
    grand["items"] = gitems
    save_entry(notebook_dir, grand)

    cur["parent_id"] = grand_id
    save_entry(notebook_dir, cur)
    return True

def move_entry_after(notebook_dir: str, entry_to_move_id: str, target_entry_id: str) -> bool:
    """
    Move entry_to_move_id to be a sibling immediately after target_entry_id.
    Both entries must exist and cannot be the same.
    Returns True on success, False on failure.
    """
    if entry_to_move_id == target_entry_id:
        return False

    try:
        entry_to_move = load_entry(notebook_dir, entry_to_move_id)
        target_entry = load_entry(notebook_dir, target_entry_id)

        old_parent_id = entry_to_move.get("parent_id")
        target_parent_id = target_entry.get("parent_id")

        # Remove from current location
        if old_parent_id:
            # Remove from parent's items
            old_parent = load_entry(notebook_dir, old_parent_id)
            items = list(old_parent.get("items", []))
            old_idx = _find_child_index(items, entry_to_move_id)
            if old_idx >= 0:
                items.pop(old_idx)
                old_parent["items"] = items
                save_entry(notebook_dir, old_parent)
        else:
            # Remove from root_ids
            root_ids = get_root_ids(notebook_dir)
            if entry_to_move_id in root_ids:
                root_ids.remove(entry_to_move_id)
                set_root_ids(notebook_dir, root_ids)

        # Insert in new location (after target)
        if target_parent_id:
            # Insert in target's parent items
            target_parent = load_entry(notebook_dir, target_parent_id)
            items = list(target_parent.get("items", []))
            target_idx = _find_child_index(items, target_entry_id)
            insert_idx = target_idx + 1 if target_idx >= 0 else len(items)
            items.insert(insert_idx, {"type": "child", "id": entry_to_move_id})
            target_parent["items"] = items
            save_entry(notebook_dir, target_parent)

            # Update entry's parent
            entry_to_move["parent_id"] = target_parent_id
            save_entry(notebook_dir, entry_to_move)
        else:
            # Insert in root_ids after target
            root_ids = get_root_ids(notebook_dir)
            if target_entry_id in root_ids:
                target_idx = root_ids.index(target_entry_id)
                root_ids.insert(target_idx + 1, entry_to_move_id)
                set_root_ids(notebook_dir, root_ids)

                # Update entry to be root-level
                entry_to_move["parent_id"] = None
                save_entry(notebook_dir, entry_to_move)

        return True

    except Exception:
        return False

# ---------- Collapse / Expand ----------

def set_collapsed(notebook_dir: str, entry_id: str, collapsed: bool) -> bool:
    """Set the 'collapsed' flag on an entry. Returns True if a change was made."""
    e = load_entry(notebook_dir, entry_id)
    cur = bool(e.get("collapsed", False))
    if cur == bool(collapsed):
        return False

    e["collapsed"] = bool(collapsed)
    save_entry(notebook_dir, e)
    return True

def toggle_collapsed(notebook_dir: str, entry_id: str) -> bool:
    """Toggle the 'collapsed' flag on an entry. Returns True if saved."""
    e = load_entry(notebook_dir, entry_id)
    e["collapsed"] = not bool(e.get("collapsed", False))
    save_entry(notebook_dir, e)
    return True
