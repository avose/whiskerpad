WhiskerPad Development Notes
Last Updated: 2025-09-09

PROJECT OVERVIEW
-----------------
WhiskerPad is a hierarchical note-taking application inspired by Circus Ponies NoteBook, built with wxPython. 
It organizes information in interconnected tree structures with support for rich text, images, and PDFs. 
Features include version control with Git, bookmarkable tabs for quick navigation, and full-text search.

CORE FEATURES
-------------
- Editable hierarchical notebook/tree structure (outline view, nodes, indentation)
- Inline rich text editing with formatting (bold, italic, color, highlight)
- Images, image import, scaling, thumbnails associated with tree nodes
- Internal links between nodes: Ctrl+C on node sets bookmark, Ctrl+V in edit mode pastes link
- Blue underlined links for working links; red links for broken/missing targets
- Atomic link behavior: links cannot be edited inline, removed as complete units
- Navigation tabs (vertical panel): black tabs for existing targets, red for missing
- Version control integration with Git for automatic commits and history browsing
- Full-text search across all notebook content including extracted PDF text
- PDF import and text extraction using PyMuPDF
- Drag and drop functionality for images and files
- Read-only mode for safe historical version browsing
- Enhanced logging with automatic filename detection and click-to-copy functionality

ARCHITECTURE OVERVIEW
----------------------
The application follows a Model-View architecture with clear separation of concerns:

Core Components:
- MainFrame: Main application window with toolbar, menu, and content management
- GCView: Graphics context-based view for rendering hierarchical tree with variable-height rows
- NotePanel: Container for individual notebook views with entry management
- VersionManager: Git integration for version control, commits, and history browsing
- HistoryBrowserDialog: Non-modal dialog for browsing and managing commit history
- TabsPanel: Vertical tab interface for bookmarked entries with visual link validation
- EditState: Rich text editing state management and formatting operations
- RichText/TextRun: Rich text model with inline formatting support
- NotebookCache: Performance caching layer for entry data and layout
- FlatTree: Synchronizes persistent tree structure with flat display representation

FLAT TREE ARCHITECTURE (ui/flat_tree.py)
-----------------------------------------
The FlatTree class provides critical abstraction between hierarchical storage and UI display:

Purpose:
- Efficient flattened representation of hierarchical notebook structure
- Fast incremental updates for insertions, deletions, collapse/expand operations
- Core data structure for variable-height scrollable tree view (GCView)

Key Features:
- Maintains flat list of rows with level (depth), entry ID, and display information
- Synchronizes with persistent tree structure stored in JSON files
- Supports subtree invalidation and incremental rebuilds
- Enables efficient navigation, hit-testing, and selection operations

Critical Synchronization Requirement:
The persistent tree structure and flat display list MUST stay synchronized.
Any operation that modifies hierarchy needs to update both structures.
The FlatTree class handles this synchronization automatically.

VERSION CONTROL SYSTEM
-----------------------
WhiskerPad includes comprehensive Git-based version control:

VersionManager Features:
- Automatic background commits every 5+ minutes when changes detected
- Manual checkpoint creation with user-provided messages
- Non-destructive history browsing with read-only mode
- Safe copy operations for historical versions
- Git LFS support for large binary files (images, PDFs)
- Comprehensive debug logging for troubleshooting

HistoryBrowserDialog:
- Non-modal dialog allowing history browsing while main app remains accessible
- Commit list with date, changes count, and commit messages
- "View Selected" for temporary historical state viewing
- "Save Copy" for non-destructive historical version export
- Automatic tab state restoration when browsing historical commits

Read-Only Mode:
- Automatically enabled during history browsing
- Disables all editing operations, toolbar, and specific menu items
- Prevents accidental modifications while viewing historical states
- Restores full editing capability when history browser closes
- Menu items (Import PDF, Save Checkpoint) are disabled during read-only mode

