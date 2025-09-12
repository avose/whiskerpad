'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''
from __future__ import annotations

import wx
import math
from dataclasses import dataclass
from typing import List, Optional, Callable

from core.log import Log
from ui.icons import wpIcons
from ui.decorators import check_read_only


@dataclass
class TabInfo:
    def __init__(self, entry_id: str, display_text: str, color=None):
        self.entry_id = entry_id
        self.display_text = display_text
        
        # Ensure color is always a wx.Colour object
        if color is None:
            self.color = wx.Colour(200, 200, 200)  # Default gray
        elif isinstance(color, (list, tuple)):
            if len(color) == 3:
                self.color = wx.Colour(color[0], color[1], color[2])
            else:
                raise ValueError(f"Invalid color tuple length: {len(color)}, expected 3")
        elif isinstance(color, wx.Colour):
            self.color = color
        else:
            raise TypeError(f"Invalid color type: {type(color)}")

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "entry_id": self.entry_id,
            "display_text": self.display_text,
            "color": [self.color.Red(), self.color.Green(), self.color.Blue()]  # Always serialize as list!
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'TabInfo':
        """Create TabInfo from dictionary."""
        # Let it crash if required keys are missing - no defensive gets!
        return cls(
            entry_id=data["entry_id"],  # Will KeyError if missing - GOOD!
            display_text=data["display_text"],  # Will KeyError if missing - GOOD!
            color=data["color"]  # Will be None if missing, handled by __init__
        )

