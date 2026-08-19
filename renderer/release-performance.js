(() => {
  'use strict';

  // Post-consolidation performance coordinator.
  //
  // Historical release layers each installed a document-wide MutationObserver.
  // On large Mod/World/editor surfaces one DOM change could therefore trigger
  // several whole-document selector passes in the same frame. Keep those layers
  // compatible, but funnel only their broad documentElement observers through a
  // single idle-time coordinator. Targeted observers (dialogs/editors/etc.) stay
  // native and immediate.
  const NativeMutationObserver = window.MutationObserver;
  if (typeof NativeMutationObserver !== 'function' || window.__DWSYNC_FAST_NAV__) return;

  const broadSubscribers = new Set();
  let broadNativeObserver = null;
  let broadScheduled = false;
  let interactionUntil = 0;
  let longTasks = [];

  const now = () => performance.now();
  const interacting = () => now() < interactionUntil;

  function markInteraction(duration = 180) {
    interactionUntil = Math.max(interactionUntil, now() + duration);
    if (document.documentElement.dataset.dwsInteracting !== '1') {
      document.documentElement.dataset.dwsInteracting = '1';
    }
    clearTimeout(markInteraction._timer);
    markInteraction._timer = setTimeout(() => {
      if (!interacting()) delete document.documentElement.dataset.dwsInteracting;
    }, duration + 24);
  }

  function runBroadSubscribers() {
    broadScheduled = false;
    if (interacting()) {
      setTimeout(scheduleBroadSubscribers, 72);
      return;
    }
    for (const observer of [...broadSubscribers]) {
      if (!observer._dwsConnected) continue;
      try { observer._callback([], observer); } catch (error) { setTimeout(() => { throw error; }, 0); }
    }
  }

  function scheduleBroadSubscribers() {
    if (broadScheduled || !broadSubscribers.size) return;
    broadScheduled = true;
    const run = () => {
      if (interacting()) {
        broadScheduled = false;
        setTimeout(scheduleBroadSubscribers, 72);
        return;
      }
      requestAnimationFrame(runBroadSubscribers);
    };
    if (typeof requestIdleCallback === 'function') requestIdleCallback(run, { timeout: 220 });
    else setTimeout(run, 64);
  }

  function ensureBroadNativeObserver() {
    if (broadNativeObserver) return;
    broadNativeObserver = new NativeMutationObserver(() => scheduleBroadSubscribers());
    broadNativeObserver.observe(document.documentElement, { childList: true, subtree: true });
  }

  class CoordinatedMutationObserver {
    constructor(callback) {
      if (typeof callback !== 'function') throw new TypeError('MutationObserver callback must be a function');
      this._callback = callback;
      this._native = null;
      this._broad = false;
      this._dwsConnected = false;
    }

    observe(target, options = {}) {
      const broad = target === document.documentElement
        && options?.childList === true
        && options?.subtree === true
        && options?.attributes !== true
        && options?.characterData !== true;
      if (!broad) {
        if (!this._native) this._native = new NativeMutationObserver(this._callback);
        this._native.observe(target, options);
        this._dwsConnected = true;
        return;
      }
      this._broad = true;
      this._dwsConnected = true;
      broadSubscribers.add(this);
      ensureBroadNativeObserver();
      scheduleBroadSubscribers();
    }

    disconnect() {
      this._dwsConnected = false;
      if (this._broad) broadSubscribers.delete(this);
      this._native?.disconnect();
    }

    takeRecords() {
      return this._native?.takeRecords?.() || [];
    }
  }

  window.MutationObserver = CoordinatedMutationObserver;

  // Scroll/tab/window input has priority over presentation enhancement work.
  document.addEventListener('wheel', () => markInteraction(180), { capture: true, passive: true });
  document.addEventListener('pointerdown', () => markInteraction(140), { capture: true, passive: true });
  document.addEventListener('keydown', (event) => {
    if (['PageUp','PageDown','Home','End','ArrowUp','ArrowDown','Tab'].includes(event.key)) markInteraction(160);
  }, { capture: true });
  document.addEventListener('scroll', () => markInteraction(150), { capture: true, passive: true });

  // Keep a small long-task ledger for hands-on profiling without network or log spam.
  try {
    if (typeof PerformanceObserver === 'function' && PerformanceObserver.supportedEntryTypes?.includes('longtask')) {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          longTasks.push({ at: Date.now(), duration_ms: Math.round(entry.duration * 10) / 10 });
        }
        if (longTasks.length > 80) longTasks = longTasks.slice(-80);
      });
      observer.observe({ entryTypes: ['longtask'] });
    }
  } catch (_) {}

  window.__DWSYNC_FAST_NAV__ = {
    version: 1,
    markInteraction,
    scheduleEnhancements: scheduleBroadSubscribers,
    snapshot: () => ({
      broad_observers: broadSubscribers.size,
      interacting: interacting(),
      long_tasks: longTasks.slice(),
    }),
  };
})();