TABS AND NAVIGATION
-------------------
TabsPanel provides bookmark-style navigation with enhanced features:

Features:
- Vertical tabs with file-tab appearance and custom colors
- Visual validation: black text for valid targets, red for broken links
- Right-click context menu: rename, remove, color selection with color swatches
- Smooth scrolling for large numbers of tabs with scroll arrows
- Automatic synchronization with notebook metadata
- Proper restoration during history browsing
- Tab persistence and loading without defensive error handling

Tab Colors:
- Default: Light gray (200, 200, 200)
- Color palette: Gray, Red, Orange, Yellow, Green, Blue, Purple, Pink, Cyan, Lime, Magenta, Teal
- Color selection via context menu with visual color swatches

ENHANCED LOGGING SYSTEM
------------------------
Improved logging with better debugging capabilities:

Features:
- Automatic filename detection using inspect.stack()
- Click-to-copy functionality in log viewer
- Clean log message format: [filename] message
- Right-click context menu for log operations
- Save log to file and copy to clipboard options
- No defensive error handling - exceptions propagate for easier debugging

LOG VIEWER:
- Pop-up log list viewer accessible from status bar
- Click on any log entry automatically copies the message text to clipboard
- Multi-line text wrapping for better readability
- Monospace font for consistent formatting

CURRENT FILE STRUCTURE
-----------------------
Core Files:
- ui/main_frame.py - Main application window with enhanced close handling
- core/tree.py - Entry storage and retrieval
- core/tree_utils.py - Tree manipulation functions
- ui/cache.py - Performance caching layer
- ui/model.py - Tree flattening algorithms
- ui/flat_tree.py - FlatTree management and synchronization
- core/version_manager.py - Git integration with comprehensive logging
- core/log.py - Enhanced logging system with filename detection

UI Components:
- ui/view.py - Main view with _rows list and display logic
- ui/history_browser.py - Non-modal history browser dialog
- ui/tabs_panel.py - Enhanced tab management with colors and persistence
- ui/statusbar.py - Status bar with enhanced log viewer
- ui/help.py - About dialog with background image support
- ui/mouse.py - Mouse event handling
- ui/keys.py - Keyboard event handling
- ui/row.py - Row painting and display
- ui/edit_state.py - Rich text editing state

Import/Export:
- ui/pdf_import.py - PDF text extraction
- ui/image_import.py - Image handling
- ui/clipboard.py - Copy/paste operations

RECENT MAJOR UPDATES
--------------------
1. Enhanced Tab System:
   - Fixed tab persistence bug - tabs now save/load correctly without defensive error handling
   - Improved color serialization to/from JSON format
   - Added comprehensive right-click context menu with color swatches
   - Tabs update correctly when browsing historical commits

2. Version Control Improvements:
   - Added comprehensive debug logging throughout VersionManager
   - Fixed history browser tab restoration when viewing historical commits
   - Enhanced read-only mode with proper menu item disabling
   - Improved dialog close event handling for proper Git state restoration

3. Logging System Overhaul:
   - Automatic filename detection in log messages using inspect.stack()
   - Click-to-copy functionality in log viewer
   - Removed "(debug-#n)" prefix for cleaner log output
   - Enhanced status bar popup with better text wrapping

4. UI Polish:
   - Added About dialog with background image and non-resizable window
   - Improved main frame close handling to properly close child dialogs
   - Enhanced error handling throughout - removed defensive try/except blocks
   - Better visual feedback for tab states and link validation

PERFORMANCE OPTIMIZATIONS
--------------------------
- NotebookCache provides efficient caching for large notebooks
- Incremental updates (update_tree_incremental) avoid full rebuilds
- LayoutIndex provides efficient row position calculations
- Image thumbnailing is cached and optimized
- FlatTree provides efficient tree operations without full rebuilds

DEPENDENCIES
------------
Required:
- wxPython - GUI framework
- Standard library - json, pathlib, threading, inspect, etc.

