'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''
from __future__ import annotations

import tempfile
import os
from pathlib import Path
from typing import Optional
import wx

__all__ = ["Clipboard"]

class Clipboard:
    """
    Unified clipboard operations for text and images with cross-platform compatibility.
    """

    @staticmethod
    def copy_text(text: str) -> bool:
        """Copy text to clipboard with Mac compatibility improvements."""
        if not text:
            raise ValueError("Cannot copy empty text")

        if not wx.TheClipboard.Open():
            raise RuntimeError("Could not open clipboard")

        try:
            data = wx.TextDataObject(text)
            success = wx.TheClipboard.SetData(data)
            if success:
                wx.TheClipboard.Flush()  # Critical for Mac compatibility
            return success
        finally:
            wx.TheClipboard.Close()

    @staticmethod
    def get_text() -> Optional[str]:
        """Get text from clipboard if available."""
        if not wx.TheClipboard.Open():
            raise RuntimeError("Could not open clipboard")

        try:
            if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_UNICODETEXT)):
                data = wx.TextDataObject()
                success = wx.TheClipboard.GetData(data)
                if success:
                    return data.GetText()
            return None
        finally:
            wx.TheClipboard.Close()

    @staticmethod
    def copy_image(image_path: str) -> bool:
        """Copy full-sized image file to clipboard for cross-platform compatibility."""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")

        if not wx.TheClipboard.Open():
            raise RuntimeError("Could not open clipboard for image copy")

        try:
            # Load image and convert to bitmap for cross-platform compatibility
            image = wx.Image(image_path)
            if not image.IsOk():
                raise RuntimeError(f"Could not load image: {image_path}")

            bitmap = wx.Bitmap(image)

            # Create composite data object for maximum compatibility
            composite = wx.DataObjectComposite()

            # Add bitmap data (works with most image editors)
            bitmap_data = wx.BitmapDataObject(bitmap)
            composite.Add(bitmap_data, True)  # True = preferred format

            # Add file data (works with file managers)
            file_data = wx.FileDataObject()
            file_data.AddFile(image_path)
            composite.Add(file_data, False)

            success = wx.TheClipboard.SetData(composite)
            if success:
                wx.TheClipboard.Flush()
            else:
                raise RuntimeError("Failed to set image data on clipboard")

            return success
        finally:
            wx.TheClipboard.Close()

    @staticmethod
    def has_image() -> bool:
        """Check if clipboard contains image data (bitmap or files)."""
        if not wx.TheClipboard.Open():
            raise RuntimeError("Could not open clipboard")

        try:
            # Check for bitmap data first
            if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_BITMAP)):
                return True

            # Check for file data that might be images
            if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_FILENAME)):
                file_data = wx.FileDataObject()
                if wx.TheClipboard.GetData(file_data):
                    filenames = file_data.GetFilenames()
                    if filenames:
                        # Check if any file is a supported image format
                        image_files = [f for f in filenames if Clipboard._is_image_file(f)]
                        return len(image_files) > 0

            return False
        finally:
            wx.TheClipboard.Close()

    @staticmethod
    def get_image() -> Optional[str]:
        """Get image data from clipboard and save to temp file. Returns temp file path."""
        if not wx.TheClipboard.Open():
            raise RuntimeError("Could not open clipboard")

        try:
            temp_path = None

            # Try to get bitmap data first (from screenshots, image editors)
            if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_BITMAP)):
                bitmap_data = wx.BitmapDataObject()
                if wx.TheClipboard.GetData(bitmap_data):
                    bitmap = bitmap_data.GetBitmap()
                    if bitmap.IsOk():
                        # Convert bitmap to image and save to temp file
                        image = bitmap.ConvertToImage()
                        temp_fd, temp_path = tempfile.mkstemp(suffix='.png')
                        os.close(temp_fd)  # Close the file descriptor

                        if image.SaveFile(temp_path, wx.BITMAP_TYPE_PNG):
                            return temp_path
                        else:
                            os.unlink(temp_path)
                            raise RuntimeError(f"Failed to save bitmap to {temp_path}")

            # Try to get file data (from file managers)
            if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_FILENAME)):
                file_data = wx.FileDataObject()
                if wx.TheClipboard.GetData(file_data):
                    filenames = file_data.GetFilenames()
                    if filenames:
                        # Return first supported image file
                        for filename in filenames:
                            if Clipboard._is_image_file(filename) and os.path.exists(filename):
                                return filename

            return None
        finally:
            wx.TheClipboard.Close()

    @staticmethod
    def _is_image_file(filepath: str) -> bool:
        """Check if file is a supported image type."""
        try:
            from utils.image_types import is_supported_image_path
            return is_supported_image_path(filepath)
        except ImportError:
            # Fallback to basic extension check
            ext = Path(filepath).suffix.lower()
            return ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp']
