from __future__ import annotations
import wx
from typing import Dict, List, Any
from tree import load_entry, save_entry
from ui.notebook_hit_test import item_rect as hit_item_rect, hit_test, caret_hit
from ui.inline_editor import InlineEditor
from ui.constants import INDENT_W, GUTTER_W, PADDING, DATE_COL_W, DEFAULT_ROW_H
from ui.view_paint import measure_item as vp_measure_item, draw_item as vp_draw_item


class NotebookView(wx.VListBox):
    """
    Virtual, owner-drawn view that flattens the entry tree into a list of rows:
      - Node rows (caret + the node's own text in `ops`)
    Collapsed nodes hide BOTH their legacy rich blocks and all descendants.
    """
    ROW_H = DEFAULT_ROW_H
    INDENT_W = INDENT_W
    GUTTER_W = GUTTER_W  # space for caret
    PADDING = PADDING
    DATE_COL_W = DATE_COL_W  # width of left date gutter



    def _row_rect(self, n: int) -> wx.Rect:


        return hit_item_rect(self, n)

    def __init__(self, parent: wx.Window, nb_dir: str, root_id: str):
        super().__init__(parent, style=wx.BORDER_SIMPLE | wx.VSCROLL | wx.WANTS_CHARS)
        self.nb_dir = nb_dir
        self.root_id = root_id

        self._entry_cache: Dict[str, Dict[str, Any]] = {}
        # rows: list of dicts; kind == "node"
        # node: {"kind":"node","entry_id":eid,"level":lvl}
        self._rows: List[Dict[str, Any]] = []

        self._font = self.GetFont()
        self._bold = wx.Font(
            self._font.GetPointSize(),
            self._font.GetFamily(),
            wx.FONTSTYLE_NORMAL,
            wx.FONTWEIGHT_BOLD,
        )
        self._wrap_cache_w = -1  # last width we wrapped for
        # Ensure vertical scrollbar shows on all platforms and ROW_H matches font metrics
        # Ensure vertical scrollbar shows on all platforms and ROW_H matches font metrics
        self.SetWindowStyleFlag(self.GetWindowStyleFlag() | wx.VSCROLL | wx.ALWAYS_SHOW_SB)
        dc = wx.ClientDC(self)
        dc.SetFont(self._font)
        lh = dc.GetTextExtent("Ag")[1]
        # Set instance ROW_H to exactly one text line + vertical padding
        self.ROW_H = max(int(lh + 2 * self.PADDING), int(getattr(self, "ROW_H", 22)))
        # Interactions
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char)
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_RIGHT_DOWN, self._on_left_down)

        # Inline editor controller
        self._iedit = InlineEditor(self, self.nb_dir, self._get, self._rows)

        self.rebuild()

    # ---------- entry/cache ----------
    def _get(self, eid: str) -> Dict[str, Any]:
        e = self._entry_cache.get(eid)
        if e is None:
            e = load_entry(self.nb_dir, eid)
            self._entry_cache[eid] = e
        return e

    def invalidate_cache(self, entry_id: str | None = None):
        if entry_id is None:
            self._entry_cache.clear()
        else:
            self._entry_cache.pop(entry_id, None)

        # ---------- building the flattened rows ----------
    def rebuild(self):
        self._rows.clear()

        def visit(eid: str, level: int):
            e = self._get(eid)
            # node row
            self._rows.append({"kind": "node", "entry_id": eid, "level": level})
            if e.get("collapsed", False):
                return
            for it in e.get("items", []):
                if it.get("type") == "child":
                    visit(it.get("id"), level + 1)

        visit(self.root_id, 0)

        cur = self.GetSelection()
        self.SetItemCount(len(self._rows))
        if 0 <= cur < len(self._rows):
            self.SetSelection(cur)
        self.RefreshAll()

    # ---------- measurement & wrapping ----------
    def _client_text_width(self, level: int) -> int:
        w = self.GetClientSize().width
        left = self.DATE_COL_W + self.PADDING + level * self.INDENT_W + self.GUTTER_W + 4
        right_pad = self.PADDING + 4
        return max(10, w - left - right_pad)
    def OnMeasureItem(self, n: int) -> int:  # type: ignore[override]
        row = self._rows[n]
        return vp_measure_item(self, row)

        # Legacy rich block rows
        curw = self._client_text_width(row["level"])
        wkey = (row.get("_wrap_w") or -1)
        if wkey != curw or "_wrap_h" not in row:
            text = flatten_ops(row.get("ops", []))
            dc = wx.ClientDC(self)
            lines, lh, th = measure_wrapped(text, curw, dc, self._font, self.PADDING)
            row["_wrap_lines"] = lines
            row["_wrap_lh"] = lh
            row["_wrap_h"] = th
            row["_wrap_w"] = curw
        return max(self.ROW_H, int(row.get("_wrap_h") or self.ROW_H))


    def OnDrawItem(self, dc: wx.DC, rect: wx.Rect, n: int):  # type: ignore[override]
        row = self._rows[n]
        vp_draw_item(self, dc, rect, row, self.IsSelected(n))

    def _toggle_selected_node(self):
        n = self.GetSelection()
        if not (0 <= n < len(self._rows)):
            return
        row = self._rows[n]
        if row["kind"] != "node":
            return
        eid = row["entry_id"]
        e = self._get(eid)
        # Only toggle if has children
        if not any(it.get("type") in ("child",) for it in e.get("items", [])):
            return
        e["collapsed"] = not bool(e.get("collapsed", False))
        save_entry(self.nb_dir, e)
        self.invalidate_cache(eid)
        self.rebuild()

    def _on_left_down(self, evt: wx.MouseEvent):
        # Click position (relative to this view)
        pos = evt.GetPosition()

        # If an editor is open: commit on click outside; focus if clicked inside editor
        if self._iedit.active:
            r = self._iedit.ctrl.GetRect()
            if r.Contains(pos):
                self._iedit.ctrl.SetFocus()
                return  # swallow so list doesn't change selection
            else:
                self._iedit.commit()
            # continue handling this click after committing

        # Non-interactive gutter: clicks strictly inside the date gutter do nothing (except selection)        # Non-interactive gutter: clicks strictly inside the date gutter do nothing (except selection)
        if pos.x < getattr(self, "DATE_COL_W", 0):
            idx, rect = hit_test(self, pos)
            if idx >= 0:
                self.SetSelection(idx)
            return

        # Single-click hit test: left-of-caret toggles; right side edits

        idx, rect = hit_test(self, pos)
        if idx < 0 or rect is None:
            evt.Skip()
            return

        self.SetSelection(idx)
        row = self._rows[idx]
        if row.get("kind") == "node":
            level = int(row.get("level", 0))
            x0 = rect.x + self.DATE_COL_W + self.PADDING + level * self.INDENT_W
            caret_right_x = x0 + self.GUTTER_W
            # Toggle if click is to the left of (or on) the caret
            if pos.x <= caret_right_x:
                self._toggle_selected_node()
                return

        # Otherwise: begin inline edit on the clicked row (node or legacy rich)
        wx.CallAfter(self._iedit.begin, idx)



    def _on_dclick(self, _evt: wx.MouseEvent):
        # If an editor is already open, just focus it.
        if self._iedit.active:
            self._iedit.ctrl.SetFocus()
            return

        pos = _evt.GetPosition()
        idx, rect = hit_test(self, pos)
        if idx < 0 or rect is None:
            return

        self.SetSelection(idx)
        row = self._rows[idx]
        # Caret gutter toggles collapse if it's a node with children.
        if row.get("kind") == "node" and caret_hit(self, row, rect, pos):
            self._toggle_selected_node()
            return

        # Otherwise begin inline edit on that row.
        wx.CallAfter(self._iedit.begin, idx)


    def _on_char(self, evt: wx.KeyEvent):
        # If an inline editor is active, don't intercept keys at the list level.
        if self._iedit.active:
            evt.Skip()
            return
        code = evt.GetKeyCode()
        n = self.GetSelection()
        row = self._rows[n] if 0 <= n < len(self._rows) else None
        if code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            if row:
                wx.CallAfter(self._iedit.begin, n)
            else:
                self._toggle_selected_node()
        elif code == wx.WXK_SPACE:
            self._toggle_selected_node()
        else:
            evt.Skip()

    def _on_size(self, _evt: wx.SizeEvent):
        # Reposition any active inline editor on resize.
        self._iedit.reposition()
        w = self.GetClientSize().width
        if w != self._wrap_cache_w:
            self._wrap_cache_w = w
            # force re-measure of wrapped text on width change
            for r in self._rows:
                r.pop("_wrap_w", None)
                r.pop("_wrap_h", None)
                r.pop("_wrap_lines", None)
                r.pop("_wrap_src", None)
            self.RefreshAll()
        _evt.Skip()

    # ---------- public helpers ----------
    def set_root(self, root_id: str):
        self.root_id = root_id
        self.invalidate_cache()
        self.rebuild()

    def current_entry_id(self) -> str | None:
        n = self.GetSelection()
        if 0 <= n < len(self._rows):
            row = self._rows[n]
            return row["entry_id"]
        return None


    def select_entry(self, entry_id: str) -> bool:


        for i, row in enumerate(self._rows):


            if row['kind'] == 'node' and row['entry_id'] == entry_id:


                self.SetSelection(i)


                self.RefreshAll()


                return True


        return False
    # ---------- inline editing ----------
    # Public helpers
    def edit_entry(self, entry_id: str) -> bool:
        for i, row in enumerate(self._rows):
            if row.get("kind") == "node" and row.get("entry_id") == entry_id:
                self.SetSelection(i)
                self._iedit.begin(i)
                return True
        return False
