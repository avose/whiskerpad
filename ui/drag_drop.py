import wx
from utils.image_types import is_supported_image_path

class ImageDropTarget(wx.FileDropTarget):
    """
    Drag & drop handler for image files.
    Filters for supported image types and calls a callback with the file paths.
    """
    def __init__(self, view, on_image_drop_callback):
        super().__init__()
        self.view = view
        self.on_image_drop = on_image_drop_callback
        self._drag_active = False

    def OnEnter(self, x, y, defResult):
        """Visual feedback when drag enters the view"""
        self._drag_active = True
        self.view.SetCursor(wx.Cursor(wx.CURSOR_COPY_ARROW))
        return wx.DragCopy

    def OnLeave(self):
        """Clean up when drag leaves"""
        self._drag_active = False
        self.view.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))

    def OnDragOver(self, x, y, defResult):
        """Continue showing visual feedback during drag"""
        return wx.DragCopy if self._drag_active else wx.DragNone

    def OnDropFiles(self, x, y, filenames):
        """Handle the actual file drop"""
        # Filter for supported image files only
        image_files = [f for f in filenames if is_supported_image_path(f)]
        
        if not image_files:
            wx.LogWarning("No supported image files in drop")
            self.view.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))
            self._drag_active = False
            return False
        
        # Reset cursor
        self.view.SetCursor(wx.Cursor(wx.CURSOR_DEFAULT))
        self._drag_active = False
        
        # Call the same callback that the toolbar button uses!
        if callable(self.on_image_drop):
            self.on_image_drop(image_files)
        
        return True
