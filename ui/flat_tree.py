# ui/flat_tree.py
'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''

from __future__ import annotations
from typing import List, Optional, Set
import wx
import shutil

from core.log import Log
from core.tree_utils import (
    add_sibling_after,
    move_entry_after, 
    indent_under_prev_sibling,
    outdent_to_parent_sibling,
    toggle_collapsed,
    set_collapsed,
    get_ancestors,
)
from core.tree import (
    create_node,
    load_entry,
    entry_dir,
    save_entry,
    get_root_ids,
    set_root_ids,
)
from ui.types import Row
from ui.scroll import soft_ensure_visible
from ui.model import update_tree_incremental
from ui.decorators import check_read_only


__all__ = ["FlatTree"]

class FlatTree:
    """
    Centralized API for all tree/row operations that maintains synchronization
    between the persistent tree structure and flat display list. Also handles
    view-dependent operations like ancestor expansion and navigation.
    """
    
    def __init__(self, view):
        self.view = view
        self.notebook_dir = view.notebook_dir
        # In-memory collapsed state for read-only mode.
        self._transient_collapsed = {}

    def is_read_only(self) -> bool:
        """Check if in read-only mode"""
        return self.view.is_read_only()

    def enter_read_only_mode(self):
        """Enter read-only mode - initialize transient collapsed state"""
        # Copy current persistent collapsed state to transient
        self._transient_collapsed = {}

        # Load current collapsed states from all visible entries
        for row in self.view._rows:
            try:
                entry = self.view.cache.entry(row.entry_id)
                is_collapsed = entry.get_collapsed(False)
            except Exception:
                # Skip entries that can't be loaded, don't break the entire operation
                continue
            if is_collapsed:
                self.transient_collapsed[row.entry_id] = True

    def exit_read_only_mode(self):
        """Exit read-only mode - discard transient state"""
        self._transient_collapsed = {}

    def is_collapsed(self, entry_id: str) -> bool:
        """Check if entry is collapsed, using transient state in read-only mode"""
        if self.view.is_read_only():
            # In read-only mode, check transient state first
            return self._transient_collapsed.get(entry_id, False)
        else:
            # Normal mode - check persistent state
            try:
                entry = self.view.cache.entry(entry_id)
                return entry.get("collapsed", False)
            except:
                return False

    @check_read_only
    def create_siblings_batch(self, target_id: str, count: int) -> List[str]:
        """Efficiently create multiple siblings (for PDF import)."""
        new_ids = []
        current_target = target_id
        
        for ndx in range(count):
            new_id = self.create_sibling_after(current_target)
            new_ids.append(new_id)
            current_target = new_id  # Chain insertions
            
        return new_ids

    @check_read_only
    def create_sibling_after(self, target_id: str) -> str:
        """Create sibling after target with proper descendant handling."""
        # 1. Create in persistent tree
        new_id = add_sibling_after(self.notebook_dir, target_id)
        if not new_id:
            raise RuntimeError("Failed to create sibling")
        
        # 2. Find target in flat list and calculate insertion position
        target_idx = self._find_row_index(target_id)
        if target_idx is None:
            # Fallback to full rebuild if target not found
            self.view.rebuild()
            return new_id
            
        # 3. Apply the critical descendant-aware insertion logic
        insert_idx = self._find_insertion_after_descendants(target_idx)
        level = self.view._rows[target_idx].level
        
        # 4. Insert into flat list
        new_row = Row(kind="node", entry_id=new_id, level=level)
        self.view._rows.insert(insert_idx, new_row)
        
        # 5. Update layout index and UI
        self._update_after_insertion(insert_idx, new_row)
        
        return new_id
    
    @check_read_only
    def create_child_under(
            self,
            parent_id: str,
            content: Optional[List[Dict[str, Any]]] = None,
            index: Optional[int] = None,
    ) -> str:
        """Create child under parent at specified index (or end)."""
        new_id = create_node(self.notebook_dir, parent_id=parent_id, content=content, insert_index=index)
        
        # Find insertion point in flat list
        parent_idx = self._find_row_index(parent_id)
        if parent_idx is None:
            self.view.rebuild()
            return new_id
            
        # Insert after parent (children immediately follow parent)
        parent_level = self.view._rows[parent_idx].level
        insert_idx = parent_idx + 1
        
        new_row = Row(kind="node", entry_id=new_id, level=parent_level + 1)
        self.view._rows.insert(insert_idx, new_row)
        
        self._update_after_insertion(insert_idx, new_row)
        return new_id

    def _is_target_descendant_of_source(self, source_id: str, target_id: str) -> bool:
        """Check if target is a descendant of source by walking up from target to root.
        Returns True if moving source to target would create a circular dependency."""

        # Walk up the tree from target toward root
        current_id = target_id

        while current_id:
            if current_id == source_id:
                # Found source in target's ancestry - would create cycle
                return True

            try:
                # Get parent of current entry
                entry = load_entry(self.notebook_dir, current_id)
                if not entry:
                    # Reached root or missing entry
                    break
                # May be None at root
                current_id = entry.get("parent_id")
            except Exception:
                # Entry is corrupted or missing, can't continue traversal
                break

        # Reached root without finding source - move is safe
        return False

    @check_read_only
    def move_entry_after(self, source_id: str, target_id: str) -> bool:
        """Move source entry to be after target."""
        if self._is_target_descendant_of_source(source_id, target_id):
            return False
        if not move_entry_after(self.notebook_dir, source_id, target_id):
            return False
            
        # Full rebuild for moves (simpler and safer)
        self.view.rebuild()
        return True
    
    @check_read_only
    def delete_entry(self, entry_id: str) -> bool:
        """
        Delete the entry and all descendants, including disk cleanup,
        cache invalidation, and view refresh.
        """
        # 1. Collect all descendants recursively
        to_delete = set()

        def _collect_descendants(eid: str):
            if eid in to_delete:
                return  # Avoid infinite loops
            to_delete.add(eid)
            try:
                entry = load_entry(self.notebook_dir, eid)
                for item in entry.get("items", []):
                    if isinstance(item, dict) and item.get("type") == "child":
                        child_id = item.get("id")
                        if isinstance(child_id, str):
                            _collect_descendants(child_id)
            except Exception as e:
                Log.debug(f"Failed to load descendants for {eid}: {e}")

        _collect_descendants(entry_id)

        # 2. Remove from parent's items or root_ids
        entry = load_entry(self.notebook_dir, entry_id)
        parent_id = entry.get("parent_id")

        if parent_id:
            # Remove from parent's items list
            parent = load_entry(self.notebook_dir, parent_id)
            items = parent.get("items", [])
            parent["items"] = [
                item for item in items
                if not (isinstance(item, dict) and 
                       item.get("type") == "child" and 
                       item.get("id") == entry_id)
            ]
            save_entry(self.notebook_dir, parent)
        else:
            # Remove from root_ids
            root_ids = get_root_ids(self.notebook_dir)
            if entry_id in root_ids:
                root_ids.remove(entry_id)
                set_root_ids(self.notebook_dir, root_ids)

        # 3. Delete all entry directories from disk
        for eid in to_delete:
            entry_path = entry_dir(self.notebook_dir, eid)
            if entry_path.exists():
                try:
                    shutil.rmtree(entry_path)
                except (OSError, PermissionError) as e:
                    Log.debug(f"Failed to delete entry directory {entry_path}: {e}")

        # 4. Invalidate cache for deleted entries
        self.view.cache.invalidate_entries(to_delete)

        # 5. Rebuild view to reflect changes
        self.view.rebuild()

        return True
    
    @check_read_only
    def indent_entry(self, entry_id: str) -> bool:
        """Indent entry under previous sibling."""
        if not indent_under_prev_sibling(self.notebook_dir, entry_id):
            return False
            
        # Use incremental update instead of full rebuild
        self._refresh_hierarchy_change(entry_id)
        return True
    
    @check_read_only
    def outdent_entry(self, entry_id: str) -> bool:
        """Outdent entry to parent level."""
        if not outdent_to_parent_sibling(self.notebook_dir, entry_id):
            return False
            
        self._refresh_hierarchy_change(entry_id)
        return True

    # ------------------------------------------------------------------ #
    # Collapse / Show / Toggle display of children.
    # ------------------------------------------------------------------ #

    def set_collapsed_state(self, entry_id: str, collapsed: bool) -> bool:
        """Set the collapsed state of an entry. Returns True if state changed."""
        current_state = self.is_collapsed(entry_id)
        if current_state == collapsed:
            return False  # No change needed

        if self.view.is_read_only():
            # Update transient state
            self._transient_collapsed[entry_id] = collapsed
        else:
            # Update persistent state
            set_collapsed(self.notebook_dir, entry_id, collapsed)

        # Do the full UI update (borrowed from toggle_collapse)
        self.view.invalidate_subtree_cache(entry_id)
        self.view._rows = update_tree_incremental(
            self.notebook_dir, self.view._rows, entry_id, self.view
        )
        self.view._index.rebuild(self.view, self.view._rows)
        self.view.SetVirtualSize((-1, self.view._index.content_height()))
        self.view._refresh_changed_area(entry_id)
        return True

    def expand_entry(self, entry_id: str) -> bool:
        """Expand a single entry. Returns True if expansion occurred."""
        return self.set_collapsed_state(entry_id, False)

    def collapse_entry(self, entry_id: str) -> bool:
        """Collapse a single entry. Returns True if collapse occurred."""
        return self.set_collapsed_state(entry_id, True)

    def toggle_collapse(self, entry_id: str) -> bool:
        """Toggle collapse state of entry."""
        current_state = self.is_collapsed(entry_id)
        return self.set_collapsed_state(entry_id, not current_state)
   
    def expand_ancestors(self, entry_id: str) -> bool:
        """Expand all ancestors of the target entry. Returns True if any were expanded."""
        expanded_any = False

        # Get all ancestor IDs using the existing helper from core.tree_utils
        ancestors = get_ancestors(self.notebook_dir, entry_id)

        # Expand each ancestor using the unified state setter
        for ancestor_id in ancestors:
            if self.set_collapsed_state(ancestor_id, False):
                expanded_any = True

        # No need for self.view.rebuild() since set_collapsed_state handles UI updates
        return expanded_any

    def expand_descendants(self, entry_id: str) -> bool:
        """Expand the starting node and all of its collapsed descendants."""
        expanded_any = False

        # Expand start node itself
        if self.expand_entry(entry_id):
            expanded_any = True

        # Expand all descendants
        start_idx = self._find_row_index(entry_id)
        if start_idx is None:
            return expanded_any

        start_level = self.view._rows[start_idx].level
        i = start_idx + 1
        while i < len(self.view._rows):
            row = self.view._rows[i]
            if row.level <= start_level:
                break
            if self.expand_entry(row.entry_id):
                expanded_any = True
            i += 1

        return expanded_any

    def ensure_entry_visible(self, entry_id: str) -> bool:
        """
        Expand ancestors and navigate to entry. Returns True if successful.
        This is the main function to use for reliable bookmark navigation.
        """
        # 1. Check if target entry exists
        try:
            target_entry = self.view.cache.entry(entry_id)
        except:
            return False

        # 2. Expand all collapsed ancestors
        expanded_any = self.expand_ancestors(entry_id)

        # 3. Rebuild view if we expanded anything
        if expanded_any:
            self.view.rebuild()

        # 4. Navigate to the target entry
        return self.view.select_entry(entry_id, ensure_visible=True)
    
    # ------------------------------------------------------------------ #
    # Helper methods
    # ------------------------------------------------------------------ #
    
    def _find_row_index(self, entry_id: str) -> Optional[int]:
        """Find row index for entry_id."""
        for i, row in enumerate(self.view._rows):
            if row.entry_id == entry_id:
                return i
        return None
    
    def _collect_descendants(self, start_idx: int) -> Set[str]:
        """Collect all descendant entry IDs starting from row index."""
        if start_idx >= len(self.view._rows):
            return set()
            
        descendants = {self.view._rows[start_idx].entry_id}
        start_level = self.view._rows[start_idx].level
        
        for i in range(start_idx + 1, len(self.view._rows)):
            if self.view._rows[i].level <= start_level:
                break
            descendants.add(self.view._rows[i].entry_id)
            
        return descendants
    
    @check_read_only
    def _update_after_insertion(self, insert_idx: int, new_row: Row):
        """Update layout and UI after row insertion."""
        self.view._index.insert_row(self.view, insert_idx, new_row)
        try:
            self.view.cache.invalidate_entry(new_row.entry_id)
        except Exception as e:
            Log.debug(f"Cache invalidation failed for {new_row.entry_id}: {e}")
        self.view.SetVirtualSize((-1, self.view._index.content_height()))
        self.view._refresh_from_row(insert_idx)
    
    def _refresh_hierarchy_change(self, entry_id: str):
        """Refresh after hierarchy change (indent/outdent)."""
        try:
            self.view.cache.invalidate_entry(entry_id)
        except Exception as e:
            Log.debug(f"Cache invalidation failed for {entry_id}: {e}")
        self.view.rebuild()  # Could be optimized to incremental later
        
        # Restore selection to the moved entry
        for i, row in enumerate(self.view._rows):
            if row.entry_id == entry_id:
                self.view._change_selection(i)
                soft_ensure_visible(self.view, i)
                break

    def _find_insertion_after_descendants(self, row_idx: int) -> int:
        """Find where to insert a sibling after this row and all its descendants."""
        if row_idx < 0 or row_idx >= len(self.view._rows):
            return len(self.view._rows)

        target_level = self.view._rows[row_idx].level
        search_idx = row_idx + 1

        # Skip over all descendants (rows with higher level than target)
        while search_idx < len(self.view._rows):
            if self.view._rows[search_idx].level <= target_level:
                return search_idx
            search_idx += 1

        return len(self.view._rows)
