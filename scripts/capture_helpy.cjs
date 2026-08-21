'use strict';

const {app,BrowserWindow}=require('electron');
const fs=require('fs');
const http=require('http');
const path=require('path');

const project=path.resolve(__dirname,'..');
const website=path.join(project,'website');
const help=path.join(project,'help');
const helpAssets=path.join(project,'renderer','assets','help');
const captures=[
  ['getting-started','38-helpy-website.png'],
  ['characters-rsdw','39-helpy-characters.png'],
  ['mods-items','40-helpy-mods.png'],
];
const types={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.json':'application/json; charset=utf-8','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.svg':'image/svg+xml','.ico':'image/x-icon'};

function resolveRequest(requestUrl){
  const pathname=decodeURIComponent(new URL(requestUrl,'http://127.0.0.1').pathname);
  let root=website;let relative=pathname.replace(/^\//,'')||'helpy.html';
  if(pathname.startsWith('/help/')){root=help;relative=pathname.slice('/help/'.length);}
  else if(pathname.startsWith('/assets/help/')){root=helpAssets;relative=pathname.slice('/assets/help/'.length);}
  const target=path.resolve(root,relative);return target===root||target.startsWith(root+path.sep)?target:null;
}

app.whenReady().then(async()=>{
  const server=http.createServer((request,response)=>{
    const target=resolveRequest(request.url||'/');
    if(!target||!fs.existsSync(target)||!fs.statSync(target).isFile()){response.writeHead(404);response.end('Not found');return;}
    response.writeHead(200,{'Content-Type':types[path.extname(target).toLowerCase()]||'application/octet-stream','Cache-Control':'no-store'});fs.createReadStream(target).pipe(response);
  });
  await new Promise((resolve)=>server.listen(0,'127.0.0.1',resolve));
  const port=server.address().port;const win=new BrowserWindow({show:false,width:1440,height:1000,backgroundColor:'#0b0d0f',webPreferences:{sandbox:true,contextIsolation:true,nodeIntegration:false}});
  try{
    for(const [pageId,filename] of captures){
      await win.loadURL(`http://127.0.0.1:${port}/helpy.html?embed=1&theme=dark&capture=${encodeURIComponent(pageId)}#${encodeURIComponent(pageId)}`);
      await win.webContents.executeJavaScript(`new Promise((resolve,reject)=>{const started=Date.now();const ready=()=>{const selected=document.querySelector('[data-helpy-page].active');const image=document.querySelector('.helpy-article-shot img');if(selected?.dataset.helpyPage===${JSON.stringify(pageId)}&&(!image||image.complete))return requestAnimationFrame(()=>requestAnimationFrame(resolve));if(Date.now()-started>10000)return reject(new Error('Helpy render timed out'));setTimeout(ready,100);};ready();})`);
      const image=await win.webContents.capturePage();fs.writeFileSync(path.join(helpAssets,filename),image.toPNG());console.log(`[OK] ${pageId} -> renderer/assets/help/${filename}`);
    }
  }finally{win.destroy();server.close();app.quit();}
}).catch((error)=>{console.error(error);app.exit(1);});
