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

def notebook_paths(notebook_dir: str):
    notebook_path = Path(notebook_dir).expanduser().resolve()
    return {
        "root": notebook_path,
        "notebook_json": notebook_path / "notebook.json",
        "entries": notebook_path / "entries",
        "trash": notebook_path / "_trash",
        "cache": notebook_path / "_cache",
    }

# ---------- notebook.json ----------

def load_notebook(notebook_dir: str) -> Dict[str, Any]:
    paths = notebook_paths(notebook_dir)
    metadata = _read_json(paths["notebook_json"], {})
    if not metadata:
        raise ValueError(f"notebook.json not found in {notebook_dir}")
    return metadata

def save_notebook(notebook_dir: str, metadata: Dict[str, Any]) -> None:
    paths = notebook_paths(notebook_dir)
    _atomic_write_json(paths["notebook_json"], metadata)

def get_root_ids(notebook_dir: str) -> List[str]:
    return list(load_notebook(notebook_dir).get("root_ids", []))

def set_root_ids(notebook_dir: str, ids: List[str]) -> None:
    metadata = load_notebook(notebook_dir)
    metadata["root_ids"] = list(ids)
    save_notebook(notebook_dir, metadata)

# ---------- entries/<shard>/<id>/entry.json ----------

def _new_id() -> str:
    return uuid.uuid4().hex[:12]

def entry_dir(notebook_dir: str, entry_id: str) -> Path:
    """
    Strict sharded layout:
    entries/<first_2_chars>/<entry_id>/
    """
    base = notebook_paths(notebook_dir)["entries"]
    return base / entry_id[:2] / entry_id

def entry_json_path(notebook_dir: str, entry_id: str) -> Path:
    return entry_dir(notebook_dir, entry_id) / "entry.json"

def create_node(notebook_dir: str, parent_id: Optional[str] = None, title: str = "",
                insert_index: Optional[int] = None) -> str:
    """
    Create a new node with rich text format.
    If parent_id is None, append to notebook.root_ids.
    Otherwise, append a {'type':'child','id': new_id} into parent's items (or at insert_index).

    Returns new entry_id.
    """
    eid = _new_id()
    d = entry_dir(notebook_dir, eid)
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
        ids = get_root_ids(notebook_dir)
        ids.append(eid)
        set_root_ids(notebook_dir, ids)
    else:
        # Add to parent's items
        parent = load_entry(notebook_dir, parent_id)
        child_item = {"type": "child", "id": eid}
        if insert_index is None or insert_index < 0 or insert_index > len(parent["items"]):
            parent["items"].append(child_item)
        else:
            parent["items"].insert(insert_index, child_item)
        save_entry(notebook_dir, parent)

    return eid

def load_entry(notebook_dir: str, entry_id: str) -> Dict[str, Any]:
    paths = entry_json_path(notebook_dir, entry_id)
    if not paths.exists():
        raise ValueError(f"entry.json for id={entry_id} not found")
    return _read_json(paths, {})

def save_entry(notebook_dir: str, entry: Dict[str, Any]) -> None:
    entry["updated_ts"] = int(time.time())
    paths = entry_json_path(notebook_dir, entry["id"])
    _atomic_write_json(paths, entry)

# ---------- Rich Text Utilities ----------

def get_entry_rich_text(notebook_dir: str, entry_id: str) -> List[Dict[str, Any]]:
    """Get the rich text content of an entry."""
    entry = load_entry(notebook_dir, entry_id)
    return entry.get("text", [{"content": ""}])

def set_entry_rich_text(notebook_dir: str, entry_id: str, rich_text: List[Dict[str, Any]]) -> None:
    """Set the rich text content of an entry."""
    entry = load_entry(notebook_dir, entry_id)
    entry["text"] = rich_text
    entry["edit"] = ""  # Clear edit field when setting final text
    save_entry(notebook_dir, entry)

def get_entry_edit_rich_text(notebook_dir: str, entry_id: str) -> List[Dict[str, Any]]:
    """Get the temporary edit rich text of an entry."""
    entry = load_entry(notebook_dir, entry_id)
    edit_data = entry.get("edit", [])

    # Handle legacy plain text edit fields
    if isinstance(edit_data, str):
        if edit_data:
            return [{"content": edit_data}]
        else:
            return [{"content": ""}]

    # Return rich text format
    return edit_data if edit_data else [{"content": ""}]

def set_entry_edit_rich_text(notebook_dir: str, entry_id: str, rich_text: List[Dict[str, Any]]) -> None:
    """Set the temporary edit rich text of an entry (auto-saved during editing)."""
    entry = load_entry(notebook_dir, entry_id)
    entry["edit"] = rich_text
    entry["last_edit_ts"] = int(time.time())
    save_entry(notebook_dir, entry)

def commit_entry_edit(notebook_dir: str, entry_id: str, rich_text: List[Dict[str, Any]]) -> None:
    """Commit edit rich text to final text and clear edit field."""
    entry = load_entry(notebook_dir, entry_id)
    entry["text"] = rich_text
    entry["edit"] = []  # Clear edit field (now empty rich text array)
    entry["last_edit_ts"] = int(time.time())
    save_entry(notebook_dir, entry)

def cancel_entry_edit(notebook_dir: str, entry_id: str) -> None:
    """Cancel editing by clearing the edit field."""
    entry = load_entry(notebook_dir, entry_id)
    entry["edit"] = []  # Clear edit field (now empty rich text array)
    save_entry(notebook_dir, entry)
