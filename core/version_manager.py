# core/version_manager.py

from __future__ import annotations

from typing import List, Optional
import threading
import time

from core.log import Log
from core.git import (
    CommitInfo,
    GitError,
    init_repository,
    create_commit,
    get_commit_history,
    checkout_commit,
    return_to_head,
    reset_to_commit,
    consolidate_commits,
    has_uncommitted_changes,
    count_changed_entries,
    is_git_available,
    is_lfs_available,
)

__all__ = ["VersionManager"]

class VersionManager:
    """
    High-Level Version Control Coordinator for WhiskerPad Notebooks
    
    ARCHITECTURE OVERVIEW:
    =====================
    
    This class serves as the central coordinator for WhiskerPad's "time machine" functionality.
    It manages the lifecycle of notebook versioning through a simple state machine:
    
    NORMAL MODE → HISTORY BROWSING MODE → [Optional: REWIND] → NORMAL MODE
    
    KEY DESIGN PRINCIPLES:
    - Never calls Git commands directly - only uses functions from core.git
    - Maintains mutual exclusion: history browsing = read-only mode
    - Always commits changes before entering history mode (prevents conflicts)
    - Thread-safe through internal locking for concurrent notebook access
    
    STATE MANAGEMENT:
    - Each notebook directory has its own VersionManager.NotebookState
    - State tracks commit timing, change counts, and history browsing mode
    - Auto-commits happen every 5+ minutes when changes are detected
    - Manual checkpoints can be triggered by user at any time
    
    HISTORY BROWSING WORKFLOW:
    1. User opens history browser → auto-commit current changes → enter read-only mode
    2. User selects historical commit → temporary checkout → main UI shows old state  
    3. User can "rewind" (destructive) → hard reset + return to normal mode
    4. User closes browser → return to HEAD → exit read-only mode
    
    COMMIT CONSOLIDATION:
    - Automatically consolidates old commits to prevent unbounded growth
    - Recent commits kept at full granularity, older ones get squashed
    - Uses time-based retention policy (minutes→hours→days→months→years)
    
    ERROR HANDLING:
    - Git/LFS availability checked before operations
    - Auto-commit failures are logged but don't block user workflow
    - Manual operations raise GitError for UI to handle appropriately
    """

    def __init__(self, io_worker):
        """
        Initialize the VersionManager.
        
        Args:
            io_worker: Background thread pool for async Git operations
        """
        self.io_worker = io_worker
        self._notebook_states = {}  # notebook_dir -> NotebookState
        self._lock = threading.Lock()  # Protects _notebook_states access
        Log.debug("VersionManager initialized", 1)

    class NotebookState:
        """
        Internal state tracking for a single notebook's versioning status.
        
        This encapsulates all the information needed to coordinate versioning
        operations for one notebook directory, including timing, change tracking,
        and read-only mode state.
        """
        
        def __init__(self):
            self.last_commit_time = 0.0        # Unix timestamp of last commit
            self.changes_since_commit = 0      # Change counter (for future use)
            self.in_history_mode = False       # True = history browser open, read-only
            self.readonly_commit = None        # Current commit hash being viewed (or None)

    def _get_state(self, notebook_dir: str) -> NotebookState:
        """
        Get or create the state object for a notebook directory.
        Thread-safe through internal locking.
        """
        with self._lock:
            state = self._notebook_states.get(notebook_dir)
            if not state:
                state = VersionManager.NotebookState()
                self._notebook_states[notebook_dir] = state
            return state

    def ensure_repository(self, notebook_dir: str):
        """
        Ensure that the notebook directory is properly set up as a Git repository
        with Git LFS configured for image files.
        
        This is called automatically by other methods but can also be called
        explicitly during notebook initialization.
        
        Raises:
            GitError: If Git/LFS is not available or initialization fails
        """
        # Validate prerequisites first
        if not is_git_available():
            raise GitError(
                "Git is not installed or not found in the system path.\n"
                "Please install Git before using version control features."
            )
        
        if not is_lfs_available():
            raise GitError(
                "Git LFS is not installed or not found in the system path.\n"
                "Please install Git LFS before using version control features."
            )

        # Initialize repository - this is idempotent (safe to call multiple times)
        if not init_repository(notebook_dir):
            raise GitError(f"Failed to initialize Git repository at {notebook_dir}")

    def note_change(self, notebook_dir: str):
        """
        Signal that content has changed in the notebook.
        
        This is called by the NotebookCache when entries are saved.
        It's the minimal hook point that triggers auto-commit consideration.
        """
        state = self._get_state(notebook_dir)
        
        with self._lock:
            state.changes_since_commit += 1
        Log.debug(f"Change noted. (total: {state.changes_since_commit})", 100)
        
        # Consider auto-commit (runs async check)
        self.auto_commit_if_needed(notebook_dir)

    def auto_commit_if_needed(self, notebook_dir: str):
        """
        Check if conditions are met for an automatic commit and trigger one if so.
        
        Auto-commit happens when:
        - At least 5 minutes have passed since last commit
        - Notebook is not in history browsing mode (read-only)
        - There are actual changes to commit (detected by git diff)
        
        This method runs asynchronously and does not block the UI.
        Failures are logged but do not interrupt user workflow.
        """
        state = self._get_state(notebook_dir)

        # No commits allowed in read-only history browsing mode
        if state.in_history_mode:
            Log.debug(f"Auto-commit skipped (in history mode)", 1)
            return

        try:
            # Check time threshold (5 minutes minimum between auto-commits)
            now = time.time()
            time_since_commit = now - state.last_commit_time
            if time_since_commit < 300:  # 5 minutes = 300 seconds
                Log.debug(
                    f"Auto-commit skipped "
                    "(time threshold not met: {time_since_commit:.1f}s)",
                    1
                )
                return

            # Generate commit message by counting changed entries
            commit_msg = self._generate_auto_commit_message(notebook_dir)
            if not commit_msg:
                Log.debug(f"Auto-commit skipped (no changes detected)", 1)
                return  # No changes detected, skip commit

            # Schedule commit on background thread to avoid blocking UI
            Log.debug(f"Scheduling auto-commit: {commit_msg}", 1)
            def async_commit():
                try:
                    create_commit(notebook_dir, commit_msg)
                    with self._lock:
                        state.last_commit_time = time.time()
                        state.changes_since_commit = 0
                    Log.debug(f"Auto-commit successful", 1)
                except GitError as e:
                    # Log but don't raise - auto-commit failures shouldn't break workflow
                    Log.debug(f"Auto-commit failed: {e}", 0)
                    
            self.io_worker.submit(async_commit)

        except Exception as e:
            # Catch-all to ensure auto-commit never crashes the application
            Log.debug(f"Auto-commit check failed: {e}", 0)

    def _generate_auto_commit_message(self, notebook_dir: str) -> Optional[str]:
        """
        Generate an appropriate commit message for auto-commits.
        Returns None if no changes detected (prevents unnecessary commits).
        """
        try:
            # Check if there are any uncommitted changes first
            if not has_uncommitted_changes(notebook_dir):
                return None  # No changes to commit

            # Count entry files that have changed
            changed_count = count_changed_entries(notebook_dir)

            if changed_count == 0:
                return "Auto-save: changes detected"
            else:
                entry_word = "entry" if changed_count == 1 else "entries" 
                return f"Auto-save: {changed_count} {entry_word} changed"

        except GitError:
            # If we can't determine changes, skip the commit
            return None

    def create_manual_checkpoint(self, notebook_dir: str, message: str):
        """
        Create a manual checkpoint commit with a user-provided message.

        Raises:
            GitError: If repository is in history mode or commit fails
            ValueError: If no changes to commit
        """
        state = self._get_state(notebook_dir)

        # Cannot create checkpoints while in read-only history browsing mode
        if state.in_history_mode:
            raise GitError("Cannot create checkpoint while history browser is open.")

        # Ensure repository is properly initialized
        self.ensure_repository(notebook_dir)

        # NEW: Check for uncommitted changes first
        try:
            if not has_uncommitted_changes(notebook_dir):
                raise ValueError("No changes to commit")
        except GitError:
            # If we can't check changes, proceed anyway
            Log.debug(f"Could not check for changes, proceeding anyway", 1)

        # Perform commit synchronously (blocking operation)
        # User expects immediate feedback for manual checkpoints
        create_commit(notebook_dir, f"Checkpoint: {message}")

        # Update state after successful commit
        with self._lock:
            state.last_commit_time = time.time()
            state.changes_since_commit = 0
        Log.debug(f"Manual checkpoint created: {message}", 1)

    def open_history_browser(self, notebook_dir: str) -> List[CommitInfo]:
        """
        Prepare for history browsing by entering read-only mode.
        
        CRITICAL WORKFLOW:
        1. Auto-commit any current changes (prevents data loss)
        2. Switch notebook to read-only mode (prevents new commits)
        3. Return commit history for UI display
        
        This ensures that:
        - No work can be lost (everything is committed before browsing)
        - No conflicts can occur (read-only prevents concurrent changes)
        - History is complete and current (includes any uncommitted work)
        
        Returns:
            List of CommitInfo objects for display in history browser UI
            
        Raises:
            GitError: If repository initialization fails
        """
        Log.debug(f"Opening history browser.", 1)
        state = self._get_state(notebook_dir)
        
        # If already in history mode, just return current history
        if state.in_history_mode:
            Log.debug(f"History browser already open.", 1)
            return get_commit_history(notebook_dir)

        # Ensure repository is properly set up
        self.ensure_repository(notebook_dir)

        # CRITICAL: Commit any current changes before entering read-only mode
        # This prevents data loss and ensures complete history
        commit_msg = self._generate_auto_commit_message(notebook_dir)
        if commit_msg:
            Log.debug(f"Auto-saving before history view.", 1)
            create_commit(notebook_dir, "Auto-save before history view")

        # Enter read-only mode - no new commits allowed while browser is open
        with self._lock:
            state.in_history_mode = True
            state.readonly_commit = None  # Start viewing HEAD

        # Return commit history for UI display
        Log.debug(f"History browser opened (read-only mode active)", 1)
        return get_commit_history(notebook_dir)

    def view_historical_commit(self, notebook_dir: str, commit_hash: str) -> bool:
        """
        Checkout a specific commit for historical viewing (read-only).
        
        This temporarily changes the working directory to show the notebook
        as it existed at the specified commit. The main UI will trigger a
        full rebuild() to display the historical state.
        
        Args:
            commit_hash: Git commit hash to checkout
            
        Returns:
            True if checkout successful, False otherwise
            
        Raises:
            GitError: If not currently in history browsing mode
        """
        Log.debug(f"Viewing historical commit {commit_hash[:8]}", 1)
        state = self._get_state(notebook_dir)
        
        if not state.in_history_mode:
            raise GitError("History browser must be open to view historical commits.")

        # Checkout the specified commit
        success = checkout_commit(notebook_dir, commit_hash)
        
        if success:
            with self._lock:
                state.readonly_commit = commit_hash
            Log.debug(f"Successfully checked out commit {commit_hash[:8]}", 1)
        else:
            Log.debug(f"Failed to checkout commit {commit_hash[:8]}", 0)
                
        return success

    def close_history_browser(self, notebook_dir: str) -> bool:
        """
        Exit history browsing mode and return to normal editing.
        
        WORKFLOW:
        1. Checkout the latest commit (HEAD) to restore current state
        2. Exit read-only mode to re-enable editing
        3. Main UI will trigger rebuild() to show current state
        
        Returns:
            True if successful return to normal mode
        """
        Log.debug(f"Closing history browser.", 1)
        state = self._get_state(notebook_dir)

        if not state.in_history_mode:
            Log.debug(f"History browser already closed.", 1)
            return True  # Already in normal mode

        # Return to the latest commit (HEAD of main/master branch)
        success = return_to_head(notebook_dir)
        
        if success:
            with self._lock:
                state.readonly_commit = None
                state.in_history_mode = False
            Log.debug(f"History browser closed (editing mode restored)", 1)
        else:
            Log.debug(f"Failed to return to HEAD.", 0)

        return success

    def consolidate_history(self, notebook_dir: str) -> bool:
        """
        Trigger commit consolidation to keep Git history manageable.
        
        This uses the time-based retention policy to squash old commits:
        - Recent commits: Keep all (full granularity)
        - Older commits: Progressive consolidation by time buckets
        
        This should be called periodically (e.g., daily) or after significant
        numbers of commits accumulate.
        
        Returns:
            True if consolidation successful or not needed
        """
        Log.debug(f"Starting history consolidation for.", 1)

        try:
            success = consolidate_commits(notebook_dir)
            if success:
                Log.debug(f"History consolidation completed.", 1)
            else:
                Log.debug(f"History consolidation not needed.", 1)
            return success
        except GitError as e:
            Log.debug(f"History consolidation failed: {e}", 0)
            return False

    def is_in_history_mode(self, notebook_dir: str) -> bool:
        """
        Check if the specified notebook is currently in history browsing mode.
        
        This can be used by the UI to determine whether to show read-only
        indicators and disable editing controls.
        """
        state = self._get_state(notebook_dir)
        return state.in_history_mode

    def get_current_commit(self, notebook_dir: str) -> Optional[str]:
        """
        Get the commit hash currently being viewed (for read-only mode).
        
        Returns None if in normal editing mode, or the commit hash if
        viewing a historical state.
        """
        state = self._get_state(notebook_dir)
        return state.readonly_commit if state.in_history_mode else None
