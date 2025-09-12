# ui/pdf_import.py
'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import wx

from core.tree import load_entry, save_entry
from ui.image_import import import_image_into_entry
from ui.icons import wpIcons
from utils.paths import sanitize_basename

# PDF library detection
try:
    import fitz  # PyMuPDF
    PDF_IMPORT_AVAILABLE = True
except ImportError:
    PDF_IMPORT_AVAILABLE = False

__all__ = [
    "PDF_IMPORT_AVAILABLE",
    "is_pdf_import_available",
    "show_pdf_import_dialog"
]

def is_pdf_import_available() -> bool:
    """Check if PDF import functionality is available."""
    return PDF_IMPORT_AVAILABLE

def validate_pdf_file(pdf_path: str) -> Dict[str, Any]:
    """
    Validate PDF and return metadata.

    Returns:
        {
            "valid": bool,
            "page_count": int,
            "error": str | None,
            "requires_password": bool
        }
    """
    if not PDF_IMPORT_AVAILABLE:
        return {"valid": False, "error": "PyMuPDF not installed", "page_count": 0, "requires_password": False}

    try:
        doc = fitz.open(pdf_path)

        if doc.needs_pass:
            doc.close()
            return {"valid": False, "error": "PDF requires password", "page_count": 0, "requires_password": True}

        page_count = doc.page_count
        doc.close()

        return {"valid": True, "error": None, "page_count": page_count, "requires_password": False}

    except Exception as e:
        return {"valid": False, "error": f"Invalid PDF: {str(e)}", "page_count": 0, "requires_password": False}

def parse_page_range(range_text: str, max_pages: int) -> List[int]:
    """
    Parse page range string into list of page numbers (1-indexed).

    Examples:
        "all" -> [1, 2, 3, ..., max_pages]
        "1-5,7,10-12" -> [1, 2, 3, 4, 5, 7, 10, 11, 12]

    Raises ValueError for invalid ranges.
    """
    range_text = range_text.strip().lower()

    if range_text == "all":
        return list(range(1, max_pages + 1))

    pages = []
    parts = range_text.split(",")

    for part in parts:
        part = part.strip()

        if "-" in part:
            # Range like "5-10"
            start_str, end_str = part.split("-", 1)
            start = int(start_str.strip())
            end = int(end_str.strip())

            if start < 1 or end > max_pages or start > end:
                raise ValueError(f"Invalid range {part} (pages must be 1-{max_pages})")

            pages.extend(range(start, end + 1))
        else:
            # Single page like "7"
            page = int(part)
            if page < 1 or page > max_pages:
                raise ValueError(f"Invalid page {page} (must be 1-{max_pages})")

            pages.append(page)

    # Remove duplicates and sort
    return sorted(list(set(pages)))

