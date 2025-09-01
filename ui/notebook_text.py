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

def measure_rich_text_wrapped(
    rich_text: RichText,
    maxw: int,
    dc,
    font_normal,
    font_bold,
    padding: int
) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Measure wrapped rich text and return line information with formatting.

    Returns:
        (line_segments, line_height, total_height_with_padding)

    Where line_segments is a list of:
    {
        'segments': [{'text': str, 'bold': bool, 'italic': bool, 'color': str, 'bg': str, 'width': int}],
        'height': int
    }
    """
    if not rich_text or not rich_text.runs:
        # Empty rich text
        dc.SetFont(font_normal)
        lh = dc.GetTextExtent("Ag")[1]
        return ([{'segments': [], 'height': lh}], lh, lh + 2 * padding)

    # Calculate line height from fonts
    dc.SetFont(font_normal)
    lh_normal = dc.GetTextExtent("Ag")[1]
    dc.SetFont(font_bold)
    lh_bold = dc.GetTextExtent("Ag")[1]
    line_height = max(lh_normal, lh_bold)

    line_segments = []
    current_line = []
    current_line_width = 0

    for run in rich_text.runs:
        font = font_bold if run.bold else font_normal
        dc.SetFont(font)

        # Split run by actual newlines first
        paragraphs = run.content.split('\n')

        for para_idx, paragraph in enumerate(paragraphs):
            if para_idx > 0:
                # Explicit newline - finish current line
                if current_line:
                    line_segments.append({
                        'segments': current_line[:],
                        'height': line_height
                    })
                    current_line = []
                    current_line_width = 0

            if not paragraph:
                # Empty paragraph (from newline) - create empty line segment
                line_segments.append({
                    'segments': [],
                    'height': line_height
                })
                continue

            # Word-wrap this paragraph
            words = paragraph.split(' ')

            for word_idx, word in enumerate(words):
                if word_idx > 0:
                    # Add space before word (except first word)
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
                        'width': word_width
                    })
                    current_line_width += word_width
                else:
                    # Word doesn't fit - wrap to next line
                    line_segments.append({
                        'segments': current_line[:],
                        'height': line_height
                    })

                    current_line = [{
                        'text': word,
                        'bold': run.bold,
                        'italic': run.italic,
                        'color': run.color,
                        'bg': run.bg,
                        'width': word_width
                    }]
                    current_line_width = word_width

    # Add final line if any content remains
    if current_line:
        line_segments.append({
            'segments': current_line[:],
            'height': line_height
        })
    elif not line_segments:
        # Ensure at least one empty line
        line_segments.append({
            'segments': [],
            'height': line_height
        })

    total_height = sum(line['height'] for line in line_segments) + 2 * padding
    return line_segments, line_height, total_height
