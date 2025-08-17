from __future__ import annotations
import wx

# Use your icons.py (Silk icons via wpIcons)
from ui.icons import wpIcons
from ui.file_dialogs import choose_image_files

class TopToolbar(wx.Panel):
    """
    Simple top toolbar with a vertical gradient background and icon-only buttons.
    Buttons: Open Notebook, Add Child.
    """
    def __init__(self, parent: wx.Window, on_open, on_add_images):
        super().__init__(parent, style=wx.BORDER_NONE)
        self._on_open = on_open
        self._on_add_images = on_add_images

        # Reduce flicker and allow custom paint
        self.SetDoubleBuffered(True)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)
        self.Bind(wx.EVT_PAINT, self._on_paint)

        # Layout
        s = wx.BoxSizer(wx.HORIZONTAL)
        s.AddSpacer(6)

        btn_open = self._make_icon_button("application_get", "Open Notebook", self._on_open)
        s.Add(btn_open, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)

        # Add Image(s)
        btn_img = self._make_icon_button("image_add", "Add Image(s)", self._on_add_images_click)
        s.Add(btn_img, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)

        s.AddStretchSpacer(1)
        s.AddSpacer(6)
        self.SetSizer(s)

        # Reasonable height
        self.SetMinSize((-1, 40))

    def _make_icon_button(self, icon_name: str, tooltip: str, handler):
        bmp = None
        if 'wpIcons' in globals() and hasattr(wpIcons, 'Get'):
            bmp = wpIcons.Get(icon_name)
        if isinstance(bmp, wx.Bitmap) and bmp.IsOk():
            btn = wx.BitmapButton(self, bitmap=bmp, style=wx.BU_EXACTFIT | wx.NO_BORDER)
            btn.SetToolTip(tooltip)
        else:
            fallback = wx.Bitmap(16, 16)
            btn = wx.BitmapButton(self, bitmap=fallback, style=wx.BU_EXACTFIT | wx.NO_BORDER)
            btn.SetToolTip(tooltip + " (icon missing)")
        btn.Bind(wx.EVT_BUTTON, lambda evt: handler())
        return btn

    def _on_paint(self, _evt):
        dc = wx.AutoBufferedPaintDC(self)
        w, h = self.GetClientSize()
        top = wx.Colour(238, 238, 238)
        bot = wx.Colour(208, 208, 208)
        rect = wx.Rect(0, 0, w, h)
        if hasattr(dc, 'GradientFillLinear'):
            dc.GradientFillLinear(rect, top, bot, wx.SOUTH)
        else:
            dc.SetBrush(wx.Brush(top))
            dc.SetPen(wx.Pen(top))
            dc.DrawRectangle(rect)
        line = wx.Colour(180, 180, 180)
        dc.SetPen(wx.Pen(line))
        dc.DrawLine(0, h - 1, w, h - 1)

    def _on_add_images_click(self):
        """
        Open a file picker and report selected image paths.
        (Next step will import into the current entry and create new node(s).)
        If a handler was provided, pass the selected paths to it.
        """
        try:
            paths = choose_image_files(self, multiple=True)
            if not paths:
                return
            # Forward to app handler if available
            if callable(self._on_add_images):
                self._on_add_images(paths)
        except Exception as e:
            wx.LogError(f"Image selection failed: {e}")
