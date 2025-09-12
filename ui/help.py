################################################################################################
'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.

This file holds the code for windows created by the Help menu: About and Donate.
'''
################################################################################################

import wx
import os
from pathlib import Path

from core.version import wpVersion
from ui.icons import wpIcons

################################################################################################
class BackgroundPanel(wx.Panel):
    def __init__(self, parent, image_path):
        super().__init__(parent)

        # CRITICAL: Must set background style before using AutoBufferedPaintDC
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)

        self.background_bmp = wx.Bitmap(image_path, wx.BITMAP_TYPE_PNG)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda evt: None)  # Prevent flicker

    def on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.Clear()
        dc.DrawBitmap(self.background_bmp, 0, 0)

class wpAboutFrame(wx.Frame):
    def __init__(self, parent, style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX)):
        wx.Frame.__init__(self, parent, title="About WhiskerPad", style=style)

        self.icon = wx.Icon()
        self.icon.CopyFromBitmap(wpIcons.Get('information'))
        self.SetIcon(self.icon)

        # Load background image
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_pdir = Path(script_dir).parent.absolute()
        img_dir = os.path.join(script_pdir, "images")
        image_path = os.path.join(img_dir, "whiskerpad.jpg")

        # Create background panel
        self.main_panel = BackgroundPanel(self, image_path)

        # Get image dimensions
        bmp_size = self.main_panel.background_bmp.GetSize()
        bmp_width = bmp_size.width
        bmp_height = bmp_size.height

        # Create main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Centered title at top
        title_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.st_title = wx.StaticText(self.main_panel, wx.ID_ANY, "WhiskerPad")
        self.st_title.SetFont(wx.Font(wx.FontInfo(12).Bold()))
        self.st_title.SetForegroundColour(wx.Colour(50, 50, 50))
        title_sizer.AddStretchSpacer()
        title_sizer.Add(self.st_title, 0, wx.ALIGN_CENTER)
        title_sizer.AddStretchSpacer()
        main_sizer.Add(title_sizer, 0, wx.EXPAND | wx.TOP, 20)
        # Version
        version_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.st_version = wx.StaticText(self.main_panel, wx.ID_ANY, f"(v{wpVersion})")
        self.st_version.SetFont(wx.Font(wx.FontInfo(10).Bold()))
        self.st_version.SetForegroundColour(wx.Colour(50, 50, 50))
        version_sizer.AddStretchSpacer()
        version_sizer.Add(self.st_version, 0, wx.ALIGN_CENTER)
        version_sizer.AddStretchSpacer()
        main_sizer.Add(version_sizer, 0, wx.EXPAND | wx.BOTTOM, 20)

        # Horizontal sizer for description on right half
        content_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Left spacer (left half of frame)
        content_sizer.AddSpacer(bmp_width // 4)

        # Description text on right half
        self.description = (
            "WhiskerPad is a hierarchical note-taking\n"
            "application inspired by Circus Ponies.\n\n"
            "Open-Source Software by ~Aaron Vose."
        )
        self.st_description = wx.StaticText(
            self.main_panel,
            wx.ID_ANY,
            self.description,
            size=(bmp_width // 4 * 3 - 40, -1)
        )
        self.st_description.SetFont(wx.Font(wx.FontInfo(10)))
        self.st_description.SetForegroundColour(wx.Colour(70, 70, 70))
        content_sizer.Add(self.st_description, 0, wx.ALL, 20)

        main_sizer.Add(content_sizer, 1, wx.EXPAND)

        # OK button at bottom right
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_ok = wx.Button(self.main_panel, wx.ID_OK, "OK")
        self.btn_ok.SetBitmap(wpIcons.Get("tick"))
        button_sizer.AddStretchSpacer()
        button_sizer.Add(self.btn_ok, 0, wx.ALL, 4)
        main_sizer.Add(button_sizer, 0, wx.EXPAND)

        # Set sizer and frame size
        self.main_panel.SetSizer(main_sizer)
        self.SetClientSize(bmp_size)

        # Lock the frame size (prevent resizing)
        self.SetMinSize(self.GetSize())
        self.SetMaxSize(self.GetSize())

        # Bind events
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.btn_ok.Bind(wx.EVT_BUTTON, self.OnClose)

        self.Center()
        self.Show(True)
        self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))

    def OnClose(self, event=None):
        self.Parent.about_frame = None
        self.Destroy()

################################################################################################
class wpDonateFrame(wx.Frame):

    def __init__(self, parent=None):
        style = wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX)
        super().__init__(parent, title="Support WhiskerPad", style=style)
        self.icon = wx.Icon()
        self.icon.CopyFromBitmap(wpIcons.Get('money_dollar'))
        self.SetIcon(self.icon)
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # Load and show the PNG image.
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_pdir = Path(script_dir).parent.absolute()
        img_dir = os.path.join(script_pdir, "images")
        image_path = os.path.join(img_dir, "btc_addr.png")
        bitmap = wx.Bitmap(image_path, wx.BITMAP_TYPE_PNG)
        qr_image = wx.StaticBitmap(panel, bitmap=bitmap)
        vbox.Add(qr_image, 0, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, 15)

        # Add label and address.
        btc_addr = "1DW8hyB4LgXu4kSdwJ8dYedGNvv49Pudsr"
        btc_label = wx.StaticText(panel, label="Bitcoin Address:")
        addr_sizer = wx.BoxSizer(wx.HORIZONTAL)
        addr_style = wx.TE_READONLY | wx.TE_CENTER | wx.BORDER_NONE
        addr_text = wx.TextCtrl(panel, value=btc_addr, style=addr_style)
        font = addr_text.GetFont()
        font.SetPointSize(9)
        addr_text.SetFont(font)
        copy_icon = wpIcons.Get('page_white_copy')
        copy_btn = wx.BitmapButton(panel, bitmap=copy_icon, style=wx.BORDER_NONE)
        copy_btn.Bind(wx.EVT_BUTTON, lambda evt: self.CopyToClipboard(btc_addr))
        addr_sizer.Add(addr_text, 1, wx.EXPAND | wx.RIGHT, 5)
        addr_sizer.Add(copy_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        vbox.Add(btc_label, 0, wx.ALIGN_CENTER | wx.BOTTOM, 2)
        vbox.Add(addr_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Add OK button to close.
        ok_btn = wx.Button(panel, label="OK")
        ok_btn.SetBitmap(wpIcons.Get("tick"))
        ok_btn.Bind(wx.EVT_BUTTON, self.OnClose)
        vbox.AddStretchSpacer()
        vbox.Add(ok_btn, 0, wx.ALIGN_RIGHT, 4)

        panel.SetSizer(vbox)
        panel.Layout()
        self.SetSize((300, 340))
        self.Centre()
        self.Show()
        self.SetCursor(wx.Cursor(wx.CURSOR_ARROW))

    def CopyToClipboard(self, text):
        # Copy BTC address to clipboard.
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()

    def OnClose(self, event):
        # Clear parent's donate_frame and close.
        self.Parent.donate_frame = None
        self.Close()

################################################################################################
