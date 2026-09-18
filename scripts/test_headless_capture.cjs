'use strict';
const assert = require('node:assert/strict');
const {test} = require('node:test');
const {EventEmitter} = require('node:events');
const {PassThrough} = require('node:stream');
const {connect} = require('./validate_world_cards_headless.cjs');
function fixture() {
  const child = new EventEmitter();
  child.stdio = [null, null, null, new PassThrough(), new PassThrough()];
  const requests = [];
  child.stdio[3].on('data', chunk => requests.push(JSON.parse(String(chunk).slice(0,-1))));
  return {child, requests, send:connect(child), reply:text=>child.stdio[4].write(text)};
}
test('DevTools pipe handles split frames, events, and out-of-order session responses', async () => {
  const f = fixture();
  const a = f.send('Page.enable', {}, 'session-a'), b = f.send('Browser.getVersion');
  assert.equal(f.requests[0].sessionId, 'session-a');
  f.reply('{"method":"Page.loadEventFired","params":{}}\0{"id":2,"res');
  f.reply('ult":{"product":"test-browser"}}\0{"id":1,"result":{}}\0');
  assert.deepEqual(await a, {}); assert.equal((await b).product, 'test-browser');
});
test('DevTools protocol failures are not reported as a layout pass', async () => {
  const f = fixture(), promise = f.send('Page.captureScreenshot');
  f.reply('{"id":1,"error":{"message":"capture failed"}}\0');
  await assert.rejects(promise, /capture failed/);
});
test('Browser exit rejects pending commands and future sends', async () => {
  const f = fixture(), promise = f.send('Page.navigate');
  f.child.emit('exit', 1);
  await assert.rejects(promise, /Browser closed/);
  await assert.rejects(f.send('Page.captureScreenshot'), /connection is closed/);
});
test('Malformed frames and pipe errors reject their pending commands', async () => {
  const f = fixture(), badFrame = f.send('Page.enable'); f.reply('not-json\0');
  await assert.rejects(badFrame, SyntaxError);
  const g = fixture(), badPipe = g.send('Page.enable'); g.child.stdio[3].emit('error', new Error('broken pipe'));
  await assert.rejects(badPipe, /broken pipe/);
});
