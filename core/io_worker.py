# core/io_worker.py
'''
Copyright 2025 Aaron Vose (avose@aaronvose.net)
Licensed under the LGPL v2.1; see the file 'LICENSE' for details.
'''
import threading
import queue
import traceback

import wx

class IOWorker:
    """Single background thread for file/IO tasks. GUI stays in wx main thread."""

    def __init__(self):
        self._q = queue.Queue()
        self._t = threading.Thread(target=self._run, name="IOWorker", daemon=True)
        self._t.start()

    def submit(self, fn, *args, callback=None, **kwargs):
        """Queue a task; callback(result, error) runs on GUI thread via wx.CallAfter."""
        self._q.put((fn, args, kwargs, callback))

    def _run(self):
        """Background thread main loop."""
        while True:
            fn, args, kwargs, cb = self._q.get()
            result = None
            err = None

            try:
                result = fn(*args, **kwargs)
            except Exception as e:
                err = (e, traceback.format_exc())

            if cb:
                wx.CallAfter(cb, result, err)
            elif err is not None:
                # No callback provided; print traceback to aid debugging.
                print(err[1], end="")

            self._q.task_done()
