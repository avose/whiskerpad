from __future__ import annotations

import wx
from typing import Tuple, List, Optional
from ui.edit_state import RichText, TextRun

__all__ = [
    "char_pos_from_pixel", 
    "pixel_pos_from_char", 
    "CursorRenderer"
]

def char_pos_from_pixel(
    rich_text: RichText, 
    click_x: int, 
    click_y: int,
    text_area_x: int,
    text_area_y: int,
    available_width: int,
    dc: wx.DC,
    font_normal: wx.Font,
    font_bold: wx.Font,
    line_height: int
) -> int:
    """
    Convert pixel coordinates to character position in rich text.
    
    Args:
        rich_text: The rich text to analyze
        click_x, click_y: Mouse click coordinates
        text_area_x, text_area_y: Top-left of text area
        available_width: Width available for text wrapping
        dc: Device context for text measurement
        font_normal, font_bold: Fonts for normal and bold text
        line_height: Height of each line
        
    Returns:
        Character position (0-based) in the rich text
    """
    if not rich_text or not rich_text.runs:
        return 0
    
    # Calculate which line was clicked
    click_y_in_text = click_y - text_area_y
    if click_y_in_text < 0:
        return 0
    
    line_idx = max(0, int(click_y_in_text // line_height))
    
    # Wrap the text to get line breaks
    wrapped_lines = _wrap_rich_text(rich_text, available_width, dc, font_normal, font_bold)
    
    if line_idx >= len(wrapped_lines):
        # Click below last line - position at end
        return rich_text.char_count()
    
    # Find character position within the clicked line
    line_info = wrapped_lines[line_idx]
    click_x_in_line = click_x - text_area_x
    
    if click_x_in_line <= 0:
        return line_info['start_char']
    
    # Measure text segments until we find where the click lands
    char_pos = line_info['start_char']
    x_pos = 0
    
    for segment in line_info['segments']:
        segment_width = segment['width']
        
        if x_pos + segment_width >= click_x_in_line:
            # Click is within this segment
            return char_pos + _find_char_in_segment(
                segment, click_x_in_line - x_pos, dc, font_normal, font_bold
            )
        
        x_pos += segment_width
        char_pos += len(segment['text'])
    
    # Click is past the end of the line
    return line_info['end_char']

def pixel_pos_from_char(
    rich_text: RichText,
    char_pos: int,
    text_area_x: int,
    text_area_y: int,
    available_width: int,
    dc: wx.DC,
    font_normal: wx.Font,
    font_bold: wx.Font,
    line_height: int
) -> Tuple[int, int]:
    """
    Convert character position to pixel coordinates.
    
    Returns:
        (x, y) pixel coordinates for the cursor
    """
    if not rich_text or not rich_text.runs or char_pos <= 0:
        return (text_area_x, text_area_y)
    
    char_pos = min(char_pos, rich_text.char_count())
    
    # Wrap the text to find which line the character is on
    wrapped_lines = _wrap_rich_text(rich_text, available_width, dc, font_normal, font_bold)
    
    for line_idx, line_info in enumerate(wrapped_lines):
        if line_info['start_char'] <= char_pos <= line_info['end_char']:
            # Character is on this line
            y = text_area_y + line_idx * line_height
            
            # Find x position within the line
            chars_into_line = char_pos - line_info['start_char']
            x = text_area_x
            
            chars_measured = 0
            for segment in line_info['segments']:
                segment_len = len(segment['text'])
                
                if chars_measured + segment_len >= chars_into_line:
                    # Character is within this segment
                    chars_in_segment = chars_into_line - chars_measured
                    if chars_in_segment > 0:
                        partial_text = segment['text'][:chars_in_segment]
                        font = font_bold if segment['bold'] else font_normal
                        dc.SetFont(font)
                        partial_width = dc.GetTextExtent(partial_text)[0]
                        x += partial_width
                    return (x, y)
                
                x += segment['width']
                chars_measured += segment_len
            
            return (x, y)
    
    # Fallback: position at end of last line
    if wrapped_lines:
        last_line = wrapped_lines[-1]
        y = text_area_y + (len(wrapped_lines) - 1) * line_height
        x = text_area_x + sum(seg['width'] for seg in last_line['segments'])
        return (x, y)
    
    return (text_area_x, text_area_y)

def _wrap_rich_text(
    rich_text: RichText,
    available_width: int,
    dc: wx.DC,
    font_normal: wx.Font,
    font_bold: wx.Font
) -> List[dict]:
    """
    Wrap rich text and return line information.
    
    Returns list of line info dicts with:
    - start_char: starting character position
    - end_char: ending character position
    - segments: list of text segments with formatting and width
    """
    if not rich_text or not rich_text.runs:
        return []
    
    lines = []
    current_line_segments = []
    current_line_width = 0
    char_pos = 0
    line_start_char = 0
    
    space_width = dc.GetTextExtent(" ")[0]
    
    for run in rich_text.runs:
        font = font_bold if run.bold else font_normal
        dc.SetFont(font)
        
        # Split run by actual newlines first
        paragraphs = run.content.split('\n')
        
        for para_idx, paragraph in enumerate(paragraphs):
            if para_idx > 0:
                # Explicit newline - finish current line
                if current_line_segments:
                    lines.append({
                        'start_char': line_start_char,
                        'end_char': char_pos,
                        'segments': current_line_segments[:]
                    })
                    current_line_segments = []
                    current_line_width = 0
                    line_start_char = char_pos
                char_pos += 1  # For the newline character
            
            if not paragraph:
                continue
            
            # Word-wrap this paragraph
            words = paragraph.split(' ')
            
            for word_idx, word in enumerate(words):
                if word_idx > 0:
                    # Add space before word (except first word)
                    word = ' ' + word
                
                word_width = dc.GetTextExtent(word)[0]
                
                # Check if word fits on current line
                if current_line_width + word_width <= available_width or not current_line_segments:
                    # Word fits or it's the first word on line
                    current_line_segments.append({
                        'text': word,
                        'bold': run.bold,
                        'italic': run.italic,
                        'color': run.color,
                        'bg': run.bg,
                        'width': word_width
                    })
                    current_line_width += word_width
                    char_pos += len(word)
                else:
                    # Word doesn't fit - wrap to next line
                    lines.append({
                        'start_char': line_start_char,
                        'end_char': char_pos,
                        'segments': current_line_segments[:]
                    })
                    
                    current_line_segments = [{
                        'text': word,
                        'bold': run.bold,
                        'italic': run.italic,
                        'color': run.color,
                        'bg': run.bg,
                        'width': word_width
                    }]
                    current_line_width = word_width
                    line_start_char = char_pos
                    char_pos += len(word)
    
    # Add final line if any content remains
    if current_line_segments:
        lines.append({
            'start_char': line_start_char,
            'end_char': char_pos,
            'segments': current_line_segments[:]
        })
    
    return lines

def _find_char_in_segment(
    segment: dict,
    click_x_in_segment: int,
    dc: wx.DC,
    font_normal: wx.Font,
    font_bold: wx.Font
) -> int:
    """Find which character in a segment was clicked."""
    text = segment['text']
    font = font_bold if segment['bold'] else font_normal
    dc.SetFont(font)
    
    # Binary search would be more efficient, but simple linear search for now
    best_pos = 0
    best_distance = abs(click_x_in_segment)
    
    for i in range(len(text) + 1):
        substr = text[:i]
        width = dc.GetTextExtent(substr)[0]
        distance = abs(width - click_x_in_segment)
        
        if distance < best_distance:
            best_distance = distance
            best_pos = i
    
    return best_pos

class CursorRenderer:
    """Handles rendering the text cursor."""
    
    def __init__(self, cursor_width: int = 1):
        self.cursor_width = cursor_width
        self.cursor_color = wx.BLACK
    
    def draw_cursor(
        self,
        gc: wx.GraphicsContext,
        x: int,
        y: int,
        height: int,
        visible: bool = True
    ):
        """Draw the cursor at the specified position."""
        if not visible:
            return
        
        # Draw a thin vertical line
        gc.SetPen(wx.Pen(self.cursor_color, self.cursor_width))
        gc.StrokeLine(x, y, x, y + height)
