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
    if(complete)complete({status:url.searchParams.get('status'),detail:url.searchParams.get('detail')||''});
    response.writeHead(204);response.end();return;
  }
  const relative=decodeURIComponent(url.pathname).replace(/^\/+/, '');
  const target=path.resolve(root,relative||'scripts/fixtures/world_cards.html');
  if(target!==root&&!target.startsWith(root+path.sep)){response.writeHead(403);response.end();return;}
  try{const data=fs.readFileSync(target);response.writeHead(200,{'Content-Type':contentTypes[path.extname(target).toLowerCase()]||'application/octet-stream'});response.end(data);}
  catch(_){response.writeHead(404);response.end();}
});

function renderedValidation(dom){
  const status=(String(dom||'').match(/<html[^>]*\bdata-validation=["'](pass|fail)["']/i)||[])[1]||'';
  const raw=(String(dom||'').match(/<output[^>]*id=["']validation-result["'][^>]*>([\s\S]*?)<\/output>/i)||[])[1]||'';
  const detail=raw.replace(/<[^>]*>/g,'').replace(/&amp;/g,'&').replace(/&quot;/g,'"').replace(/&#39;/g,"'").trim();
  return status?{status:status.toLowerCase(),detail}:null;
}

function runCase(testCase,port){
  return new Promise((resolve,reject)=>{
    const screenshot=path.join(outputDir,`world-cards-${testCase.name}.png`);
    const profile=fs.mkdtempSync(path.join(os.tmpdir(),'dwsync-gui-'));
    let settled=false,stderr='',stdout='',reported=null,child=null,shutdownTimer=null;
    const cleanup=()=>{try{fs.rmSync(profile,{recursive:true,force:true});}catch(_){}};
    const finish=(error,value)=>{
      if(settled)return;
      settled=true;clearTimeout(timer);clearTimeout(shutdownTimer);pending.delete(testCase.name);
      if(child&&child.exitCode===null&&!child.killed){try{child.kill();}catch(_){}}
      cleanup();error?reject(error):resolve(value);
    };
    const settleValidation=(validation)=>validation?.status==='pass'
      ? finish(null,{screenshot,detail:validation.detail||'PASS'})
      : finish(new Error(`${testCase.name}: ${validation?.detail||'layout failed'}`));
    const onReported=(validation)=>{
      if(settled||!validation)return;
      reported=validation;
      // Give Chromium a brief chance to flush the requested screenshot/DOM, then
      // stop it if the headless process lingers after already reporting layout.
      if(child&&child.exitCode===null&&!shutdownTimer){
        shutdownTimer=setTimeout(()=>{if(child&&child.exitCode===null&&!child.killed){try{child.kill();}catch(_){}}},1000);
      }else if(!child||child.exitCode!==null){settleValidation(validation);}
    };
    const timer=setTimeout(()=>finish(new Error(`${testCase.name}: browser did not return a layout result${stderr?` · ${stderr.slice(-800)}`:''}`)),30000);
    pending.set(testCase.name,onReported);
    const fixture=testCase.fixture||'scripts/fixtures/world_cards.html';
    const url=`http://127.0.0.1:${port}/${fixture}?theme=${encodeURIComponent(testCase.theme)}&case=${encodeURIComponent(testCase.name)}`;
    const args=['--headless=new','--disable-gpu','--hide-scrollbars','--run-all-compositor-stages-before-draw','--virtual-time-budget=2500','--dump-dom',`--window-size=${testCase.width},${testCase.height}`,`--user-data-dir=${profile}`,`--screenshot=${screenshot}`,url];
    if(process.env.CI==='true'&&process.platform!=='win32')args.unshift('--no-sandbox');
    child=spawn(browser,args,{windowsHide:true});
    child.stdout.on('data',(chunk)=>{stdout+=String(chunk);});
    child.stderr.on('data',(chunk)=>{stderr+=String(chunk);});
    child.on('error',(error)=>finish(error));
    child.on('exit',(code,signal)=>{
      if(settled)return;
      clearTimeout(shutdownTimer);shutdownTimer=null;
      const rendered=renderedValidation(stdout);
      const validation=rendered||reported;
      if(validation)return settleValidation(validation);
      if(code&&code!==0)return finish(new Error(stderr||`${testCase.name}: browser exited ${code}`));
      if(signal)return finish(new Error(`${testCase.name}: browser exited on ${signal} without a rendered validation result${stderr?` · ${stderr.slice(-800)}`:''}`));
      finish(new Error(`${testCase.name}: browser exited without a rendered validation result${stderr?` · ${stderr.slice(-800)}`:''}`));
    });
  });
}

(async()=>{
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const port=server.address().port;
  const cases=[{name:'dark-desktop',theme:'dark',width:1100,height:900},{name:'light-desktop',theme:'light',width:1100,height:900},{name:'light-mobile',theme:'light',width:430,height:1100},{name:'placard-flip',theme:'glass',width:720,height:720,fixture:'scripts/fixtures/website_placard_flip.html'}];
  try{for(const testCase of cases){const result=await runCase(testCase,port);console.log(`[OK] ${testCase.name}: ${result.detail}; screenshot ${result.screenshot}`);}}
  finally{await new Promise((resolve)=>server.close(resolve));}
})().catch((error)=>{console.error(`[ERROR] ${error.message||error}`);process.exitCode=1;});