class TabsPanel(wx.Panel):
    """Vertical tabs panel with physical file tab appearance."""
    
    def __init__(
        self,
        parent: wx.Window,
        on_tab_click: Optional[Callable] = None,
        on_tab_changed: Optional[Callable] = None,
    ):
        super().__init__(parent)
        self.on_tab_click = on_tab_click
        self.on_tab_changed = on_tab_changed
        self.tabs: List[TabInfo] = []
        self.selected_tab_idx = -1
        self.hover_tab_idx = -1
        self.scroll_offset = 0  # Smooth scrolling offset in pixels
        
        # Drawing constants
        self.TAB_WIDTH = 24
        self.TAB_MIN_HEIGHT = 60
        self.TAB_MAX_HEIGHT = 120
        self.ARROW_HEIGHT = 16
        self.TAB_SPACING = 2
        self.TAB_ANGLE = 5  # Pixels for angled cut
        
        # Colors
        self.ACTIVE_TAB_COLOR = wx.Colour(255, 255, 255)
        self.INACTIVE_TAB_COLOR = wx.Colour(235, 235, 235)
        self.HOVER_TAB_COLOR = wx.Colour(245, 245, 245)
        self.ACTIVE_TEXT_COLOR = wx.Colour(0, 0, 0)
        self.INACTIVE_TEXT_COLOR = wx.Colour(0, 0, 0)
        
        # Fonts
        base_font = self.GetFont()
        self.normal_font = base_font
        self.bold_font = wx.Font(
            base_font.GetPointSize(),
            base_font.GetFamily(),
            wx.FONTSTYLE_NORMAL,
            wx.FONTWEIGHT_BOLD
        )
        
        self._setup_drawing()
        self._bind_events()

    def is_read_only(self) -> bool:
        """Check if in read-only mode"""
        app = wx.GetApp()
        main_frame = app.GetTopWindow()
        return main_frame.is_read_only()

    def _setup_drawing(self):
        """Setup drawing properties."""
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetDoubleBuffered(True)
        self.SetMinSize((self.TAB_WIDTH + 4, -1))
    
    def _bind_events(self):
        """Bind all event handlers."""
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_mouse_down)
        self.Bind(wx.EVT_LEFT_DCLICK, self._on_mouse_down)
        self.Bind(wx.EVT_RIGHT_DOWN, self._on_right_down)  # Add this line
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_mouse_wheel)

    @check_read_only
    def _on_right_down(self, evt: wx.MouseEvent):
        """Handle right-click for context menu."""
        pos = evt.GetPosition()
        tab_idx = self._hit_test_tabs(pos)

        if tab_idx >= 0 and tab_idx < len(self.tabs):
            # Right-clicked on a tab - show context menu
            self._show_tab_context_menu(tab_idx, pos)

    def _create_color_swatch_bitmap(self, color: wx.Colour, size: int = 16) -> wx.Bitmap:
        """Create a small bitmap showing the color as a square swatch with border."""
        bitmap = wx.Bitmap(size, size)
        dc = wx.MemoryDC(bitmap)

        # Fill the entire bitmap with the color
        dc.SetBrush(wx.Brush(color))
        dc.SetPen(wx.Pen(color))
        dc.DrawRectangle(0, 0, size, size)

        # Add a subtle dark border around the swatch
        border_color = wx.Colour(100, 100, 100)
        dc.SetPen(wx.Pen(border_color, 1))
        dc.SetBrush(wx.Brush(wx.Colour(0, 0, 0, 0)))  # Transparent brush
        dc.DrawRectangle(0, 0, size, size)

        # Clean up
        dc.SelectObject(wx.NullBitmap)
        return bitmap

    @check_read_only
    def _show_tab_context_menu(self, tab_idx: int, pos: wx.Point):
        """Show context menu for a tab."""
        if not (0 <= tab_idx < len(self.tabs)):
            return

        self.context_tab_idx = tab_idx  # Store for menu handlers

        # Create popup menu
        menu = wx.Menu()

        # Rename option with icon
        rename_item = wx.MenuItem(menu, wx.ID_ANY, "Rename Tab")
        rename_icon = wpIcons.Get("tab_edit")
        if rename_icon:
            rename_item.SetBitmap(rename_icon)
        menu.Append(rename_item)
        menu.Bind(wx.EVT_MENU, self._on_rename_tab, rename_item)

        menu.AppendSeparator()

        # Remove option with icon
        remove_item = wx.MenuItem(menu, wx.ID_ANY, "Remove Tab")
        remove_icon = wpIcons.Get("tab_delete")
        if remove_icon:
            remove_item.SetBitmap(remove_icon)
        menu.Append(remove_item)
        menu.Bind(wx.EVT_MENU, self._on_remove_tab, remove_item)

        menu.AppendSeparator()

        # Color submenu with color swatch icons (existing code)
        color_submenu = wx.Menu()

        # Define color palette
        colors = [
            ("Gray", wx.Colour(200, 200, 200)),
            ("Red", wx.Colour(255, 100, 100)),
            ("Orange", wx.Colour(255, 165, 0)),
            ("Yellow", wx.Colour(255, 255, 100)),
            ("Green", wx.Colour(100, 255, 100)),
            ("Blue", wx.Colour(100, 150, 255)),
            ("Purple", wx.Colour(200, 100, 255)),
            ("Pink", wx.Colour(255, 150, 200)),
            ("Cyan", wx.Colour(100, 255, 255)),
            ("Lime", wx.Colour(150, 255, 50)),
            ("Magenta", wx.Colour(255, 100, 150)),
            ("Teal", wx.Colour(100, 200, 200)),
        ]

        # Store colors in a dict keyed by menu item ID
        self._color_map = {}

        for color_name, color in colors:
            # Create menu item manually so we can set bitmap before appending
            color_item = wx.MenuItem(color_submenu, wx.ID_ANY, color_name)

            # Create and set the color swatch bitmap
            swatch_bitmap = self._create_color_swatch_bitmap(color)
            color_item.SetBitmap(swatch_bitmap)

            # Store color using menu item ID as key
            self._color_map[color_item.GetId()] = color

            # Append the item and bind the event
            color_submenu.Append(color_item)
            color_submenu.Bind(wx.EVT_MENU, self._on_set_tab_color, color_item)

        menu.AppendSubMenu(color_submenu, "Tab Color")

        # Show menu
        self.PopupMenu(menu, pos)
        menu.Destroy()

        # Clean up color map
        del self._color_map

    @check_read_only
    def _on_rename_tab(self, evt):
        """Handle rename tab menu selection."""
        tab_idx = self.context_tab_idx
        current_name = self.tabs[tab_idx].display_text
        new_name = self._show_rename_dialog(current_name)
        Log.debug(f"_on_rename_tab(), {tab_idx=}, {current_name=}, {new_name=}", 1)

        if new_name and new_name != current_name:
            self.tabs[tab_idx].display_text = new_name
            self.Refresh()
            if self.on_tab_changed:
                self.on_tab_changed()

    @check_read_only
    def _on_remove_tab(self, evt):
        """Handle remove tab menu selection."""
        tab_idx = self.context_tab_idx
        tab_name = self.tabs[tab_idx].display_text

        tab_name = self.tabs[tab_idx].display_text
        Log.debug(f"_on_remove_tab(), {tab_idx=}, {tab_name=}", 1)
        self.tabs.pop(tab_idx)

        # Adjust selection if needed
        if self.selected_tab_idx >= len(self.tabs):
            self.selected_tab_idx = len(self.tabs) - 1
        elif self.selected_tab_idx >= tab_idx:
            self.selected_tab_idx -= 1

        self.Refresh()
        if self.on_tab_changed:
            self.on_tab_changed()

    @check_read_only
    def _on_set_tab_color(self, evt):
        """Handle tab color selection."""
        # Remove defensive programming - let it fail loudly
        tab_idx = self.context_tab_idx

        # Get color from our stored map
        menu_id = evt.GetId()
        color = self._color_map[menu_id]
        self.tabs[tab_idx].color = color
        self.Refresh()

        # Call the callback - let it fail if not set properly
        if self.on_tab_changed:
            self.on_tab_changed()

    def _show_rename_dialog(self, current_name: str) -> str:
        """Show dialog to rename a tab."""
        dlg = wx.TextEntryDialog(
            self,
            "Enter new tab name:",
            "Rename Tab",
            current_name
        )

        result = ""
        if dlg.ShowModal() == wx.ID_OK:
            result = dlg.GetValue().strip()
            if len(result) > 15:
                result = result[:12] + "..."

        dlg.Destroy()
        return result

    def _entry_exists(self, entry_id: str) -> bool:
        """Check if an entry still exists in the current notebook."""
        try:
            # Get the main frame to access the current notebook
            main_frame = wx.GetApp().GetTopWindow()
            if (hasattr(main_frame, '_current_note_panel') and
                main_frame._current_note_panel):
                # Use the view's cache to check if entry exists
                main_frame._current_note_panel.view.cache.entry(entry_id)
                return True
        except Exception:
            pass
        return False

    def _calculate_tab_height(self, text: str) -> int:
        """Calculate tab height needed for rotated text."""
        dc = wx.ClientDC(self)
        dc.SetFont(self.normal_font)
        text_width, text_height = dc.GetTextExtent(text)
        # When rotated 90° clockwise, text_width becomes the tab height
        return max(self.TAB_MIN_HEIGHT, 
                   min(text_width + 20, self.TAB_MAX_HEIGHT))
    
    def _get_total_tabs_height(self) -> int:
        """Get total height needed for all tabs."""
        total = 0
        for tab in self.tabs:
            total += self._calculate_tab_height(tab.display_text) + self.TAB_SPACING
        return total
    
    def _need_scrolling(self) -> bool:
        """Check if scrolling is needed."""
        client_height = self.GetClientSize().height
        total_tabs_height = self._get_total_tabs_height()

        # Only need scrolling if tabs don't fit in full client area
        return total_tabs_height > client_height
    
    def _on_paint(self, evt: wx.PaintEvent):
        """Paint the tabs panel."""
        dc = wx.AutoBufferedPaintDC(self)
        gc = wx.GraphicsContext.Create(dc)

        if not gc:
            return

        # Clear background
        size = self.GetClientSize()
        gc.SetBrush(wx.Brush(wx.Colour(240, 240, 240)))
        gc.DrawRectangle(0, 0, size.width, size.height)

        # Determine if we need scrolling and set tab area bounds
        need_scroll = self._need_scrolling()

        if need_scroll:
            # Draw scroll arrows (these stay fixed)
            self._draw_scroll_arrows(gc, size)
            tabs_start_y = self.ARROW_HEIGHT
            tabs_end_y = size.height - self.ARROW_HEIGHT
        else:
            # No arrows needed - tabs use full height
            tabs_start_y = 0
            tabs_end_y = size.height
            # Reset scroll offset if scrolling is no longer needed
            self.scroll_offset = 0

        # Draw tabs in the available area
        self._draw_tabs(gc, tabs_start_y, tabs_end_y, size.width)
    
    def _draw_scroll_arrows(self, gc: wx.GraphicsContext, size: wx.Size):
        """Draw up and down scroll arrows."""
        arrow_width = size.width
        
        # Up arrow background
        gc.SetBrush(wx.Brush(wx.Colour(220, 220, 220)))
        gc.DrawRectangle(0, 0, arrow_width, self.ARROW_HEIGHT)
        
        # Down arrow background  
        gc.SetBrush(wx.Brush(wx.Colour(220, 220, 220)))
        gc.DrawRectangle(0, size.height - self.ARROW_HEIGHT, arrow_width, self.ARROW_HEIGHT)
        
        # Arrow shapes (simple triangles)
        gc.SetBrush(wx.Brush(wx.Colour(100, 100, 100)))
        
        # Up arrow triangle
        center_x = arrow_width // 2
        up_points = [
            (center_x, 3),
            (center_x - 4, self.ARROW_HEIGHT - 3),
            (center_x + 4, self.ARROW_HEIGHT - 3)
        ]
        gc.DrawLines(up_points)
        
        # Down arrow triangle
        down_y = size.height - self.ARROW_HEIGHT
        down_points = [
            (center_x, size.height - 3),
            (center_x - 4, down_y + 3),
            (center_x + 4, down_y + 3)
        ]
        gc.DrawLines(down_points)
    
    def _draw_tabs(self, gc: wx.GraphicsContext, start_y: int, end_y: int, width: int):
        """Draw all visible tabs within the clipped area."""

        # Clip drawing to the scrollable area only
        gc.PushState()
        gc.Clip(0, start_y, width, end_y - start_y)

        current_y = start_y - self.scroll_offset

        for i, tab in enumerate(self.tabs):
            tab_height = self._calculate_tab_height(tab.display_text)

            # Skip tabs that are completely above visible area
            if current_y + tab_height < start_y:
                current_y += tab_height + self.TAB_SPACING
                continue

            # Stop if tab is completely below visible area  
            if current_y > end_y:
                break

            # Draw this tab (will be clipped automatically)
            is_selected = (i == self.selected_tab_idx)
            is_hover = (i == self.hover_tab_idx)

            self._draw_tab(gc, tab, current_y, tab_height, width, is_selected, is_hover)

            current_y += tab_height + self.TAB_SPACING

        # Restore graphics context state
        gc.PopState()
    
    def _draw_tab(self, gc: wx.GraphicsContext, tab: TabInfo, y: int, height: int,
                  width: int, is_selected: bool, is_hover: bool):
        """Draw a single tab with trapezoid shape and custom colors."""

        # Get base color from tab
        base_color = tab.color if tab.color else wx.Colour(200, 200, 200)

        # Check if the tab target still exists
        target_exists = self._entry_exists(tab.entry_id)

        # Determine colors and font based on state
        if is_selected:
            # Bright version of tab color for selected
            bg_color = wx.Colour(
                min(255, base_color.Red() + 24),
                min(255, base_color.Green() + 24),
                min(255, base_color.Blue() + 24)
            )
            # Use red text for broken targets, black for working ones
            text_color = wx.Colour(255, 0, 0) if not target_exists else self.ACTIVE_TEXT_COLOR
            font = self.bold_font
        else:
            # Dark version of tab color for non-selected
            if is_hover:
                # Slightly lighter than normal for hover
                bg_color = wx.Colour(
                    max(0, base_color.Red()),
                    max(0, base_color.Green()),
                    max(0, base_color.Blue())
                )
            else:
                # Darker version for normal state
                bg_color = wx.Colour(
                    max(0, base_color.Red() - 24),
                    max(0, base_color.Green() - 24),
                    max(0, base_color.Blue() - 24)
                )
            # Use red text for broken targets, black for working ones
            text_color = wx.Colour(255, 0, 0) if not target_exists else self.INACTIVE_TEXT_COLOR
            font = self.normal_font

        # Rest of the drawing code remains the same...
        # Create trapezoid path (file tab shape - wider on left side)
        path = gc.CreatePath()
        # Bottom left (extended outward)
        path.MoveToPoint(0, y)
        # Bottom right
        path.AddLineToPoint(width - 1, y + self.TAB_ANGLE)
        # Top right (same as bottom)
        path.AddLineToPoint(width - 1, y + height - self.TAB_ANGLE)
        # Top left (tapered inward)
        path.AddLineToPoint(0, y + height)
        path.CloseSubpath()

        # Draw tab background with 3D effect for selected tabs
        if is_selected:
            # Draw subtle shadow for "forward" effect
            shadow_path = gc.CreatePath()
            shadow_path.MoveToPoint(-1, y - 1)
            shadow_path.AddLineToPoint(width, y + self.TAB_ANGLE - 1)
            shadow_path.AddLineToPoint(width, y + height - self.TAB_ANGLE + 1)
            shadow_path.AddLineToPoint(-1, y + height + 1)
            shadow_path.CloseSubpath()
            gc.SetBrush(wx.Brush(bg_color))
            gc.FillPath(shadow_path)
        else:
            gc.SetBrush(wx.Brush(bg_color))

        # Fill tab shape
        gc.FillPath(path)

        # Draw tab border
        gc.SetPen(wx.Pen(wx.Colour(120, 120, 120), 1))
        gc.StrokePath(path)

        # Draw rotated text
        gc.SetFont(font, text_color)  # Now uses the determined text_color

        # Calculate text position (centered in tab)
        text_x = width // 2
        text_y = y + height // 2

        # Rotate and draw text
        gc.PushState()
        gc.Translate(text_x, text_y)
        gc.Rotate(math.radians(90))  # 90 degrees clockwise

        text_width, text_height = gc.GetTextExtent(tab.display_text)
        gc.DrawText(tab.display_text, -text_width // 2, -text_height // 2)
        gc.PopState()
    
    def _on_mouse_down(self, evt: wx.MouseEvent):
        """Handle mouse clicks."""
        pos = evt.GetPosition()
        size = self.GetClientSize()
        
        # Check scroll arrows first
        if self._need_scrolling():
            if pos.y <= self.ARROW_HEIGHT:
                self._scroll_up()
                return
            elif pos.y >= size.height - self.ARROW_HEIGHT:
                self._scroll_down()
                return
        
        # Check tab clicks
        tab_idx = self._hit_test_tabs(pos)
        if tab_idx >= 0 and tab_idx < len(self.tabs):
            self.selected_tab_idx = tab_idx
            self.Refresh()
            
            if self.on_tab_click:
                tab = self.tabs[tab_idx]
                self.on_tab_click(tab.entry_id)
    
    def _on_motion(self, evt: wx.MouseEvent):
        """Handle mouse motion for hover effects."""
        old_hover = self.hover_tab_idx
        self.hover_tab_idx = self._hit_test_tabs(evt.GetPosition())
        
        if old_hover != self.hover_tab_idx:
            self.Refresh()
    
    def _on_leave(self, evt: wx.MouseEvent):
        """Clear hover state when mouse leaves panel."""
        if self.hover_tab_idx >= 0:
            self.hover_tab_idx = -1
            self.Refresh()
    
    def _on_mouse_wheel(self, evt: wx.MouseEvent):
        """Handle smooth scrolling with mouse wheel."""
        if not self._need_scrolling():
            return
        
        # 32 pixels per scroll notch
        delta = -evt.GetWheelRotation() // evt.GetWheelDelta() * 32
        self._scroll_by_pixels(delta)
    
    def _hit_test_tabs(self, pos: wx.Point) -> int:
        """Determine which tab was clicked. Returns tab index or -1."""
        size = self.GetClientSize()
        
        if self._need_scrolling():
            tabs_start_y = self.ARROW_HEIGHT
            tabs_end_y = size.height - self.ARROW_HEIGHT
        else:
            tabs_start_y = 0
            tabs_end_y = size.height
        
        if pos.y < tabs_start_y or pos.y > tabs_end_y:
            return -1
        
        current_y = tabs_start_y - self.scroll_offset
        
        for i, tab in enumerate(self.tabs):
            tab_height = self._calculate_tab_height(tab.display_text)
            
            if current_y <= pos.y <= current_y + tab_height:
                return i
            
            current_y += tab_height + self.TAB_SPACING
        
        return -1
    
    def _scroll_up(self):
        """Scroll up by one tab height."""
        if not self._need_scrolling() or not self.tabs:
            return

        # Find average tab height for consistent scrolling
        avg_tab_height = self._get_average_tab_height()
        self._scroll_by_pixels(-avg_tab_height)

    def _scroll_down(self):
        """Scroll down by one tab height."""
        if not self._need_scrolling() or not self.tabs:
            return

        # Find average tab height for consistent scrolling  
        avg_tab_height = self._get_average_tab_height()
        self._scroll_by_pixels(avg_tab_height)

    def _get_average_tab_height(self) -> int:
        """Get average tab height for consistent arrow scrolling."""
        if not self.tabs:
            return self.TAB_MIN_HEIGHT

        total_height = 0
        for tab in self.tabs:
            total_height += self._calculate_tab_height(tab.display_text) + self.TAB_SPACING

        return total_height // len(self.tabs)

    def _scroll_by_pixels(self, delta: int):
        """Scroll by specified pixel amount."""
        if not self._need_scrolling():
            return

        size = self.GetClientSize()
        available_height = size.height - (2 * self.ARROW_HEIGHT)  # Always consistent
        max_offset = max(0, self._get_total_tabs_height() - available_height)

        self.scroll_offset = max(0, min(max_offset, self.scroll_offset + delta))
        self.Refresh()
    
    # Public API methods
    def add_tab(self, entry_id: str, display_text: str):
        """Add a new tab."""
        # Truncate display text if too long
        if len(display_text) > 15:
            display_text = display_text[:12] + "..."
        
        tab = TabInfo(entry_id, display_text)
        self.tabs.append(tab)
        self.Refresh()
    
    def remove_tab(self, entry_id: str) -> bool:
        """Remove tab by entry ID. Returns True if found and removed."""
        for i, tab in enumerate(self.tabs):
            if tab.entry_id == entry_id:
                self.tabs.pop(i)
                
                # Adjust selection if needed
                if self.selected_tab_idx >= len(self.tabs):
                    self.selected_tab_idx = len(self.tabs) - 1
                elif self.selected_tab_idx >= i:
                    self.selected_tab_idx -= 1
                
                self.Refresh()
                return True
        return False
    
    def select_tab(self, entry_id: str) -> bool:
        """Select tab by entry ID. Returns True if found."""
        for i, tab in enumerate(self.tabs):
            if tab.entry_id == entry_id:
                self.selected_tab_idx = i
                self.Refresh()
                return True
        return False
    
    def clear_tabs(self):
        """Remove all tabs."""
        self.tabs.clear()
        self.selected_tab_idx = -1
        self.hover_tab_idx = -1
        self.scroll_offset = 0
        self.Refresh()
