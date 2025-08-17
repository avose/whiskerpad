# WhiskerPad — Developer Notes

Last updated: 2025-08-16 (America/Vancouver). Target env: Python 3.12, wxPython 4.2.3 (phoenix, GTK3).

WhiskerPad is a lightweight, local-first notebook with an outline UX. The notebook is a tree of entries, and each entry’s content is its text (stored as Quill-style ops). Editing is inline in the outline; no separate dialog.

These notes cover the architecture, data model, UI behavior, dev workflow, and the collaboration conventions for patching.

-------------------------------------------------------------------------------

## Quickstart

- Run
    python3 whiskerpad.py

- wx requirement: ≥ 4.2.3 (phoenix). Enforced at startup.

- Create/Open: toolbar → “Open Notebook” (validates existing folder or creates fresh one).

- Add child: toolbar → “Add Child”.

- Edit:
    • Single-click to the **right** of the caret → inline editor opens.
    • Ctrl+Enter or click outside (including the date gutter) → commit.
    • Esc → cancel (no changes).
    • Single-click **on/left of caret** → toggle collapse/expand (only if node has children).
    • Single-click **in left date gutter** → non-interactive no-op (but will still commit any open editor).

- Scroll: vertical scrollbar is always available.

-------------------------------------------------------------------------------

## Repository layout (key files)

whiskerpad/
  whiskerpad.py                # entry script (calls whiskerpad.app:main)
  app.py                       # wx.App bootstrap; version guard; shows MainFrame
  io_worker.py                 # background worker (UI-safe callbacks)
  storage.py                   # ensure_notebook(path,..) for create/open/validate
  tree.py                      # notebook model + JSON I/O (see Data Model)
  ui/
    main_frame.py              # frame, menu, toolbar wiring, embeds NotePanel
    top_toolbar.py             # Open, Add Child (icons via ui.icons/wpIcons)
    notebook_view.py           # NotebookView: outline renderer + inline editor
    notebook_text.py           # text helpers: flatten_ops, wrapping, measuring
    notebook_hit_test.py       # row rects, hit testing, caret-zone checks
    icons.py                   # icon registry (Silk icons)
  icons/
    ...                        # Silk icons used by wpIcons

.gitignore contains:
  *~
  **/__pycache__/

-------------------------------------------------------------------------------

## Data model (on disk)

Notebook directory layout:

<notebook-root>/
  notebook.json                # { name, root_ids: [...] }
  entries/<id>/entry.json      # one file per entry
  _trash/                      # reserved (not used yet)
  _cache/                      # reserved (not used yet)

notebook.json

{
  "name": "My Notebook",
  "root_ids": ["17c629e9ce74", "..."]
}

entries/<id>/entry.json (current shape)

{
  "id": "17c629e9ce74",
  "title": "New Entry",
  "parent_id": null,               // or parent entry id
  "collapsed": false,
  "created_ts": 1723830000,
  "updated_ts": 1723830000,        // auto-bumped on save_entry()
  "last_edit_ts": 1723830456,      // set ONLY when ops (content) changes
  "ops": [                         // OPTIONAL; if empty/absent, UI falls back to 'title'
    {"insert": "Hello world\n"}
  ],
  "items": [
    {"type": "child", "id": "abcd1234ef56"},
    {"type": "rich", "id": "blk-...", "ops": [{"insert": "legacy block\n"}]}
  ]
}

Notes
- Nodes-as-text: each entry owns its text via ops. We still render legacy rich blocks (read-only) but no longer create new ones.
- Timestamps
  • created_ts: set at creation.
  • updated_ts: set on any save_entry() (structural OR content).
  • last_edit_ts: set ONLY when ops (content) changes during inline commit. The UI date gutter displays this (fallback to created_ts).

Key APIs (tree.py)
- get_root_ids(path), set_root_ids(path, ids)
- create_node(nb_dir, parent_id=None, title="New Entry", insert_index=None)
- load_entry(nb_dir, entry_id), save_entry(nb_dir, entry_dict)
- add_rich_block(...) exists for legacy compatibility (not used by new UI)

-------------------------------------------------------------------------------

## UI / UX (current behavior)

NotebookView (ui/notebook_view.py)
- Virtualized outline: wx.VListBox (owner-drawn, wrapped text).
- Left date gutter:
  • DATE_COL_W = 88 px; light grey background with a thin divider.
  • Shows ISO date (YYYY-MM-DD) from last_edit_ts, fallback to created_ts.
  • Non-interactive: a click here does not toggle or edit, but WILL commit an open editor first.
