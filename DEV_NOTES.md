WhiskerPad Development Notes
Last Updated: 2025-09-08

PROJECT OVERVIEW
-----------------
WhiskerPad is a hierarchical note-taking application built with wxPython. It uses a tree-based 
structure where each node can contain rich text with formatting support. The application supports:

Core Features:
--------------
- Editable hierarchical notebook/tree (with Outline view, nodes, indentation)
- Inline rich text editing with formatting (bold, italic, color, highlight)
- Images, image import, scaling, thumbnails associated with tree nodes
- Internal links between nodes: Ctrl+C on a node sets as bookmark, Ctrl+V in edit mode pastes link
- Blue underlined links for working links; broken links show as red and nonfunctional
- Atomic link behavior: user cannot edit link text inline; links are removed as a whole (delete/backspace at boundary)
- Navigation tabs (vertical at right): show as black if target exists, as red if target is missing
- Selection and caret handling: indentation/caret area and date gutter are correctly hit-tested and update selection accordingly
- Toolbar for common actions: copy, cut, paste, color, image ops, etc.
- All grid/tree and rich text cache and layout are centralized and updated for performance
- Deletion of nodes deletes children and invalidates links/tabs (shown visually as red)
- All icons (including link icons if used) are 16x16px PNGs
- Full dark mode/light mode color support planned (work in progress)

ARCHITECTURE OVERVIEW
----------------------
The application follows a Model-View architecture:

Core Components:
- `MainFrame`: Main application window with toolbar and content area
- `GCView`: Graphics context-based view for rendering the hierarchical tree
- `NotePanel`: Container for individual notebook views
- `TopToolbar`: Toolbar with file operations, clipboard, and formatting controls
- `EditState`: Manages rich text editing state and operations
- `RichText`/`TextRun`: Rich text model with formatting support
- `NotebookCache`: Caching layer for entry data and layout information
- `LayoutIndex`: Manages row positioning and scrolling for variable-height rows

Key Features Implemented:
- Variable-height rows with proper scrolling
- Inline rich text editing with cursor positioning
- Text selection with visual feedback (black outline rectangles)
- Mouse interaction: click to edit, drag to select, double-click for word selection
- Keyboard shortcuts for navigation and editing
- Clipboard integration for copy/paste operations
- Tree manipulation: collapse/expand, indent/outdent
- Image import and display
- Color formatting via toolbar color pickers
- Rich text editing with inline formatting
- PDF import and text extraction
- Hierarchical notebook structure with collapsible entries
- Image embedding and manipulation
- Full-text search across all content
- Drag and drop functionality

CURRENT ARCHITECTURE

Core Components:
- ui/view.py - Main view class (GCView) with scrollable tree display
- core/tree.py - Persistent storage layer for notebook entries
- core/tree_utils.py - Tree structure manipulation functions
- ui/cache.py - NotebookCache for performance optimization
- ui/model.py - Tree flattening logic (flatten_tree, update_tree_incremental)

Key Data Structures:
1. Persistent Tree - JSON files on disk, hierarchical structure
   - Each entry has parent_id and items array with child references
   - Modified by functions in tree_utils.py (add_sibling_after, indent_under_prev_sibling, etc.)

2. Flat Display List - self._rows: List[Row] in view.py
   - Generated from persistent tree by flatten_tree()
   - Each Row has entry_id, level, and display info
   - Used for efficient rendering and UI operations

3. FlatTree Management (ui/flat_tree.py)
   - Encapsulates the flattened tree representation and operations
   - Provides efficient incremental updates for insertions, deletions, collapse/expand operations
   - Maintains synchronization between persistent tree structure and flat display list
   - Serves as the core data structure for the variable-height scrollable tree view (GCView)

FLAT TREE ARCHITECTURE (ui/flat_tree.py)
-----------------------------------------
The FlatTree class provides a critical abstraction layer that manages the relationship between
the hierarchical persistent tree structure and the flat display representation used by the UI.

Purpose:
- Provides an efficient, flattened representation of the hierarchical notebook/tree structure
- Enables fast incremental updates for insertions, deletions, collapse/expand, and reordering of nodes
- Serves as the core data structure for the variable-height scrollable tree view (GCView)

