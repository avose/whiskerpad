'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''
from functools import wraps

def check_read_only(method):
    """Decorator to silently skip method execution if in read-only mode."""
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        if self.is_read_only():
            return
        return method(self, *args, **kwargs)
    return wrapper
