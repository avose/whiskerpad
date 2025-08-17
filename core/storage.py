from __future__ import annotations

import json, os, time

from pathlib import Path

from typing import Dict, Any

NOTEBOOK_VERSION = 2

def ensure_notebook(target_dir: str, name: str | None = None) -> Dict[str, Any]:
    """
    Create or load a notebook directory.
    
    Structure:
    <target_dir>/
      notebook.json
      entries/
      _trash/
      _cache/

    Returns: {'path': str, 'created': bool, 'name': str}
    Raises: ValueError on unsafe directory conditions.
    """
    p = Path(target_dir).expanduser().resolve()
    nb_json = p / "notebook.json"

    if p.exists() and nb_json.exists():
        with nb_json.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        return {"path": str(p), "created": False, "name": meta.get("name", p.name)}

    if p.exists():
        # If it exists but is not empty and not a notebook, bail (avoid clobber).
        if any(p.iterdir()):
            raise ValueError(f"Directory exists and is not an empty notebook dir: {p}")
    else:
        p.mkdir(parents=True, exist_ok=True)

    # Create minimal structure
    for sub in ("entries", "_trash", "_cache"):
        (p / sub).mkdir(exist_ok=True)

    meta = {
        "name": name or p.name,
        "version": NOTEBOOK_VERSION,
        "created_ts": int(time.time()),
        "root_ids": [],
    }

    tmp = p / "notebook.json.tmp"
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    tmp.replace(nb_json)
    
    return {"path": str(p), "created": True, "name": meta["name"]}
