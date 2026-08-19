(() => {
  'use strict';
  // The V2 handler persists nav_collapsed through the backend, which can take a
  // visible round-trip before render(). Give the shell immediate optimistic
  // feedback; the normal application.update call remains the authority and
  // reconciles the persisted state afterwards.
  document.addEventListener('click', (event) => {
    const button = event.target?.closest?.('#toggle-nav-collapse');
    if (!button) return;
    const shell = document.getElementById('app');
    if (!shell) return;
    shell.classList.toggle('nav-collapsed', !shell.classList.contains('nav-collapsed'));
  }, true);
})();
