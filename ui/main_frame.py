'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''
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
from core.version_manager import VersionManager
from ui.toolbar import Toolbar
from ui.file_dialogs import choose_image_files
from ui.statusbar import StatusBar
from ui.image_import import import_image_into_entry
from ui.note_panel import NotePanel
from ui.icons import wpIcons
from ui.tabs_panel import TabsPanel, TabInfo
from ui.pdf_import import show_pdf_import_dialog, is_pdf_import_available
from ui.search import show_search_dialog
from ui.help import wpAboutFrame, wpDonateFrame
from ui.licenses import wpLicenseFrame
from ui.history_browser import HistoryBrowserDialog


class MainFrame(wx.Frame):
    """Main application frame for WhiskerPad application. """
    def __init__(self, verbosity: int = 0):
        super().__init__(None, title="WhiskerPad", size=(900, 700))
        self.SetMinSize((700, 500))

        self.io = IOWorker()
        self.version_manager = VersionManager(self.io)
        self._history_browser = None
        self._read_only = False
        self._auto_commit_timer = wx.Timer(self)
        self._auto_commit_timer.Start(60000)  # 60 seconds
        self.Bind(wx.EVT_TIMER, self._on_auto_commit_timer, self._auto_commit_timer)
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
        self.Bind(wx.EVT_CLOSE, self.Close)

        self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))

    # ---------------- FG / BG coloring ----------------

    def on_action_clear_style(self, event = None):
        """Clear text formatting from selection and for new text"""
        if self._current_note_panel and self._current_note_panel.view._edit_state.active:
            edit_state = self._current_note_panel.view._edit_state
            if edit_state.has_selection():
                # Apply to selected text
                if edit_state.clear_formatting_on_selection():
                    # Save the changes
                    rich_data = edit_state.rich_text.to_storage()
                    self._current_note_panel.view.cache.set_edit_rich_text(edit_state.entry_id, rich_data)
                    self._current_note_panel.view.invalidate_cache(edit_state.entry_id)
                    self._current_note_panel.view._invalidate_edit_row_cache()
                    self._current_note_panel.view._refresh_edit_row()
                    self.SetStatusText(f"Cleared text style from selection")
                else:
                    self.SetStatusText("No text selected")
            else:
                # Set format for new text
                formatting = {"color": None, "bg": None, "bold": False, "italic": False}
                edit_state.set_format_state(**formatting)
                self.SetStatusText(f"Text style cleared for new text")

        self._restore_view_focus()

    def on_action_fg_color_changed(self, color):
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

    def on_action_bg_color_changed(self, color):
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

    def on_action_copy(self, evt=None):
        """Handle copy button click."""
        if self._current_note_panel:
            self._current_note_panel.view.copy()
        self._restore_view_focus()

    def on_action_paste(self, evt=None):
        """Handle paste button click."""
        if self._current_note_panel:
            self._current_note_panel.view.paste()
        self._restore_view_focus()

    def on_action_cut(self, evt=None):
        """Handle cut button click."""
        if self._current_note_panel:
            self._current_note_panel.view.cut()
        self._restore_view_focus()

    # ---------------- Image operations ----------------

    def on_action_zoom_in(self, evt=None):
        """Handle zoom in button click."""
        if self._current_note_panel:
            self._current_note_panel.view.zoom_image_in()
        self._restore_view_focus()

    def on_action_zoom_out(self, evt=None):
        """Handle zoom out button click."""
        if self._current_note_panel:
            self._current_note_panel.view.zoom_image_out()
        self._restore_view_focus()

    def on_action_zoom_reset(self, evt=None):
        """Handle zoom reset button click."""
        if self._current_note_panel:
            self._current_note_panel.view.zoom_image_reset()
        self._restore_view_focus()

    def on_action_rotate_clockwise(self, evt=None):
        """Handle rotate clockwise button click."""
        if self._current_note_panel:
            self._current_note_panel.view.rotate_image_clockwise()
        self._restore_view_focus()

    def on_action_rotate_anticlockwise(self, evt=None):
        """Handle rotate anticlockwise button click."""
        if self._current_note_panel:
            self._current_note_panel.view.rotate_image_anticlockwise()
        self._restore_view_focus()

    def on_action_flip_vertical(self, evt=None):
        """Handle flip vertical button click."""
        if self._current_note_panel:
            self._current_note_panel.view.flip_image_vertical()
        self._restore_view_focus()

    def on_action_flip_horizontal(self, evt=None):
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
        self.new_notebook_menu_item = m_new
        m_open = m_file.Append(wx.ID_OPEN, "&Open Notebook...\tCtrl-O")
        self.open_notebook_menu_item = m_open

        # History
        m_file.AppendSeparator()
        mi_history = wx.MenuItem(m_file, wx.ID_ANY, "History &Browser...\tCtrl-B")
        history_icon = wpIcons.Get("hourglass")
        if history_icon:
            mi_history.SetBitmap(history_icon)
        m_file.Append(mi_history)
        self.Bind(wx.EVT_MENU, self._on_history_browser, mi_history)
        mi_checkpoint = wx.MenuItem(m_file, wx.ID_ANY, "&Save Checkpoint...\tCtrl-S")
        checkpoint_icon = wpIcons.Get("disk")
        if checkpoint_icon:
            mi_checkpoint.SetBitmap(checkpoint_icon)
        m_file.Append(mi_checkpoint)
        self.Bind(wx.EVT_MENU, self._on_create_checkpoint, mi_checkpoint)
        self.checkpoint_menu_item = mi_checkpoint

        # Add separator and PDF import
        m_file.AppendSeparator()

        # Only add PDF import menu if PyMuPDF is available
        if is_pdf_import_available():
            # Create MenuItem object explicitly instead of using Append()
            m_import_pdf = wx.MenuItem(m_file, wx.ID_ANY, "Import &PDF")
            # Set the bitmap BEFORE appending to menu
            pdf_icon = wpIcons.Get("page_white_acrobat")
            if pdf_icon:
                m_import_pdf.SetBitmap(pdf_icon)
            # Now append the MenuItem object to the menu
            m_file.Append(m_import_pdf)
            # Bind the event handler
            self.Bind(wx.EVT_MENU, self.on_import_pdf, m_import_pdf)
            self.import_pdf_menu_item = m_import_pdf
        else:
            self.import_pdf_menu_item = None

        m_file.AppendSeparator()
        m_quit = m_file.Append(wx.ID_EXIT, "E&xit")
        self.Bind(wx.EVT_MENU, self.on_action_new, m_new)
        self.Bind(wx.EVT_MENU, self.on_action_open, m_open)
        self.Bind(wx.EVT_MENU, self.on_quit, m_quit)
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
        self._toolbar = Toolbar(root)
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

    def on_action_new(self, evt=None):
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

    def on_action_open(self, evt=None):
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

        # Initialize Git repository for this notebook
        try:
            self.version_manager.ensure_repository(self.current_notebook_path)
        except Exception as e:
            wx.MessageBox(
                f"Failed to initialize version control:\n\n{str(e)}\n\n"
                f"The notebook will work normally but history features won't be available.",
                "Version Control Warning",
                wx.OK | wx.ICON_WARNING
            )

        label = f"Notebook: {result['name']}\nPath: {self.current_notebook_path}"

        if self.info is not None:
            self.info.SetLabel(label)

        self.SetTitle(f"WhiskerPad — {result['name']}")

        # Auto-show the first root entry (create one if empty)
        roots = get_root_ids(self.current_notebook_path)
        if not roots:
            root_content = [{"content": "Root"}]
            rid = create_node(self.current_notebook_path, parent_id=None, content=root_content)
            # Seed the first child under root
            _first_child = create_node(self.current_notebook_path, parent_id=rid)
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

    def _on_tab_selected(self, entry_id: str):  # Remove notebook_path parameter
        """Handle tab selection - ensure ancestors are expanded, then navigate."""
        if not self._current_note_panel:
            self.SetStatusText("No notebook open")
            return

        view = self._current_note_panel.view
        success = view.navigate_to_entry(entry_id)
        if success:
            self.SetStatusText("Navigated to bookmarked entry")
            Log.debug(f"Tab jump to {entry_id=}.", 1)
        else:
            self.SetStatusText("Could not find bookmarked entry (may have been deleted)")
            Log.debug(f"Tab target DNE: {entry_id=}.", 0)

        self._restore_view_focus()

    def on_action_add_tab(self, evt=None):
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

        try:
            # Create TabInfo without notebook_path
            tab_info = TabInfo(entry_id, "New Tab")
            self.tabs_panel.tabs.append(tab_info)

            # Open rename dialog immediately
            new_tab_idx = len(self.tabs_panel.tabs) - 1
            new_name = self.tabs_panel._show_rename_dialog("New Tab")

            if new_name:
                self.tabs_panel.tabs[new_tab_idx].display_text = new_name
                self.tabs_panel.Refresh()
                self.SetStatusText(f"Created tab: {new_name}")
                self._save_tabs_to_notebook()
            else:
                self.tabs_panel.tabs.pop()
                self.tabs_panel.Refresh()
                self.SetStatusText("Tab creation cancelled")

            if view._bookmark_source_id:
                view.clear_bookmark_source()

        except Exception as e:
            self.SetStatusText(f"Failed to create tab: {e}")

        self._restore_view_focus()

    def _save_tabs_to_notebook(self):
        """Save current tabs to notebook metadata (new format only)."""
        Log.debug(f"_save_tabs_to_notebook()", 1)
        metadata = load_notebook(self.current_notebook_path)

        # Save tabs
        tabs_data = []
        for tab in self.tabs_panel.tabs:
            tabs_data.append(tab.to_dict())

        metadata["tabs"] = tabs_data
        save_notebook(self.current_notebook_path, metadata)

    def _load_tabs_from_notebook(self):
        """Load tabs from notebook metadata (new format only)."""
        Log.debug(f"_load_tabs_from_notebook()", 1)
        metadata = load_notebook(self.current_notebook_path)
        tabs_data = metadata.get("tabs", [])

        self.tabs_panel.clear_tabs()
        for tab_data in tabs_data:
            tab_info = TabInfo.from_dict(tab_data)
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
                         on_image_drop=self.on_action_add_images)

        self._content_sizer.Add(panel, 1, wx.EXPAND | wx.ALL, 0)
        self.info = None
        self._content_panel.Layout()

        self._current_entry_id = root_entry_id
        self._current_note_panel = panel

    # --------------- Add row ---------------

    def on_action_show_all(self, event):
        """Handle Show All toolbar button - expand current node and all its descendants"""
        if not self._current_note_panel:
            return

        view = self._current_note_panel.view

        # If we have a current selection, expand it and all its descendants
        if view._rows and 0 <= view._sel < len(view._rows):
            current_entry_id = view._rows[view._sel].entry_id
            expanded_any = view.flat_tree.expand_descendants(current_entry_id)

            if expanded_any:
                self.SetStatusText("Expanded selection and all descendants")
            else:
                self.SetStatusText("Selection and descendants already expanded")
        else:
            # No selection - expand all top-level entries and their descendants
            expanded_any = False
            for row in view._rows:
                if row.level == 0:  # Top-level entries
                    if view.flat_tree.expand_descendants(row.entry_id):
                        expanded_any = True

            if expanded_any:
                self.SetStatusText("Expanded all entries")
            else:
                self.SetStatusText("All entries already expanded")

        self._restore_view_focus()

    # --------------- Add row ---------------

    def on_action_add_row(self, event=None):
        """Handle Add Row toolbar button - shared by Enter key"""
        if not self._current_note_panel:
            return False

        view = self._current_note_panel.view

        # Handle both edit mode and navigation mode
        if view._edit_state.active:
            # Exit edit mode, save current content
            current_entry_id = view._edit_state.entry_id
            view.exit_edit_mode(save=True)
            new_id = view.flat_tree.create_sibling_after(current_entry_id)
        else:
            # Navigation mode - handle empty notebook case
            if len(view._rows) == 0:
                from core.tree import get_root_ids, create_node
                root_ids = get_root_ids(view.notebook_dir)
                if root_ids:
                    new_id = create_node(view.notebook_dir, parent_id=root_ids[0])
                    if new_id:
                        view.rebuild()
                        if view._rows:
                            view.enter_edit_mode(0, 0)
                        return True
                return False

            if not (0 <= view._sel < len(view._rows)):
                return False
            cur_id = view._rows[view._sel].entry_id
            new_id = view.flat_tree.create_sibling_after(cur_id)

        if new_id:
            # Find and start editing the new node
            for i, row in enumerate(view._rows):
                if row.entry_id == new_id:
                    view.enter_edit_mode(i, 0)
                    from ui.scroll import soft_ensure_visible
                    soft_ensure_visible(view, i)
                    break
            self._restore_view_focus()
            return True

        self._restore_view_focus()
        return False

    # --------------- Image import handler ---------------

    def on_action_add_images(self, evt=None):
        """Handle add images action - open file dialog and import images"""
        from ui.file_dialogs import choose_image_files

        paths = choose_image_files(self, multiple=True)
        if not paths:
            return

        # Now call your existing logic with the paths
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
            cur_id = root_ids[0] # Use the hidden root as parent
            is_empty_notebook = True

        insertion_id = cur_id
        last_new_id = None

        for src in paths:
            if is_empty_notebook:
                new_id = self._current_note_panel.view.flat_tree.create_child_under(cur_id)
            else:
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
                    insertion_id = new_id # Only update insertion_id for sibling mode
                last_new_id = new_id

        if last_new_id:
            # Refresh view and select the last created node
            note.view.rebuild()

            if last_new_id:
                # Refresh view and select the last created node
                note.view.rebuild()

                # Select the newly created entry (handles finding the row automatically)
                view = self._current_note_panel.view
                if view._edit_state.active:
                    view.exit_edit_mode(save=True)
                if note.select_entry(last_new_id):
                    self.SetStatusText(f"Added {len(paths)} image(s).")
                else:
                    wx.LogWarning(f"Could not select newly created entry: {last_new_id}")
                    self.SetStatusText(f"Added {len(paths)} image(s), but selection failed.")

        self.SetStatusText(f"Added {len(paths)} image(s).")

    # --------------- Row deletion ---------------

    def on_action_delete(self, evt=None):
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

    # --------------- Search deletion ---------------

    def on_action_search(self, query):
        """Handle search from toolbar."""
        if not self.current_notebook_path or not self._current_note_panel:
            wx.MessageBox("Open a notebook first", "Search", wx.OK | wx.ICON_INFORMATION)
            return

        # Show non-modal search dialog
        show_search_dialog(self, self.current_notebook_path, self._current_note_panel.view, query)

    # --------------- Indent / Outdent ---------------

    def on_action_indent(self, event=None):
        """Handle Indent Row toolbar button - shared by Tab key"""
        if not self._current_note_panel:
            return False

        view = self._current_note_panel.view

        if view._edit_state.active:
            # Edit mode - save content, indent, restore edit state
            current_entry_id = view._edit_state.entry_id
            current_cursor_pos = view._edit_state.cursor_pos

            # Save current content
            if view._edit_state.rich_text:
                rich_data = view._edit_state.rich_text.to_storage()
                view.cache.set_edit_rich_text(current_entry_id, rich_data)
                from core.tree import commit_entry_edit
                commit_entry_edit(view.notebook_dir, current_entry_id, rich_data)

            success = view.flat_tree.indent_entry(current_entry_id)

            if success:
                # Re-enter edit mode at same cursor position
                for i, row in enumerate(view._rows):
                    if row.entry_id == current_entry_id:
                        view.enter_edit_mode(i, current_cursor_pos)
                        view.select_entry(current_entry_id, ensure_visible=True)
                        break
        else:
            # Navigation mode
            if not (0 <= view._sel < len(view._rows)):
                return False
            cur_id = view._rows[view._sel].entry_id
            success = view.flat_tree.indent_entry(cur_id)

            if success:
                view.select_entry(cur_id, ensure_visible=False)

        self._restore_view_focus()
        return success if 'success' in locals() else False

    def on_action_outdent(self, event=None):
        """Handle Outdent Row toolbar button - shared by Shift+Tab key"""
        if not self._current_note_panel:
            return False

        view = self._current_note_panel.view

        if view._edit_state.active:
            # Edit mode - save content, outdent, restore edit state
            current_entry_id = view._edit_state.entry_id
            current_cursor_pos = view._edit_state.cursor_pos

            # Save current content
            if view._edit_state.rich_text:
                rich_data = view._edit_state.rich_text.to_storage()
                view.cache.set_edit_rich_text(current_entry_id, rich_data)
                from core.tree import commit_entry_edit
                commit_entry_edit(view.notebook_dir, current_entry_id, rich_data)

            success = view.flat_tree.outdent_entry(current_entry_id)

            if success:
                # Re-enter edit mode at same cursor position
                for i, row in enumerate(view._rows):
                    if row.entry_id == current_entry_id:
                        view.enter_edit_mode(i, current_cursor_pos)
                        view.select_entry(current_entry_id, ensure_visible=True)
                        break
        else:
            # Navigation mode - check level restriction
            if not (0 <= view._sel < len(view._rows)):
                return False
            current_row = view._rows[view._sel]
            if current_row.level == 0:
                return False  # Can't outdent children of hidden root

            cur_id = current_row.entry_id
            success = view.flat_tree.outdent_entry(cur_id)

            if success:
                view.select_entry(cur_id, ensure_visible=False)

        self._restore_view_focus()
        return success if 'success' in locals() else False

    # --------------- Lines to rows ---------------

    def on_action_lines_to_rows(self, event=None):
        """Split current row on newlines into separate sibling rows."""
        if not self._current_note_panel:
            self.SetStatusText("No notebook open")
            return

        view = self._current_note_panel.view

        if not (0 <= view._sel < len(view._rows)):
            return  # No selection - silent noop

        current_row = view._rows[view._sel]
        target_id = current_row.entry_id

        entry = view.cache.entry(target_id)
        rich_text_data = entry.get("text", [])

        plain_text = ""
        for run in rich_text_data:
            plain_text += run.get("content", "")

        # Better CRLF handling
        lines = plain_text.splitlines()

        if len(lines) <= 1:
            return  # Silent noop

        if view._edit_state.active:
            view.exit_edit_mode(save=True)

        try:
            new_ids = view.flat_tree.create_siblings_batch(target_id, len(lines))

            # NEW: write each line into the corresponding new entry via the cache
            for new_id, line in zip(new_ids, lines):
                e = view.cache.entry(new_id)         # load into cache (or fetch existing cached copy)
                e["text"] = [{"content": line}]      # plain-text run
                e["edit"] = ""                       # not in edit mode
                view.cache.save_entry_data(e)        # persist via cache

            view.flat_tree.delete_entry(target_id)

            if new_ids:
                view.select_entry(new_ids, ensure_visible=True)
                self.SetStatusText(f"Split into {len(new_ids)} rows")

        except Exception as e:
            self.SetStatusText(f"Failed to split row: {e}")

        self._restore_view_focus()

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

    # --------------- History Browser ---------------

    def _on_history_browser(self, event=None):
        """Open the history browser dialog for the current notebook."""
        if not self.current_notebook_path:
            wx.MessageBox(
                "Open a notebook first to view history.",
                "No Notebook Open",
                wx.OK | wx.ICON_INFORMATION
            )
            return

        # Prevent multiple history browsers
        if self._history_browser:
            self._history_browser.Raise()
            return

        # Create and show non-modal dialog
        self._history_browser = HistoryBrowserDialog(
            self,
            self.current_notebook_path,
            self.version_manager
        )
        self._history_browser.Show()

        # Clean up reference when dialog closes
        def on_dialog_close(evt):
            self._history_browser = None
            evt.Skip()

        self._history_browser.Bind(wx.EVT_CLOSE, on_dialog_close)
        self._restore_view_focus()

    def set_read_only_mode(self, read_only: bool):
        """Switch between read-only and editable mode."""
        self._read_only = read_only

        if read_only:
            self.SetStatusText("Read-only mode: Viewing historical version.")
            # Disable editing controls
            if self._toolbar:
                self._toolbar.Enable(False)
            # Disable specific menu items
            self.checkpoint_menu_item.Enable(False)
            self.import_pdf_menu_item.Enable(False)
            self.new_notebook_menu_item.Enable(False)
            self.open_notebook_menu_item.Enable(False)
        else:
            self.SetStatusText("Ready")
            # Re-enable editing controls
            if self._toolbar:
                self._toolbar.Enable(True)
            self.checkpoint_menu_item.Enable(True)
            self.import_pdf_menu_item.Enable(True)
            self.new_notebook_menu_item.Enable(True)
            self.open_notebook_menu_item.Enable(True)

        # Propagate to current view
        if self._current_note_panel and self._current_note_panel.view:
            self._current_note_panel.view._read_only = read_only
            if read_only:
                self._current_note_panel.view.flat_tree.enter_read_only_mode()
            else:
                self._current_note_panel.view.flat_tree.exit_read_only_mode()

    def is_read_only(self) -> bool:
        """Check if currently in read-only mode"""
        return self._read_only

    def reload_notebook(self):
        """Reload the current notebook (for after Git checkout operations)."""
        if not self.current_notebook_path or not self._current_note_panel:
            return

        # Force complete reload of the current view
        if self._current_note_panel:
            self._current_note_panel.reload()
            self._restore_view_focus()
        self._load_tabs_from_notebook()

    def _on_auto_commit_timer(self, event):
        """Periodically check if auto-commit is needed."""
        if self.current_notebook_path:
            try:
                self.version_manager.auto_commit_if_needed(self.current_notebook_path)
            except Exception:
                # Silently ignore auto-commit errors so they don't disrupt workflow
                pass

    def _on_create_checkpoint(self, event=None):
        """Create a manual checkpoint with user-provided message."""
        if not self.current_notebook_path:
            wx.MessageBox(
                "Open a notebook first to create a checkpoint.",
                "No Notebook Open",
                wx.OK | wx.ICON_INFORMATION
            )
            return

        # Get checkpoint message from user
        with wx.TextEntryDialog(
            self,
            "Enter a description for this checkpoint:",
            "Create Checkpoint",
            "Manual checkpoint"
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                self.SetStatusText("Checkpoint cancelled")
                return

            message = dlg.GetValue().strip()
            if not message:
                message = "Manual checkpoint"

        # Show progress
        self.SetStatusText("Creating checkpoint...")

        try:
            self.version_manager.create_manual_checkpoint(self.current_notebook_path, message)
            self.SetStatusText(f"Checkpoint created: {message}")

        except ValueError as e:
            # Handle "no changes" case gracefully
            if "No changes to commit" in str(e):
                wx.MessageBox(
                    "No changes to save.\n\nAll your work is already saved.",
                    "No Changes",
                    wx.OK | wx.ICON_INFORMATION
                )
                self.SetStatusText("No changes to save")
            else:
                wx.MessageBox(str(e), "Checkpoint Error", wx.OK | wx.ICON_ERROR)
                self.SetStatusText(f"Checkpoint error: {e}")

        except Exception as e:
            error_msg = f"Failed to create checkpoint: {str(e)}"
            self.SetStatusText(error_msg)
            wx.MessageBox(error_msg, "Checkpoint Error", wx.OK | wx.ICON_ERROR)

        self._restore_view_focus()

    # --------------- Close ---------------

    def on_quit(self, event):
        evt = wx.CloseEvent(wx.wxEVT_CLOSE_WINDOW)
        wx.PostEvent(self, evt)

    def Close(self, event):
        """Clean up before closing the application."""
        # Close history browser if it's open
        if self._history_browser:
            self._history_browser.Close()
            self._history_browser = None
        event.Skip()
