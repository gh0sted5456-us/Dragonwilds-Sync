(() => {
  'use strict';
  if (window.DragonwildsDOMLifecycle) return;
  const callbacks = new Set();
  let observer = null;

  const start = () => {
    if (observer || !document.documentElement) return;
    observer = new MutationObserver((records) => {
      for (const callback of [...callbacks]) {
        try { callback(records); } catch (error) { console.error('[dom-lifecycle]', error); }
      }
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  };

  window.DragonwildsDOMLifecycle = {
    register(callback) {
      if (typeof callback !== 'function') return () => {};
      callbacks.add(callback);
      start();
      return () => callbacks.delete(callback);
    },
  };
  start();
})();
