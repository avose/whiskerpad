from __future__ import annotations
import wx

# Use your icons.py (Silk icons via wpIcons)
from ui.icons import wpIcons  # fallback if imported oddly

class TopToolbar(wx.Panel):
    """
    Simple top toolbar with a vertical gradient background and icon-only buttons.
    Buttons: Open Notebook, Add Child.
    """
    def __init__(self, parent: wx.Window, on_open, on_add_child=None):
        super().__init__(parent, style=wx.BORDER_NONE)
        self._on_open = on_open
        self._on_add_child = on_add_child

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

        btn_add = self._make_icon_button(
            "application_side_expand",
            "Add Child",
            lambda: self._on_add_child() if self._on_add_child else None,
        )
        s.Add(btn_add, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)

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
