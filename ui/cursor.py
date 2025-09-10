# ui/cursor.py

from __future__ import annotations

import wx

__all__ = ["CursorRenderer"]

# Cursor rendering constants
DEFAULT_CURSOR_WIDTH = 1
CURSOR_COLOR = wx.BLACK

class CursorRenderer:
    """Handles rendering the text cursor."""

    def __init__(self, cursor_width: int = DEFAULT_CURSOR_WIDTH):
        self.cursor_width = cursor_width
        self.cursor_color = CURSOR_COLOR

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