- Caret & indent:
  • Caret glyph (▶/▼/•) is aligned with the first line (top) of the node, not vertically centered.
  • Click on/left of caret toggles collapse, but only if the node has children.
- Inline editor:
  • Single-click to the right of the caret opens a wx.TextCtrl (TE_MULTILINE | TE_PROCESS_TAB).
  • Commit: Ctrl+Enter, or click anywhere outside the editor.
  • Cancel: Esc.
  • On commit, text is diffed vs the current ops; if changed, ops is updated and last_edit_ts is set.
- Wrapping & height:
  • Measurement trims a single trailing newline to avoid phantom blank lines.
  • Row height (ROW_H) initialized from font metrics (one text line + padding).
  • Vertical scrollbar is always visible (style + ALWAYS_SHOW_SB).
- Resize:
  • Re-measures wrap on width change and repositions any active editor overlay.

Top toolbar (ui/top_toolbar.py)
- Buttons:
  • Open Notebook (application_get)
  • Add Child (application_side_expand)
- “Add Text” button was removed (nodes are text).

MainFrame (ui/main_frame.py)
- Menubar: New (create), Open, Exit.
- After open/create, ensures at least one root entry and shows it.
- “Add Child” expands the parent, creates a child, reloads the view, and selects it.

-------------------------------------------------------------------------------

## Development workflow & conventions

Critical collaboration rules
- If anything is unclear, **please ask** before patching. Ask for:
  • the exact file contents (provide sed -n 'a,bp' file | nl -ba),
  • the exact command(s) run and full stdout/stderr,
  • screenshots are fine but text logs are better.
- One instruction at a time for chains (install/config/run). Wait for confirmation at each step.
- Small, surgical patches; commit after each user-visible change or fix.
- Prefer single-file rewrites when safer/clearer than a regex edit.
- No migrations unless specifically requested (we test on fresh notebooks during MVP).

Coding structure
- Keep NotebookView lean by factoring helpers:
  • ui/notebook_text.py → flatten_ops, wrap_lines, measure_wrapped
  • ui/notebook_hit_test.py → item_rect, hit_test, caret_hit
- UI changes should come with clear click/keyboard contracts and platform-safe wx patterns (focus, flicker, resize).

Git habits
- Keep “git add …” and “git commit -m …” as separate commands.
- Commit message style: user-visible change first, internal detail second.

-------------------------------------------------------------------------------

## Troubleshooting (common/solved)

- No scrollbar → enabled wx.VSCROLL | wx.WANTS_CHARS and ALWAYS_SHOW_SB.
- Two-line “New Entry” rows → stopped forcing newline on commit; measurement trims a single trailing newline.
- Editor didn’t commit on click-away → _on_left_down commits before handling gutter/no-op.
- Caret was vertically centered → now drawn at top line (rect.y + PADDING).
- Spacebar didn’t insert space (early dev) → ensured editor gets key events.

If you hit a regression:
1) Reproduce and include exact traceback or description.
2) Paste the relevant file segment with line numbers.
3) We’ll patch in a small step and validate.

-------------------------------------------------------------------------------

## Short roadmap

Polish
- Keyboard polish (e.g., Tab behavior for indent/outdent).
- Configurable date gutter format (keep ISO default).
- Hover affordance for caret zone.

Editing & structure
- Drag-and-drop reordering.
- Multi-select operations (collapse/expand group, move group).
- Undo/Redo stack (content first; then structure).
- Autosave debounce and dirty indicators.

Rendering
- Richer text phase (switch to StyledTextCtrl or RichTextCtrl path; keep wrapping/measure abstractions).

Persistence
- Export/Import (Markdown bundle, JSON).
- Trash/restore semantics.

-------------------------------------------------------------------------------

## Sanity test sequence

1. Create a notebook → verify folder structure and a single root.
2. Add several children → scrollbar appears; caret toggles expand/collapse as expected.
3. Inline edit nodes → Ctrl+Enter commits; click-away commits; Esc cancels.
4. Date gutter shows created date first; after editing, shows last edit date.
5. Resize window → editor overlay repositions correctly; wrapped text re-measures.
6. Empty text → renders as a single line; no phantom blank line.

-------------------------------------------------------------------------------

## When opening a new chat

Please include:
- The exact command(s) you ran and full stdout/stderr (use code blocks).
- The specific file/lines you’re referring to (use sed -n 'a,bp' file | nl -ba).
- What you expected vs what happened.

Remember: if anything is ambiguous, **ask first**. We will go slowly and think through the change before writing code.
