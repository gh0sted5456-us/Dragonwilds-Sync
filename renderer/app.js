(() => {
  'use strict';
  const query = new URLSearchParams(window.location.search);
  let context = {};
  try { context = window.dragonwildsV3?.quickContext?.() || {}; } catch (_) {}
  const quick = context.enabled === true || query.get('quick') === '1' || query.get('minimal') === '1';
  if (quick) {
    document.documentElement.dataset.v3Quick = '1';
    document.write('<script src="release-quick-game-handoff.js?v=3.5.1-game-handoff"><\\/script>');
    return;
  }
  // Full mode executes the exact previously verified renderer synchronously so
  // the later release enhancement scripts retain their original ordering.
  document.write('<script src="app-v2.js?v=3.5.0-shortcuts-windows"><\\/script>');
  // Additive profile-mod workflow: user-managed mods live in each World's
  // profile folder and explicit Refresh reconciles that folder authoritatively.
  document.write('<script src="release-profile-mod-folders.js?v=3.5.2-profile-authority"><\\/script>');
  // Installation mapping stays machine-owned and separate from profile content.
  // Defaults derive from the exact linked executable; operators may explicitly
  // map UE4SS, RuneSchema and PAK destinations for current/future loader layouts.
  document.write('<script src="release-machine-mod-mapping.js?v=3.5.2-machine-mod-mapping"><\\/script>');
  // Fresh profile inventory immediately updates the presentation layer.
  document.write('<script src="release-live-mod-inventory.js?v=3.5.2-live-mod-inventory"><\\/script>');
})();
