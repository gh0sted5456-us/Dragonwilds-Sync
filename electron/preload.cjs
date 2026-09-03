'use strict';

// Historical compatibility alias only.
// Every live BrowserWindow uses preload-v2.cjs directly. Keep this tiny redirect
// so old source-contract fixtures that still resolve electron/preload.cjs read
// the current bridge instead of carrying a second implementation.
require('./preload-v2.cjs');
