from __future__ import annotations
import wx
from ui.view import GCView as NotebookView

class NotePanel(wx.Panel):
    """Mixed viewer: node rows with inline carets + interleaved rich blocks."""
    def __init__(self, parent: wx.Window, nb_dir: str, entry_id: str, on_image_drop=None):
        super().__init__(parent)
        self.nb_dir = nb_dir
        self.root_id = entry_id

        s = wx.BoxSizer(wx.VERTICAL)
        # Pass the callback through to the view
        self.view = NotebookView(self, nb_dir, entry_id, on_image_drop=on_image_drop)
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
