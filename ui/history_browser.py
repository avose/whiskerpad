# ui/history_browser.py

from __future__ import annotations

import wx
import os
import shutil
from pathlib import Path
from typing import List, Optional

from core.git import CommitInfo, GitError
from core.version_manager import VersionManager
from ui.icons import wpIcons

__all__ = ["HistoryBrowserDialog"]

class HistoryBrowserDialog(wx.Dialog):
    """
    Non-modal History Browser Dialog for WhiskerPad Version Control

    OVERVIEW:
    ========
    This dialog displays the Git commit history for a notebook and allows users to:
    - Browse historical versions (read-only viewing)
    - Save copies of historical versions (non-destructive operation)

    KEY FEATURES:
    - Non-modal design allows keeping dialog open while browsing history
    - Read-only mode prevents accidental changes during history browsing
    - Safe "save copy" operation instead of destructive rewind
    - Automatic commit of current changes before entering history mode

    USER WORKFLOW:
    1. Dialog opens → VersionManager commits current changes → enters read-only mode
    2. User selects commit → "View Selected" → main window shows historical state
    3. Optional: "Save Copy As..." → save historical version to new location
    4. Dialog closes → return to current state → re-enable editing

    SAFETY FEATURES:
    - All current work is automatically saved before browsing
    - No destructive operations - only safe copying
    - Clear status indicators for current viewing state
    - Graceful error handling with user-friendly messages
    """

    def __init__(self, parent: wx.Window, notebook_dir: str, version_manager: VersionManager):
        """
        Initialize the History Browser dialog.

        Args:
            parent: Parent window (typically MainFrame)
            notebook_dir: Path to notebook directory
            version_manager: Coordinate version control operations
        """
        super().__init__(
            parent,
            title=f"History Browser — {notebook_dir}",
            size=(800, 500),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        self.notebook_dir = notebook_dir
        self.version_manager = version_manager
        self.parent_frame = parent

        # State tracking
        self._commits: List[CommitInfo] = []
        self._selected_commit_hash: str = ""
        self._selected_index: int = -1

        self._init_ui()
        self._bind_events()
        self.CenterOnParent()

        # Load history and enter read-only mode
        self._load_commit_history()

    def _init_ui(self):
        """Initialize the user interface components."""
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Header with current status
        self._create_header(main_sizer)
        main_sizer.AddSpacer(4)

        # Commit list (main content area)
        self._create_commit_list(main_sizer)

        # Action buttons
        self._create_buttons(main_sizer)

        self.SetSizer(main_sizer)

    def _create_header(self, parent_sizer: wx.BoxSizer):
        """Create header section with status information."""
        header_panel = wx.Panel(self)
        header_panel.SetBackgroundColour(wx.Colour(240, 240, 240))
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Book icon
        book_icon = wpIcons.Get("book")
        icon_bitmap = wx.StaticBitmap(header_panel, bitmap=book_icon)
        header_sizer.Add(icon_bitmap, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 8)

        # Text content
        text_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Title
        title_label = wx.StaticText(header_panel, label="Notebook History")
        title_font = title_label.GetFont()
        title_font.SetPointSize(title_font.GetPointSize() + 2)
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        title_label.SetFont(title_font)

        # Status information (using bullet_blue icon or text bullet)
        self.status_label = wx.StaticText(
            header_panel,
            label="• Currently viewing: Latest (read-only mode active)"
        )

        text_sizer.Add(title_label, 0, wx.TOP, 8)
        text_sizer.Add(self.status_label, 0, wx.BOTTOM, 8)
        
        header_sizer.Add(text_sizer, 1, wx.LEFT | wx.RIGHT, 8)
        
        header_panel.SetSizer(header_sizer)
        parent_sizer.Add(header_panel, 0, wx.EXPAND)

    def _create_commit_list(self, parent_sizer: wx.BoxSizer):
        """Create the main commit list control using DataViewListCtrl."""
        self.commit_list = wx.dataview.DataViewListCtrl(
            self,
            style=wx.dataview.DV_ROW_LINES | wx.dataview.DV_VERT_RULES | wx.dataview.DV_SINGLE
        )
        # Configure columns with alignment
        self.commit_list.AppendTextColumn("Date & Time", width=150)
        # Right-align the Changes column (numerical data)
        self.commit_list.AppendTextColumn(
            "Changes", 
            width=75, 
            align=wx.ALIGN_RIGHT
        )
        self.commit_list.AppendTextColumn("Message", width=425)
        self.commit_list.AppendTextColumn("Commit ID", width=100, align=wx.ALIGN_CENTER)

        # Make the Message column expandable to use remaining space
        message_col = self.commit_list.GetColumn(2)
        if message_col:
            message_col.SetFlags(wx.dataview.DATAVIEW_COL_RESIZABLE | wx.dataview.DATAVIEW_COL_SORTABLE)

        # Make Commit ID column non-reorderable (keep it rightmost)
        commit_id_col = self.commit_list.GetColumn(3)
        if commit_id_col:
            commit_id_col.SetFlags(wx.dataview.DATAVIEW_COL_RESIZABLE)  # Remove reorderable flag

        parent_sizer.Add(
            self.commit_list,
            1,
            wx.EXPAND | wx.TOP | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            2
        )

    def _create_buttons(self, parent_sizer: wx.BoxSizer):
        """Create action buttons at bottom of dialog."""
        button_panel = wx.Panel(self)
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # View button with eye icon
        self.view_btn = wx.Button(button_panel, label=" View Selected")
        self.view_btn.SetToolTip("Temporarily view the selected historical version")
        self.view_btn.Enable(False)
        
        # Set eye icon if available
        eye_icon = wpIcons.Get("eye")
        self.view_btn.SetBitmap(eye_icon)

        # Save Copy button with disk icon
        self.save_copy_btn = wx.Button(button_panel, label=" Save Copy")
        self.save_copy_btn.SetToolTip("Save a copy of this version to a new location")
        self.save_copy_btn.Enable(False)
        
        # Set disk icon if available
        disk_icon = wpIcons.Get("disk")
        self.save_copy_btn.SetBitmap(disk_icon)

        # Close button
        self.close_btn = wx.Button(button_panel, wx.ID_CLOSE, "Close")
        self.close_btn.SetToolTip("Close history browser and return to editing")

        # Layout buttons
        button_sizer.Add(self.view_btn, 0, wx.ALL, 2)
        button_sizer.Add(self.save_copy_btn, 0, wx.ALL, 2)
        button_sizer.AddStretchSpacer()
        button_sizer.Add(self.close_btn, 0, wx.ALL, 2)

        button_panel.SetSizer(button_sizer)
        parent_sizer.Add(button_panel, 0, wx.EXPAND | wx.ALL, 0)

    def _bind_events(self):
        """Bind event handlers."""
        # DataView selection events
        self.commit_list.Bind(wx.dataview.EVT_DATAVIEW_SELECTION_CHANGED, self._on_commit_selected)

        # Double-click to view
        self.commit_list.Bind(wx.dataview.EVT_DATAVIEW_ITEM_ACTIVATED, self._on_view_selected)

        # Prevent column reordering for Commit ID column
        self.commit_list.Bind(wx.dataview.EVT_DATAVIEW_COLUMN_REORDERED, self._on_column_reordered)

        # Button events
        self.view_btn.Bind(wx.EVT_BUTTON, self._on_view_selected)
        self.save_copy_btn.Bind(wx.EVT_BUTTON, self._on_save_copy_selected)
        self.close_btn.Bind(wx.EVT_BUTTON, self._on_close)

        # Dialog close event
        self.Bind(wx.EVT_CLOSE, self._on_close)

    def _load_commit_history(self):
        """Load commit history from VersionManager and populate the list."""
        try:
            # This automatically commits current changes and enters read-only mode
            self._commits = self.version_manager.open_history_browser(self.notebook_dir)

            # Update parent frame to show read-only state
            if hasattr(self.parent_frame, 'set_read_only_mode'):
                self.parent_frame.set_read_only_mode(True)

            self._populate_commit_list()

        except GitError as e:
            wx.MessageBox(
                f"Failed to load commit history:\n\n{str(e)}",
                "Version Control Error",
                wx.OK | wx.ICON_ERROR,
                parent=self
            )
            self.EndModal(wx.ID_CANCEL)

    def _populate_commit_list(self):
        """Populate the DataView control with commit data."""
        self.commit_list.DeleteAllItems()

        if not self._commits:
            # No commits available - add placeholder row
            self.commit_list.AppendItem([
                "No commit history available",
                "",
                "Create your first checkpoint to see history", 
                ""
            ])
            return

        # Add each commit to the list
        for commit in self._commits:
            self.commit_list.AppendItem([
                commit.date,
                str(commit.changed_entries),
                commit.message,
                commit.hash[:8]  # Short hash
            ])

    def _on_column_reordered(self, event):
        """Prevent reordering of the Commit ID column (keep it rightmost)."""
        # Get the column that was moved
        moved_column = event.GetColumn()

        # If the Commit ID column (index 3) was moved, veto the event
        if moved_column == 3:
            event.Veto()
            wx.MessageBox(
                "The Commit ID column must remain on the right side.",
                "Column Position Fixed",
                wx.OK | wx.ICON_INFORMATION,
                parent=self
            )
            return

        # Allow other columns to be reordered among themselves
        event.Skip()

    def _on_commit_selected(self, event):
        """Handle commit selection in the DataView."""
        selection = self.commit_list.GetSelection()

        if selection.IsOk():
            # Get the row index
            self._selected_index = self.commit_list.ItemToRow(selection)

            if 0 <= self._selected_index < len(self._commits):
                commit = self._commits[self._selected_index]
                self._selected_commit_hash = commit.hash

                # Enable action buttons
                self.view_btn.Enable(True)
                self.save_copy_btn.Enable(True)

                # Update status
                self.status_label.SetLabel(f"• Selected: {commit.date} — {commit.message}")
            else:
                self._on_commit_deselected()
        else:
            self._on_commit_deselected()

    def _on_commit_deselected(self):
        """Handle commit deselection."""
        self._selected_index = -1
        self._selected_commit_hash = ""

        # Disable action buttons
        self.view_btn.Enable(False)
        self.save_copy_btn.Enable(False)

        # Reset status
        self.status_label.SetLabel("• Currently viewing: Latest (read-only mode active)")

    def _on_view_selected(self, event):
        """Handle viewing a selected historical commit."""
        if not self._selected_commit_hash:
            # No selection, try to get current selection
            selection = self.commit_list.GetSelection()
            if not selection.IsOk():
                return

            self._selected_index = self.commit_list.ItemToRow(selection)
            if not (0 <= self._selected_index < len(self._commits)):
                return

            self._selected_commit_hash = self._commits[self._selected_index].hash

        try:
            success = self.version_manager.view_historical_commit(
                self.notebook_dir,
                self._selected_commit_hash
            )
            if not success:
                wx.MessageBox(
                    "Failed to checkout the selected commit.",
                    "Checkout Error",
                    wx.OK | wx.ICON_ERROR,
                    parent=self
                )
                return

            commit = self._commits[self._selected_index]
            self.status_label.SetLabel(f"• Viewing: {commit.date} — {commit.message} (Historical)")
            wx.CallAfter(self.parent_frame.reload_notebook)
            self.parent_frame.SetStatusText(f"Viewing historical version: {commit.date}")

        except GitError as e:
            wx.MessageBox(
                f"Error during checkout:\n\n{str(e)}",
                "Version Control Error",
                wx.OK | wx.ICON_ERROR,
                parent=self
            )

    def _on_save_copy_selected(self, event):
        """Handle saving a copy of the selected commit (safe operation)."""
        if not self._selected_commit_hash:
            return

        commit = self._commits[self._selected_index]

        # Show directory picker dialog
        with wx.DirDialog(
            self,
            "Choose folder where to save the notebook copy:",
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return

            parent_folder = dlg.GetPath()

        # Get name for the copied notebook with clean formatting
        base_name = os.path.basename(self.notebook_dir)
        # Convert "2025-09-08 20:45" to "2025_09_08_2045"
        clean_date = commit.date.replace('-', '_').replace(' ', '_').replace(':', '')
        default_name = f"{base_name}_copy_{clean_date}"

        with wx.TextEntryDialog(
            self,
            "Enter name for the copied notebook:",
            "Save Copy As",
            default_name
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return

            copy_name = dlg.GetValue().strip()
            if not copy_name:
                copy_name = default_name

        dest_path = os.path.join(parent_folder, copy_name)

        # Check if destination already exists
        if os.path.exists(dest_path):
            result = wx.MessageBox(
                f"A folder named '{copy_name}' already exists.\n\nOverwrite it?",
                "Folder Exists",
                wx.YES_NO | wx.ICON_QUESTION,
                parent=self
            )
            if result != wx.YES:
                return

        # Perform the copy operation
        self.parent_frame.SetStatusText("Saving copy...")
        wx.BeginBusyCursor()

        try:
            success = self._clone_notebook_at_commit(dest_path, commit)
            if success:
                # Show success message
                wx.MessageBox(
                    f"Notebook copy saved successfully to:\n{dest_path}\n\n"
                    f"Version: {commit.date} — {commit.message}\n\n",
                    "Copy Successful",
                    wx.OK | wx.ICON_INFORMATION,
                    parent=self
                )
            else:
                wx.MessageBox(
                    "Failed to save notebook copy.\nSee status bar for details.",
                    "Copy Failed",
                    wx.OK | wx.ICON_ERROR,
                    parent=self
                )

        except Exception as e:
            wx.MessageBox(
                f"Error saving notebook copy:\n\n{str(e)}",
                "Copy Error",
                wx.OK | wx.ICON_ERROR,
                parent=self
            )

        finally:
            wx.EndBusyCursor()
            self.parent_frame.SetStatusText("Ready")

    def _clone_notebook_at_commit(self, dest_path: str, commit: CommitInfo) -> bool:
        """Clone the notebook repository and checkout the specific commit."""
        try:
            # Remove destination if it exists
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)

            # Git-based cloning (preserves full history)
            try:
                from git import Repo
                repo = Repo.clone_from(self.notebook_dir, dest_path)
                # Checkout the specific commit
                repo.git.checkout(commit.hash)
                self.parent_frame.SetStatusText(f"Git clone successful: {commit.message[:50]}...")
                return True

            except ImportError:
                # GitPython not available, fall back to directory copy
                self.parent_frame.SetStatusText("GitPython not available, using directory copy...")
            except Exception as git_error:
                self.parent_frame.SetStatusText(f"Git clone failed: {git_error}, trying directory copy...")

        except Exception as e:
            self.parent_frame.SetStatusText(f"Clone operation failed: {e}")
            return False

    def _on_close(self, event):
        """Handle dialog close event."""
        self._close_and_cleanup()
        event.Skip()

    def _close_and_cleanup(self):
        """Close dialog and clean up version manager state."""
        try:
            # Return to current version and exit read-only mode
            self.version_manager.close_history_browser(self.notebook_dir)

            # Update parent frame to normal editing mode
            self.parent_frame.set_read_only_mode(False)

            # Trigger reload to show current state
            wx.CallAfter(self.parent_frame.reload_notebook)

            # Clear status
            self.parent_frame.SetStatusText("Ready")

        except GitError as e:
            wx.MessageBox(
                f"Error returning from history browser:\n\n{str(e)}",
                "Version Control Error",
                wx.OK | wx.ICON_ERROR,
                parent=self
            )
        finally:
            self.Destroy()
