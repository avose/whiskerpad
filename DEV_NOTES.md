WhiskerPad - DEV_NOTES.txt
Updated: 2025-08-23 (Rich Text Editing Implementation Complete)

================================================================================
PROJECT OVERVIEW
================================================================================
WhiskerPad is a wxPython notebook application that emphasizes smooth scrolling,
inline images, and hierarchical editing. We have successfully implemented a
custom rich text editing system that provides WYSIWYG word processor 
functionality while maintaining the tree structure for organization.

Latest milestone - "Rich Text Editing System"
- Custom rich text editor using GraphicsContext (not RichTextCtrl)
- Click anywhere to position cursor and start typing immediately
- Word processor UX: seamless editing transitions between tree nodes
- Persistent editing state to prevent data loss on power outages
- Rich text format with support for bold, italic, colors, and highlights

================================================================================
CURRENT ARCHITECTURE
================================================================================
The application follows a clean separation between core business logic and UI:

core/  (pure business logic)
  ├── tree.py               – entry storage, rich text format, CRUD operations
  ├── tree_utils.py         – indent/outdent, collapse, tree manipulation
  ├── storage.py            – notebook create/load operations
  └── io_worker.py          – background I/O thread

ui/   (wxPython front-end)
  ├── view.py               – main ScrolledWindow with rich text editing integration
  ├── layout.py             – rich text wrapping and layout calculations
  ├── row.py                – rich text rendering and cursor drawing
  ├── paint.py              – overall painting coordination
  ├── mouse.py              – character-level click handling and edit mode entry
  ├── keys.py               – comprehensive keyboard handling for editing/navigation
  ├── select.py             – selection management with proper highlight refresh
  ├── scroll.py             – scrolling with coordinate system handling
  ├── model.py              – tree flattening for display
  ├── index.py              – layout indexing for efficient scrolling
  ├── edit_state.py         – rich text editing state management
  ├── cursor.py             – cursor positioning and rendering utilities
  ├── notebook_text.py      – rich text extraction and layout measurement
  ├── image_utils.py        – thumbnail generation for images
  ├── image_loader.py       – bitmap caching and loading
  ├── image_import.py       – image file importing workflow
  └── main_frame.py         – application frame and notebook management

utils/ – generic helpers (fs_atomic, img_tokens, paths, image_types, orphan_images)

================================================================================
RICH TEXT EDITING SYSTEM
================================================================================

Storage Format:
Entries use a clean rich text format in the "text" field:
{
  "id": "abc123",
  "text": [
    {"content": "Hello ", "bold": false, "italic": false, "color": null, "bg": null},
    {"content": "world", "bold": true, "italic": false, "color": "#ff0000", "bg": null}
  ],
  "edit": "",  // Temporary plain text during editing (auto-saved for crash recovery)
  "parent_id": "def456",
  ...
}

Core Components:

1. EditState Class (ui/edit_state.py):
   - Manages all editing state (cursor position, rich text being edited)
   - TextRun and RichText classes for rich text data manipulation
   - Handles text insertion, deletion, cursor movement

2. Cursor System (ui/cursor.py):
   - char_pos_from_pixel(): Converts mouse clicks to character positions
   - pixel_pos_from_char(): Converts character positions to pixel coordinates
   - Handles rich text wrapping and coordinate systems
   - CursorRenderer for drawing the text cursor

3. Layout System (ui/layout.py):
   - ensure_wrap_cache(): Calculates rich text layout with word wrapping
   - Maintains formatting information per line segment
   - Handles both rich text and image content

4. Rendering System (ui/row.py):
   - RowPainter with rich text support
   - _draw_rich_text(): Renders formatted text with fonts, colors, backgrounds
   - _draw_cursor(): Positions and draws cursor during editing
   - Maintains support for image tokens on separate lines

User Experience:
- Click anywhere in text to position cursor and start editing immediately
- Cursor moves and text appears as you type (full WYSIWYG experience)
- Enter key creates new sibling nodes (like paragraphs in word processors)  
- Shift+Enter inserts literal newlines within current node
- Escape cancels editing, clicking elsewhere saves and switches nodes
- Tab/Shift+Tab for tree operations (indent/outdent) work during editing
- All existing tree navigation preserved (arrows, page up/down, etc.)

