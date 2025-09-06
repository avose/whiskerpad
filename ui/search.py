from __future__ import annotations

import multiprocessing as mp
import os
import re
import time
from pathlib import Path
from typing import List, Tuple, Optional
import queue

import wx
import wx.dataview

from core.tree import notebook_paths, load_entry


class SearchWorkerProcess(mp.Process):
    """Worker process for searching notebook entries."""
    
    def __init__(self, notebook_dir: str, query: str, entry_chunks: List[str], 
                 result_queue: mp.Queue, progress_queue: mp.Queue):
        super().__init__(daemon=True)
        self.notebook_dir = notebook_dir
        self.query = query.lower()  # Case-insensitive search
        self.entry_chunks = entry_chunks
        self.result_queue = result_queue
        self.progress_queue = progress_queue
        
    def run(self):
        """Search through assigned entry chunks."""
        try:
            for entry_id in self.entry_chunks:
                try:
                    self._search_entry(entry_id)
                except Exception:
                    # Skip entries that can't be read
                    pass
                finally:
                    # Report progress after each entry processed
                    self.progress_queue.put(1)
                    
        except Exception:
            # Worker process error - just exit
            pass
    
    def _search_entry(self, entry_id: str):
        """Search a single entry for the query phrase."""
        try:
            entry = load_entry(self.notebook_dir, entry_id)

            # Check if this entry has extracted PDF text
            if "page_text" in entry and entry["page_text"]:
                # Use pre-extracted text for PDF pages
                full_text = entry["page_text"]
            else:
                # Use existing rich text extraction for regular entries
                text_parts = []
                for text_item in entry.get("text", []):
                    content = text_item.get("content", "")
                    if content:
                        text_parts.append(content)
                if not text_parts:
                    return  # No text content
                full_text = " ".join(text_parts)

            # Rest of search logic
            lower_text = full_text.lower()
            match_pos = lower_text.find(self.query)

            if match_pos >= 0:
                snippet = self._create_snippet(full_text, match_pos)
                timestamp = (entry.get("last_edit_ts") or 
                            entry.get("updated_ts") or 
                            entry.get("created_ts", 0))

                result = (entry_id, timestamp, snippet, match_pos)
                self.result_queue.put(result)

        except Exception as e:
            import traceback
            traceback.print_exc()
    
    def _create_snippet(self, text: str, match_pos: int) -> str:
        """Create snippet with 32 chars before/after match, with markup highlighting."""
        match_end = match_pos + len(self.query)

        # Calculate snippet bounds
        start = max(0, match_pos - 32)
        end = min(len(text), match_end + 32)

        snippet = text[start:end]

        # Find the match position within the snippet
        snippet_match_start = match_pos - start
        snippet_match_end = snippet_match_start + len(self.query)

        # Insert markup around the match
        highlighted_snippet = (
            snippet[:snippet_match_start] +
            f'<span bgcolor="#ADD8E6">{snippet[snippet_match_start:snippet_match_end]}</span>' +
            snippet[snippet_match_end:]
        )

        # Add ellipsis if truncated
        if start > 0:
            highlighted_snippet = "..." + highlighted_snippet
        if end < len(text):
            highlighted_snippet = highlighted_snippet + "..."

        return highlighted_snippet


