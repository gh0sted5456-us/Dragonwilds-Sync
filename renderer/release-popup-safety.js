(() => {
  'use strict';
  const popupSelector = '[role="dialog"][aria-modal="true"],.v3p4-mod-dialog,.modal-backdrop,.studio-repository-backdrop';
  const closeSelector = '[data-v3p4-close-mods],[data-v3p4-close-window],[data-phase5-window-close],[data-modal-close],[data-close],[aria-label*="close" i],.modal-close,.popup-close';

  function visible(node) {
    if (!node?.isConnected || node.hidden) return false;
    const style = getComputedStyle(node); return style.display !== 'none' && style.visibility !== 'hidden';
  }

  function fallbackRemove(popup) {
    requestAnimationFrame(() => {
      if (!visible(popup)) return;
      popup.dispatchEvent(new CustomEvent('dws:popup-force-close',{bubbles:true}));
      if (visible(popup)) popup.remove();
    });
  }

  function closePopup(popup, nativeControl = null) {
    if (!popup) return;
    if (popup.classList.contains('v3p4-mod-dialog')) {
      const key = popup.dataset.v3p4ModDialog || nativeControl?.dataset?.v3p4CloseMods;
      window.__DWSYNC_V3_PHASE4__?.closeModPopup?.(key); return;
    }
    const control = nativeControl || popup.querySelector(closeSelector);
    if (control && !control.matches('[data-popup-safety-close]')) control.click();
    fallbackRemove(popup);
  }

  function prepare(popup) {
    if (!popup || popup.dataset.popupSafety === '1') return;
    popup.dataset.popupSafety = '1';
    if (!popup.querySelector(closeSelector)) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'popup-safety-close'; button.dataset.popupSafetyClose = '1'; button.setAttribute('aria-label','Close popup'); button.textContent = '×'; popup.prepend(button);
    }
  }

  function prepareAll(root = document) { root.querySelectorAll?.(popupSelector).forEach(prepare); }
  document.addEventListener('pointerdown',(event)=>{
    const popup=event.target.closest?.(popupSelector); if(!popup)return;
    const close=event.target.closest?.(`${closeSelector},[data-popup-safety-close]`);
    if(close){event.preventDefault();event.stopPropagation();closePopup(popup,close);return;}
    if(event.target===popup){event.preventDefault();event.stopPropagation();closePopup(popup);}
  },true);
  document.addEventListener('keydown',(event)=>{
    if(event.key!=='Escape')return;const popups=[...document.querySelectorAll(popupSelector)].filter(visible);const popup=popups.at(-1);if(!popup)return;event.preventDefault();event.stopPropagation();closePopup(popup);
  },true);
  new MutationObserver((records)=>{for(const record of records)for(const node of record.addedNodes){if(node.nodeType!==1)continue;if(node.matches?.(popupSelector))prepare(node);prepareAll(node);}}).observe(document.documentElement,{childList:true,subtree:true});
  prepareAll();
})();
