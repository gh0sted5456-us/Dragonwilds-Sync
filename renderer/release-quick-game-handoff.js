(() => {
  'use strict';

  const api = window.dragonwilds;
  if (!api?.invoke || !api?.windowMinimize || !api?.windowRestore) return;

  const query = new URLSearchParams(location.search);
  let context = {};
  try { context = window.dragonwildsV3?.quickContext?.() || {}; } catch (_) {}
  const quick = context.enabled === true || query.get('quick') === '1' || query.get('minimal') === '1';
  const profileId = String(context.profileId || query.get('worldId') || '');
  const fallbackKind = String(query.get('worldKind') || '');
  const mode = ['player', 'coop', 'server'].includes(String(context.mode || ''))
    ? String(context.mode)
    : (query.get('minimal') === '1' || fallbackKind === 'server' ? 'server' : (fallbackKind === 'private' ? 'coop' : 'player'));
  if (!quick || mode !== 'player') return;

  let initialized = false;
  let lastActive = false;
  let minimizedForGame = false;
  let pollTimer = null;
  let polling = false;

  async function poll() {
    if (polling) return;
    polling = true;
    try {
      const status = await api.invoke('quick.status', { profile_id: profileId, mode: 'player' });
      const active = status?.active === true;
      if (!initialized) {
        initialized = true;
        lastActive = active;
        return;
      }

      if (active && !lastActive && !minimizedForGame) {
        minimizedForGame = true;
        await api.windowMinimize();
      } else if (!active && lastActive && minimizedForGame) {
        minimizedForGame = false;
        await api.windowRestore();
      }
      lastActive = active;
    } catch (_) {
      // A transient status failure must never restore/minimize the window. Keep
      // the previous known state and retry on the next bounded poll.
    } finally {
      polling = false;
    }
  }

  function schedule() {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(async () => {
      await poll();
      schedule();
    }, minimizedForGame ? 2000 : 3000);
    pollTimer.unref?.();
  }

  document.addEventListener('DOMContentLoaded', async () => {
    await poll();
    schedule();
  }, { once: true });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) void poll(); });
  window.addEventListener('beforeunload', () => clearTimeout(pollTimer), { once: true });
})();
