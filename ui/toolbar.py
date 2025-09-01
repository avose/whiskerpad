from __future__ import annotations

import wx

from ui.icons import wpIcons
from ui.file_dialogs import choose_image_files


class Toolbar(wx.Panel):
    """
    Simple toolbar with a vertical gradient background and buttons.
    Buttons: Open Notebook, Add Child, Text Color, Background Color.
    """

    def __init__(
            self,
            parent: wx.Window,
            on_open,
            on_add_images,
            on_fg_color,
            on_bg_color,
            on_copy,
            on_paste,
            on_cut,
            on_delete,
    ):
        super().__init__(parent, style=wx.BORDER_NONE)

        # Store callbacks
        self._on_open = on_open
        self._on_add_images = on_add_images
        self._on_fg_color = on_fg_color
        self._on_bg_color = on_bg_color
        self._on_copy = on_copy
        self._on_paste = on_paste
        self._on_cut = on_cut
        self._on_delete = on_delete

        # Initialize UI components
        self._setup_painting()
        self._create_controls()
        self._setup_layout()
        self._bind_events()

        # Set minimum size
        self.SetMinSize((-1, 40))

    def _setup_painting(self):
        """Configure custom painting for gradient background"""
        self.SetDoubleBuffered(True)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def _create_controls(self):
        """Create all toolbar controls"""
        # Main action buttons
        self.btn_open = self._create_icon_button("book_add", "Open Notebook")
        self.btn_add_images = self._create_icon_button("image_add", "Add Image(s)")
        self.btn_delete = self._create_icon_button("delete", "Delete")

        # Clipboard buttons
        self.btn_copy = self._create_icon_button("page_white_copy", "Copy")
        self.btn_paste = self._create_icon_button("paste_plain", "Paste")
        self.btn_cut = self._create_icon_button("cut", "Cut")

        # Color picker sections
        self.fg_section = self._create_fg_color_section()
        self.bg_section = self._create_bg_color_section()

    def _create_icon_button(self, icon_name: str, tooltip: str):
        """Create a standard icon button"""
        bmp = wpIcons.Get(icon_name)
        if bmp and bmp.IsOk():
            btn = wx.BitmapButton(self, bitmap=bmp, style=wx.BU_EXACTFIT | wx.NO_BORDER)
        else:
            # Fallback bitmap if icon not found
            fallback = wx.Bitmap(16, 16)
            btn = wx.BitmapButton(self, bitmap=fallback, style=wx.BU_EXACTFIT | wx.NO_BORDER)
            tooltip += " (icon missing)"

        btn.SetToolTip(wx.ToolTip(tooltip))
        btn.SetCanFocus(False)  # Prevent button from stealing focus
        return btn

    def _create_fg_color_section(self):
        """Create foreground color picker with icon label"""
        section_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Get style icon for foreground color
        style_icon = wpIcons.Get("style")
        if style_icon and style_icon.IsOk():
            fg_icon = wx.StaticBitmap(self, bitmap=style_icon)
            fg_icon.SetToolTip(wx.ToolTip("Text Color"))
        else:
            # Fallback to small text if icon not found
            fg_icon = wx.StaticText(self, label="Text Color")
            fg_icon.SetFont(wx.Font(7, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))

        # Create color picker
        self.fg_color_picker = wx.ColourPickerCtrl(
            self,
            colour=wx.Colour(0, 0, 0),  # Black default
            size=wx.Size(32, 20),  # Keep it small
            style=wx.CLRP_DEFAULT_STYLE
        )
        self.fg_color_picker.SetToolTip(wx.ToolTip("Text Color"))

        # Add to section sizer
        section_sizer.Add(fg_icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        section_sizer.Add(self.fg_color_picker, 0, wx.ALIGN_CENTER_VERTICAL)

        return section_sizer

    def _create_bg_color_section(self):
        """Create background color picker with icon label"""
        section_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Get paintbrush icon for background color
        paintbrush_icon = wpIcons.Get("paintbrush")
        if paintbrush_icon and paintbrush_icon.IsOk():
            bg_icon = wx.StaticBitmap(self, bitmap=paintbrush_icon)
            bg_icon.SetToolTip(wx.ToolTip("Highlight Color"))
        else:
            # Fallback to small text if icon not found
            bg_icon = wx.StaticText(self, label="Highlight")
            bg_icon.SetFont(wx.Font(7, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))

        # Create color picker
        self.bg_color_picker = wx.ColourPickerCtrl(
            self,
            colour=wx.Colour(246, 252, 246),  # View background default
            size=wx.Size(32, 20),  # Keep it small
            style=wx.CLRP_DEFAULT_STYLE
        )
        self.bg_color_picker.SetToolTip(wx.ToolTip("Highlight Color"))

        # Add to section sizer
        section_sizer.Add(bg_icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        section_sizer.Add(self.bg_color_picker, 0, wx.ALIGN_CENTER_VERTICAL)

        return section_sizer

    def _setup_layout(self):
        """Arrange all controls in the toolbar layout"""
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Left side - main buttons
        main_sizer.AddSpacer(2)
        main_sizer.Add(self.btn_open, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2)
        main_sizer.Add(self.btn_add_images, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2)
        main_sizer.Add(self.btn_delete, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2)

        # Clipboard buttons
        main_sizer.AddSpacer(6)  # Small separator
        main_sizer.Add(self.btn_cut, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2)
        main_sizer.Add(self.btn_copy, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2)
        main_sizer.Add(self.btn_paste, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2)

        # Color picker sections
        main_sizer.AddSpacer(6)  # Small separator
        main_sizer.Add(self.fg_section, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2)
        main_sizer.Add(self.bg_section, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2)

        # Right side - stretch spacer
        main_sizer.AddStretchSpacer(1)
        main_sizer.AddSpacer(6)

        self.SetSizer(main_sizer)

    def _bind_events(self):
        """Bind all event handlers"""
        # Button events
        self.btn_open.Bind(wx.EVT_BUTTON, lambda evt: self._on_open(evt))
        self.btn_add_images.Bind(wx.EVT_BUTTON, lambda evt: self._on_add_images_click())
        self.btn_delete.Bind(wx.EVT_BUTTON, lambda evt: self._on_delete(evt))

        # Clipboard button events
        self.btn_copy.Bind(wx.EVT_BUTTON, lambda evt: self._on_copy(evt) if self._on_copy else None)
        self.btn_paste.Bind(wx.EVT_BUTTON, lambda evt: self._on_paste(evt) if self._on_paste else None)
        self.btn_cut.Bind(wx.EVT_BUTTON, lambda evt: self._on_cut(evt) if self._on_cut else None)

        # Color picker events
        self.fg_color_picker.Bind(wx.EVT_COLOURPICKER_CHANGED, self._on_fg_color_changed)
        self.bg_color_picker.Bind(wx.EVT_COLOURPICKER_CHANGED, self._on_bg_color_changed)

    def _on_fg_color_changed(self, event):
        """Handle foreground color picker change"""
        if callable(self._on_fg_color):
            color = event.GetColour()
            self._on_fg_color(color)

    def _on_bg_color_changed(self, event):
        """Handle background color picker change"""
        if callable(self._on_bg_color):
            color = event.GetColour()
            self._on_bg_color(color)

    def _on_add_images_click(self):
        """Open a file picker and report selected image paths"""
        try:
            paths = choose_image_files(self, multiple=True)
            if not paths:
                return

            if callable(self._on_add_images):
                self._on_add_images(paths)

        except Exception as e:
            wx.LogError(f"Image selection failed: {e}")

    def _on_paint(self, _evt):
        """Paint the gradient background"""
        dc = wx.AutoBufferedPaintDC(self)
        w, h = self.GetClientSize()

        # Gradient colors
        top = wx.Colour(238, 238, 238)
        bot = wx.Colour(208, 208, 208)

        # Draw gradient background
        rect = wx.Rect(0, 0, w, h)
        if hasattr(dc, 'GradientFillLinear'):
            dc.GradientFillLinear(rect, top, bot, wx.SOUTH)
        else:
            # Fallback for older wxPython versions
            dc.SetBrush(wx.Brush(top))
            dc.SetPen(wx.Pen(top))
            dc.DrawRectangle(rect)

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
