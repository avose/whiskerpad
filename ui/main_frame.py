import os
import wx

from whiskerpad.core.io_worker import IOWorker
from whiskerpad.core.storage import ensure_notebook
from core.tree import get_root_ids, create_node, load_entry, save_entry
from ui.top_toolbar import TopToolbar
from ui.image_import import import_image_into_entry
from core.tree_utils import add_sibling_after
from ui.note_panel import NotePanel
from ui.icons import wpIcons

class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="WhiskerPad", size=(900, 700))

        self.io = IOWorker()
        self.current_nb_path: str | None = None
        self._current_entry_id: str | None = None
        self._current_note_panel: NotePanel | None = None

        book_bitmap = wpIcons.Get("book")
        icon = wx.Icon()
        icon.CopyFromBitmap(book_bitmap)
        self.SetIcon(icon)

        self._build_menu()
        self.CreateStatusBar()
        self.SetStatusText("Ready.")
        self._build_body()

    # ---------------- FG / BG coloring ----------------

    def _on_fg_color_changed(self, color):
        """Handle foreground color change from toolbar"""
        # This gets called with the actual wx.Colour object
        self.SetStatusText(f"Text color: RGB({color.Red()}, {color.Green()}, {color.Blue()})")

    def _on_bg_color_changed(self, color):
        """Handle background color change from toolbar"""  
        # This gets called with the actual wx.Colour object
        self.SetStatusText(f"Background color: RGB({color.Red()}, {color.Green()}, {color.Blue()})")

    # ---------------- UI scaffolding ----------------

    def _build_menu(self):
        mb = wx.MenuBar()
        
        # File menu
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

        # Top toolbar with proper color picker callbacks
        self._toolbar = TopToolbar(root,
                                  on_open=lambda: self.on_open_notebook(None),
                                  on_add_images=self._on_add_images,
                                  on_fg_color=self._on_fg_color_changed,
                                  on_bg_color=self._on_bg_color_changed)
        v.Add(self._toolbar, 0, wx.EXPAND)

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
        
        if self.info is not None:
            self.info.SetLabel(label)
        
        self.SetTitle(f"WhiskerPad — {result['name']}")

        # Auto-show the first root entry (create one if empty)
        roots = get_root_ids(self.current_nb_path)
        if not roots:
            rid = create_node(self.current_nb_path, parent_id=None, title="Root")
            # Seed the first child under root
            _first_child = create_node(self.current_nb_path, parent_id=rid, title="")
            roots = [rid]

        self._show_entry(roots[0])
        self.SetStatusText("Notebook ready.")

    # ---------------- Embed NotePanel ----------------

    def _show_entry(self, entry_id: str):
        """Clear banner content and embed a NotePanel for the given entry."""
        self._content_sizer.Clear(delete_windows=True)

        # Pass our existing _on_add_images method as the drag & drop callback
        # This is the SAME method the toolbar button calls!
        panel = NotePanel(self._content_panel, self.current_nb_path, entry_id, 
                         on_image_drop=self._on_add_images)

        self._content_sizer.Add(panel, 1, wx.EXPAND | wx.ALL, 0)
        self.info = None # banner label no longer present
        self._content_panel.Layout()

        self._current_entry_id = entry_id
        self._current_note_panel = panel

    # --------------- Image import handler ---------------

    def _on_add_images(self, paths: list[str]) -> None:
        """
        Import selected image files into the current entry's directory and
        create new node(s) after the current selection, each with a single
        {{img "…"}} token as its text.
        """
        if not self.current_nb_path or not self._current_note_panel:
            wx.LogWarning("Open a notebook first.")
            return

        nb_dir = self.current_nb_path
        note = self._current_note_panel
        cur_id = note.current_selection_id() or self._current_entry_id

        if not cur_id:
            # Fallback to the displayed root
            cur_id = note.root_id

        insertion_id = cur_id
        last_new_id = None

        for src in paths:
            try:
                # Create a sibling after insertion_id (Enter-like behavior)
                new_id = add_sibling_after(nb_dir, insertion_id)
                
                if new_id:
                    # Import file into the new entry dir
                    info = import_image_into_entry(nb_dir, new_id, src)
                    token = info["token"]

                    # Set the node text to the token
                    e = load_entry(nb_dir, new_id)
                    e["text"] = [{"content": token}]  # Rich text format
                    e["edit"] = ""  # Clear edit field
                    save_entry(nb_dir, e)

                    insertion_id = new_id
                    last_new_id = new_id
                else:
                    # Fallback: create under current entry as child
                    from tree import create_node
                    new_id = create_node(nb_dir, parent_id=cur_id, title="")
                    info = import_image_into_entry(nb_dir, new_id, src)
                    token = info["token"]
                    e = load_entry(nb_dir, new_id)
                    e["text"] = [{"content": token}]  # Rich text format
                    e["edit"] = ""  # Clear edit field
                    save_entry(nb_dir, e)
                    last_new_id = new_id

            except Exception as ex:
                wx.LogError(f"Failed to add image {src}: {ex}")

        if last_new_id:
            # Refresh view and select the last created node
            note.view.rebuild()
            # Use the selection change method
            for i, row in enumerate(note.view._rows):
                if row.entry_id == last_new_id:
                    note.view._change_selection(i)
                    break
            note.select_entry(last_new_id)

        self.SetStatusText(f"Added {len(paths)} image(s).")
