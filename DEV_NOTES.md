DEV_NOTES.txt - WhiskerPad Development Notes
============================================

PROJECT OVERVIEW
-----------------
WhiskerPad is a hierarchical note-taking application built with wxPython. It uses a tree-based 
structure where each node can contain rich text with formatting support. The application supports:

- Hierarchical note organization with collapsible tree structure
- Rich text editing with bold, italic, text color, and background color formatting
- Text selection with mouse drag and keyboard shortcuts (Shift+arrows, etc.)
- Copy/paste/cut operations via keyboard shortcuts (Ctrl+C/V/X) and toolbar buttons
- Word selection via double-click
- Image insertion and display within notes
- Multi-line text support with Shift+Enter for line breaks
- Tree navigation and manipulation (indent/outdent with Tab/Shift+Tab)
- Persistent storage using JSON format


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


CURRENT STATUS
--------------
The application is functionally complete for basic note-taking operations. Users can:
- Create and organize hierarchical notes
- Edit text with rich formatting
- Navigate the tree structure efficiently
- Perform standard text operations (select, copy, paste, cut)
- Insert and view images
- Save and load notebooks

All major features are working, but there are some quality issues that need addressing.


NEXT STEPS / ISSUES TO ADDRESS
-------------------------------

0. Don't render the root node. / Subtle blue background.
1. Copy and paste images.
2. Drag rows by bullets to reorder rows (and their children).
3. Image thumbnail resize support, rotate, flip.
4. Import PDFs as images with each PDF page being an image (row).
5. Add lines to bullet button to turn lines within a row into full rows.
6. Bookmarks (add / delete, activate) to jump to rows.
7. Undo / Redo
8. Notebook versioning with git, minute, hour, day, week, month, year.
9. Expand / contract all bullets at and beneath selected row.
10. MULTI-LINE issues: EDITING, TEXT SELECTION, AND CURSOR POSITIONING
   There are issues with text selection and cursor positioning on multi-line rows:
   - Mouse coordinate to character position conversion may be incorrect
   - Double-click word selection doesn't work properly on multi-line text
   - Text selection behavior is inconsistent across line boundaries
   - Cursor positioning after operations like paste may be wrong
   - May be related to line height calculations or coordinate transformations
   - Affects user experience when editing longer text entries
11. Help / about / licenses.


TECHNICAL IMPLEMENTATION NOTES
-------------------------------

Text Selection System:
- Uses black outline rectangles around selected text (not filled highlights)
- Selection spans can cross multiple formatting runs while preserving individual formatting
- Integrates with clipboard operations for copy/cut/paste
- Keyboard selection with Shift+arrows, Shift+Home/End

Rich Text Format:
- Text stored as runs with consistent formatting (TextRun objects)
- Supports bold, italic, text color, background color
- Format inheritance when inserting new text
- Proper serialization to/from JSON storage format

Caching Architecture:
- NotebookCache manages entry data and layout information
- Separate cache invalidation for data vs. layout changes
- LayoutIndex handles row positioning for variable-height content
- Cache rebuilding triggered by text changes, tree operations

Mouse and Keyboard Interaction:
- Comprehensive event handling for editing and navigation
- Support for drag selection, word selection, tree manipulation
- Focus management to keep editing view active during toolbar interactions
- Integration between mouse clicks and keyboard shortcuts


DEVELOPMENT WORKFLOW
--------------------
When making changes:
1. Test with both single-line and multi-line text entries
2. Verify text selection works across formatting boundaries  
3. Ensure clipboard operations maintain focus in editing view
4. Test tree navigation and manipulation operations
5. Verify cache invalidation doesn't cause performance issues
6. Check that changes persist correctly when saving/loading notebooks

The codebase is generally well-structured but needs cleanup to remove defensive programming
patterns and improve maintainability. The core functionality is solid and the architecture
supports the planned features well.

SOURCE CODE FILE OVERVIEW
==========================

Core Application Files:
- main_frame.py
  Main application window managing notebook loading, content embedding,
  toolbar creation, and global UI event handling.

- view.py
  Core graphical tree view rendering the hierarchy with variable row heights,
  handling user interaction, layout management, and inline rich text editing.

- note_panel.py
  Container component hosting the editable notebook interface,
  manages display of the current entry and interaction with the view.

User Interface Components:
- top_toolbar.py
  Implementation of the top toolbar with buttons for notebook operations, adding images,
  clipboard (copy/paste/cut), and color pickers for text foreground and background.

- icons.py
  Resource loader and management for UI icons.

- file_dialogs.py
  Encapsulated file dialog helpers for image import and notebook file selection.

Input Handling:
- keys.py
  Centralized key event routing handling all keyboard input for navigation and editing,
  including text input, cursor movement, selection, and command shortcuts.

- mouse.py
  Mouse event handling providing click, double-click, drag selection, 
  and scroll behaviors within the hierarchical tree.

Rendering and Layout:
- row.py
  Per-row rendering logic using wx.GraphicsContext,
  including drawing text, images, gutters, and selection highlights.

- paint.py
  Painting utilities for rendering backgrounds and rows efficiently.

- layout.py
  Text measurement, wrapping, and layout calculations for
  variable-height rich text rows.

Text Editing System:
- edit_state.py
  Rich text model and editing state management, including cursor position, selection,
  and text formatting operations (bold, italic, colors).

Navigation and Selection:
- scroll.py
  Scroll behavior utilities, ensuring visibility and smooth navigation
  in large hierarchical trees.

- select.py
  Selection state management within the tree, including keyboard and mouse
  driven selection changes.

Data Management:
- cache.py (or notebook_cache.py)
  Caches notebook data and layout computations to optimize rendering performance,
  supports incremental updates and invalidation.

Image Support:
- image_import.py
  Image file import and processing for embedding in notebook entries.

- image_loader.py
  Image loading and thumbnail generation for display optimization.

- image_utils.py
  Image manipulation utilities including thumbnail creation and sizing.

────────────────────────────────────────────────────────
Repo structure
────────────────────────────────────────────────────────

avose@echo:whiskerpad$ tree
.
├── app.py
├── core
│   ├── __init__.py
│   ├── io_worker.py
│   ├── storage.py
│   ├── tree.py
│   └── tree_utils.py
├── create_test_notebook.py
├── DEV_NOTES.md
├── icons
│   ├── application_add.png
│   ├── application_get.png
│   ├── application_side_expand.png
│   ├── book_add.png
│   ├── book.png
│   ├── cut.png
│   ├── image_add.png
│   ├── page_add.png
│   ├── page_white_copy.png
│   ├── paintbrush.png
│   ├── paste_plain.png
│   └── style.png
├── __init__.py
├── ui
│   ├── cache.py
│   ├── constants.py
│   ├── cursor.py
│   ├── drag_drop.py
│   ├── edit_state.py
│   ├── file_dialogs.py
│   ├── icons.py
│   ├── image_import.py
│   ├── image_loader.py
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
│   ├── row.py
│   ├── scroll.py
│   ├── select.py
│   ├── top_toolbar.py
│   ├── types.py
│   └── view.py
├── utils
│   ├── fs_atomic.py
│   ├── image_types.py
│   ├── img_tokens.py
│   ├── orphan_images.py
│   └── paths.py
└── whiskerpad.py