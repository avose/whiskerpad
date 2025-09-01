from __future__ import annotations

import wx

from ui.layout import measure_row_height

# Scroll behavior constants
SCROLL_MARGIN = 0  # Pixels to leave at edge when scrolling

def visible_range(view) -> tuple[int, int]:
    """
    Return (first, last) fully visible row indices.
    Walks from the first partially-visible row until the bottom using pixel scrolling.
    """
    n = len(view._rows)
    if n <= 0:
        return (0, -1)

    # Get scroll position from ScrolledWindow
    scroll_x, scroll_y = view.GetViewStart()
    scroll_y_px = scroll_y * view.GetScrollPixelsPerUnit()[1]

    start_idx, y_into = view._index.find_row_at_y(scroll_y_px)
    if start_idx < 0:
        return (0, -1)

    client_height = view.GetClientSize().height
    y = -int(y_into)
    current_idx = int(start_idx)
    last = current_idx - 1

    while current_idx < n and y < client_height:
        h = int(measure_row_height(view, view._rows[current_idx]))
        y += h
        last = current_idx
        current_idx += 1

    return (int(start_idx), min(last, n - 1))

def soft_ensure_visible(view, idx: int) -> None:
    """Ensure idx is visible using pixel-based scrolling."""
    n = len(view._rows)
    if n <= 0 or not (0 <= idx < n):
        return

    ch = view.GetClientSize().height
    top = int(view._index.row_top(idx))
    h = int(view._index.row_height(idx))

    if h >= ch:
        # Row is taller than viewport; scroll to show top
        view.SetVirtualSize((-1, view._index.content_height()))
        view.Scroll(-1, top // view.GetScrollPixelsPerUnit()[1])
        return

    # Get current scroll position
    scroll_x, scroll_y = view.GetViewStart()
    cur = scroll_y * view.GetScrollPixelsPerUnit()[1]

    bottom = top + h

    # If above, scroll up to top; if below, scroll so bottom fits;
    # else no change.
    if top < cur:
        new_y = top
    elif bottom > (cur + ch):
        new_y = bottom - ch
    else:
        return

    new_y_clamped = clamp_scroll_y(view, new_y)
    view.SetVirtualSize((-1, view._index.content_height()))
    view.Scroll(-1, new_y_clamped // view.GetScrollPixelsPerUnit()[1])

def content_height(view) -> int:
    """
    Total content height in pixels. Uses the current row heights.
    If a LayoutIndex exists and exposes content height, prefer it.
    """
    if hasattr(view._index, "content_height"):
        return int(view._index.content_height())

    total = 0
    for i in range(len(view._rows)):
        total += int(measure_row_height(view, view._rows[i]))
    return total

def clamp_scroll_y(view, y: int) -> int:
    """Clamp pixel scroll position to [0 .. max_scroll]."""
    ch = view.GetClientSize().height
    h = max(0, content_height(view) - ch)
    return max(0, min(y, h))
