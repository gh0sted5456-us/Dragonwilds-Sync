(() => {
  'use strict';
  const api = window.dragonwilds;
  let cache = null, fetchedAt = 0, pending = false;
  const allWorlds = (state) => [
    ...(state?.client?.worlds || []),
    ...(state?.client?.discovered_worlds || []),
    ...(state?.client?.directory_worlds || []),
    ...(state?.client?.private_worlds || []),
    ...(state?.server_profiles || []),
  ].filter(Boolean);
  const syncVersion = (world) => String(
    world?.sync_version ||
    world?.runtime_stack?.dragonwilds_sync?.version ||
    world?.manifest_cache?.runtime_stack?.dragonwilds_sync?.version ||
    world?.status?.runtime_stack?.dragonwilds_sync?.version || ''
  ).trim();
  async function state() {
    if (cache && Date.now() - fetchedAt < 5000) return cache;
    try { cache = await api?.invoke?.('state.get', {}); fetchedAt = Date.now(); } catch (_) {}
    return cache || {};
  }
  async function enhance() {
    pending = false;
    const current = await state();
    const worlds = new Map(allWorlds(current).map((world)=>[String(world.id||world.profile_id||''), world]));
    document.querySelectorAll('[data-world-id]').forEach((card)=>{
      if(card.querySelector('[data-sync-version-badge]')) return;
      const world = worlds.get(String(card.dataset.worldId||''));
      const version = syncVersion(world);
      if(!version) return;
      const badge = document.createElement('span');
      badge.dataset.syncVersionBadge = '1'; badge.className = 'badge sync-version-badge'; badge.textContent = `SYNC ${version}`;
      const target = card.querySelector('.badges,.world-list-title,.title-line,.world-card-title') || card;
      target.appendChild(badge);
    });
  }
  function schedule(){ if(pending)return; pending=true; requestAnimationFrame(enhance); }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',schedule,{once:true});else schedule();
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true});
})();
