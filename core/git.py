# core/git.py
'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import defaultdict
import tempfile
import shutil

# GitPython imports
from git import Repo, GitCommandError, InvalidGitRepositoryError, BadName
from git.exc import GitError as GitPythonError

__all__ = [
    "CommitInfo",
    "GitError", 
    "init_repository",
    "setup_lfs_patterns",
    "create_commit",
    "get_commit_history",
    "checkout_commit",
    "return_to_head", 
    "reset_to_commit",
    "has_uncommitted_changes",
    "count_changed_entries",
    "is_git_available",
    "is_lfs_available",
    "consolidate_commits",
]

@dataclass
class CommitInfo:
    """Information about a Git commit"""
    hash: str
    date: str  # Format: "2025-09-08 20:45"
    message: str
    changed_entries: int

class GitError(Exception):
    """Git operation failed"""
    pass

def _get_repo(notebook_dir: str) -> Repo:
    """Get Repo instance with error handling"""
    try:
        return Repo(notebook_dir)
    except InvalidGitRepositoryError:
        raise GitError(f"Not a git repository: {notebook_dir}")
    except Exception as e:
        raise GitError(f"Failed to access repository: {e}")

def is_git_available() -> bool:
    """Check if Git is installed and GitPython can access it"""
    try:
        # Test by creating a temporary repo
        with tempfile.TemporaryDirectory() as temp_dir:
            Repo.init(temp_dir)
        return True
    except Exception:
        return False

def is_lfs_available() -> bool:
    """Check if Git LFS is available"""
    try:
        # Test LFS availability by trying to run git lfs version
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Repo.init(temp_dir)
            repo.git.lfs('version')
        return True
    except Exception:
        return False

def init_repository(notebook_dir: str) -> bool:
    """
    Initialize a Git repository if none exists.
    Returns True if repo exists or was created successfully.
    """
    notebook_path = Path(notebook_dir)
    git_dir = notebook_path / '.git'
    
    if git_dir.exists():
        try:
            repo = _get_repo(notebook_dir)
            # Ensure existing repo has at least one commit
            _ensure_initial_commit(repo)
            return True
        except GitError:
            pass
    
    try:
        repo = Repo.init(notebook_dir, initial_branch="master")
        _configure_user_if_needed(repo)
        
        # CRITICAL: Create initial commit for new repositories
        _ensure_initial_commit(repo)
        
        return True
    except Exception as e:
        raise GitError(f"Failed to initialize repository: {e}")

def _ensure_initial_commit(repo: Repo) -> None:
    """Ensure repository has at least one commit (creates initial commit if needed)."""
    try:
        # Check if HEAD exists (repository has commits)
        repo.head.commit
    except Exception:
        # No commits exist, create initial commit
        try:
            from git import Actor
            
            # Stage any existing files
            repo.git.add('.')
            
            # Create initial commit with proper author
            author = Actor("WhiskerPad User", "whiskerpad@localhost")
            repo.index.commit("Initial commit", author=author, committer=author)
            
        except Exception as e:
            # If initial commit fails, try empty commit
            try:
                author = Actor("WhiskerPad User", "whiskerpad@localhost") 
                repo.index.commit("Initial empty commit", author=author, committer=author)
            except Exception:
                # Last resort - let it fail, the repo will work for basic operations
                pass

def _ensure_initial_commit(repo: Repo) -> None:
    """Ensure repository has at least one commit (creates initial commit if needed)."""
    try:
        # Check if HEAD exists (repository has commits)
        repo.head.commit
    except Exception:
        # No commits exist, create initial commit
        try:
            from git import Actor
            
            # Stage any existing files
            repo.git.add('.')
            
            # Create initial commit with proper author
            author = Actor("WhiskerPad User", "whiskerpad@localhost")
            repo.index.commit("Initial commit", author=author, committer=author)
            
        except Exception as e:
            # If initial commit fails, try empty commit
            try:
                author = Actor("WhiskerPad User", "whiskerpad@localhost") 
                repo.index.commit("Initial empty commit", author=author, committer=author)
            except Exception:
                # Last resort - let it fail, the repo will work for basic operations
                pass

def _configure_user_if_needed(repo: Repo) -> None:
    """Set default Git user config if not already configured"""
    try:
        with repo.config_writer() as config:
            # Check if user.name exists
            try:
                config.get_value('user', 'name')
            except:
                config.set_value('user', 'name', 'WhiskerPad User')
            
            # Check if user.email exists  
            try:
                config.get_value('user', 'email')
            except:
                config.set_value('user', 'email', 'whiskerpad@localhost')
    except Exception:
        # Config errors shouldn't block repo creation
        pass

