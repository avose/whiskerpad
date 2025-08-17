from __future__ import annotations

import wx
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

__all__ = ["TextRun", "RichText", "EditState"]

@dataclass
class TextRun:
    """A single run of text with consistent formatting."""
    content: str
    bold: bool = False
    italic: bool = False
    color: Optional[str] = None  # hex color like "#ff0000"
    bg: Optional[str] = None     # hex background color

    def copy(self) -> TextRun:
        """Create a copy of this text run."""
        return TextRun(
            content=self.content,
            bold=self.bold,
            italic=self.italic,
            color=self.color,
            bg=self.bg
        )

    def same_format(self, other: TextRun) -> bool:
        """Check if this run has the same formatting as another."""
        return (self.bold == other.bold and
                self.italic == other.italic and
                self.color == other.color and
                self.bg == other.bg)

class RichText:
    """Rich text model consisting of formatted text runs."""
    
    def __init__(self, runs: Optional[List[TextRun]] = None):
        self.runs = runs or [TextRun("")]
        self._normalize()
    
    @classmethod
    def from_plain_text(cls, text: str) -> RichText:
        """Create rich text from plain text string."""
        return cls([TextRun(text)])
    
    @classmethod 
    def from_storage(cls, data: List[Dict[str, Any]]) -> RichText:
        """Create rich text from storage format."""
        runs = []
        for item in data:
            if isinstance(item, dict):
                runs.append(TextRun(
                    content=item.get("content", ""),
                    bold=item.get("bold", False),
                    italic=item.get("italic", False),
                    color=item.get("color"),
                    bg=item.get("bg")
                ))
        return cls(runs) if runs else cls()
    
    def to_storage(self) -> List[Dict[str, Any]]:
        """Convert to storage format."""
        result = []
        for run in self.runs:
            item = {"content": run.content}
            if run.bold:
                item["bold"] = True
            if run.italic:
                item["italic"] = True
            if run.color:
                item["color"] = run.color
            if run.bg:
                item["bg"] = run.bg
            result.append(item)
        return result
    
    def to_plain_text(self) -> str:
        """Extract plain text without formatting."""
        return "".join(run.content for run in self.runs)
    
    def char_count(self) -> int:
        """Get total character count."""
        return len(self.to_plain_text())
    
    def _normalize(self):
        """Merge adjacent runs with same formatting and remove empty runs."""
        if not self.runs:
            self.runs = [TextRun("")]
            return
            
        # Remove empty runs except if it's the only one
        self.runs = [run for run in self.runs if run.content or len(self.runs) == 1]
        
        if not self.runs:
            self.runs = [TextRun("")]
            return
        
        # Merge adjacent runs with same formatting
        merged = [self.runs[0]]
        for run in self.runs[1:]:
            if merged[-1].same_format(run):
                merged[-1].content += run.content
            else:
                merged.append(run)
        
        self.runs = merged
    
    def insert_text(self, position: int, text: str, formatting: Optional[TextRun] = None):
        """Insert text at the given character position with optional formatting."""
        if not text:
            return
            
        # Default formatting from adjacent character or plain
        if formatting is None:
            formatting = self._get_format_at_position(position)
        
        # Find which run contains this position
        char_pos = 0
        for i, run in enumerate(self.runs):
            run_len = len(run.content)
            
            if char_pos + run_len >= position:
                # Insert within this run
                pos_in_run = position - char_pos
                
                if formatting.same_format(run):
                    # Same formatting - just insert text
                    run.content = (run.content[:pos_in_run] + 
                                  text + 
                                  run.content[pos_in_run:])
                else:
                    # Different formatting - split the run
                    before = run.content[:pos_in_run]
                    after = run.content[pos_in_run:]
                    
                    # Replace current run with up to 3 new runs
                    new_runs = []
                    if before:
                        new_runs.append(TextRun(before, run.bold, run.italic, run.color, run.bg))
                    new_runs.append(TextRun(text, formatting.bold, formatting.italic, formatting.color, formatting.bg))
                    if after:
                        new_runs.append(TextRun(after, run.bold, run.italic, run.color, run.bg))
                    
                    self.runs[i:i+1] = new_runs
                
                self._normalize()
                return
            
            char_pos += run_len
        
        # Position is at the very end - append
        if formatting.same_format(self.runs[-1]):
            self.runs[-1].content += text
        else:
            self.runs.append(TextRun(text, formatting.bold, formatting.italic, formatting.color, formatting.bg))
        
        self._normalize()
    
    def delete_range(self, start: int, end: int):
        """Delete characters from start to end (exclusive)."""
        if start >= end or start >= self.char_count():
            return
            
        end = min(end, self.char_count())
        
        # Find runs that are affected
        char_pos = 0
        new_runs = []
        
        for run in self.runs:
            run_start = char_pos
            run_end = char_pos + len(run.content)
            
            if run_end <= start:
                # Run is completely before deletion - keep it
                new_runs.append(run)
            elif run_start >= end:
                # Run is completely after deletion - keep it
                new_runs.append(run)
            else:
                # Run is partially or completely within deletion range
                keep_before = max(0, start - run_start)
                keep_after_start = max(0, end - run_start)
                
                before_text = run.content[:keep_before] if keep_before > 0 else ""
                after_text = run.content[keep_after_start:] if keep_after_start < len(run.content) else ""
                
                if before_text:
                    new_runs.append(TextRun(before_text, run.bold, run.italic, run.color, run.bg))
                if after_text:
                    new_runs.append(TextRun(after_text, run.bold, run.italic, run.color, run.bg))
            
            char_pos = run_end
        
        self.runs = new_runs if new_runs else [TextRun("")]
        self._normalize()
    
    def _get_format_at_position(self, position: int) -> TextRun:
        """Get the formatting that should be used at the given position."""
        if position <= 0:
            return self.runs[0].copy() if self.runs else TextRun("")
        
        char_pos = 0
        for run in self.runs:
            if char_pos + len(run.content) >= position:
                return run.copy()
            char_pos += len(run.content)
        
        # Position is at the end - use last run's formatting
        return self.runs[-1].copy() if self.runs else TextRun("")