Technical Features:
- Custom implementation using wxPython GraphicsContext for full control
- Efficient partial refresh during editing (only redraws changed areas)
- Proper coordinate system handling for scrolled content
- Automatic crash recovery via persistent "edit" field
- Character-level mouse hit testing with sub-pixel accuracy
- Rich text wrapping that preserves formatting across line breaks

================================================================================
KEY IMPLEMENTATION DETAILS
================================================================================

Coordinate Systems:
The application handles multiple coordinate systems correctly:
- Content coordinates: Where text actually exists in the document
- Window coordinates: What the user sees in the scrolled view
- Mouse click conversion accounts for scroll offsets

Edit Mode Flow:
1. Mouse click -> char_pos_from_click() -> enter_edit_mode()
2. Keyboard input -> EditState manipulation -> immediate save to "edit" field
3. Exit editing -> commit rich text to "text" field -> clear "edit" field

Selection and Highlighting:
- _change_selection() method ensures both old and new highlights refresh
- Proper coordinate conversion for RefreshRect() calls
- Full refresh fallback for reliability

Image Integration:
- Images remain on separate lines (no inline images within text)
- Image import creates nodes with {{img "filename"}} tokens
- Existing image functionality fully preserved

Performance Optimizations:
- Layout caching prevents unnecessary recalculation
- Partial refreshes during editing
- Efficient text measurement and character positioning
- Bitmap caching for image thumbnails

================================================================================
CURRENT STATUS
================================================================================

Completed Features:
✓ Rich text editing with cursor positioning
✓ Click-to-edit functionality
✓ Word processor-style Enter key behavior
✓ Character-level mouse interaction
✓ Keyboard input handling (letters, numbers, symbols with shift)
✓ Tree navigation integration (Tab, arrows, etc.)
✓ Crash-resistant editing with auto-save
✓ Rich text storage format
✓ Image import and display
✓ Scrolling and coordinate system handling
✓ Selection highlighting with proper refresh

Known Working:
- Create new notebooks with rich text format
- Click anywhere to edit at precise cursor positions
- Type text and see immediate feedback
- Use Enter to create new nodes, Shift+Enter for newlines
- Navigate tree with keyboard while preserving editing
- Import images that display correctly
- Scroll and edit at any position
- Selection highlighting updates correctly

================================================================================
NEXT DEVELOPMENT PRIORITIES
================================================================================

1. File Drag and Drop Support:
   - Implement wx.FileDropTarget for the main view
   - Support dragging image files directly into the application
   - Auto-import and create nodes for dropped files
   - Handle multiple file drops efficiently

2. Rich Text Formatting UI:
   - Add text color and background color selection
   - Keyboard shortcuts for formatting (Ctrl+B for bold, Ctrl+I for italic)
   - Text selection with mouse drag
   - Apply formatting to selected text ranges
   - Format toolbar or context menu

3. Small Issues to Address:
   - Selection highlight persistence issues in edge cases
   - Potential cursor positioning accuracy improvements
   - Performance optimization for very large documents
   - Edge cases in coordinate conversion
   - Text selection behavior refinement

4. Advanced Features (Future):
   - Copy/paste with formatting preservation
   - Undo/redo system for rich text operations
   - Find/replace functionality
   - Export capabilities (HTML, PDF, etc.)
   - Themes and appearance customization

================================================================================
DEVELOPMENT WORKFLOW
================================================================================

Testing Strategy:
- Create new notebooks to test rich text format
- Test editing at various scroll positions
- Verify tree operations work during editing
- Test image import and display
- Check coordinate systems with different window sizes

Code Quality:
- Clean separation between core and UI layers
- No backwards compatibility or migration code
- Comprehensive error handling
- Consistent coordinate system handling
- Efficient rendering and caching strategies

Architecture Decisions:
- Custom rich text implementation provides full control
- GraphicsContext ensures consistent cross-platform rendering
- EditState pattern centralizes editing logic
- Rich text runs format balances simplicity and functionality
- Persistent edit field prevents data loss

================================================================================
NOTES
================================================================================

- The rich text system is designed for simplicity and performance
- No complex layouts (tables, columns) - tree structure provides organization
- Images always on separate lines for clean layout
- Custom implementation avoids wxPython RichTextCtrl limitations
- Edit field auto-save provides excellent crash recovery
- Word processor UX with tree structure benefits
- Coordinate system handling is critical for proper cursor positioning
- Full refresh fallback ensures reliability over micro-optimizations

Next session should focus on drag-and-drop file support and color formatting.
Update this file as new features are implemented.
