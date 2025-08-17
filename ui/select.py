# ui/gc_select.py

from __future__ import annotations

from ui.scroll import soft_ensure_visible

def select_row(view, idx: int, ensure_visible: bool = True, refresh: bool = True) -> bool:
    if not (0 <= idx < len(view._rows)):
        return False

    view._change_selection(idx)

    if ensure_visible:
        soft_ensure_visible(view, idx)

    return True

def select_entry_id(view, entry_id: str, ensure_visible: bool = True) -> bool:
    for i, r in enumerate(view._rows):
        if r.entry_id == entry_id:
            return select_row(view, i, ensure_visible=ensure_visible, refresh=True)
    return False