Optional:
- PyMuPDF (fitz) - PDF text extraction
- GitPython - Enhanced Git operations (falls back to command-line git)

OUTSTANDING ISSUES / TODO
--------------------------
1. Undo/redo system implementation
2. Multi-line text editing issues:
   - Mouse coordinate to character position conversion
   - Double-click word selection on multi-line text
   - Text selection behavior across line boundaries
   - Cursor positioning after operations like paste
3. Complete dark mode/light mode theming
4. User preferences and configuration UI
5. Performance optimizations for very large notebooks
6. Context menu for main row view (toolbar alternative)
7. New features:
   - Lines to rows conversion button
   - Expand/contract all bullets functionality

DEBUGGING NOTES
----------------
- All error handling now uses explicit exceptions rather than defensive programming
- Log messages include source filenames automatically
- Click any log entry to copy the message to clipboard for easy bug reporting
- History browser properly handles Git state restoration
- Tab persistence works reliably without silent failures

This document reflects the current state of WhiskerPad development as of September 9, 2025.

REPO LAYOUT
-----------
avose@echo:whiskerpad$ tree
.
├── app.py
├── core
│   ├── git.py
│   ├── __init__.py
│   ├── io_worker.py
│   ├── log.py
│   ├── storage.py
│   ├── tree.py
│   ├── tree_utils.py
│   ├── version_manager.py
│   └── version.py
├── DEV_NOTES.md
├── icons
│   ├── application_add.png
│   ├── application_get.png
│   ├── application_side_expand.png
│   ├── book_add.png
│   ├── book_open.png
│   ├── book.png
│   ├── cut.png
│   ├── delete.png
│   ├── disk.png
│   ├── error.png
│   ├── eye.png
│   ├── hourglass.png
│   ├── image_add.png
│   ├── information.png
│   ├── link_add.png
│   ├── money_dollar.png
│   ├── page_add.png
│   ├── page_white_acrobat.png
│   ├── page_white_copy.png
│   ├── paintbrush.png
│   ├── paste_plain.png
│   ├── script_key.png
│   ├── shape_flip_horizontal.png
│   ├── shape_flip_vertical.png
│   ├── shape_rotate_anticlockwise.png
│   ├── shape_rotate_clockwise.png
│   ├── style.png
│   ├── tab_add.png
│   ├── tab_delete.png
│   ├── tab_edit.png
│   ├── zoom_in.png
│   ├── zoom_out.png
│   └── zoom.png
├── images
│   ├── btc_addr.png
│   └── whiskerpad.jpg
├── __init__.py
├── LICENSE
├── requirements.txt
├── tools
│   └── create_test_notebook.py
├── ui
│   ├── cache.py
│   ├── clipboard.py
│   ├── constants.py
│   ├── cursor.py
│   ├── decorators.py
│   ├── drag_drop.py
│   ├── edit_state.py
│   ├── file_dialogs.py
│   ├── flat_tree.py
│   ├── help.py
│   ├── history_browser.py
│   ├── icons.py
│   ├── image_import.py
│   ├── image_loader.py
│   ├── image_transform.py
│   ├── image_utils.py
│   ├── index.py
│   ├── keys.py
│   ├── layout.py
│   ├── licenses.py
│   ├── main_frame.py
│   ├── model.py
│   ├── mouse.py
│   ├── notebook_text.py
│   ├── note_panel.py
│   ├── paint.py
│   ├── pdf_import.py
│   ├── row.py
│   ├── row_utils.py
│   ├── scroll.py
│   ├── search.py
│   ├── select.py
│   ├── statusbar.py
│   ├── tabs_panel.py
│   ├── toolbar.py
│   ├── types.py
│   └── view.py
├── utils
│   ├── fs_atomic.py
│   ├── image_types.py
│   ├── img_tokens.py
│   ├── orphan_images.py
│   └── paths.py
└── whiskerpad.py

