from __future__ import annotations

import json, os, uuid, time
from pathlib import Path
from typing import Dict, Any, List, Optional

def _read_json(p: Path, default: Any) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed JSON in {p}: {e}") from e

def _atomic_write_json(p: Path, obj: Dict[str, Any]) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(p)

    # Ensure directory entry is durable
    dir_fd = os.open(str(p.parent), os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)

def nb_paths(nb_dir: str):
    nb = Path(nb_dir).expanduser().resolve()
    return {
        "root": nb,
        "notebook_json": nb / "notebook.json",
        "entries": nb / "entries",
        "trash": nb / "_trash",
        "cache": nb / "_cache",
    }

# ---------- notebook.json ----------

def load_notebook(nb_dir: str) -> Dict[str, Any]:
    p = nb_paths(nb_dir)
    meta = _read_json(p["notebook_json"], {})
    if not meta:
        raise ValueError(f"notebook.json not found in {nb_dir}")
    return meta

def save_notebook(nb_dir: str, meta: Dict[str, Any]) -> None:
    p = nb_paths(nb_dir)
    _atomic_write_json(p["notebook_json"], meta)

def get_root_ids(nb_dir: str) -> List[str]:
    return list(load_notebook(nb_dir).get("root_ids", []))

def set_root_ids(nb_dir: str, ids: List[str]) -> None:
    meta = load_notebook(nb_dir)
    meta["root_ids"] = list(ids)
    save_notebook(nb_dir, meta)

# ---------- entries/<shard>/<id>/entry.json ----------

def _new_id() -> str:
    return uuid.uuid4().hex[:12]

def entry_dir(nb_dir: str, entry_id: str) -> Path:
    """
    Strict sharded layout:
    entries/<first_2_chars>/<entry_id>/
    """
    base = nb_paths(nb_dir)["entries"]
    return base / entry_id[:2] / entry_id

def entry_json_path(nb_dir: str, entry_id: str) -> Path:
    return entry_dir(nb_dir, entry_id) / "entry.json"

def create_node(nb_dir: str, parent_id: Optional[str] = None, title: str = "",
                insert_index: Optional[int] = None) -> str:
    """
    Create a new node with rich text format.
    If parent_id is None, append to notebook.root_ids.
    Otherwise, append a {'type':'child','id': new_id} into parent's items (or at insert_index).
    
    Returns new entry_id.
    """
    eid = _new_id()
    d = entry_dir(nb_dir, eid)
    d.mkdir(parents=True, exist_ok=True)

    now = int(time.time())
    
    # Rich text format with single "text" field - start empty if no title given
    if title:
        text_content = [{"content": title}]
    else:
        text_content = [{"content": ""}]  # Empty but still valid rich text structure
    
    entry = {
        "id": eid,
        "text": text_content,
        "edit": "",                   # Temporary editing field
        "parent_id": parent_id,
        "collapsed": False,
        "created_ts": now,
        "updated_ts": now,
        "last_edit_ts": None,
        "items": []  # child links and future attachments
    }

    _atomic_write_json(d / "entry.json", entry)
    if parent_id is None:
        # Add to root_ids
        ids = get_root_ids(nb_dir)
        ids.append(eid)
        set_root_ids(nb_dir, ids)
    else:
        # Add to parent's items
        parent = load_entry(nb_dir, parent_id)
        child_item = {"type": "child", "id": eid}
        if insert_index is None or insert_index < 0 or insert_index > len(parent["items"]):
            parent["items"].append(child_item)
        else:
            parent["items"].insert(insert_index, child_item)
        save_entry(nb_dir, parent)

    return eid

def load_entry(nb_dir: str, entry_id: str) -> Dict[str, Any]:
    p = entry_json_path(nb_dir, entry_id)
    if not p.exists():
        raise ValueError(f"entry.json for id={entry_id} not found")
    return _read_json(p, {})

def save_entry(nb_dir: str, entry: Dict[str, Any]) -> None:
    entry["updated_ts"] = int(time.time())
    p = entry_json_path(nb_dir, entry["id"])
    _atomic_write_json(p, entry)

# ---------- Rich Text Utilities ----------

def get_entry_rich_text(nb_dir: str, entry_id: str) -> List[Dict[str, Any]]:
    """Get the rich text content of an entry."""
    entry = load_entry(nb_dir, entry_id)
    return entry.get("text", [{"content": ""}])

def set_entry_rich_text(nb_dir: str, entry_id: str, rich_text: List[Dict[str, Any]]) -> None:
    """Set the rich text content of an entry."""
    entry = load_entry(nb_dir, entry_id)
    entry["text"] = rich_text
    entry["edit"] = ""  # Clear edit field when setting final text
    save_entry(nb_dir, entry)

def get_entry_edit_text(nb_dir: str, entry_id: str) -> str:
    """Get the temporary edit text of an entry."""
    entry = load_entry(nb_dir, entry_id)
    return entry.get("edit", "")

def set_entry_edit_text(nb_dir: str, entry_id: str, edit_text: str) -> None:
    """Set the temporary edit text of an entry (auto-saved during editing)."""
    entry = load_entry(nb_dir, entry_id)
    entry["edit"] = edit_text
    entry["last_edit_ts"] = int(time.time())
    save_entry(nb_dir, entry)

def commit_entry_edit(nb_dir: str, entry_id: str, rich_text: List[Dict[str, Any]]) -> None:
    """Commit edit text to final text and clear edit field."""
    entry = load_entry(nb_dir, entry_id)
    entry["text"] = rich_text
    entry["edit"] = ""
    entry["last_edit_ts"] = int(time.time())
    save_entry(nb_dir, entry)

def cancel_entry_edit(nb_dir: str, entry_id: str) -> None:
    """Cancel editing by clearing the edit field."""
    entry = load_entry(nb_dir, entry_id)
    entry["edit"] = ""
    save_entry(nb_dir, entry)
