# app.py
'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''
import sys
import traceback
import wx

from core.log import Log

def on_exception(exc_type, exc_value, exc_traceback):
    """Show unhandled exceptions in a dialog instead of silent failure."""
    if issubclass(exc_type, KeyboardInterrupt):
        # Allow Ctrl+C to work normally
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Format the full traceback
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    tb_text = ''.join(tb_lines)
    error_message = f"!ERROR! Unhandled Exception:\n{tb_text}"

    try:
        # Show on status bar
        main_frame = wx.GetApp().GetTopWindow()
        if hasattr(main_frame, 'SetStatusText'):
            Log.debug(error_message, 0)
            main_frame.SetStatusText(error_message)
    except:
        try:
            # Show in log
            Log.debug(error_message, 0)
        except:
            # Print to console
            print(error_message)

if tuple(getattr(wx, 'VERSION', (0,0,0))[:3]) < (4, 2, 3):
    raise RuntimeError(f"WhiskerPad requires wxPython ≥ 4.2.3; found {wx.__version__}")

from whiskerpad.ui.main_frame import MainFrame

def main(verbosity: int = 0, stdexp: bool = False):
    # Install the exception handler
    if not stdexp:
        sys.excepthook = on_exception

    app = wx.App(False)

    frame = MainFrame(verbosity=verbosity)
    frame.Show()

    return app.MainLoop()
