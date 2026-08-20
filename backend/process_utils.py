from __future__ import annotations

import os
import subprocess
import time
from typing import Any

_ORIGINAL_OS_REPLACE = os.replace
_WINDOWS_REPLACE_DELAYS = (0.01, 0.02, 0.04, 0.08, 0.16, 0.25, 0.40, 0.60)
_WINDOWS_TRANSIENT_REPLACE_ERRORS = {5, 32, 33}  # access denied / sharing / lock violation


def atomic_replace_with_retry(source, destination):
    """Preserve os.replace semantics while tolerating transient Windows locks.

    Defender/indexers and just-closed process handles can briefly hold the
    destination. Retrying the atomic promotion is safe because the destination
    is never truncated or rewritten in place; the fully-written staging file
    remains the source until replacement succeeds or the bounded retry expires.
    """
    for attempt in range(len(_WINDOWS_REPLACE_DELAYS) + 1):
        try:
            return _ORIGINAL_OS_REPLACE(source, destination)
        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            transient = isinstance(exc, PermissionError) or winerror in _WINDOWS_TRANSIENT_REPLACE_ERRORS
            if os.name != "nt" or not transient or attempt >= len(_WINDOWS_REPLACE_DELAYS):
                raise
            time.sleep(_WINDOWS_REPLACE_DELAYS[attempt])


def install_windows_atomic_replace_retry() -> bool:
    if os.name != "nt":
        return False
    if getattr(os.replace, "_dws_windows_retry", False):
        return True
    atomic_replace_with_retry._dws_windows_retry = True
    os.replace = atomic_replace_with_retry
    return True


# process_utils is intentionally imported before profile_store by the service
# graph. Install once so all later atomic JSON/cache/profile promotions inherit
# the same bounded Windows behavior without weakening their atomicity.
install_windows_atomic_replace_retry()


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
