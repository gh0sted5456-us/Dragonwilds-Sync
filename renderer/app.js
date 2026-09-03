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
  document.write('<script src="app-v2.js?v=3.5.0-shortcuts-windows"><\\/script>');
  // Additive profile-mod workflow: user-managed mods live in each World's
  // profile folder and explicit Rescan reconciles that folder authoritatively.
  // It also annotates the packaged UE4SS/RuneSchema builds as protected recovery
  // baselines without changing Quick Mode or the retained renderer bundle.
  document.write('<script src="release-profile-mod-folders.js?v=3.5.1-profile-mod-folders"><\\/script>');
})();
