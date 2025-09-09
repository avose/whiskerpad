################################################################################################
'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.

This file holds the code for the main application window's status bar.
'''
################################################################################################

import wx
import datetime

from core.log import Log

################################################################################################
class LogList(wx.VListBox):
    DATE_W       = 20
    LINE_NUM_W   = 9
    LINE_MAX_PAD = 2

    def __init__(self, parent, log, size):
        self.log = log
        style = wx.LB_MULTIPLE | wx.LB_EXTENDED | wx.SIMPLE_BORDER
        self.char_w,self.char_h = 9,9
        super(LogList, self).__init__(parent, style=style, size=size)
        self.fontinfo = wx.FontInfo(9).FaceName("Monospace")
        self.font = wx.Font(self.fontinfo)
        dc = wx.MemoryDC()
        dc.SetFont(self.font)
        self.SetBackgroundColour((0,0,0))
        self.char_w,self.char_h = dc.GetTextExtent("X")
        self.SetItemCount(self.log.count())
        self.ScrollRows(self.log.count())
        self.Bind(wx.EVT_LEFT_UP, self._on_item_clicked)
        self.Show(True)
        return

    def LineWrapText(self, initial_text):
        if initial_text is None or len(initial_text) == 0:
            return ("", 0)
        max_offset = self.LINE_NUM_W + self.DATE_W + self.LINE_MAX_PAD
        max_len = max(1, int(self.Size[0]/self.char_w)-max_offset)
        nlines = 0
        text = ""
        initial_text = initial_text.replace("\t","    ")
        lines = initial_text.split("\n")
        for line in lines:
            while len(line) > max_len:
                text += line[0:max_len] + '\n'
                line = line[max_len:]
                nlines += 1
            text += line + '\n'
            nlines += 1
        return (text, nlines)

    def OnMeasureItem(self, index):
        timestamp, text = self.log.get(index)
        text, rows = self.LineWrapText(text)
        return  rows * self.char_h

    def OnDrawItem(self, dc, rect, index):
        timestamp, text = self.log.get(index)
        text, rows = self.LineWrapText(self.log.get(index)[1])
        dc.Clear()
        dc.SetFont(self.font)
        # Draw background and borders.
        if self.IsSelected(index):
            brush = wx.Brush((64,0,64))
        else:
            brush = wx.Brush((0,0,0))
        dc.SetBrush(brush)
        dc.SetPen(wx.Pen((0,0,100)))
        dc.DrawRectangle(rect[0], rect[1], rect[2], rect[3])
        dc.SetPen(wx.Pen((0,75,150)))
        offset = self.LINE_NUM_W - 0.5
        dc.DrawLine(rect[0] + int(offset*self.char_w), rect[1],
                    rect[0] + int(offset*self.char_w), rect[1]+rect[3])
        offset = self.LINE_NUM_W + self.DATE_W - 0.5
        dc.DrawLine(rect[0] + int(offset*self.char_w), rect[1],
                    rect[0] + int(offset*self.char_w), rect[1]+rect[3])
        # Draw log line number and date.
        dc.SetTextForeground((255,255,0))
        dc.DrawText("%d"%index, rect[0], rect[1])
        dc.SetTextForeground((255,0,255))
        offset = self.LINE_NUM_W
        dc.DrawText(timestamp, rect[0] + offset*self.char_w, rect[1])
        # Draw log entry text.
        dc.SetTextForeground((128,192,128))
        offset = self.LINE_NUM_W + self.DATE_W
        dc.DrawText(text, rect[0] + offset*self.char_w, rect[1])
        # Update to catch new log entries.
        self.SetItemCount(self.log.count())
        return

    def OnDrawBackground(self, dc, rect, index):
        dc.Clear()
        pen = wx.Pen((0,0,255))
        dc.SetPen(pen)
        brush = wx.Brush((0,0,0))
        dc.SetBrush(brush)
        dc.DrawRectangle(rect[0], rect[1], rect[2], rect[3])
        # Update to catch new log entries.
        self.SetItemCount(self.log.count())
        return

    def OnDrawSeparator(self, dc, rect, index):
        return

    def _on_item_clicked(self, event):
        """Copy the clicked log entry's text to clipboard."""
        # Let the normal selection handling happen first
        event.Skip()

        # Get the item that was clicked
        pos = event.GetPosition()
        item_index = self.VirtualHitTest(pos.y)

        if item_index != wx.NOT_FOUND and item_index < self.log.count():
            # Get the log entry - this returns (timestamp, text)
            timestamp, text = self.log.get(item_index)

            # Copy just the text portion (not timestamp or index) to clipboard
            if text:
                data_obj = wx.TextDataObject(text)
                wx.TheClipboard.Open()  # Let it fail if clipboard can't open
                wx.TheClipboard.SetData(data_obj)
                wx.TheClipboard.Close()


################################################################################################
class StatusBarPopup(wx.PopupTransientWindow):
    WIN_HEIGHT = 300

    def __init__(self, parent, log):
        style = wx.SIMPLE_BORDER
        wx.PopupTransientWindow.__init__(self, parent, style)
        self.log = log
        box_main = wx.BoxSizer(wx.VERTICAL)
        self.log_list = LogList(
            self,
            self.log,
            (parent.Size[0], max(self.WIN_HEIGHT, parent.Size[1]))
        )
        box_main.Add(self.log_list, 1, wx.EXPAND)
        self.SetSizerAndFit(box_main)
        self.Show(True)
        return

    def ProcessLeftDown(self, event):
        return wx.PopupTransientWindow.ProcessLeftDown(self, event)

    def OnDismiss(self):
        self.Parent.popup = None
        return

################################################################################################
class StatusBar(wx.StatusBar):
    def __init__(self, parent):
        super(StatusBar, self).__init__(parent)
        
        # Remove all left-click handlers
        self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
        
        Log.add("Create StatusBar")
        self.popup = None
        return

    def OnRightDown(self, event):
        """Handle right-click to show context menu with log options."""
        # Create popup menu
        menu = wx.Menu()
        
        item_show_log = menu.Append(wx.ID_ANY, "Show Log")
        menu.AppendSeparator()
        item_save = menu.Append(wx.ID_SAVE, "Save Log to File...")
        item_copy = menu.Append(wx.ID_COPY, "Copy Log to Clipboard")
        menu.AppendSeparator()
        item_clear = menu.Append(wx.ID_CLEAR, "Clear Log")
        
        # Bind menu events
        self.Bind(wx.EVT_MENU, self.OnShowLog, item_show_log)
        self.Bind(wx.EVT_MENU, self.OnSaveLogToFile, item_save)
        self.Bind(wx.EVT_MENU, self.OnCopyLogToClipboard, item_copy)
        self.Bind(wx.EVT_MENU, self.OnClearLog, item_clear)
        
        # Show the popup menu at mouse position
        self.PopupMenu(menu)
        menu.Destroy()

    def OnShowLog(self, event):
        """Show the log popup window."""
        if self.popup is not None:
            self.popup.Dismiss()
            self.popup = None

        self.popup = StatusBarPopup(self, Log)
        pos = self.ClientToScreen((0, 0))
        self.popup.Position((pos[0], pos[1] - StatusBarPopup.WIN_HEIGHT), (0, 0))
        self.popup.Popup()

    def OnSaveLogToFile(self, event):
        """Save log to a text file."""
        with wx.FileDialog(
            self, 
            "Save Log to file", 
            wildcard="Text files (*.txt)|*.txt|Log files (*.log)|*.log|All files (*.*)|*.*", 
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        ) as fileDialog:
            
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            
            path = fileDialog.GetPath()
            Log.write_to_file(path)
            self.SetStatusText(f"Log saved to: {path}")

    def OnCopyLogToClipboard(self, event):
        """Copy entire log to clipboard."""
        try:
            # Format log entries for clipboard
            log_entries = Log.get()
            clipboard_content = "\n".join([f"[{timestamp}] {message}" for timestamp, message in log_entries])
            
            # Copy to clipboard
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(clipboard_content))
                wx.TheClipboard.Close()
                self.SetStatusText(f"Copied {len(log_entries)} log entries to clipboard")
            else:
                self.SetStatusText("Error: Could not access clipboard")
                
        except Exception as e:
            self.SetStatusText(f"Error copying to clipboard: {e}")

    def OnClearLog(self, event):
        """Clear the log after confirmation."""
        result = wx.MessageBox(
            "Are you sure you want to clear the entire log?", 
            "Clear Log", 
            wx.YES_NO | wx.ICON_QUESTION
        )
        
        if result == wx.YES:
            Log.clear()
            self.SetStatusText("Log cleared")

################################################################################################