@dataclass
class EditState:
    """Manages all rich text editing state and operations."""
    
    # Core editing state
    active: bool = False
    row_idx: int = -1
    entry_id: str = ""
    cursor_pos: int = 0
    
    # Selection (for future implementation)
    selection_start: Optional[int] = None
    selection_end: Optional[int] = None
    
    # Cursor blinking
    cursor_visible: bool = True
    
    # Rich text being edited
    rich_text: Optional[RichText] = None
    
    def start_editing(self, row_idx: int, entry_id: str, rich_text: RichText, cursor_pos: int = 0):
        """Begin editing a specific row."""
        self.active = True
        self.row_idx = row_idx
        self.entry_id = entry_id
        self.rich_text = rich_text
        self.cursor_pos = min(cursor_pos, rich_text.char_count())
        self.cursor_visible = True
        self.selection_start = None
        self.selection_end = None
    
    def stop_editing(self) -> Optional[RichText]:
        """Stop editing and return final rich text."""
        final_text = self.rich_text
        self.active = False
        self.row_idx = -1
        self.entry_id = ""
        self.rich_text = None
        self.cursor_pos = 0
        self.selection_start = None
        self.selection_end = None
        return final_text
    
    def get_plain_text(self) -> str:
        """Get the current text as plain string."""
        return self.rich_text.to_plain_text() if self.rich_text else ""
    
    def insert_text(self, text: str):
        """Insert plain text at cursor position."""
        if self.rich_text and text:
            self.rich_text.insert_text(self.cursor_pos, text)
            self.cursor_pos += len(text)
    
    def delete_before_cursor(self):
        """Delete character before cursor (backspace)."""
        if self.rich_text and self.cursor_pos > 0:
            self.rich_text.delete_range(self.cursor_pos - 1, self.cursor_pos)
            self.cursor_pos -= 1
    
    def delete_after_cursor(self):
        """Delete character after cursor (delete key)."""
        if self.rich_text and self.cursor_pos < self.rich_text.char_count():
            self.rich_text.delete_range(self.cursor_pos, self.cursor_pos + 1)
    
    def move_cursor(self, delta: int):
        """Move cursor by delta characters."""
        if self.rich_text:
            self.cursor_pos = max(0, min(self.rich_text.char_count(), self.cursor_pos + delta))
    
    def set_cursor_position(self, position: int):
        """Set cursor to specific position."""
        if self.rich_text:
            self.cursor_pos = max(0, min(self.rich_text.char_count(), position))
