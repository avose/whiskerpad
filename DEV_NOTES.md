WhiskerPad ― DEVELOPMENT NOTES
Last updated: 2025-08-24

────────────────────────────────────────────────────────
WhiskPad – Development Notes
────────────────────────────────────────────────────────
WhiskPad is a **hierarchical note-taking application** written in Python with a wxPython GUI.  
It stores each notebook as a directory of JSON “entries”, arranged in a tree.  
Every entry can contain rich-text (bold, italic, underline, FG/BG colour) and
embedded image tokens that render as thumbnails.

Key capabilities
• Inline rich-text editing directly inside the tree.
• Variable-height rows with smooth, virtual scrolling.
• Collapse/expand (folding) of any subtree.
• Incremental updates when nodes are added, moved or edited.
• Fast image loading via background-generated thumbnails.

Code organisation
• core/   – data model, file-IO and storage helpers  
• ui/     – all widgets, rendering, input handling  
• utils/  – image helpers, atomic file ops, misc utilities  

Performance architecture
• A unified **NotebookCache** keeps entry JSON and computed layout
  (row height, wrapped text, scaled thumbnail sizes).
• Layout is lazily cached and auto-invalidates when the available
  text-width changes (e.g. window resize) or when an entry is edited.
• Fast-path height look-ups make scrolling and hit-testing O(1).

(The remainder of this file records recent refactors, upcoming work and
house-keeping guidelines.)

────────────────────────────────────────────────────────
Core refactor completed
────────────────────────────────────────────────────────
1. Introduced ui/cache.py
   • Unified NotebookCache holds both entry_data and layout_data.
   • Layout validation uses text_width only.
   • Fast-path row-height lookup (`row_height()`).
   • Public helpers: entry(), save_entry(), layout_valid(), store_layout(),
     row_height(), invalidate_layout_only(), invalidate_entry(),
     invalidate_entries(), invalidate_all().

2. Removed per-row cache dicts
   • Deleted `cache` field from ui/types.Row.
   • All modules now call NotebookCache instead of row.cache.

3. Updated modules
   • ui/layout.py — no row.cache; wraps use NotebookCache.
   • ui/row.py — rendering rewired to NotebookCache; fixed
     `GraphicsContext.DrawRectangle` calls (pass x,y,w,h, not wx.Rect).
   • ui/mouse.py — click logic uses NotebookCache (`layout().get("is_img")`).
   • ui/view.py — holds a single NotebookCache instance; resize calls
     `invalidate_layout_only()`; subtree ops call `invalidate_entries()`.
   • ui/paint.py — signature change already handled.

4. Bug fixes
   • Added `invalidate_all()` and `invalidate_entries()` to NotebookCache.
   • RowPainter.draw signature restored: now
     `draw(self, gc, rect, row, entry, *, selected=False)`.
   • Replaced every `gc.DrawRectangle(rect)` with
     `gc.DrawRectangle(rect.x, rect.y, rect.width, rect.height)`.

────────────────────────────────────────────────────────
Next technical tasks
────────────────────────────────────────────────────────
• Search repo for any lingering “.cache[” or `.get("_wrap_”` use (should be none).
• Profile scrolling & resize to verify fast-path gains.
• Add user-configurable thumbnail scale → include `thumb_scale`
  in `layout_data["computed_for"]`.
• Extend NotebookCache with LRU eviction once notebooks grow very large.
• Unit-test collapse/expand and incremental insert paths.

────────────────────────────────────────────────────────
Future feature ideas
────────────────────────────────────────────────────────
• Drag-and-drop image insertion (ties into thumbnail scaling).
• Global undo/redo spanning edits, moves, and collapses.
• Background IO thread for image thumbs to keep UI 100 % responsive.
• Optional disk-backed cache for low-memory environments.

────────────────────────────────────────────────────────
Housekeeping
────────────────────────────────────────────────────────
• Always pass primitive args to wx.GraphicsContext methods.
• Keep all font constants in ui/constants (size/family never change).
• Commit-edit helpers in NotebookCache ensure cache coherence.

────────────────────────────────────────────────────────
Repo structure
────────────────────────────────────────────────────────
whiskerpad$ tree
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
│   ├── image_add.png
│   └── page_add.png
├── __init__.py
├── ui
│   ├── cache.py
│   ├── constants.py
│   ├── cursor.py
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