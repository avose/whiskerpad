import os
import wx

from whiskerpad.io_worker import IOWorker
from whiskerpad.storage import ensure_notebook
from tree import get_root_ids, create_node, load_entry, save_entry
from ui.top_toolbar import TopToolbar
from ui.note_panel import NotePanel


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="WhiskerPad", size=(900, 700))
        self.io = IOWorker()
        self.current_nb_path = None
        self._current_entry_id = None
        self._current_note_panel = None

        self._build_menu()
        self.CreateStatusBar()
        self.SetStatusText("Ready.")
        self._build_body()

    # ---------------- UI scaffolding ----------------

    def _build_menu(self):
        mb = wx.MenuBar()

        # File
        m_file = wx.Menu()
        m_new = m_file.Append(wx.ID_NEW, "&New Notebook...\tCtrl-N")
        m_open = m_file.Append(wx.ID_OPEN, "&Open Notebook...\tCtrl-O")
        m_file.AppendSeparator()
        m_quit = m_file.Append(wx.ID_EXIT, "E&xit")
        mb.Append(m_file, "&File")

        self.SetMenuBar(mb)

        # Bindings
        self.Bind(wx.EVT_MENU, self.on_new_notebook, m_new)
        self.Bind(wx.EVT_MENU, self.on_open_notebook, m_open)
        self.Bind(wx.EVT_MENU, lambda evt: self.Close(), m_quit)

    def _build_body(self):
        root = wx.Panel(self)
        v = wx.BoxSizer(wx.VERTICAL)

        # Top toolbar (always visible)
        tb = TopToolbar(root,
                        on_open=lambda: self.on_open_notebook(None),
                        on_add_child=self.on_add_child)
        v.Add(tb, 0, wx.EXPAND)

        # Content area below toolbar
        content = wx.Panel(root)
        cs = wx.BoxSizer(wx.VERTICAL)
        self.info = wx.StaticText(content, label="No notebook open.")
        cs.Add(self.info, 0, wx.ALL, 10)
        content.SetSizer(cs)

        v.Add(content, 1, wx.EXPAND)
        root.SetSizer(v)

        # Keep handles for swapping in NotePanel later
        self._content_panel = content
        self._content_sizer = cs

    # ---------------- Notebook create/open ----------------

    def on_new_notebook(self, _evt):
        with wx.DirDialog(self, "Choose parent directory (a subfolder will be created)") as dd:
            if dd.ShowModal() != wx.ID_OK:
                return
            parent = dd.GetPath()

        with wx.TextEntryDialog(self, "Notebook name:", "WhiskerPad") as te:
            if te.ShowModal() != wx.ID_OK:
                return
            name = te.GetValue().strip()
        if not name:
            wx.MessageBox("Name cannot be empty.", "Error", wx.ICON_ERROR)
            return

        target = os.path.join(parent, name)
        self.SetStatusText(f"Creating notebook at {target}...")
        self.io.submit(ensure_notebook, target, name=name, callback=self._on_nb_ready)

    def on_open_notebook(self, _evt):
        with wx.DirDialog(self, "Open existing notebook (folder with notebook.json)") as dd:
            if dd.ShowModal() != wx.ID_OK:
                return
            path = dd.GetPath()
        self.SetStatusText(f"Opening {path}...")
        # Reuse ensure_notebook for validation/load
        self.io.submit(ensure_notebook, path, name=None, callback=self._on_nb_ready)

    def _on_nb_ready(self, result, error):
        if error:
            err, tb = error
            msg = f"{err}\n\n{tb}"
            wx.MessageBox(msg, "Create/Open Notebook Failed", wx.ICON_ERROR)
            self.SetStatusText("Ready.")
            return

        self.current_nb_path = result["path"]
        label = f"Notebook: {result['name']}\nPath: {self.current_nb_path}"

        info = getattr(self, "info", None)
        if info is not None:
            info.SetLabel(label)
        else:
            self.SetTitle(f"WhiskerPad — {result['name']}")

        # Auto-show the first root entry (create one if empty)
        roots = get_root_ids(self.current_nb_path)
        if not roots:
            rid = create_node(self.current_nb_path, parent_id=None, title="Root")
            roots = [rid]
        self._show_entry(roots[0])

        self.SetStatusText("Notebook ready.")

    # ---------------- Tools actions ----------------

    def on_view_note(self, _evt):
        """Open the first root; mostly redundant now that we auto-open on _on_nb_ready."""
        if not self.current_nb_path:
            wx.MessageBox("Open or create a notebook first.", "Info")
            return
        roots = get_root_ids(self.current_nb_path)
        if not roots:
            rid = create_node(self.current_nb_path, parent_id=None, title="Root")
            roots = [rid]
        self._show_entry(roots[0])
        self.SetStatusText(f"Viewing root: {roots[0]}")

    # ---------------- Embed NotePanel ----------------

    def _show_entry(self, entry_id: str):
        """Clear banner content and embed a NotePanel for the given entry."""
        self._content_sizer.Clear(delete_windows=True)
        panel = NotePanel(self._content_panel, self.current_nb_path, entry_id)
        self._content_sizer.Add(panel, 1, wx.EXPAND | wx.ALL, 0)
        self.info = None  # banner label no longer present
        self._content_panel.Layout()
        self._current_entry_id = entry_id
        self._current_note_panel = panel

    # ---------------- Toolbar actions ----------------

    def on_add_child(self):
        # Require an open notebook and an active note panel
        if not self.current_nb_path or not getattr(self, "_current_note_panel", None):
            wx.Bell()
            self.SetStatusText("No entry selected to add a child.")
            return

        # Parent = currently selected node (fallback to the root of this panel)
        parent_id = (self._current_note_panel.current_selection_id()
                     or getattr(self._current_note_panel, "root_id", None))
        if not parent_id:
            wx.Bell()
            self.SetStatusText("No valid parent entry.")
            return

                # Ensure parent is expanded, then create the child
        parent = load_entry(self.current_nb_path, parent_id)
        parent["collapsed"] = False
        save_entry(self.current_nb_path, parent)

        child_id = create_node(self.current_nb_path, parent_id=parent_id, title="New Entry")

        # Refresh the panel view and auto-select the new child
        self._current_note_panel.reload()
        self._current_note_panel.select_entry(child_id)


        # Begin inline edit of the new child node text
        if hasattr(self._current_note_panel, "edit_entry"):
            self._current_note_panel.edit_entry(child_id)


        self.SetStatusText(f"Added child {child_id} under {parent_id}")
