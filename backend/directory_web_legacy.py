from __future__ import annotations

"""Deprecated module-name alias for :mod:`directory_web_compat`.

Current code should use ``directory_web_compat``. Keep this alias for one
compatibility cycle so older imports resolve the same WebHost implementation
without retaining a second copy of the page generator.
"""

import sys as _sys
import directory_web_compat as _compat

_sys.modules[__name__] = _compat
