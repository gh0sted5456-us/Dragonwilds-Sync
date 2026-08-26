(() => {
  'use strict';

  const HELP_BASE = 'https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync-Web/main/renderer/assets/help/';

  const safeHelpImage = (value) => {
    try {
      const url = new URL(String(value || '').trim(), HELP_BASE);
      if (url.protocol !== 'https:') return '';
      if (!['raw.githubusercontent.com', 'github.com'].includes(url.hostname)) return '';
      return url.href;
    } catch (_) {
      return '';
    }
  };

  function upgradeHelpImages(root = document) {
    root.querySelectorAll('.dws-live-help-markdown p:not([data-help-media-checked])').forEach((paragraph) => {
      paragraph.dataset.helpMediaChecked = '1';
      const text = String(paragraph.textContent || '').trim();
      const match = text.match(/^!\[([^\]]*)\]\(([^)]+)\)(?:\s+\"([^\"]*)\")?$/);
      if (!match) return;
      const src = safeHelpImage(match[2]);
      if (!src) return;
      const figure = document.createElement('figure');
      figure.className = 'dws-help-figure';
      const image = document.createElement('img');
      image.src = src;
      image.alt = match[1] || match[3] || 'Dragonwilds Sync help image';
      image.loading = 'lazy';
      image.decoding = 'async';
      image.referrerPolicy = 'no-referrer';
      figure.appendChild(image);
      const captionText = match[3] || match[1];
      if (captionText) {
        const caption = document.createElement('figcaption');
        caption.textContent = captionText;
        figure.appendChild(caption);
      }
      paragraph.replaceWith(figure);
    });
  }

  let scheduled = false;
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      upgradeHelpImages();
    });
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', schedule, {once:true});
  else schedule();
  new MutationObserver(schedule).observe(document.documentElement, {childList:true, subtree:true});
})();
