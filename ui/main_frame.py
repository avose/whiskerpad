import os
import wx
from pathlib import Path
import shutil

from core.log import Log
from core.io_worker import IOWorker
from core.storage import ensure_notebook
from core.tree import (
    get_root_ids,
    set_root_ids,
    create_node,
    load_entry,
    save_entry,
    entry_dir,
    load_notebook,
    save_notebook,
)
from ui.toolbar import Toolbar
from ui.statusbar import StatusBar
from ui.image_import import import_image_into_entry
from ui.note_panel import NotePanel
from ui.icons import wpIcons
from ui.tabs_panel import TabsPanel, TabInfo
from ui.pdf_import import show_pdf_import_dialog, is_pdf_import_available
from ui.search import show_search_dialog
from ui.help import wpAboutFrame, wpLicenseFrame, wpDonateFrame


class MainFrame(wx.Frame):
    LICENSES_ID = wx.NewIdRef()

    def __init__(self, verbosity: int = 0):
        super().__init__(None, title="WhiskerPad", size=(900, 700))
        self.SetMinSize((640, 480))

        self.io = IOWorker()
        self.current_notebook_path: str | None = None
        self._current_entry_id: str | None = None
        self._current_note_panel: NotePanel | None = None

        book_bitmap = wpIcons.Get("book")
        icon = wx.Icon()
        icon.CopyFromBitmap(book_bitmap)
        self.SetIcon(icon)

        self._build_menu()
        Log.set_verbosity(verbosity)
        self.SetStatusBar(StatusBar(self))
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
        if self._current_note_panel:
            self._current_note_panel.view.copy()
        self._restore_view_focus()

    def _on_paste(self, evt=None):
        """Handle paste button click."""
        if self._current_note_panel:
            self._current_note_panel.view.paste()
        self._restore_view_focus()

    def _on_cut(self, evt=None):
        """Handle cut button click."""
        if self._current_note_panel:
            self._current_note_panel.view.cut()
        self._restore_view_focus()

    # ---------------- Image operations ----------------

    def _on_zoom_in(self, evt=None):
        """Handle zoom in button click."""
        if self._current_note_panel:
            self._current_note_panel.view.zoom_image_in()
        self._restore_view_focus()

    def _on_zoom_out(self, evt=None):
        """Handle zoom out button click."""
        if self._current_note_panel:
            self._current_note_panel.view.zoom_image_out()
        self._restore_view_focus()

    def _on_zoom_reset(self, evt=None):
        """Handle zoom reset button click."""
        if self._current_note_panel:
            self._current_note_panel.view.zoom_image_reset()
        self._restore_view_focus()

    def _on_rotate_clockwise(self, evt=None):
        """Handle rotate clockwise button click."""
        if self._current_note_panel:
            self._current_note_panel.view.rotate_image_clockwise()
        self._restore_view_focus()

    def _on_rotate_anticlockwise(self, evt=None):
        """Handle rotate anticlockwise button click."""
        if self._current_note_panel:
            self._current_note_panel.view.rotate_image_anticlockwise()
        self._restore_view_focus()

    def _on_flip_vertical(self, evt=None):
        """Handle flip vertical button click."""
        if self._current_note_panel:
            self._current_note_panel.view.flip_image_vertical()
        self._restore_view_focus()

    def _on_flip_horizontal(self, evt=None):
        """Handle flip horizontal button click."""
        if self._current_note_panel:
            self._current_note_panel.view.flip_image_horizontal()
        self._restore_view_focus()

    # ---------------- UI scaffolding ----------------

    def _build_menu(self):
        mb = wx.MenuBar()

        # File menu
        m_file = wx.Menu()
        m_new = m_file.Append(wx.ID_NEW, "&New Notebook...\tCtrl-N")
        m_open = m_file.Append(wx.ID_OPEN, "&Open Notebook...\tCtrl-O")

        # Add separator and PDF import
        m_file.AppendSeparator()

        # Only add PDF import menu if PyMuPDF is available
        if is_pdf_import_available():
            # Create MenuItem object explicitly instead of using Append()
            m_import_pdf = wx.MenuItem(m_file, wx.ID_ANY, "Import &PDF...\tCtrl-Shift-P")

            # Set the bitmap BEFORE appending to menu
            pdf_icon = wpIcons.Get("page_white_acrobat")
            if pdf_icon:
                m_import_pdf.SetBitmap(pdf_icon)

            # Now append the MenuItem object to the menu
            m_file.Append(m_import_pdf)

            # Bind the event handler
            self.Bind(wx.EVT_MENU, self.on_import_pdf, m_import_pdf)

        m_file.AppendSeparator()
        m_quit = m_file.Append(wx.ID_EXIT, "E&xit")
        self.Bind(wx.EVT_MENU, self.on_new_notebook, m_new)
        self.Bind(wx.EVT_MENU, self.on_open_notebook, m_open)
        self.Bind(wx.EVT_MENU, lambda evt: self.Close(), m_quit)
        mb.Append(m_file, "&File")

        # Help menu
        m_help = wx.Menu()

        # About menu item.
        mi_info = wx.MenuItem(m_file, wx.ID_ANY, "About WhiskerPad")
        info_icon = wpIcons.Get("information")
        if info_icon:
            mi_info.SetBitmap(info_icon)
        m_help.Append(mi_info)
        self.Bind(wx.EVT_MENU, self.show_about_dialog, mi_info)

        # Licenses menu item.
        mi_licenses = wx.MenuItem(m_file, wx.ID_ANY, "Licenses")
        licenses_icon = wpIcons.Get("script_key")
        if licenses_icon:
            mi_licenses.SetBitmap(licenses_icon)
        m_help.Append(mi_licenses)
        self.Bind(wx.EVT_MENU, self.show_license_dialog, mi_licenses)

        # Donate menu item.
        mi_donate = wx.MenuItem(m_file, wx.ID_ANY, "Donate")
        donate_icon = wpIcons.Get("money_dollar")
        if donate_icon:
            mi_donate.SetBitmap(donate_icon)
        m_help.Append(mi_donate)
        self.Bind(wx.EVT_MENU, self.show_donate_dialog, mi_donate)

        # Set the menu bar.
        mb.Append(m_help, "&Help")
        self.SetMenuBar(mb)

    def _build_body(self):
        root = wx.Panel(self)

        # Main vertical sizer for toolbar + content row
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Top toolbar - spans full width
        self._toolbar = Toolbar(
            root,  # Direct child of root
            on_open=self.on_open_notebook,
            on_add_images=self._on_add_images,
            on_add_tab=self._on_add_tab,
            on_copy=self._on_copy,
            on_paste=self._on_paste,
            on_cut=self._on_cut,
            on_delete=self._on_delete,
            on_zoom_in=self._on_zoom_in,
            on_zoom_out=self._on_zoom_out,
            on_zoom_reset=self._on_zoom_reset,
            on_rotate_clockwise=self._on_rotate_clockwise,
            on_rotate_anticlockwise=self._on_rotate_anticlockwise,
            on_flip_vertical=self._on_flip_vertical,
            on_flip_horizontal=self._on_flip_horizontal,
            on_fg_color=self._on_fg_color_changed,
            on_bg_color=self._on_bg_color_changed,
            on_search=self._on_search,
        )
        main_sizer.Add(self._toolbar, 0, wx.EXPAND)

        # Horizontal sizer for content area + tabs
        content_row_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Left side - content area
        content = wx.Panel(root)  # Direct child of root
        cs = wx.BoxSizer(wx.VERTICAL)
        self.info = wx.StaticText(content, label="No notebook open.")
        cs.Add(self.info, 0, wx.ALL, 10)
        content.SetSizer(cs)
        content_row_sizer.Add(content, 1, wx.EXPAND)

        # Right side - tabs panel
        self.tabs_panel = TabsPanel(
            root, 
            on_tab_click=self._on_tab_selected,
            on_tab_changed=self._save_tabs_to_notebook,
        )
        content_row_sizer.Add(self.tabs_panel, 0, wx.EXPAND)

        # Add content row to main vertical sizer
        main_sizer.Add(content_row_sizer, 1, wx.EXPAND)

        # Set main sizer on root
        root.SetSizer(main_sizer)

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

        self._show_notebook(roots[0])

        # Force focus to the view, especially important when notebook is empty
        if self._current_note_panel:
            wx.CallAfter(self._current_note_panel.view.SetFocus)

        # Restore tabs.
        wx.CallAfter(self._load_tabs_from_notebook)

        self.SetStatusText("Notebook ready.")

    # ---------------- Import PDF ----------------

    def on_import_pdf(self, event):
        """Handle File -> Import PDF menu selection."""
        if not self._current_note_panel:
            self.SetStatusText("Open a notebook first")
            return

        if not is_pdf_import_available():
            wx.MessageBox(
                "PDF import requires PyMuPDF library.\n\nInstall with: pip install PyMuPDF",
                "PDF Import Not Available",
                wx.OK | wx.ICON_INFORMATION
            )
            return

        self.SetStatusText("Opening PDF import dialog...")

        try:
            # Show the PDF import dialog
            result_message = show_pdf_import_dialog(self, self._current_note_panel.view)

            if result_message:
                # Import was successful - force complete view refresh
                self._current_note_panel.view.invalidate_cache()  # Clear all caches
                self._current_note_panel.view.rebuild()           # Rebuild tree structure
                self.SetStatusText(result_message)
                self._restore_view_focus()
            else:
                # Import was cancelled
                self.SetStatusText("PDF import cancelled")

        except Exception as e:
            error_msg = f"PDF import failed: {str(e)}"
            self.SetStatusText(error_msg)
            wx.MessageBox(error_msg, "PDF Import Error", wx.OK | wx.ICON_ERROR)

    # ---------------- Tabs ----------------

    def _on_tab_selected(self, entry_id: str, notebook_path: str):
        """Handle tab selection - ensure ancestors are expanded, then navigate."""
        if not self._current_note_panel:
            self.SetStatusText("No notebook open")
            return

        if self.current_notebook_path != notebook_path:
            self.SetStatusText("Tab is from a different notebook")
            return

        view = self._current_note_panel.view

        # Use the robust navigation function
        success = view.navigate_to_entry(entry_id)

        if success:
            self.SetStatusText("Navigated to bookmarked entry")
            Log.debug(f"Tab jump to {entry_id=}.", 1)
        else:
            self.SetStatusText("Could not find bookmarked entry (may have been deleted)")
            Log.debug(f"Tab target DNE: {entry_id=}.", 0)

        # Restore focus to the view
        self._restore_view_focus()

    def _on_add_tab(self, evt=None):
        """Create a new tab from the currently selected row."""
        if not self._current_note_panel:
            self.SetStatusText("No notebook open")
            return

        view = self._current_note_panel.view

        if not (0 <= view._sel < len(view._rows)):
            self.SetStatusText("No row selected - select a row to create a tab")
            return

        selected_row = view._rows[view._sel]
        entry_id = selected_row.entry_id
        Log.debug(f"_on_add_tab(), {selected_row=}", 1)
        
        try:
            # Create TabInfo object with default color
            tab_info = TabInfo(entry_id, "New Tab", self.current_notebook_path)
            self.tabs_panel.tabs.append(tab_info)

            # Open rename dialog immediately
            new_tab_idx = len(self.tabs_panel.tabs) - 1
            new_name = self.tabs_panel._show_rename_dialog("New Tab")

            if new_name:
                self.tabs_panel.tabs[new_tab_idx].display_text = new_name
                self.tabs_panel.Refresh()
                self.SetStatusText(f"Created tab: {new_name}")

                # Save the new tab
                self._save_tabs_to_notebook()
            else:
                # User cancelled, remove the tab
                self.tabs_panel.tabs.pop()
                self.tabs_panel.Refresh()
                self.SetStatusText("Tab creation cancelled")

            if view._bookmark_source_id:
                view.clear_bookmark_source()

        except Exception as e:
            error_msg = f"Failed to create tab: {e}"
            self.SetStatusText(error_msg)

        self._restore_view_focus()

    def _save_tabs_to_notebook(self):
        """Save current tabs to notebook metadata with colors."""
        if not self.current_notebook_path or not self.tabs_panel:
            return
        Log.debug(f"_save_tabs_to_notebook()", 1)

        # Load current notebook metadata
        metadata = load_notebook(self.current_notebook_path)

        # Convert tabs to saveable format with colors
        tabs_data = []
        for tab in self.tabs_panel.tabs:
            tabs_data.append(tab.to_dict())

        # Save to metadata
        metadata["tabs"] = tabs_data
        save_notebook(self.current_notebook_path, metadata)

    def _load_tabs_from_notebook(self):
        """Load tabs from notebook metadata with colors."""
        if not self.current_notebook_path or not self.tabs_panel:
            return
        Log.debug(f"_load_tabs_from_notebook()", 1)

        # Load notebook metadata
        metadata = load_notebook(self.current_notebook_path)
        tabs_data = metadata.get("tabs", [])

        # Clear existing tabs and load saved ones
        self.tabs_panel.clear_tabs()

        for tab_data in tabs_data:
            # Handle both old format (without color) and new format (with color)
            if isinstance(tab_data, dict) and "color" in tab_data:
                # New format with color
                tab_info = TabInfo.from_dict(tab_data)
                self.tabs_panel.tabs.append(tab_info)
            else:
                # Old format or simple data - create with default color
                if isinstance(tab_data, dict):
                    entry_id = tab_data["entry_id"]
                    display_text = tab_data["display_text"] 
                    notebook_path = tab_data["notebook_path"]
                else:
                    # Very old format, skip
                    continue

                tab_info = TabInfo(entry_id, display_text, notebook_path)
                self.tabs_panel.tabs.append(tab_info)

        self.tabs_panel.Refresh()

    # ---------------- Embed NotePanel ----------------

    def _show_notebook(self, root_entry_id: str):
        """Display a notebook by creating a new NotePanel for its root entry."""
        # CRITICAL: Clean up the old view before destroying it
        if self._current_note_panel and hasattr(self._current_note_panel, 'view'):
            self._current_note_panel.view.cleanup()

        self._content_sizer.Clear(delete_windows=True)

        panel = NotePanel(self._content_panel, self.current_notebook_path, root_entry_id,
                         on_image_drop=self._on_add_images)

        self._content_sizer.Add(panel, 1, wx.EXPAND | wx.ALL, 0)
        self.info = None
        self._content_panel.Layout()

        self._current_entry_id = root_entry_id
        self._current_note_panel = panel

    # --------------- Image import handler ---------------

    def _on_add_images(self, paths: list[str]) -> None:
        """Import image files and create new entries."""
        if not self.current_notebook_path or not self._current_note_panel:
            wx.LogWarning("Open a notebook first.")
            return

        notebook_dir = self.current_notebook_path
        note = self._current_note_panel
        cur_id = note.current_selection_id()

        # Check if we're in an empty notebook (cur_id is root)
        root_ids = get_root_ids(notebook_dir)
        is_empty_notebook = (cur_id in root_ids) if root_ids else False

        if not cur_id:
            # No selection - add as children of the hidden root
            if not root_ids:
                wx.LogWarning("No root found.")
                return
            cur_id = root_ids[0]  # Use the hidden root as parent
            is_empty_notebook = True

        insertion_id = cur_id
        last_new_id = None

        for src in paths:
            if is_empty_notebook:
                # Use FlatTree instead of create_node
                new_id = self._current_note_panel.view.flat_tree.create_child_under(cur_id, title="")
            else:
                # Use FlatTree instead of add_sibling_after
                new_id = self._current_note_panel.view.flat_tree.create_sibling_after(insertion_id)

            if new_id:
                # Import file into the new entry dir
                info = import_image_into_entry(notebook_dir, new_id, src)
                token = info["token"]

                # Set the node text to the image token
                entry = load_entry(notebook_dir, new_id)
                entry["text"] = [{"content": token}]
                entry["edit"] = ""
                save_entry(notebook_dir, entry)

                if not is_empty_notebook:
                    insertion_id = new_id  # Only update insertion_id for sibling mode
                last_new_id = new_id

        if last_new_id:
            # Refresh view and select the last created node
            note.view.rebuild()

            # Ensure we have rows after rebuild
            if note.view._rows:
                # Find and select the new entry
                for i, row in enumerate(note.view._rows):
                    if row.entry_id == last_new_id:
                        note.view._change_selection(i)
                        break
                note.select_entry(last_new_id)
            else:
                # If still no rows, something went wrong
                wx.LogWarning(f"No rows after adding image, last_new_id: {last_new_id}")

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

        # Use FlatTree for deletion
        success = view.flat_tree.delete_entry(selected_id)

        if success:
            # Adjust selection to nearby row
            if view._rows:
                new_sel = min(selected_idx, len(view._rows) - 1)
                view._change_selection(new_sel)
            else:
                view._change_selection(-1)  # No rows left

            self.SetStatusText("Entry deleted")
        else:
            self.SetStatusText("Failed to delete entry")

        # Restore focus to the view
        self._restore_view_focus()

    # --------------- Row deletion ---------------

    def _on_search(self, query):
        """Handle search from toolbar."""
        if not self.current_notebook_path or not self._current_note_panel:
            wx.MessageBox("Open a notebook first", "Search", wx.OK | wx.ICON_INFORMATION)
            return

        # Show non-modal search dialog
        show_search_dialog(self, self.current_notebook_path, self._current_note_panel.view, query)
    
    # --------------- Help actions ---------------

    def show_about_dialog(self, event=None):
        """Show the About dialog."""
        if not hasattr(self, 'about_frame') or not self.about_frame:
            self.about_frame = wpAboutFrame(self)
        else:
            self.about_frame.Raise()

    def show_license_dialog(self, event=None):
        """Show the License dialog.""" 
        if not hasattr(self, 'license_frame') or not self.license_frame:
            self.license_frame = wpLicenseFrame(self)
        else:
            self.license_frame.Raise()

    def show_donate_dialog(self, event=None):
        """Show the Donate dialog.""" 
        if not hasattr(self, 'donate_frame') or not self.donate_frame:
            self.donate_frame = wpDonateFrame(self)
        else:
            self.donate_frame.Raise()

    # --------------- Close ---------------

    def Close(self, force=False):
        """Clean up before closing the application."""
        # Save tabs before closing
        self._save_tabs_to_notebook()

        if self._current_note_panel and hasattr(self._current_note_panel, 'view'):
            self._current_note_panel.view.cleanup()

        return super().Close(force)