def setup_lfs_patterns(notebook_dir: str) -> bool:
    """
    Setup .gitattributes for Git LFS tracking of image files.
    Only creates if .gitattributes doesn't exist.
    """
    notebook_path = Path(notebook_dir)
    gitattributes_path = notebook_path / '.gitattributes'
    
    if gitattributes_path.exists():
        return True  # Already exists
    
    try:
        # Create .gitattributes with LFS patterns
        lfs_patterns = """# WhiskerPad Image Files - Tracked with Git LFS
*.png filter=lfs diff=lfs merge=lfs -text
*.jpg filter=lfs diff=lfs merge=lfs -text
*.jpeg filter=lfs diff=lfs merge=lfs -text
*.gif filter=lfs diff=lfs merge=lfs -text
*.bmp filter=lfs diff=lfs merge=lfs -text
*.tiff filter=lfs diff=lfs merge=lfs -text

# Entry directory images
entries/**/*.png filter=lfs diff=lfs merge=lfs -text
entries/**/*.jpg filter=lfs diff=lfs merge=lfs -text
entries/**/*.jpeg filter=lfs diff=lfs merge=lfs -text
entries/**/*.gif filter=lfs diff=lfs merge=lfs -text
"""
        
        with open(gitattributes_path, 'w', encoding='utf-8') as f:
            f.write(lfs_patterns)
        
        # Initialize LFS in this repo
        repo = _get_repo(notebook_dir)
        repo.git.lfs('install')
        
        return True
    except Exception as e:
        raise GitError(f"Failed to setup LFS patterns: {e}")

def create_commit(notebook_dir: str, message: str) -> bool:
    """
    Stage all changes and create a commit.
    Sets up LFS patterns on first commit if needed.
    """
    try:
        repo = _get_repo(notebook_dir)
        
        # Setup LFS patterns if this is the first commit
        if not (Path(notebook_dir) / '.gitattributes').exists():
            setup_lfs_patterns(notebook_dir)
        
        # Stage all changes
        repo.git.add('.')
        
        # Check if there are staged changes
        if not repo.index.diff("HEAD"):
            # No changes to commit
            return True
        
        # Create commit
        repo.index.commit(message)
        return True
        
    except GitCommandError as e:
        if 'nothing to commit' in str(e).lower():
            return True  # No changes to commit, but not an error
        raise GitError(f"Git commit failed: {e}")
    except Exception as e:
        raise GitError(f"Failed to create commit: {e}")

def has_uncommitted_changes(notebook_dir: str) -> bool:
    """
    Check if there are any uncommitted changes (staged or unstaged).
    Returns True if changes exist, False if working directory is clean.
    """
    try:
        repo = _get_repo(notebook_dir)
        return repo.is_dirty(untracked_files=True)
    except Exception as e:
        raise GitError(f"Failed to check for changes: {e}")

def count_changed_entries(notebook_dir: str, commit_hash: str = 'HEAD') -> int:
    """
    Count how many entry JSON files changed in the given commit.
    Returns 0 if unable to determine.
    """
    try:
        repo = _get_repo(notebook_dir)
        commit = repo.commit(commit_hash)
        
        # Get diff against parent (or empty tree for first commit)
        if commit.parents:
            diffs = commit.parents[0].diff(commit)
        else:
            diffs = commit.diff(None, create_patch=True)
        
        # Count entry JSON files
        entry_files = [
            diff.a_path or diff.b_path for diff in diffs
            if (diff.a_path or diff.b_path or '').startswith('entries/') and 
               (diff.a_path or diff.b_path or '').endswith('/entry.json')
        ]
        
        return len(entry_files)
    except Exception:
        return 0

def get_commit_history(notebook_dir: str, limit: int = 100) -> List[CommitInfo]:
    """
    Get commit history with entry change counts.
    Returns list sorted by newest first.
    """
    try:
        repo = _get_repo(notebook_dir)
        
        commits = []
        for commit in repo.iter_commits(max_count=limit):
            # Format date as "2025-09-08 20:45"
            commit_date = commit.committed_datetime.strftime('%Y-%m-%d %H:%M')
            
            # Count changed entries for this commit
            changed_entries = count_changed_entries(notebook_dir, commit.hexsha)
            
            commits.append(CommitInfo(
                hash=commit.hexsha,
                date=commit_date,
                message=commit.message.strip(),
                changed_entries=changed_entries
            ))
        
        return commits
        
    except GitPythonError as e:
        if 'does not have any commits yet' in str(e).lower():
            return []  # Empty repo
        raise GitError(f"Failed to get commit history: {e}")
    except Exception as e:
        raise GitError(f"Failed to get commit history: {e}")

def checkout_commit(notebook_dir: str, commit_hash: str) -> bool:
    """
    Checkout a specific commit (for read-only viewing).
    Should only be called when repository is in clean state.
    """
    try:
        repo = _get_repo(notebook_dir)
        repo.git.checkout(commit_hash)
        return True
    except GitCommandError as e:
        raise GitError(f"Git checkout failed: {e}")
    except Exception as e:
        raise GitError(f"Failed to checkout commit: {e}")

