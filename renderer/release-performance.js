(() => {
  'use strict';
  if (window.__DWSYNC_FAST_NAV__) return;

  let interactionUntil = 0;
  let interactionTimer = null;
  let longTasks = [];
  const now = () => performance.now();

  function markInteraction(duration = 180) {
    interactionUntil = Math.max(interactionUntil, now() + duration);
    document.documentElement.dataset.dwsInteracting = '1';
    clearTimeout(interactionTimer);
    interactionTimer = setTimeout(() => {
      if (now() >= interactionUntil) delete document.documentElement.dataset.dwsInteracting;
    }, duration + 24);
  }

  document.addEventListener('wheel', () => markInteraction(), { capture: true, passive: true });
  document.addEventListener('pointerdown', () => markInteraction(140), { capture: true, passive: true });
  document.addEventListener('keydown', (event) => {
    if (['PageUp', 'PageDown', 'Home', 'End', 'ArrowUp', 'ArrowDown', 'Tab'].includes(event.key)) markInteraction(160);
  }, { capture: true });
  document.addEventListener('scroll', () => markInteraction(150), { capture: true, passive: true });

  try {
    if (PerformanceObserver.supportedEntryTypes?.includes('longtask')) {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) longTasks.push({ at: Date.now(), duration_ms: Math.round(entry.duration * 10) / 10 });
        if (longTasks.length > 80) longTasks = longTasks.slice(-80);
      });
      observer.observe({ entryTypes: ['longtask'] });
    }
  } catch (_) {}

  window.__DWSYNC_FAST_NAV__ = {
    version: 2,
    markInteraction,
    snapshot: () => ({
      lifecycle_subscribers: window.DragonwildsDOMLifecycle ? 'shared' : 'unavailable',
      interacting: now() < interactionUntil,
      long_tasks: longTasks.slice(),
    }),
  };
})();
