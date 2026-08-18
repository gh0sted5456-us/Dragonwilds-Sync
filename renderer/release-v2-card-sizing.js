(() => {
  'use strict';
  let queued=false,measuring=false;

  function equalize(){
    if(measuring)return;measuring=true;
    try{
      document.querySelectorAll('.world-grid').forEach(grid=>{
        const cards=[...grid.children].filter(node=>node.matches?.('.world-card'));
        if(!cards.length){grid.style.removeProperty('--dws-uniform-card-height');return;}
        // Clear the previous measurement first so content can legitimately
        // shrink after badges/descriptions are removed.
        grid.style.removeProperty('--dws-uniform-card-height');
        cards.forEach(card=>card.style.removeProperty('min-height'));
        const tallest=Math.max(...cards.map(card=>Math.ceil(Math.max(card.scrollHeight,card.getBoundingClientRect().height))));
        if(Number.isFinite(tallest)&&tallest>0)grid.style.setProperty('--dws-uniform-card-height',`${tallest}px`);
      });
    } finally {measuring=false;}
  }

  function schedule(){if(queued)return;queued=true;requestAnimationFrame(()=>requestAnimationFrame(()=>{queued=false;equalize();}));}
  addEventListener('resize',schedule,{passive:true});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',schedule,{once:true});else schedule();
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true,characterData:true});
})();
