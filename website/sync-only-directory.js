/* Keep the public website directory scoped to Dragonwilds Sync worlds only. */
(() => {
  if (typeof renderWorlds !== 'function') return;

  const baseRenderWorlds = renderWorlds;

  function isSyncWorld(world) {
    return world?.isSyncWorld === true;
  }

  function pruneToSyncWorlds() {
    if (typeof allWorlds === 'undefined' || !Array.isArray(allWorlds)) return;
    allWorlds = allWorlds.filter(isSyncWorld);
  }

  function refreshSyncStats() {
    if (typeof deriveStatsFromWorlds === 'function') deriveStatsFromWorlds();
  }

  renderWorlds = function renderSyncOnlyWorlds() {
    pruneToSyncWorlds();
    refreshSyncStats();
    return baseRenderWorlds();
  };

  pruneToSyncWorlds();
  refreshSyncStats();
  baseRenderWorlds();
})();