Key Features:
- Maintains a flat list of rows (nodes) with level (depth), entry ID, and display information
- Synchronizes with the persistent tree structure stored on disk or in memory
- Allows fast subtree invalidation and incremental rebuilds of visible/UI tree
- Supports efficient navigation, hit-testing, and selection operations

Usage:
- Used by the GCView component to render and interact with the notebook with variable height rows
- Receives updates from persistent tree changes and rebuilds affected portions of the flat list
- Facilitates UI features such as collapsing nodes, drag/drop reordering, and indentation

Integration:
- Imported and instantiated by ui/view.py (GCView) component
- Calls from flat_tree trigger view updates, caching, and scrolling adjustments

By encapsulating the flattened tree logic, flat_tree.py improves performance and maintainability by
decoupling UI rendering details from the underlying persistent tree model.

Critical Synchronization Requirement:
The persistent tree structure and flat display list MUST stay synchronized.
Any operation that modifies hierarchy needs to update both structures.
The FlatTree class handles this synchronization automatically.

CURRENT FILE STRUCTURE

Core Files:
- ui/view.py - Main view with _rows list and display logic
- core/tree.py - Entry storage and retrieval
- core/tree_utils.py - Tree manipulation functions
- ui/cache.py - Performance caching layer
- ui/model.py - Tree flattening algorithms
- ui/flat_tree.py - FlatTree management and synchronization

UI Components:
- ui/mouse.py - Mouse event handling
- ui/keys.py - Keyboard event handling  
- ui/row.py - Row painting and display
- ui/edit_state.py - Rich text editing state
- ui/search.py - Full-text search functionality

Import/Export:
- ui/pdf_import.py - PDF text extraction
- ui/image_import.py - Image handling
- ui/clipboard.py - Copy/paste operations

SEARCH FUNCTIONALITY
- Multi-process search across all entries
- Extracts text from PDF pages using PyMuPDF
- Supports search in both rich text and extracted PDF text
- Search dialog with real-time results

PERFORMANCE NOTES
- NotebookCache provides good performance for large notebooks
- Incremental updates (update_tree_incremental) avoid full rebuilds
- LayoutIndex provides efficient row position calculations
- Image thumbnailing is cached and optimized
- FlatTree provides efficient tree operations without full rebuilds

DEPENDENCIES
- wxPython - GUI framework
- PyMuPDF (fitz) - PDF text extraction (optional)
- Standard library - json, pathlib, multiprocessing, etc.

NEXT STEPS / ISSUES TO ADDRESS
-------------------------------

1. Add lines to bullet button to turn lines within a row into full rows.
2. Undo / Redo
3. Notebook versioning with git, minute, hour, day, week, month, year.
4. Expand / contract all bullets at and beneath selected row.
5. MULTI-LINE issues: EDITING, TEXT SELECTION, AND CURSOR POSITIONING
   There are issues with text selection and cursor positioning on multi-line rows:
   - Mouse coordinate to character position conversion may be incorrect
   - Double-click word selection doesn't work properly on multi-line text
   - Text selection behavior is inconsistent across line boundaries
   - Cursor positioning after operations like paste may be wrong
   - May be related to line height calculations or coordinate transformations
   - Affects user experience when editing longer text entries

Repo structure:

avose@echo:whiskerpad$ tree
.
├── app.py
├── core
│   ├── __init__.py
│   ├── io_worker.py
│   ├── log.py
│   ├── storage.py
│   ├── tree.py
│   ├── tree_utils.py
│   └── version.py
├── create_test_notebook.py
├── DEV_NOTES.md
├── icons
│   └── <icon_name>.png
├── images
│   └── btc_addr.png
├── __init__.py
├── LICENSE
├── requirements-optional.txt
├── requirements.txt
├── ui
│   ├── cache.py
│   ├── clipboard.py
│   ├── constants.py
│   ├── cursor.py
│   ├── drag_drop.py
│   ├── edit_state.py
│   ├── file_dialogs.py
│   ├── flat_tree.py
│   ├── help.py
│   ├── icons.py
│   ├── image_import.py
│   ├── image_loader.py
│   ├── image_transform.py
│   ├── image_utils.py
│   ├── index.py
│   ├── keys.py
│   ├── layout.py
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
