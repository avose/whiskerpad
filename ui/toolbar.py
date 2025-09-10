from __future__ import annotations

import wx

from ui.icons import wpIcons
from ui.constants import DEFAULT_BG_COLOR

class Toolbar(wx.Panel):
    """
    Clean, data-driven toolbar with buttons defined in a simple list.
    Uses on_action_* methods on parent for event handling.
    """

    def __init__(self, parent: wx.Window):
        super().__init__(parent, style=wx.BORDER_NONE)
        self.main_frame = self.Parent.Parent

        # Initialize UI components
        self._setup_painting()
        self._create_controls()
        self._setup_layout()

        # Set minimum size
        self.SetMinSize((-1, 32))

    def _setup_painting(self):
        """Configure custom painting for gradient background"""
        self.SetDoubleBuffered(True)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def _create_controls(self):
        """Create all toolbar controls using data-driven approach"""
        
        # Define toolbar structure as list of (ID, tooltip, icon_name, method_name) or None for separator
        self.tools = [
            (wx.ID_OPEN, "Open Notebook", "book_open", "on_action_open"),
            None,  # separator
            (wx.NewIdRef(), "Add Image(s)", "image_add", "on_action_add_images"),
            (wx.NewIdRef(), "Delete", "delete", "on_action_delete"),
            (wx.NewIdRef(), "Create Tab from Selection", "tab_add", "on_action_add_tab"),
            None,  # separator
            (wx.NewIdRef(), "Cut", "cut", "on_action_cut"),
            (wx.NewIdRef(), "Copy", "page_white_copy", "on_action_copy"),
            (wx.NewIdRef(), "Paste", "paste_plain", "on_action_paste"),
            None,  # separator
            (wx.NewIdRef(), "Zoom Out", "zoom_out", "on_action_zoom_out"),
            (wx.NewIdRef(), "Reset Zoom", "zoom", "on_action_zoom_reset"),
            (wx.NewIdRef(), "Zoom In", "zoom_in", "on_action_zoom_in"),
            None,  # separator
            (wx.NewIdRef(), "Rotate Left", "shape_rotate_anticlockwise", "on_action_rotate_anticlockwise"),
            (wx.NewIdRef(), "Rotate Right", "shape_rotate_clockwise", "on_action_rotate_clockwise"),
            (wx.NewIdRef(), "Flip Vertical", "shape_flip_vertical", "on_action_flip_vertical"),
            (wx.NewIdRef(), "Flip Horizontal", "shape_flip_horizontal", "on_action_flip_horizontal"),
        ]

        # Create buttons and separators from tools list
        self.buttons = {}
        self.separators = []
        
        for item in self.tools:
            if item is None:
                # Create separator
                separator = wx.StaticLine(self, style=wx.LI_VERTICAL)
                self.separators.append(separator)
            else:
                # Create button
                btn_id, tooltip, icon_name, method_name = item
                btn = self._create_button(btn_id, tooltip, icon_name, method_name)
                self.buttons[btn_id] = btn

        # Create special controls (color pickers and search)
        self._create_special_controls()

    def _create_button(self, btn_id: int, tooltip: str, icon_name: str, method_name: str) -> wx.BitmapButton:
        """Create a standard toolbar button"""
        bmp = wpIcons.Get(icon_name)
        btn = wx.BitmapButton(self, id=btn_id, bitmap=bmp, 
                             style=wx.BU_EXACTFIT | wx.NO_BORDER)
        btn.SetToolTip(wx.ToolTip(tooltip))
        btn.SetCanFocus(False)  # Prevent button from stealing focus
        
        # Bind to parent method
        handler = getattr(self.main_frame, method_name)
        btn.Bind(wx.EVT_BUTTON, handler)
        
        return btn

    def _create_special_controls(self):
        """Create color pickers and search control"""
        
        # Foreground color section
        self.fg_section = self._create_fg_color_section()
        
        # Background color section  
        self.bg_section = self._create_bg_color_section()
        
        # Search control
        self.search_ctrl = wx.SearchCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_ctrl.SetMinSize(wx.Size(175, 25))
        self.search_ctrl.ShowCancelButton(True)
        self.search_ctrl.SetToolTip(wx.ToolTip("Search Notebook"))
        
        # Bind search events
        self.search_ctrl.Bind(wx.EVT_SEARCHCTRL_SEARCH_BTN, self._on_search_triggered)
        self.search_ctrl.Bind(wx.EVT_TEXT_ENTER, self._on_search_triggered)

    def _create_fg_color_section(self):
        """Create foreground color picker with icon label"""
        section_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # Style icon for foreground color
        style_icon = wpIcons.Get("style")
        fg_icon = wx.StaticBitmap(self, bitmap=style_icon)
        fg_icon.SetToolTip(wx.ToolTip("Text Color"))
        
        # Color picker
        self.fg_color_picker = wx.ColourPickerCtrl(
            self,
            colour=wx.Colour(0, 0, 0),  # Black default
            size=wx.Size(32, 20),
            style=wx.CLRP_DEFAULT_STYLE
        )
        self.fg_color_picker.SetToolTip(wx.ToolTip("Text Color"))
        self.fg_color_picker.Bind(wx.EVT_KEY_DOWN, self._on_color_picker_key)
        self.fg_color_picker.Bind(wx.EVT_COLOURPICKER_CHANGED, self._on_fg_color_changed)
        
        section_sizer.Add(fg_icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        section_sizer.Add(self.fg_color_picker, 0, wx.ALIGN_CENTER_VERTICAL)
        
        return section_sizer

    def _create_bg_color_section(self):
        """Create background color picker with icon label"""
        section_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # Paintbrush icon for background color
        paintbrush_icon = wpIcons.Get("paintbrush")
        bg_icon = wx.StaticBitmap(self, bitmap=paintbrush_icon)
        bg_icon.SetToolTip(wx.ToolTip("Highlight Color"))
        
        # Color picker
        self.bg_color_picker = wx.ColourPickerCtrl(
            self,
            colour=DEFAULT_BG_COLOR,
            size=wx.Size(32, 20),
            style=wx.CLRP_DEFAULT_STYLE
        )
        self.bg_color_picker.SetToolTip(wx.ToolTip("Highlight Color"))
        self.bg_color_picker.Bind(wx.EVT_KEY_DOWN, self._on_color_picker_key)
        self.bg_color_picker.Bind(wx.EVT_COLOURPICKER_CHANGED, self._on_bg_color_changed)
        
        section_sizer.Add(bg_icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        section_sizer.Add(self.bg_color_picker, 0, wx.ALIGN_CENTER_VERTICAL)
        
        return section_sizer

    def _setup_layout(self):
        """Arrange all controls in the toolbar layout"""
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        main_sizer.AddSpacer(2)
        
        # Add buttons and separators in order
        separator_idx = 0
        button_idx = 0
        
        for item in self.tools:
            if item is None:
                # Add separator
                separator = self.separators[separator_idx]
                main_sizer.Add(separator, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 2)
                separator_idx += 1
            else:
                # Add button
                btn_id = item[0]
                btn = self.buttons[btn_id]
                main_sizer.Add(btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 1)

        # Add color picker sections
        separator = wx.StaticLine(self, style=wx.LI_VERTICAL)
        main_sizer.Add(separator, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 2)
        main_sizer.Add(self.fg_section, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 1)
        main_sizer.Add(self.bg_section, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 1)

        # Right side - stretch spacer and search
        main_sizer.AddStretchSpacer(1)
        main_sizer.AddSpacer(2)
        main_sizer.Add(self.search_ctrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 1)
        main_sizer.AddSpacer(2)

        self.SetSizer(main_sizer)

    def _on_search_triggered(self, event):
        """Handle search button click or Enter key."""
        query = self.search_ctrl.GetValue().strip()
        if query:
            self.main_frame.on_action_search(query)

    def _on_color_picker_key(self, evt):
        """Handle key events for color pickers - let Enter pass through."""
        if evt.GetKeyCode() == wx.WXK_RETURN:
            evt.Skip()  # Let Enter pass to parent/focused control
        else:
            evt.Skip()  # Handle other keys normally

    def _on_fg_color_changed(self, event):
        """Handle foreground color picker change"""
        color = event.GetColour()
        self.main_frame.on_action_fg_color_changed(color)

    def _on_bg_color_changed(self, event):
        """Handle background color picker change"""
        color = event.GetColour()
        self.main_frame.on_action_bg_color_changed(color)

    def _on_paint(self, _evt):
        """Paint the gradient background"""
        dc = wx.AutoBufferedPaintDC(self)
        w, h = self.GetClientSize()

        # Gradient colors
        top = wx.Colour(238, 238, 238)
        bot = wx.Colour(208, 208, 208)

        # Draw gradient background
        rect = wx.Rect(0, 0, w, h)
        dc.GradientFillLinear(rect, top, bot, wx.SOUTH)

        # Bottom border line
        line_color = wx.Colour(180, 180, 180)
        dc.SetPen(wx.Pen(line_color))
        dc.DrawLine(0, h - 1, w, h - 1)

    # Public API methods for external access to color pickers
    def get_fg_color(self):
        """Get the current foreground color"""
        return self.fg_color_picker.GetColour()

    def get_bg_color(self):
        """Get the current background color"""
        return self.bg_color_picker.GetColour()

    def set_fg_color(self, color):
        """Set the foreground color"""
        self.fg_color_picker.SetColour(color)

    def set_bg_color(self, color):
        """Set the background color"""
        self.bg_color_picker.SetColour(color)
