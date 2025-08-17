import wx
if tuple(getattr(wx, 'VERSION', (0,0,0))[:3]) < (4, 2, 3):
    raise RuntimeError(f"WhiskerPad requires wxPython ≥ 4.2.3; found {wx.__version__}")
from whiskerpad.ui.main_frame import MainFrame

def main():
    app = wx.App(False)
    frame = MainFrame()
    frame.Show()
    app.MainLoop()
