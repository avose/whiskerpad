from __future__ import annotations
import wx
from ui.view import GCView as NotebookView

class NotePanel(wx.Panel):
    """v2 mixed viewer: node rows with inline carets + interleaved rich blocks (read-only)."""
    def __init__(self, parent: wx.Window, nb_dir: str, entry_id: str):
        super().__init__(parent)
        self.nb_dir = nb_dir
        self.root_id = entry_id

        s = wx.BoxSizer(wx.VERTICAL)
        self.view = NotebookView(self, nb_dir, entry_id)
        s.Add(self.view, 1, wx.EXPAND | wx.ALL, 6)
        self.SetSizer(s)

    # API used by MainFrame
    def reload(self) -> None:
        self.view.invalidate_cache()
        self.view.rebuild()

    def current_selection_id(self):
        return self.view.current_entry_id()

    def select_entry(self, entry_id: str) -> bool:
        return self.view.select_entry(entry_id)

    def edit_block(self, block_id: str) -> bool:
        return self.view.edit_block(block_id)

    def edit_entry(self, entry_id: str) -> bool:
        return self.view.edit_entry(entry_id)
