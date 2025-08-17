from __future__ import annotations
from typing import Any, Dict, Optional, List
import time
import wx

from tree import load_entry, save_entry
from ui.notebook_text import flatten_ops

class InlineEditor:
    """
    Manages the lifecycle of a single inline TextCtrl editor for NotebookView rows.
    Node-only: no legacy 'rich' blocks.
    Assumes wx >= 4.2.3 and valid invariants from the view.
    """

    def __init__(self, view, nb_dir: str, get_entry, rows: List[Dict[str, Any]]):
        self._view = view
        self._nb_dir = nb_dir
        self._get_entry = get_entry  # function(eid) -> entry dict (cached)
        self._rows = rows
        self._ctrl: Optional[wx.TextCtrl] = None
        self._ctx: Optional[Dict[str, Any]] = None  # {"row": int, "entry_id": str}

    # --- properties ---
    @property
    def ctrl(self) -> Optional[wx.TextCtrl]:
        return self._ctrl

    @property
    def active(self) -> bool:
        return self._ctrl is not None

    # --- helpers ---
    def _row_rect(self, n: int) -> wx.Rect:
        return self._view._row_rect(n)  # uses view's existing helper

    def _compute_geometry(self, n: int, level: int) -> wx.Rect:
        rect = self._row_rect(n)
        x0 = rect.x + self._view.DATE_COL_W + self._view.PADDING + level * self._view.INDENT_W
        left = x0 + self._view.GUTTER_W
        right_pad = self._view.PADDING + 4
        width = max(10, self._view.GetClientSize().width - left - right_pad)
        height = max(self._view.ROW_H - 2, rect.height - 2)
        return wx.Rect(left, rect.y + 1, width, height)

    def _node_text(self, eid: str) -> str:
        e = self._get_entry(eid)
        ops = e.get("ops", [])
        text = flatten_ops(ops) if isinstance(ops, list) else (e.get("title", "") or "")
        if text.endswith("\n"):
            text = text[:-1]
        return text.replace("\r", "")

    # --- public API ---
    def begin(self, n: int):
        if not (0 <= n < len(self._rows)):
            return
        row = self._rows[n]
        if row.get("kind") != "node":
            return

        # If already editing, cancel first (no try/except churn)
        if self._ctrl is not None:
            self.cancel()

        eid = row["entry_id"]
        level = int(row["level"])
        cur_text = self._node_text(eid)

        # Editor control
        ed = wx.TextCtrl(
            self._view,
            value=cur_text,
            style=wx.TE_MULTILINE | wx.TE_PROCESS_TAB | wx.BORDER_SIMPLE,
        )
        ed.SetFont(self._view._font)
        ed.SetSize(self._compute_geometry(n, level))
        ed.Raise()
        ed.SetFocus()
        ed.SetInsertionPointEnd()

        self._ctrl = ed
        self._ctx = {"row": n, "entry_id": eid}

        def _on_kill_focus(_evt):
            self.commit()

        def _on_key_down(evt: wx.KeyEvent):
            code = evt.GetKeyCode()
            if code == wx.WXK_ESCAPE:
                self.cancel()
                return
            if code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and evt.ControlDown():
                self.commit()
                return
            evt.Skip()

        ed.Unbind(wx.EVT_KILL_FOCUS)
        ed.Unbind(wx.EVT_KEY_DOWN)
        ed.Bind(wx.EVT_KILL_FOCUS, _on_kill_focus)
        ed.Bind(wx.EVT_KEY_DOWN, _on_key_down)

    def _destroy(self):
        if self._ctrl is not None:
            self._ctrl.Destroy()
        self._ctrl = None
        self._ctx = None

    def commit(self):
        if not self._ctrl or not self._ctx:
            return
        new_text = self._ctrl.GetValue()
        parent_id = self._ctx["entry_id"]

        e = load_entry(self._nb_dir, parent_id)
        old_text = flatten_ops(e.get("ops", []))
        changed = new_text != old_text
        if changed:
            e["ops"] = [{"insert": new_text}]
            e["last_edit_ts"] = int(time.time())
            save_entry(self._nb_dir, e)

        # Teardown and refresh
        self._destroy()
        if changed:
            self._view.invalidate_cache(parent_id)
            self._view.rebuild()
            self._view.select_entry(parent_id)
        else:
            self._view.RefreshAll()

    def cancel(self):
        self._destroy()
        self._view.RefreshAll()

    def reposition(self):
        """Reposition the editor on view resize."""
        if not self._ctrl or not self._ctx:
            return
        i = int(self._ctx.get("row", -1))
        if not (0 <= i < len(self._rows)):
            return
        level = int(self._rows[i]["level"])
        self._ctrl.SetSize(self._compute_geometry(i, level))
