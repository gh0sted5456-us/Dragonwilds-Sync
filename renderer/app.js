(() => {
  'use strict';
  const query = new URLSearchParams(window.location.search);
  let context = {};
  try { context = window.dragonwildsV3?.quickContext?.() || {}; } catch (_) {}
  const quick = context.enabled === true || query.get('quick') === '1' || query.get('minimal') === '1';
  if (quick) {
    document.documentElement.dataset.v3Quick = '1';
    return;
  }
  // Full mode executes the exact previously verified renderer synchronously so
  // the later release enhancement scripts retain their original ordering.
  document.write('<script src="app-v2.js?v=3.1.0-window-hydration"><\\/script>');
})();
