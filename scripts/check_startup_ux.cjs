const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const native = fs.readFileSync(path.join(root, 'electron/main-v2.cjs'), 'utf8');
let now = 1000000;
const timers = [], shown = [];
class Notification {
  static isSupported() { return true; }
  constructor(options) { this.options = options; }
  on() {}
  show() { shown.push(this.options); }
}
const context = vm.createContext({
  Date:{now:()=>now}, Map, String, Math, Notification,
  backgroundSettings:{notifications_enabled:true}, notificationSeen:new Map(),
  iconPath:()=>'application.ico', setTimeout:callback=>{timers.push(callback);return 1;},
  showAnnouncementOverlay:()=>{}, createWindow:()=>({show(){},focus(){}})
});
vm.runInContext(native.slice(native.indexOf('const startupNotificationDeadline'), native.indexOf('function showAnnouncementOverlay')), context);
for(let i=0;i<4;i++)context.showPassiveNotification({key:`startup-${i}`,title:`Notice ${i}`,body:'Detail'});
assert.equal(shown.length,0);
assert.equal(timers.length,1);
context.showPassiveNotification({key:'error',title:'Launch failed',kind:'error'});
assert.equal(shown.length,1);
now+=16000;timers.shift()();
assert.equal(shown.length,2);
assert.ok(shown[1].body.includes('Notice 3: Detail'));
assert.equal(shown[1].icon,'application.ico');
context.showPassiveNotification({key:'error',title:'Launch failed',kind:'error'});
assert.equal(shown.length,2);
const renderer = fs.readFileSync(path.join(root,'renderer/app-v2.js'),'utf8').replace(/\r\n/g,'\n');
assert.ok(renderer.includes("if (!detachedMode) {\n        state.entered = false;"));
const start = renderer.slice(renderer.indexOf('async function runServerStartOperation'), renderer.indexOf('function startPlayerPolling'));
assert.ok(!start.includes('setInterval'));
assert.ok(renderer.includes("panel.querySelector('#launch-verified-world')?.focus()"));
assert.ok(renderer.includes("api.invoke('world.launch_verified',{id:world.id})"));
console.log('Startup notification grouping, icons, splash entry, and honest loading: PASS');

// Shutdown must prevent timers/late IPC from spawning a replacement backend.
const shutdown = vm.createContext({
  visualShutdownStarted:true, shutdownInProgress:true, shutdownComplete:false,
  service:null, Promise, Error,
  serviceCommand:()=>{throw new Error('Backend must not respawn during shutdown');},
});
const serviceCode=native.slice(native.indexOf('function startService()'),native.indexOf('function serviceInvoke('));
vm.runInContext(serviceCode,shutdown);
shutdown.startService();
assert.equal(shutdown.service,null);
const invokeStart=native.indexOf('function serviceInvoke(');
const invokeEnd=native.indexOf('\nfunction ',invokeStart+1);
vm.runInContext(native.slice(invokeStart,invokeEnd),shutdown);
Promise.all([
  assert.rejects(shutdown.serviceInvoke('state.get'),/shutting down/),
  assert.rejects(shutdown.serviceInvoke('application.shutdown'),/not running/),
]).then(()=>console.log('Shutdown RPC containment and no backend respawn: PASS')).catch(error=>{console.error(error);process.exitCode=1;});