class PDFImportWorker(threading.Thread):
    """Background thread for PDF conversion only - model changes happen on main thread."""

    def __init__(self, dialog, pdf_path: str, page_numbers: List[int], dpi: int):
        # Call Thread.__init__ explicitly with no arguments
        threading.Thread.__init__(self, daemon=True)

        # Store our custom arguments as instance variables
        self.dialog = dialog
        self.pdf_path = pdf_path
        self.page_numbers = page_numbers
        self.dpi = dpi
        self.cancelled = False

    def cancel(self):
        """Request cancellation of the import process."""
        self.cancelled = True

    def run(self):
        """Execute PDF conversion, then trigger main thread import."""
        try:
            # Phase 1: Convert PDF pages to images (background thread)
            temp_files = self._convert_pdf_pages()

            if self.cancelled:
                self._cleanup_temp_files(temp_files)
                return

            # Phase 2: Import on main thread (thread-safe)
            wx.CallAfter(self.dialog._import_on_main_thread, temp_files)

        except Exception as e:
            wx.CallAfter(self.dialog._on_import_error, str(e))

    def _convert_pdf_pages(self) -> List[Tuple[int, str, str]]:  # Added str for page text
        """Convert selected PDF pages to temporary image files with text extraction."""
        temp_files = []
        try:
            doc = fitz.open(self.pdf_path)
            for i, page_num in enumerate(self.page_numbers):
                if self.cancelled:
                    break

                wx.CallAfter(self.dialog._update_progress,
                            f"Converting page {page_num}...", i, len(self.page_numbers))

                try:
                    # Convert page to image
                    page = doc[page_num - 1] # Convert to 0-indexed

                    # Extract text from page
                    page_text = page.get_text()

                    matrix = fitz.Matrix(self.dpi / 72.0, self.dpi / 72.0)
                    pix = page.get_pixmap(matrix=matrix)

                    # Create temporary file
                    temp_fd, temp_path = tempfile.mkstemp(suffix='.png', prefix='whiskerpad_pdf_')
                    os.close(temp_fd) # Close file descriptor

                    # Save image
                    pix.save(temp_path)

                    temp_files.append((page_num, temp_path, page_text))

                except Exception as e:
                    # Page conversion failed, skip this page
                    wx.CallAfter(self.dialog._log_page_error, page_num, f"Conversion failed: {str(e)}")

            doc.close()
        except Exception as e:
            self._cleanup_temp_files(temp_files)
            raise RuntimeError(f"PDF conversion failed: {str(e)}")

        return temp_files

    def _cleanup_temp_files(self, temp_files: List[Tuple[int, str, str]]):
        """Clean up temporary image files."""
        for page_num, temp_path, page_text in temp_files:  # Added page_text
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except Exception:
                pass # Ignore cleanup errors

