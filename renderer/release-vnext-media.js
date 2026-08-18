(() => {
  'use strict';
  const allowedImage = (value) => {
    try {
      const url = new URL(String(value || ''));
      return url.protocol === 'https:' && ['raw.githubusercontent.com', 'github.com'].includes(url.hostname) ? url.href : '';
    } catch (_) { return ''; }
  };
  function enhanceHelpImages(root = document) {
    root.querySelectorAll('.dws-live-help-markdown p:not([data-help-media-checked])').forEach((paragraph) => {
      paragraph.dataset.helpMediaChecked = '1';
      const anchor = paragraph.querySelector(':scope > a[data-help-link]');
      const leading = paragraph.firstChild?.nodeType === Node.TEXT_NODE ? String(paragraph.firstChild.textContent || '').trim() : '';
      if (!anchor || leading !== '!' || paragraph.children.length !== 1) return;
      const source = allowedImage(anchor.dataset.helpLink);
      if (!source) return;
      const figure = document.createElement('figure');
      figure.className = 'dws-live-help-figure';
      const image = document.createElement('img');
      image.src = source;
      image.alt = anchor.textContent || 'Help walkthrough image';
      image.loading = 'lazy';
      image.decoding = 'async';
      const caption = document.createElement('figcaption');
      caption.textContent = anchor.textContent || 'Walkthrough image';
      figure.append(image, caption);
      paragraph.replaceWith(figure);
    });
  }
  let queued = false;
  const schedule = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; enhanceHelpImages(); });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', schedule, {once:true}); else schedule();
  new MutationObserver(schedule).observe(document.documentElement, {childList:true, subtree:true});
})();
