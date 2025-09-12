'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''
from __future__ import annotations

from typing import List, Dict, Any, Tuple
from ui.edit_state import RichText, TextRun

def rich_text_from_entry(entry: Dict[str, Any]) -> RichText:
    """Get RichText object from an entry, prioritizing edit field during editing."""
    # During editing, use the edit field if it contains content
    edit_data = entry.get("edit", [])

    # Handle both new rich text format and legacy plain text
    if edit_data:
        if isinstance(edit_data, str):
            # Legacy plain text edit field
            return RichText.from_plain_text(edit_data)
        else:
            # New rich text edit field
            return RichText.from_storage(edit_data)

    # Otherwise use the main text field (rich text format)
    text_data = entry.get("text", [{"content": ""}])
    return RichText.from_storage(text_data)

def calculate_line_height(dc, font_normal, font_bold):
    """Calculate the maximum line height needed for normal and bold fonts."""
    dc.SetFont(font_normal)
    lh_normal = dc.GetTextExtent("Ag")[1]
    dc.SetFont(font_bold)
    lh_bold = dc.GetTextExtent("Ag")[1]
    return max(lh_normal, lh_bold)

def finish_current_line(current_line, line_start_char, char_pos, line_height):
    """Create a line segment from current line data and return next line start position."""
    line_segment = {
        'segments': current_line[:],
        'height': line_height,
        'start_char': line_start_char,
        'end_char': char_pos
    }
    return line_segment, char_pos + 1  # Next line starts after current position

def process_leading_newline(run_content, current_line, current_line_width, line_start_char, char_pos, line_height, line_segments):
    """
    Handle runs that start with newline (the key fix for formatting bug).
    This properly handles newlines that result from formatting operations splitting runs.
    """
    if run_content.startswith('\n'):
        # If we have content on current line, finish it before processing the newline
        if current_line:
            line_segment, next_line_start = finish_current_line(current_line, line_start_char, char_pos, line_height)
            line_segments.append(line_segment)
            current_line = []
            current_line_width = 0
            line_start_char = next_line_start
        
        # Account for the leading newline character in position tracking
        char_pos += 1
        
        # Remove the leading newline so normal paragraph processing can handle the rest
        run_content = run_content[1:]
    
    return run_content, current_line, current_line_width, line_start_char, char_pos, line_segments

def word_wrap_paragraph(paragraph, run, current_line, current_line_width, line_start_char, char_pos, maxw, dc, line_height, line_segments):
    """Handle word-wrapping logic for a single paragraph within a run."""
    words = paragraph.split(' ')
    
    for word_idx, word in enumerate(words):
        if word_idx > 0:
            word = ' ' + word
        
        word_width = dc.GetTextExtent(word)[0]
        
        # Check if word fits on current line
        if current_line_width + word_width <= maxw or not current_line:
            # Word fits or it's the first word on line
            current_line.append({
                'text': word,
                'bold': run.bold,
                'italic': run.italic,
                'color': run.color,
                'bg': run.bg,
                'width': word_width,
                'link_target': run.link_target,
            })
            current_line_width += word_width
            char_pos += len(word)
        else:
            # Word doesn't fit - wrap to next line
            line_segment, next_line_start = finish_current_line(current_line, line_start_char, char_pos, line_height)
            line_segments.append(line_segment)
            
            current_line = [{
                'text': word,
                'bold': run.bold,
                'italic': run.italic,
                'color': run.color,
                'bg': run.bg,
                'width': word_width,
                'link_target': run.link_target,
            }]
            current_line_width = word_width
            line_start_char = char_pos
            char_pos += len(word)
    
    return current_line, current_line_width, char_pos

def ensure_minimum_content(line_segments, line_height):
    """Ensure we have at least one line segment, even if empty."""
    if not line_segments:
        line_segments.append({
            'segments': [],
            'height': line_height,
            'start_char': 0,
            'end_char': 0
        })
    return line_segments

def measure_rich_text_wrapped(rich_text, maxw, dc, font_normal, font_bold, padding):
    """
    Measure wrapped rich text and return line information with formatting.
    
    Returns:
        (line_segments, line_height, total_height_with_padding)
    """
    # Handle empty rich text
    if not rich_text or not rich_text.runs:
        dc.SetFont(font_normal)
        lh = dc.GetTextExtent("Ag")[1]
        return ([{
            'segments': [],
            'height': lh,
            'start_char': 0,
            'end_char': 0
        }], lh, lh + 2 * padding)

    # Calculate line height
    line_height = calculate_line_height(dc, font_normal, font_bold)
    
    # Initialize state
    line_segments = []
    current_line = []
    current_line_width = 0
    char_pos = 0
    line_start_char = 0

    # Process each run
    for run in rich_text.runs:
        font = font_bold if run.bold else font_normal
        dc.SetFont(font)

        # Handle leading newlines (key fix for formatting bug)
        run_content, current_line, current_line_width, line_start_char, char_pos, line_segments = \
            process_leading_newline(run.content, current_line, current_line_width, 
                                    line_start_char, char_pos, line_height, line_segments)

        # Split remaining content by internal newlines
        paragraphs = run_content.split('\n')
        
        for para_idx, paragraph in enumerate(paragraphs):
            # Handle explicit newlines between paragraphs
            if para_idx > 0:
                if current_line:
                    line_segment, next_line_start = finish_current_line(current_line, line_start_char, char_pos, line_height)
                    line_segments.append(line_segment)
                    current_line = []
                    current_line_width = 0
                    line_start_char = next_line_start
                char_pos += 1  # Count the newline character

                # Handle empty paragraphs (double newlines)
                if not paragraph:
                    line_segments.append({
                        'segments': [],
                        'height': line_height,
                        'start_char': line_start_char,
                        'end_char': line_start_char
                    })
                    continue

            # Skip empty paragraphs at start
            if not paragraph:
                continue

            # Word-wrap this paragraph
            current_line, current_line_width, char_pos = word_wrap_paragraph(
                paragraph, run, current_line, current_line_width, line_start_char, 
                char_pos, maxw, dc, line_height, line_segments
            )

    # Add final line if any content remains
    if current_line:
        line_segment, _ = finish_current_line(current_line, line_start_char, char_pos, line_height)
        line_segments.append(line_segment)

    # Ensure we have at least one line
    line_segments = ensure_minimum_content(line_segments, line_height)

    # Calculate total height
    total_height = sum(line['height'] for line in line_segments) + 2 * padding

    return line_segments, line_height, total_height
