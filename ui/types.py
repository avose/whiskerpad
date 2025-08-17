from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class Row:
    """A single flattened row in the view."""
    kind: str           # "node"
    entry_id: str
    level: int
    cache: Dict[str, Any] = field(default_factory=dict)  # wrap + paint cache
