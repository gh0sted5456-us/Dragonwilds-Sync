"""PyInstaller runtime hook for Dragonwilds Sync service stdio.

Windows PowerShell 5.1 may prefix the first string piped to a native process
with U+FEFF even when the requested output encoding is UTF-8 without a BOM.
Electron's service transport never does this, but the packaged JSON-RPC service
is also intentionally scriptable. Strip exactly one leading BOM from the first
stdin line while otherwise behaving like the original stream.
"""
from __future__ import annotations

import sys


class _BomStrippingStdin:
    def __init__(self, stream):
        self._stream = stream
        self._first_read = True

    def _clean(self, value):
        if self._first_read and isinstance(value, str):
            self._first_read = False
            return value[1:] if value.startswith("\ufeff") else value
        self._first_read = False
        return value

    def readline(self, *args, **kwargs):
        return self._clean(self._stream.readline(*args, **kwargs))

    def __iter__(self):
        return self

    def __next__(self):
        return self._clean(next(self._stream))

    def reconfigure(self, *args, **kwargs):
        callback = getattr(self._stream, "reconfigure", None)
        if callable(callback):
            return callback(*args, **kwargs)
        return None

    def __getattr__(self, name):
        return getattr(self._stream, name)


sys.stdin = _BomStrippingStdin(sys.stdin)