def return_to_head(notebook_dir: str) -> bool:
    """
    Return to the latest commit (HEAD of default branch).
    Tries 'main' first, then 'master' as fallback.
    """
    try:
        repo = _get_repo(notebook_dir)
        
        # Determine default branch name
        for branch_name in ['main', 'master']:
            try:
                repo.git.checkout(branch_name)
                return True
            except GitCommandError:
                continue
        
        # If neither main nor master worked, try HEAD directly
        try:
            repo.git.checkout('HEAD')
            return True
        except GitCommandError as e:
            raise GitError(f"Unable to return to HEAD: {e}")
            
    except GitError:
        raise
    except Exception as e:
        raise GitError(f"Failed to return to HEAD: {e}")

def reset_to_commit(notebook_dir: str, commit_hash: str) -> bool:
    """
    Hard reset to the specified commit.
    WARNING: This is a destructive operation that will lose commits after the target.
    """
    try:
        repo = _get_repo(notebook_dir)
        repo.git.reset('--hard', commit_hash)
        return True
    except GitCommandError as e:
        raise GitError(f"Git reset failed: {e}")
    except Exception as e:
        raise GitError(f"Failed to reset to commit: {e}")

def consolidate_commits(notebook_dir: str) -> bool:
    """
    Consolidate old commits according to retention policy.
    Keeps recent commits at full granularity, older ones get squashed.
    """
    try:
        commits = get_commit_history(notebook_dir, limit=1000)
        
        if len(commits) <= 12:
            return True  # Not enough commits to consolidate
        
        # Group commits by time buckets (keep existing logic)
        consolidation_plan = _create_consolidation_plan(commits)
        
        if not consolidation_plan:
            return True  # Nothing to consolidate
        
        # Execute consolidation using GitPython
        return _execute_consolidation_gitpython(notebook_dir, consolidation_plan)
        
    except Exception as e:
        raise GitError(f"Failed to consolidate commits: {e}")

def _create_consolidation_plan(commits: List[CommitInfo]) -> List[dict]:
    """
    Create a plan for which commits to consolidate.
    Returns list of consolidation groups.
    """
    now = datetime.now()
    consolidation_groups = []
    
    # Skip the most recent 12 commits (keep full granularity)
    if len(commits) <= 12:
        return []
    
    older_commits = commits[12:]  # Skip recent 12
    
    # Group commits by time buckets
    hourly_buckets = defaultdict(list)
    daily_buckets = defaultdict(list)
    monthly_buckets = defaultdict(list)
    yearly_buckets = defaultdict(list)
    
    for commit in older_commits:
        commit_date = _parse_commit_date(commit.date)
        age = now - commit_date
        
        if age <= timedelta(days=1):
            # Last 24 hours: group by hour
            hour_key = commit_date.strftime('%Y-%m-%d %H')
            hourly_buckets[hour_key].append(commit)
        elif age <= timedelta(days=30):
            # Last 30 days: group by day
            day_key = commit_date.strftime('%Y-%m-%d')
            daily_buckets[day_key].append(commit)
        elif age <= timedelta(days=365):
            # Last 12 months: group by month
            month_key = commit_date.strftime('%Y-%m')
            monthly_buckets[month_key].append(commit)
        else:
            # Older than 1 year: group by year
            year_key = commit_date.strftime('%Y')
            yearly_buckets[year_key].append(commit)
    
    # Create consolidation groups (only for buckets with multiple commits)
    for bucket_commits in [hourly_buckets, daily_buckets, monthly_buckets, yearly_buckets]:
        for time_commits in bucket_commits.values():
            if len(time_commits) > 1:
                consolidation_groups.append({
                    'commits': time_commits,
                    'new_message': f"Consolidated: {len(time_commits)} commits",
                })
    
    return consolidation_groups

def _parse_commit_date(date_str: str) -> datetime:
    """Parse commit date string to datetime object"""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d %H:%M')
    except ValueError:
        return datetime.now()

def _execute_consolidation_gitpython(notebook_dir: str, consolidation_plan: List[dict]) -> bool:
    """
    Execute consolidation using GitPython's reset/commit approach.
    This is simpler than interactive rebase but achieves similar results.
    """
    try:
        repo = _get_repo(notebook_dir)
        
        for group in consolidation_plan:
            commits_to_squash = group['commits']
            new_message = group['new_message']
            
            if len(commits_to_squash) < 2:
                continue
            
            # Sort commits by date (newest first)
            commits_to_squash.sort(key=lambda c: c.date, reverse=True)
            
            # Simple consolidation: reset to oldest commit, then create new commit with latest state
            oldest_commit = commits_to_squash[-1]
            newest_commit = commits_to_squash[0]
            
            try:
                # Get the tree state from the newest commit
                newest_tree = repo.commit(newest_commit.hash).tree
                
                # Reset to the commit before the oldest one
                if len(repo.commit(oldest_commit.hash).parents) > 0:
                    parent_commit = repo.commit(oldest_commit.hash).parents[0]
                    
                    # Create a new commit with the consolidated message
                    repo.git.reset('--soft', parent_commit.hexsha)
                    repo.index.commit(new_message)
                    
            except Exception:
                # If consolidation fails for this group, continue with others
                continue
        
        return True
        
    except Exception as e:
        raise GitError(f"Failed to execute consolidation: {e}")
