'use strict';
const fs=require('fs');
const path=require('path');
const root=path.resolve(__dirname,'..');

function replaceOnce(file,from,to,label){
  const target=path.join(root,file);
  const text=fs.readFileSync(target,'utf8');
  const first=text.indexOf(from);
  if(first<0)throw new Error(`${label}: expected source block was not found in ${file}`);
  if(text.indexOf(from,first+from.length)>=0)throw new Error(`${label}: source block was ambiguous in ${file}`);
  fs.writeFileSync(target,text.slice(0,first)+to+text.slice(first+from.length),'utf8');
  console.log(`patched ${file}: ${label}`);
}

const passiveConsole=`    win.querySelector('#detach-runtime-console')?.addEventListener('click',async()=>{\n      try{\n        const opened=await popOutDesktopWindow(win,{title:\`${'${world.name||\'World\'}'} Runtime Console\`,width:1240,height:800});\n        if(!opened)throw new Error('The lightweight native console host is unavailable.');\n      }catch(error){toast('Runtime Console could not detach',error.message,'error');}\n    });`;
const fullConsole=`    win.querySelector('#detach-runtime-console')?.addEventListener('click',async()=>{try{const result=await window.dragonwilds.openDetachedWindow?.({route:'server-console',title:\`${'${world.name||\'World\'}'} Runtime Console\`,width:1240,height:800,context:{selectedServerWorldId:world.id}});if(result?.id&&!inlineHost)closeDesktopWindow(win);}catch(error){toast('Runtime Console could not detach',error.message,'error');}});`;
replaceOnce('renderer/app-v2.js',passiveConsole,fullConsole,'restore Runtime Console full renderer detach');

const oldContract=`must(app.includes("popOutDesktopWindow(win,{title:\`${'${world.name||\'World\'}'} Runtime Console\`")&&!app.includes("openDetachedWindow?.({route:'server-console'"),'Runtime Console must use the lightweight themed native host instead of booting another full app renderer');`;
const newContract=`must(app.includes("openDetachedWindow?.({route:'server-console'")&&!app.includes("popOutDesktopWindow(win,{title:\`${'${world.name||\'World\'}'} Runtime Console\`"),'Runtime Console must use the full detached renderer window so live controls, polling, tabs, and command state remain functional');`;
replaceOnce('scripts/check_window_navigation_lifecycle.cjs',oldContract,newContract,'pin Runtime Console to full detached renderer');

console.log('window regression patch complete');
