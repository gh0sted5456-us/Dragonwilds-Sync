(() => {
  'use strict';

  if (window.__DWSYNC_MONACO_PREWARM_INSTALLED__) return;
  window.__DWSYNC_MONACO_PREWARM_INSTALLED__ = true;

  const status = window.__DWSYNC_MONACO_STATUS__ = {
    state: window.monaco?.editor ? 'ready' : 'idle',
    started_at: 0,
    ready_at: window.monaco?.editor ? Date.now() : 0,
    duration_ms: 0,
    error: '',
  };

  let promise = null;
  function configureAndLoad(resolve, reject) {
    try {
      const amdRequire = window.require;
      if (!amdRequire?.config) throw new Error('Bundled Monaco AMD loader did not initialize.');
      window.MonacoEnvironment = {
        ...(window.MonacoEnvironment || {}),
        getWorkerUrl: () => 'vendor/monaco/vs/base/worker/workerMain.js',
      };
      amdRequire.config({ paths: { vs: 'vendor/monaco/vs' } });
      amdRequire(['vs/editor/editor.main'], () => {
        if (!window.monaco?.editor) return reject(new Error('Monaco editor.main loaded without editor API.'));
        resolve(window.monaco);
      }, reject);
    } catch (error) {
      reject(error);
    }
  }

  function warm() {
    if (window.monaco?.editor) {
      status.state = 'ready';
      status.ready_at ||= Date.now();
      return Promise.resolve(window.monaco);
    }
    if (promise) return promise;
    const started = performance.now();
    status.state = 'loading';
    status.started_at = Date.now();
    status.error = '';
    promise = new Promise((resolve, reject) => {
      if (window.require?.config) return configureAndLoad(resolve, reject);
      const existing = document.querySelector('script[data-dws-monaco-loader]');
      if (existing) {
        existing.addEventListener('load', () => configureAndLoad(resolve, reject), { once: true });
        existing.addEventListener('error', () => reject(new Error('Bundled Monaco loader.js could not be loaded.')), { once: true });
        return;
      }
      const script = document.createElement('script');
      script.src = 'vendor/monaco/vs/loader.js';
      script.async = true;
      script.dataset.dwsMonacoLoader = '1';
      script.addEventListener('load', () => configureAndLoad(resolve, reject), { once: true });
      script.addEventListener('error', () => reject(new Error('Bundled Monaco loader.js could not be loaded.')), { once: true });
      document.head.appendChild(script);
    }).then((monaco) => {
      status.state = 'ready';
      status.ready_at = Date.now();
      status.duration_ms = Math.round((performance.now() - started) * 10) / 10;
      return monaco;
    }).catch((error) => {
      status.state = 'error';
      status.error = String(error?.message || error || 'Monaco failed to initialize');
      status.duration_ms = Math.round((performance.now() - started) * 10) / 10;
      promise = null;
      console.error('[Dragonwilds Sync] Monaco prewarm failed:', error);
      throw error;
    });
    return promise;
  }

  window.__DWSYNC_MONACO__ = { warm, status: () => ({ ...status }) };

  // app.js has already established the splash and kicked off the backend
  // bootstrap before this release layer executes. Use that otherwise-idle
  // bootstrap window to load the bundled Monaco runtime immediately so the
  // first JSON/Lua/INI editor does not have to fall back to a textarea while
  // loader.js/editor.main are still cold.
  warm().catch(() => {});
})();
