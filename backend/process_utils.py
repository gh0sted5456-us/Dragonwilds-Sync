from __future__ import annotations

import os
import subprocess
from typing import Any


def hidden_process_kwargs() -> dict[str, Any]:
    """Return Windows flags that keep helper/console processes invisible.

    Dragonwilds Sync owns its logs and progress surfaces. Background helpers such
    as PowerShell, tasklist, netsh, SteamCMD, Defender, and the dedicated server
    should never flash a console window just because the user opened a World.
    """
    if os.name != "nt":
        return {}
    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
    startupinfo.wShowWindow = 0
    return {"creationflags": flags, "startupinfo": startupinfo}


def _merge(kwargs: dict[str, Any]) -> dict[str, Any]:
    merged = dict(kwargs)
    for key, value in hidden_process_kwargs().items():
        merged.setdefault(key, value)
    return merged


def popen_hidden(args, **kwargs):
    return subprocess.Popen(args, **_merge(kwargs))


def run_hidden(args, **kwargs):
    return subprocess.run(args, **_merge(kwargs))


def check_output_hidden(args, **kwargs):
    return subprocess.check_output(args, **_merge(kwargs))