class ImportPDFDialog(wx.Dialog):
    """Custom dialog for PDF import with progress."""

    def __init__(self, parent, view):
        super().__init__(parent, title="Import PDF", style=wx.DEFAULT_DIALOG_STYLE)
        self.view = view
        self.pdf_info = None
        self.worker = None

        self._create_controls()
        self._create_layout()
        self._bind_events()

        # Center dialog
        self.Center()
        self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))

    def _create_controls(self):
        """Create all dialog controls."""
        # File selection section
        self.file_label = wx.StaticText(self, label="PDF File:")
        self.file_path = wx.TextCtrl(self, style=wx.TE_READONLY)
        self.browse_button = wx.Button(self, label=" Browse...")
        self.browse_button.SetBitmap(wpIcons.Get("page_white_acrobat"))

        # PDF info display
        self.pdf_info_label = wx.StaticText(self, label="")

        # Image quality / DPI
        self.dpi_label = wx.StaticText(self, label="Image Quality (DPI):")
        dpi_choices = [str(dpi) for dpi in range(100, 651, 50)]
        self.dpi_combo = wx.ComboBox(self, choices=dpi_choices, style=wx.CB_READONLY)
        self.dpi_combo.SetSelection(dpi_choices.index("150"))  # Default to 150 DPI
        self.dpi_combo.SetMinSize(wx.Size(100, -1))

        # Page ranges.
        self.pages_label = wx.StaticText(self, label="Pages to Import:")
        self.pages_input = wx.TextCtrl(self, value="all")
        self.pages_help = wx.StaticText(self, label="Examples: 'all', '1-5,7,10-12', '1,3,5'")

        # Progress section (initially hidden)
        self.progress_label = wx.StaticText(self, label="Progress:")
        self.progress_bar = wx.Gauge(self, range=100)
        self.status_label = wx.StaticText(self, label="Ready")

        # Custom dialog buttons with icon
        self.import_button = wx.Button(self, wx.ID_ANY, " Import")
        self.import_button.SetBitmap(wpIcons.Get("tick"))
        self.cancel_button = wx.Button(self, wx.ID_CANCEL, " Cancel")
        self.cancel_button.SetBitmap(wpIcons.Get("cross"))

        # Set icon on import button
        import_icon = wpIcons.Get("page_white_acrobat")
        if import_icon:
            self.import_button.SetBitmap(import_icon)

        # Make Import button the default button (responds to Enter key)
        self.import_button.SetDefault()

        self.import_button.Enable(False)  # Disabled until valid PDF selected

        # Initially hide progress controls
        self.progress_label.Hide()
        self.progress_bar.Hide()

    def _create_layout(self):
        """Layout all controls in the dialog."""
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # File selection section
        file_sizer = wx.BoxSizer(wx.HORIZONTAL)
        file_sizer.Add(self.file_path, 1, wx.EXPAND | wx.RIGHT, 5)
        file_sizer.Add(self.browse_button, 0)

        main_sizer.Add(self.file_label, 0, wx.ALL, 5)
        main_sizer.Add(file_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
        main_sizer.Add(self.pdf_info_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        # Separator
        main_sizer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.ALL, 5)

        # Settings section
        settings_sizer = wx.FlexGridSizer(2, 2, 5, 5)
        settings_sizer.AddGrowableCol(1)

        settings_sizer.Add(self.dpi_label, 0, wx.ALIGN_CENTER_VERTICAL)
        settings_sizer.Add(self.dpi_combo, 0, 0)

        settings_sizer.Add(self.pages_label, 0, wx.ALIGN_CENTER_VERTICAL)
        settings_sizer.Add(self.pages_input, 0, wx.EXPAND)

        main_sizer.Add(settings_sizer, 0, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(self.pages_help, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        # Progress section
        main_sizer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(self.progress_label, 0, wx.LEFT | wx.RIGHT, 5)
        main_sizer.Add(self.progress_bar, 0, wx.EXPAND | wx.ALL, 5)

        # Bottom section: Status text inline with buttons
        bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        bottom_sizer.Add(self.status_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        bottom_sizer.Add(self.import_button, 0, wx.RIGHT, 5)
        bottom_sizer.Add(self.cancel_button, 0)

        main_sizer.Add(bottom_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # Use SetSizerAndFit to minimize dialog size
        self.SetSizer(main_sizer)
        self.SetMinSize((500, -1))  # 500px minimum width, auto height
        self.Fit()  # Fit height to content while respecting min width

    def _bind_events(self):
        """Bind all event handlers."""
        self.browse_button.Bind(wx.EVT_BUTTON, self._on_browse)
        self.import_button.Bind(wx.EVT_BUTTON, self._on_import)
        self.cancel_button.Bind(wx.EVT_BUTTON, self._on_cancel)
        self.pages_input.Bind(wx.EVT_TEXT, self._on_pages_changed)
        self.Bind(wx.EVT_ACTIVATE, self._on_activate)

    def _on_activate(self, event):
        """Handle dialog activation to restore focus after file picker closes."""
        if event.GetActive() and self.import_button.IsEnabled():
            # Dialog is being activated - restore focus to import button
            wx.CallAfter(self.import_button.SetFocus)
        event.Skip()

    def _on_browse(self, event):
        """Handle browse button click."""
        with wx.FileDialog(
            self,
            message="Select PDF file",
            wildcard="PDF files (*.pdf)|*.pdf|All files (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as dlg:
            result = dlg.ShowModal()

            # Delay focus restoration to override OS focus management
            def restore_focus():
                self.Raise()
                if self.import_button.IsEnabled():
                    self.import_button.SetFocus()
                else:
                    self.SetFocus()

            wx.CallAfter(restore_focus)
            wx.CallLater(150, restore_focus)  # 150ms delay

            if result == wx.ID_OK:
                pdf_path = dlg.GetPath()
                self._validate_and_load_pdf(pdf_path)

    def _validate_and_load_pdf(self, pdf_path: str):
        """Validate selected PDF and update UI."""
        self.pdf_info = validate_pdf_file(pdf_path)

        if self.pdf_info["valid"]:
            self.file_path.SetValue(pdf_path)
            page_count = self.pdf_info["page_count"]
            pdf_name = Path(pdf_path).name
            self.pdf_info_label.SetLabel(f"{pdf_name} ({page_count} pages)")
            self.pdf_info_label.SetForegroundColour(wx.Colour(0, 0, 0))
            self._validate_import_settings()
        else:
            self.file_path.SetValue("")
            self.pdf_info_label.SetLabel(f"Error: {self.pdf_info['error']}")
            self.pdf_info_label.SetForegroundColour(wx.Colour(200, 0, 0))
            self.import_button.Enable(False)

        self.Layout()

    def _on_pages_changed(self, event):
        """Handle changes to page range input."""
        self._validate_import_settings()

    def _validate_import_settings(self):
        """Validate current settings and enable/disable import button."""
        if not self.pdf_info or not self.pdf_info["valid"]:
            self.import_button.Enable(False)
            return

        # Validate page range
        try:
            pages = parse_page_range(self.pages_input.GetValue(), self.pdf_info["page_count"])
            if pages:
                self.import_button.Enable(True)
                self.status_label.SetLabel(f"Ready to import {len(pages)} pages")
                self.status_label.SetForegroundColour(wx.Colour(0, 0, 0))
            else:
                self.import_button.Enable(False)
                self.status_label.SetLabel("No pages selected")
                self.status_label.SetForegroundColour(wx.Colour(200, 0, 0))

        except ValueError as e:
            self.import_button.Enable(False)
            self.status_label.SetLabel(f"Invalid page range: {str(e)}")
            self.status_label.SetForegroundColour(wx.Colour(200, 0, 0))

    def _on_import(self, event):
        """Start the PDF import process."""
        if not self.pdf_info or not self.pdf_info["valid"]:
            return

        try:
            pages = parse_page_range(self.pages_input.GetValue(), self.pdf_info["page_count"])
            dpi = int(self.dpi_combo.GetValue())
            pdf_path = self.file_path.GetValue()

            # Switch to progress mode
            self._start_import_mode()

            # Start background worker
            self.worker = PDFImportWorker(self, pdf_path, pages, dpi)
            self.worker.start()

        except Exception as e:
            wx.MessageBox(f"Failed to start import: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)

    def _start_import_mode(self):
        """Switch dialog to import/progress mode."""
        # Disable settings controls
        self.browse_button.Enable(False)
        self.dpi_combo.Enable(False)
        self.pages_input.Enable(False)
        self.import_button.Enable(False)

        # Show and reset progress controls
        self.progress_label.Show()
        self.progress_bar.Show()
        self.progress_bar.SetValue(0)
        self.progress_bar.SetRange(100)

        # Resize dialog to fit newly visible progress controls
        self.Layout()
        self.Fit()

    def _update_progress(self, message: str, current: int, total: int):
        """Update progress bar and status (called from worker thread)."""
        if total > 0:
            progress = int((current * 100) / total)
            self.progress_bar.SetValue(progress)

        self.status_label.SetLabel(message)
        self.Refresh()

    def _log_page_error(self, page_num: int, error: str):
        """Log error for a specific page (called from worker thread)."""
        # Could be enhanced to show in dialog
        pass

    def _on_import_complete(self, imported_pages: List[int], failed_pages: List[int]):
        """Handle successful completion (called from worker thread)."""
        total_requested = len(imported_pages) + len(failed_pages)

        if failed_pages:
            message = f"Imported {len(imported_pages)} of {total_requested} pages ({len(failed_pages)} failed)"
        else:
            message = f"Successfully imported {len(imported_pages)} pages"

        self.status_label.SetLabel(message)
        self.progress_bar.SetValue(100)

        # Re-enable cancel button (now becomes "Close")
        self.cancel_button.SetLabel("Close")
        self.cancel_button.Enable(True)

        # Set dialog result and auto-close after brief delay
        wx.CallLater(1500, self._auto_close_success)

    def _on_import_error(self, error: str):
        """Handle import error (called from worker thread)."""
        self.status_label.SetLabel(f"Import failed: {error}")
        self.status_label.SetForegroundColour(wx.Colour(200, 0, 0))

        # Re-enable controls for retry
        self.browse_button.Enable(True)
        self.dpi_combo.Enable(True)
        self.pages_input.Enable(True)
        self._validate_import_settings()

        wx.MessageBox(f"PDF import failed:\n{error}", "Import Error", wx.OK | wx.ICON_ERROR)

    def _auto_close_success(self):
        """Auto-close dialog after successful import."""
        self.EndModal(wx.ID_OK)

    def _on_cancel(self, event):
        """Handle cancel button click."""
        if self.worker and self.worker.is_alive():
            # Cancel ongoing import
            self.worker.cancel()
            self.status_label.SetLabel("Cancelling...")
            wx.CallLater(500, lambda: self.EndModal(wx.ID_CANCEL))
        else:
            # Normal cancel
            self.EndModal(wx.ID_CANCEL)

    def _import_on_main_thread(self, temp_files: List[Tuple[int, str, str]]):
        """Import converted images (runs on main thread for thread safety)."""
        try:
            imported_pages, failed_pages = self._do_main_thread_import(temp_files)
            self._on_import_complete(imported_pages, failed_pages)
        except Exception as e:
            self._on_import_error(str(e))
        finally:
            # Always clean up temp files
            self.worker._cleanup_temp_files(temp_files)

    def _do_main_thread_import(self, temp_files: List[Tuple[int, str, str]]) -> Tuple[List[int], List[int]]:
        """Perform the actual import operations on the main thread."""
        view = self.view
        current_id = view.current_entry_id()

        # If no selection, find the last root-level entry to insert after
        if not current_id:
            last_root_id = None
            for row in reversed(view._rows): # Start from the end
                if row.level == 0: # Root level entry
                    last_root_id = row.entry_id
                    break

            if last_root_id:
                current_id = last_root_id
            else:
                # Fallback: if no root entries exist, get the first root ID
                from core.tree import get_root_ids
                root_ids = get_root_ids(view.notebook_dir)
                if root_ids:
                    current_id = root_ids[0]
                else:
                    raise RuntimeError("No entries found in notebook - cannot determine import location")

        # Check if notebook is empty (no direct children of root)
        has_children = any(row.level == 0 for row in view._rows)

        imported_pages = []
        failed_pages = []
        last_inserted_id = None

        # Generate base filename from PDF
        pdf_name = Path(self.worker.pdf_path).stem
        sanitized_name = sanitize_basename(pdf_name)

        for i, (page_num, temp_path, page_text) in enumerate(temp_files):
            if self.worker.cancelled:
                break

            self._update_progress(f"Importing page {page_num}...",
                                len(self.worker.page_numbers) + i,
                                len(self.worker.page_numbers) * 2)

            try:
                # Handle first page in empty notebook differently
                if not has_children and i == 0:
                    # Use FlatTree instead of create_node
                    new_id = view.flat_tree.create_child_under(current_id)
                else:
                    # Use FlatTree instead of add_sibling_after
                    insert_after_id = last_inserted_id if last_inserted_id else current_id
                    new_id = view.flat_tree.create_sibling_after(insert_after_id)

                if not new_id:
                    raise RuntimeError(f"Failed to create entry for page {page_num}")

                # Import image into the entry (main thread operation)
                info = import_image_into_entry(view.notebook_dir, new_id, temp_path)

                # Set entry text to image token AND store page text
                entry = load_entry(view.notebook_dir, new_id)
                entry["text"] = [{"content": info["token"]}]
                entry["edit"] = ""
                entry["page_text"] = page_text # Add extracted text
                save_entry(view.notebook_dir, entry)

                # Invalidate cache for the new entry
                view.cache.invalidate_entry(new_id)

                last_inserted_id = new_id
                imported_pages.append(page_num)

            except Exception as e:
                self._log_page_error(page_num, f"Import failed: {str(e)}")
                failed_pages.append(page_num)

        return imported_pages, failed_pages


def show_pdf_import_dialog(parent, view) -> Optional[str]:
    """
    Show the PDF import dialog and handle the import process.

    Returns:
        Status message for display, or None if cancelled.
    """
    if not PDF_IMPORT_AVAILABLE:
        wx.MessageBox(
            "PDF import requires PyMuPDF library.\n\nInstall with: pip install PyMuPDF",
            "PDF Import Not Available",
            wx.OK | wx.ICON_INFORMATION
        )
        return None

    dialog = ImportPDFDialog(parent, view)

    try:
        if dialog.ShowModal() == wx.ID_OK:
            # Import was successful, refresh the view
            view.rebuild()
            return "PDF import completed"
        else:
            return None  # Cancelled

    finally:
        dialog.Destroy()
