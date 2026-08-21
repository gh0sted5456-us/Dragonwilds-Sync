'use strict';

const fs=require('fs');const path=require('path');
const root=path.resolve(__dirname,'..');
const read=(file)=>fs.readFileSync(path.join(root,file),'utf8');
const fail=(message)=>{console.error(`window/navigation lifecycle: FAIL · ${message}`);process.exit(1);};
const must=(condition,message)=>{if(!condition)fail(message);};

const app=read('renderer/app-v2.js');
const main=read('electron/main-v2.cjs');
const preload=read('electron/preload-v2.cjs');
const dialog=read('renderer/dialog-host.js');
const local=read('backend/local_world.py');
const world=read('backend/world_maintenance.py');

for(const token of ['__DWSYNC_SWAP_METRICS__','sync_p95_ms','settled_p95_ms','requestAnimationFrame(()=>requestAnimationFrame'])must(app.includes(token),`missing measured swap contract ${token}`);
for(const token of ['popOutDesktopWindow','requestCloseDesktopWindow','disposeDesktopWindow','registerManagedDialogShadow'])must(app.includes(token),`missing internal window lifecycle ${token}`);
for(const token of ['openManagedDialog','managedDialogContent','managedDialogEvent','updateManagedDialog','closeManagedDialog','onManagedDialogClosed'])must(preload.includes(token),`sandbox bridge missing ${token}`);
must(main.includes("loadFile(path.join(projectRoot(), 'renderer', 'dialog-host.html')"),'ordinary pop-outs must use the lightweight dialog host');
must(dialog.includes('window.dragonwilds.windowMinimize()')&&dialog.includes('window.dragonwilds.windowClose()'),'native host controls must minimize and close through Electron');
must(app.includes('modDraftContent')&&app.includes('modInitialPath')&&app.includes("route:'mod-explorer'"),'Mod Explorer pop-out must preserve open file and draft');
must(main.includes('dragonwilds:detached-context')&&!main.includes("query: { detached: '1', route, windowId: id, ctx }"),'detached drafts must use ownership-checked IPC');
must(app.includes('editor?.dispose()')&&app.includes('referenceEditor?.dispose()'),'both Monaco editor models must be disposed');
must(app.includes('Unsaved Mod File')&&app.includes('Unsaved World File'),'editor close must guard unsaved work');
must(app.includes('Open Mod Folder')&&app.includes('open-current-mod-folder'),'mod file locations must be actionable in-app');
for(const source of [local,world])must(source.includes('"folder": str(')&&source.includes('"root": str('),'opened files must return validated folder/root paths');
must(local.includes('base not in path.parents')&&local.includes('rel.is_absolute()')&&local.includes('".." in rel.parts'),'SinglePlayer mod paths must remain contained');
must(world.includes('_resolve_inside(layout.game_root, relative_path)'),'server mod paths must remain contained');

console.log('Window lifecycle, Monaco, mod path, and measured navigation contract: PASS');