class SearchDialog(wx.Dialog):
    """Non-modal search dialog for notebook entries."""
    
    def __init__(self, parent, notebook_dir: str, initial_query: str = ""):
        super().__init__(parent, title="Search Notebook", 
                        style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        
        self.notebook_dir = notebook_dir
        self.main_view = None  # Will be set by caller
        self.workers: List[SearchWorkerProcess] = []
        self.result_queue = mp.Queue()
        self.progress_queue = mp.Queue()
        self.total_entries = 0
        self.processed_entries = 0
        self.is_searching = False
        
        self._create_controls()
        self._setup_layout()
        self._bind_events()
        
        # Set initial query and size
        if initial_query:
            self.search_ctrl.SetValue(initial_query)
        
        self.SetSize((600, 400))
        self.Center()

        # Auto-start search if initial query provided
        if initial_query.strip():
            wx.CallAfter(self._on_search, None)
        
        # Timer for polling worker results
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._poll_results)
    
    def _create_controls(self):
        """Create dialog controls."""
        # Search input
        self.search_ctrl = wx.SearchCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_ctrl.ShowCancelButton(True)
        self.search_ctrl.SetToolTip("Enter search phrase and press Enter")
        
        # Progress bar
        self.progress = wx.Gauge(self, range=100)
        self.progress.Hide()  # Initially hidden
        
        # Status label
        self.status_label = wx.StaticText(self, label="Enter search terms above")
        
        # Results list
        self.results_list = wx.dataview.DataViewListCtrl(self)

        # Add visible columns
        self.results_list.AppendTextColumn("Date", width=100)

        # Create match column with markup-enabled renderer
        match_renderer = wx.dataview.DataViewTextRenderer()
        match_renderer.EnableMarkup(True)
        match_col = wx.dataview.DataViewColumn("Match", match_renderer, 1, width=450)
        self.results_list.AppendColumn(match_col)

        # Add hidden columns for data storage
        self.results_list.AppendTextColumn("", width=0)  # Hidden timestamp
        self.results_list.AppendTextColumn("", width=0)  # Hidden entry_id

        # Hide the last two columns
        col_count = self.results_list.GetColumnCount()
        if col_count >= 4:
            self.results_list.GetColumn(2).SetHidden(True)  # Hide timestamp column
            self.results_list.GetColumn(3).SetHidden(True)  # Hide entry_id column
        
        # Control buttons
        self.search_button = wx.Button(self, label="Search")
        self.cancel_button = wx.Button(self, wx.ID_CANCEL, label="Cancel")
        self.close_button = wx.Button(self, wx.ID_CLOSE, label="Close")
        
        # Initially disable cancel
        self.cancel_button.Enable(False)
    
    def _setup_layout(self):
        """Layout dialog controls."""
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Search input section
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_sizer.Add(wx.StaticText(self, label="Search:"), 0, 
                        wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        search_sizer.Add(self.search_ctrl, 1, wx.EXPAND)
        
        main_sizer.Add(search_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        # Progress and status
        main_sizer.Add(self.progress, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        main_sizer.Add(self.status_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        # Results list
        main_sizer.Add(self.results_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        # Button row
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.Add(self.search_button, 0, wx.RIGHT, 5)
        button_sizer.Add(self.cancel_button, 0, wx.RIGHT, 5)
        button_sizer.AddStretchSpacer()
        button_sizer.Add(self.close_button, 0)
        
        main_sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        self.SetSizer(main_sizer)
    
    def _bind_events(self):
        """Bind event handlers."""
        self.search_ctrl.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.search_ctrl.Bind(wx.EVT_SEARCHCTRL_SEARCH_BTN, self._on_search)
        self.search_button.Bind(wx.EVT_BUTTON, self._on_search)
        self.cancel_button.Bind(wx.EVT_BUTTON, self._on_cancel_search)
        self.close_button.Bind(wx.EVT_BUTTON, self._on_close)
        self.results_list.Bind(wx.dataview.EVT_DATAVIEW_SELECTION_CHANGED, self._on_result_selected)
        
        # Handle dialog close
        self.Bind(wx.EVT_CLOSE, self._on_dialog_close)
    
    def _on_search(self, event):
        """Start search with current query."""
        query = self.search_ctrl.GetValue().strip()
        if not query:
            wx.MessageBox("Please enter a search term", "Search", wx.OK | wx.ICON_INFORMATION)
            return
            
        if self.is_searching:
            self._cancel_search()
            
        self._start_search(query)
    
    def _start_search(self, query: str):
        """Start multi-process search."""
        self.is_searching = True
        self.processed_entries = 0
        
        # Update UI
        self.search_button.SetLabel("Searching...")
        self.search_button.Enable(False)
        self.cancel_button.Enable(True)
        self.progress.Show()
        self.status_label.SetLabel("Preparing search...")
        self.results_list.DeleteAllItems()
        self.Layout()
        
        # Get all entry directories
        entries_dir = notebook_paths(self.notebook_dir)["entries"]
        entry_dirs = []
        
        if entries_dir.exists():
            for shard_dir in entries_dir.iterdir():
                if shard_dir.is_dir() and len(shard_dir.name) == 2:
                    for entry_dir in shard_dir.iterdir():
                        if entry_dir.is_dir():
                            entry_dirs.append(entry_dir.name)
        
        if not entry_dirs:
            self.status_label.SetLabel("No entries found in notebook")
            self._search_complete()
            return
        
        self.total_entries = len(entry_dirs)
        self.progress.SetRange(self.total_entries)
        self.progress.SetValue(0)
        
        # Split entries into 4 chunks for worker processes
        chunk_size = max(1, len(entry_dirs) // 4)
        chunks = [entry_dirs[i:i + chunk_size] for i in range(0, len(entry_dirs), chunk_size)]
        
        # Ensure we have exactly 4 chunks (last chunk may be larger)
        while len(chunks) > 4:
            chunks[3].extend(chunks.pop())
        
        # Start worker processes
        self.workers = []
        for chunk in chunks:
            if chunk:  # Don't start empty workers
                worker = SearchWorkerProcess(
                    self.notebook_dir, query, chunk, 
                    self.result_queue, self.progress_queue
                )
                self.workers.append(worker)
        for worker in self.workers:
            worker.start()
        
        # Start polling timer
        self.timer.Start(100)  # Poll every 100ms
        self.status_label.SetLabel(f"Searching {self.total_entries} entries...")
    
    def _poll_results(self, event):
        """Poll queues for progress updates and search results."""
        # Process all available progress updates
        progress_updates = 0
        try:
            while True:
                self.progress_queue.get_nowait()
                progress_updates += 1
                self.processed_entries += 1
                self.progress.SetValue(self.processed_entries)
        except queue.Empty:
            # Expected when no more progress updates available
            pass
        except Exception as e:
            print(f"ERROR: Unexpected exception in search progress queue: {e}")

        # Process all available search results  
        results_found = 0
        try:
            while True:
                result = self.result_queue.get_nowait()
                self._add_result(result)
                results_found += 1
        except queue.Empty:
            # Expected when no more results available
            pass
        except Exception as e:
            print(f"ERROR: Unexpected exception in search result queue: {e}")

        # Update status with current match count
        current_count = self.results_list.GetItemCount()
        if current_count > 0:
            self.status_label.SetLabel(f"Found {current_count} matches...")

        # Check to see if we have processed everyting.
        if self.processed_entries >= self.total_entries:
            self._search_complete()
            return
    
    def _add_result(self, result: Tuple[str, int, str, int]):
        """Add search result to list, maintaining timestamp sort order."""
        entry_id, timestamp, snippet, match_pos = result

        # Strip newlines and normalize whitespace
        snippet_clean = snippet.replace('\n', ' ').replace('\r', ' ')

        # Format date for display
        date_str = time.strftime("%Y-%m-%d", time.localtime(timestamp))

        # Find insertion point (keep sorted by timestamp, newest first)
        insert_pos = 0
        for i in range(self.results_list.GetItemCount()):
            existing_timestamp = self.results_list.GetTextValue(i, 2)
            if timestamp > int(existing_timestamp):
                insert_pos = i
                break
            insert_pos = i + 1

        # Insert with cleaned snippet
        values = [date_str, snippet_clean, str(timestamp), entry_id]
        try:
            self.results_list.InsertItem(insert_pos, values)
            count = self.results_list.GetItemCount()

            # Force refresh
            self.results_list.Refresh()
            self.Layout()

        except Exception as e:
            import traceback
            traceback.print_exc()

    def _search_complete(self):
        """Handle search completion."""
        self.timer.Stop()
        self.is_searching = False
        
        # Wait for workers to finish
        for worker in self.workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=1)
        
        self.workers.clear()
        
        # Update UI
        self.search_button.SetLabel("Search")
        self.search_button.Enable(True)
        self.cancel_button.Enable(False)
        
        result_count = self.results_list.GetItemCount()
        if result_count == 0:
            self.status_label.SetLabel("No matches found")
        else:
            self.status_label.SetLabel(f"Found {result_count} matches")
    
    def _on_cancel_search(self, event):
        """Cancel ongoing search."""
        if self.is_searching:
            self._cancel_search()
    
    def _cancel_search(self):
        """Cancel the current search operation."""
        self.timer.Stop()
        self.is_searching = False
        
        # Terminate workers
        for worker in self.workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=1)
        
        self.workers.clear()
        
        # Clear queues
        try:
            while True:
                self.result_queue.get_nowait()
        except:
            pass
        
        try:
            while True:
                self.progress_queue.get_nowait()
        except:
            pass
        
        # Reset UI
        self.search_button.SetLabel("Search")
        self.search_button.Enable(True)
        self.cancel_button.Enable(False)
        self.progress.Hide()
        self.status_label.SetLabel("Search cancelled")
        self.Layout()
    
    def _on_result_selected(self, event):
        """Handle result selection - navigate to entry in main view."""
        selection = self.results_list.GetSelectedRow()
        if selection >= 0 and self.main_view:
            # Get entry_id from hidden column
            entry_id = self.results_list.GetTextValue(selection, 3) # Hidden column 3
            if entry_id:
                # Use FlatTree navigation instead of direct tree_utils call
                self.main_view.flat_tree.ensure_entry_visible(entry_id)

    def _on_close(self, event):
        """Handle close button."""
        self.Close()
    
    def _on_dialog_close(self, event):
        """Handle dialog close event."""
        if self.is_searching:
            self._cancel_search()
        
        self.timer.Stop()
        event.Skip()
    
    def set_main_view(self, view):
        """Set reference to main notebook view for navigation."""
        self.main_view = view


def show_search_dialog(parent, notebook_dir: str, main_view, initial_query: str = ""):
    """Show the search dialog."""
    dialog = SearchDialog(parent, notebook_dir, initial_query)
    dialog.set_main_view(main_view)
    dialog.Show()
    return dialog
