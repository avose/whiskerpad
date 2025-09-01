from __future__ import annotations

from typing import Optional

from core.tree import load_entry, save_entry, create_node, get_root_ids, set_root_ids

__all__ = [
    "add_sibling_after",
    "indent_under_prev_sibling",
    "outdent_to_parent_sibling",
    "set_collapsed",
    "toggle_collapsed",
]


def _find_child_index(items: list, child_id: str) -> int:
    """Find index of child with given ID in items list. Returns -1 if not found."""
    return next(
        (i for i, item in enumerate(items)
         if isinstance(item, dict) and item.get("type") == "child" and item.get("id") == child_id),
        -1
    )

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

# ---------- Indent / Outdent ----------

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
    # Shift-Tab is a no-op.  Bail out before doing any modifications.
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
