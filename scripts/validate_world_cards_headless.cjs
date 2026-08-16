'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '..');
const outputDir = path.join(root, 'Codex Outputs', 'GUI Validation');
const candidates = process.platform === 'win32'
  ? [
      process.env['ProgramFiles(x86)'] && path.join(process.env['ProgramFiles(x86)'], 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
      process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
      'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    ]
  : ['/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome'];
const browser = candidates.filter(Boolean).find((candidate) => fs.existsSync(candidate));
if (!browser) throw new Error('Edge/Chromium was not found for GUI validation.');
fs.mkdirSync(outputDir, { recursive:true });

const contentTypes={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.svg':'image/svg+xml'};
const pending=new Map();
const server=http.createServer((request,response)=>{
  const url=new URL(request.url,'http://127.0.0.1');
  if(url.pathname==='/__validation'){
    const name=url.searchParams.get('case')||'';const complete=pending.get(name);
    if(complete){pending.delete(name);complete({status:url.searchParams.get('status'),detail:url.searchParams.get('detail')||''});}
    response.writeHead(204);response.end();return;
  }
  const relative=decodeURIComponent(url.pathname).replace(/^\/+/, '');
  const target=path.resolve(root,relative||'scripts/fixtures/world_cards.html');
  if(target!==root&&!target.startsWith(root+path.sep)){response.writeHead(403);response.end();return;}
  try{const data=fs.readFileSync(target);response.writeHead(200,{'Content-Type':contentTypes[path.extname(target).toLowerCase()]||'application/octet-stream'});response.end(data);}
  catch(_){response.writeHead(404);response.end();}
});

function runCase(testCase,port){
  return new Promise((resolve,reject)=>{
    const screenshot=path.join(outputDir,`world-cards-${testCase.name}.png`);
    const profile=fs.mkdtempSync(path.join(os.tmpdir(),'dwsync-gui-'));
    let settled=false,stderr='';
    const finish=(error,value)=>{if(settled)return;settled=true;clearTimeout(timer);pending.delete(testCase.name);error?reject(error):resolve(value);};
    const timer=setTimeout(()=>finish(new Error(`${testCase.name}: browser did not return a layout result`)),20000);
    pending.set(testCase.name,(validation)=>validation.status==='pass'?finish(null,{screenshot,detail:validation.detail}):finish(new Error(`${testCase.name}: ${validation.detail||'layout failed'}`)));
    const url=`http://127.0.0.1:${port}/scripts/fixtures/world_cards.html?theme=${encodeURIComponent(testCase.theme)}&case=${encodeURIComponent(testCase.name)}`;
    const child=spawn(browser,['--headless=new','--disable-gpu','--hide-scrollbars','--run-all-compositor-stages-before-draw','--virtual-time-budget=1500',`--window-size=${testCase.width},${testCase.height}`,`--user-data-dir=${profile}`,`--screenshot=${screenshot}`,url],{windowsHide:true});
    child.stderr.on('data',(chunk)=>{stderr+=String(chunk);});
    child.on('error',(error)=>finish(error));
    child.on('exit',(code)=>{if(code&&code!==0)finish(new Error(stderr||`${testCase.name}: browser exited ${code}`));});
  });
}

(async()=>{
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const port=server.address().port;
  const cases=[{name:'dark-desktop',theme:'dark',width:1100,height:900},{name:'light-desktop',theme:'light',width:1100,height:900},{name:'light-mobile',theme:'light',width:430,height:1100}];
  try{for(const testCase of cases){const result=await runCase(testCase,port);console.log(`[OK] ${testCase.name}: ${result.detail}; screenshot ${result.screenshot}`);}}
  finally{await new Promise((resolve)=>server.close(resolve));}
})().catch((error)=>{console.error(`[ERROR] ${error.message||error}`);process.exitCode=1;});
