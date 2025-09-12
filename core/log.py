################################################################################################

'''

Copyright 2025 Aaron Vose (avose@aaronvose.net)

Licensed under the LGPL v2.1; see the file 'LICENSE' for details.

This file holds the code for the info / debug logger.

'''

################################################################################################

import inspect
from datetime import datetime

################################################################################################

class LogManager():
    __log = None

    def __init__(self, verbosity: int = 0):
        if LogManager.__log is None:
            now = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
            LogManager.__log = [(now, "Begin WhiskerPad Log")]
        self.verbosity = verbosity

    def add(self, text: str):
        now = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        LogManager.__log.append((now, text))

    def debug(self, text: str, level: int = 0):
        if self.verbosity >= level:
            # Get caller's filename automatically
            stack = inspect.stack()
            if len(stack) > 1:
                caller_frame = stack[1]
                # Just filename, not full path
                filename = caller_frame.filename.split('/')[-1]
            else:
                filename = "unknown"

            # Format: [filename] message (removed debug level)
            formatted_msg = f"[{filename}] {text}"
            self.add(formatted_msg)

    def get(self, index: int = None):
        if index is not None:
            return LogManager.__log[index]
        return LogManager.__log.copy()

    def count(self):
        return len(LogManager.__log)

    def set_verbosity(self, verbosity: int = 0):
        self.verbosity = verbosity

    def clear(self):
        """Clear all log entries."""
        if LogManager.__log is not None:
            LogManager.__log.clear()
            now = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
            LogManager.__log.append((now, "Log cleared"))

    def write_to_file(self, filepath: str):
        """Write all log entries to a file."""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                for timestamp, message in LogManager.__log:
                    f.write(f"[{timestamp}] {message}\n")
            self.add(f"Log written to file: {filepath}")
        except Exception as e:
            self.add(f"Failed to write log to file '{filepath}': {e}")

################################################################################################

Log = LogManager()

################################################################################################
