import os
import wx

from whiskerpad.core.io_worker import IOWorker
from whiskerpad.core.storage import ensure_notebook
from core.tree import get_root_ids, create_node, load_entry, save_entry
from ui.toolbar import Toolbar
from ui.image_import import import_image_into_entry
from core.tree_utils import add_sibling_after
from ui.note_panel import NotePanel
from ui.icons import wpIcons

class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="WhiskerPad", size=(900, 700))

        self.io = IOWorker()
        self.current_notebook_path: str | None = None
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
        # Convert wx.Colour to hex string
        hex_color = f"#{color.Red():02x}{color.Green():02x}{color.Blue():02x}"

        # Apply to current editing state
        if self._current_note_panel and self._current_note_panel.view._edit_state.active:
            edit_state = self._current_note_panel.view._edit_state
            if edit_state.has_selection():
                # Apply to selected text
                if edit_state.apply_color_to_selection(hex_color):
                    # Save the changes
                    rich_data = edit_state.rich_text.to_storage()
                    self._current_note_panel.view.cache.set_edit_rich_text(edit_state.entry_id, rich_data)
                    self._current_note_panel.view.invalidate_cache(edit_state.entry_id)
                    self._current_note_panel.view._invalidate_edit_row_cache()
                    self._current_note_panel.view._refresh_edit_row()
                    self.SetStatusText(f"Applied text color {hex_color} to selection")
                else:
                    self.SetStatusText("No text selected")
            else:
                # Set format for new text
                edit_state.current_color = hex_color
                self.SetStatusText(f"Text color: {hex_color} (applied to new text)")
        else:
            self.SetStatusText(f"Text color set to {hex_color} (start editing to apply)")

        self._restore_view_focus()

    def _on_bg_color_changed(self, color):
        """Handle background color change from toolbar"""
        # Convert wx.Colour to hex string
        hex_color = f"#{color.Red():02x}{color.Green():02x}{color.Blue():02x}"

        # Apply to current editing state
        if self._current_note_panel and self._current_note_panel.view._edit_state.active:
            edit_state = self._current_note_panel.view._edit_state
            if edit_state.has_selection():
                # Apply to selected text
                if edit_state.apply_bg_color_to_selection(hex_color):
                    # Save the changes
                    rich_data = edit_state.rich_text.to_storage()
                    self._current_note_panel.view.cache.set_edit_rich_text(edit_state.entry_id, rich_data)
                    self._current_note_panel.view.invalidate_cache(edit_state.entry_id)
                    self._current_note_panel.view._invalidate_edit_row_cache()
                    self._current_note_panel.view._refresh_edit_row()
                    self.SetStatusText(f"Applied highlight color {hex_color} to selection")
                else:
                    self.SetStatusText("No text selected")
            else:
                # Set format for new text
                edit_state.current_bg = hex_color
                self.SetStatusText(f"Highlight color: {hex_color} (applied to new text)")
        else:
            self.SetStatusText(f"Highlight color set to {hex_color} (start editing to apply)")

        self._restore_view_focus()

    # ---------------- Clipboard interaction ----------------

    def _on_copy(self, evt=None):
        """Handle copy button click."""
        if self._current_note_panel and self._current_note_panel.view._edit_state.active:
            self._current_note_panel.view.copy()

        self._restore_view_focus()

    def _on_paste(self, evt=None):
        """Handle paste button click."""
        if self._current_note_panel and self._current_note_panel.view._edit_state.active:
            self._current_note_panel.view.paste()

        self._restore_view_focus()

    def _on_cut(self, evt=None):
        """Handle cut button click."""
        if self._current_note_panel and self._current_note_panel.view._edit_state.active:
            self._current_note_panel.view.cut()

        self._restore_view_focus()

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
        self._toolbar = Toolbar(
            root,
            on_open=self.on_open_notebook,
            on_add_images=self._on_add_images,
            on_fg_color=self._on_fg_color_changed,
            on_bg_color=self._on_bg_color_changed,
            on_copy=self._on_copy,
            on_paste=self._on_paste,
            on_cut=self._on_cut,
            on_delete=self._on_delete,
        )

        v.Add(self._toolbar, 0, wx.EXPAND)

        # Content area below toolbar
        content = wx.Panel(root)
        cs = wx.BoxSizer(wx.VERTICAL)
        self.info = wx.StaticText(content, label="No notebook open.")
        cs.Add(self.info, 0, wx.ALL, 10)
        content.SetSizer(cs)
        v.Add(content, 1, wx.EXPAND)

        root.SetSizer(v)  # Now all children have 'root' as parent

        # Keep handles for swapping in NotePanel later
        self._content_panel = content
        self._content_sizer = cs

    def _restore_view_focus(self):
        """Restore focus to the current note panel view after toolbar interactions."""
        if self._current_note_panel:
            self._current_note_panel.view.SetFocus()

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

        self.current_notebook_path = result["path"]
        label = f"Notebook: {result['name']}\nPath: {self.current_notebook_path}"

        if self.info is not None:
            self.info.SetLabel(label)

        self.SetTitle(f"WhiskerPad — {result['name']}")

        # Auto-show the first root entry (create one if empty)
        roots = get_root_ids(self.current_notebook_path)
        if not roots:
            rid = create_node(self.current_notebook_path, parent_id=None, title="Root")
            # Seed the first child under root
            _first_child = create_node(self.current_notebook_path, parent_id=rid, title="")
            roots = [rid]

        self._show_entry(roots[0])
        self.SetStatusText("Notebook ready.")

    # ---------------- Embed NotePanel ----------------

    def _show_entry(self, entry_id: str):
        """Clear banner content and embed a NotePanel for the given entry."""
        self._content_sizer.Clear(delete_windows=True)

        # Pass our existing _on_add_images method as the drag & drop callback
        # This is the SAME method the toolbar button calls!
        panel = NotePanel(self._content_panel, self.current_notebook_path, entry_id,
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
        if not self.current_notebook_path or not self._current_note_panel:
            wx.LogWarning("Open a notebook first.")
            return

        nb_dir = self.current_notebook_path
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

# --------------- Row deletion ---------------

    def _on_delete(self, evt=None):
        """Handle delete button click - delete the currently selected row."""
        if not self._current_note_panel:
            self.SetStatusText("No notebook open")
            return

        view = self._current_note_panel.view
        if not view or view._sel < 0 or view._sel >= len(view._rows):
            self.SetStatusText("No row selected")
            return

        # Exit edit mode if active
        if view._edit_state.active:
            view.exit_edit_mode(save=True)

        selected_idx = view._sel
        selected_row = view._rows[selected_idx]
        selected_id = selected_row.entry_id

        try:
            # Delete the entry and its children
            self._delete_entry_and_children(view.notebook_dir, selected_id)

            # Rebuild the view to reflect changes
            view.rebuild()

            # Adjust selection to nearby row
            if view._rows:
                new_sel = min(selected_idx, len(view._rows) - 1)
                view._change_selection(new_sel)
            else:
                view._change_selection(-1)  # No rows left

            self.SetStatusText("Entry deleted")

        except Exception as e:
            self.SetStatusText(f"Delete failed: {e}")

        # Restore focus to the view
        self._restore_view_focus()

    def _delete_entry_and_children(self, notebook_dir: str, entry_id: str):
        """Delete an entry and all its children recursively."""
        from core.tree import load_entry, get_root_ids, set_root_ids, save_entry
        from pathlib import Path
        import shutil

        def _collect_descendants(eid: str, collected: set):
            """Recursively collect all descendant entry IDs."""
            if eid in collected:
                return  # Avoid infinite loops
            collected.add(eid)

            try:
                entry = load_entry(notebook_dir, eid)
                for item in entry.get("items", []):
                    if isinstance(item, dict) and item.get("type") == "child":
                        child_id = item.get("id")
                        if isinstance(child_id, str):
                            _collect_descendants(child_id, collected)
            except:
                pass  # Entry might not exist

        # Collect all entries to delete (entry + all descendants)
        to_delete = set()
        _collect_descendants(entry_id, to_delete)

        # Remove from parent's items or root_ids
        try:
            entry = load_entry(notebook_dir, entry_id)
            parent_id = entry.get("parent_id")

            if parent_id:
                # Remove from parent's items list
                parent = load_entry(notebook_dir, parent_id)
                items = parent.get("items", [])
                parent["items"] = [
                    item for item in items 
                    if not (isinstance(item, dict) and 
                           item.get("type") == "child" and 
                           item.get("id") == entry_id)
                ]
                save_entry(notebook_dir, parent)
            else:
                # Remove from root_ids
                root_ids = get_root_ids(notebook_dir)
                if entry_id in root_ids:
                    root_ids.remove(entry_id)
                    set_root_ids(notebook_dir, root_ids)
        except Exception as e:
            print(f"Warning: Could not update parent: {e}")

        # Delete all entry directories from disk
        from core.tree import entry_dir
        for eid in to_delete:
            try:
                entry_path = entry_dir(notebook_dir, eid)
                if entry_path.exists():
                    shutil.rmtree(entry_path)
            except Exception as e:
                print(f"Warning: Could not delete directory for {eid}: {e}")

        # Invalidate cache for deleted entries
        if hasattr(self._current_note_panel.view, 'cache'):
            self._current_note_panel.view.cache.invalidate_entries(to_delete)
