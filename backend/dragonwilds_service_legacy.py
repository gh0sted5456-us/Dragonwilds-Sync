from __future__ import annotations

"""Deprecated module-name alias for :mod:`dragonwilds_service_compat`.

Current code should use ``dragonwilds_service_compat``.  Keep this tiny alias for
one compatibility cycle so older internal imports and saved tooling continue to
resolve the same module object without maintaining a second service engine.
"""

import sys as _sys
import dragonwilds_service_compat as _compat

# Make both module names resolve to the exact same object. This is important for
# runtime patches that inspect/modify the service through ``sys.modules``.
_sys.modules[__name__] = _compat
