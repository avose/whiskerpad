################################################################################################
'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.

This file holds the code for loading PNG icon images.
'''
################################################################################################

import os
from pathlib import Path
import wx

################################################################################################

class wpIconManager:
    """
    Lazy icon manager:
      - Does NOT load bitmaps at import time (safe before wx.App exists).
      - Loads from <project_root>/icons/*.png (i.e., one level up from ui/).
    """
    __icons = {}
    __loaded = False

    def _load_if_needed(self):
        if wpIconManager.__loaded:
            return
        script_dir = os.path.dirname(os.path.abspath(__file__))  # .../whiskerpad/ui
        project_root = Path(script_dir).parent  # .../whiskerpad
        img_dir = project_root / "icons"
        if img_dir.is_dir():
            for fname in os.listdir(img_dir):
                name, ext = os.path.splitext(fname)
                if ext.lower() != ".png":
                    continue
                try:
                    bmp = wx.Bitmap(wx.Image(str(img_dir / fname), wx.BITMAP_TYPE_ANY))
                    if bmp.IsOk():
                        wpIconManager.__icons[name] = bmp
                except Exception:
                    # Ignore individual icon load failures
                    pass
        wpIconManager.__loaded = True

    def Get(self, name):
        self._load_if_needed()
        return wpIconManager.__icons.get(name)

################################################################################################

# Create a shared instance, but loading is deferred until first Get()
wpIcons = wpIconManager()

################################################################################################
