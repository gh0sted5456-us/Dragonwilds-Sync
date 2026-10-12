const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { DatabaseSync } = require('node:sqlite');
const { createHash, generateKeyPairSync, sign } = require('node:crypto');
const { stripTypeScriptTypes } = require('node:module');
function load(name) {
  const text = fs.readFileSync(path.join(__dirname, 'src', name + '.ts'), 'utf8');
  const compiled = stripTypeScriptTypes(text)
    .replace("import coreWorker from './index';", "const coreWorker = require('./index').default;")
    .replace('export default', 'module.exports.default =');
  const module = { exports: {} };
  new Function('require', 'module', 'exports', compiled)(id => load(id.replace('./','')), module, module.exports);
  return module.exports;
}
(async () => {
  const db = new DatabaseSync(':memory:');
  for (const name of fs.readdirSync(path.join(__dirname,'migrations')).filter(n=>n.endsWith('.sql')).sort())
    db.exec(fs.readFileSync(path.join(__dirname,'migrations',name),'utf8'));
  const queries=[];
  const DB={prepare(sql){let args=[];return {
    bind(...values){args=values;return this;},
    async first(){queries.push(sql);return db.prepare(sql).get(...args)||null;},
    async all(){queries.push(sql);return {results:db.prepare(sql).all(...args)};},
    async run(){queries.push(sql);return {meta:db.prepare(sql).run(...args)};},
  };},async batch(statements){return Promise.all(statements.map(s=>s.run()));}};
  const worker=load('public-directory-entry').default;
  const now=Math.floor(Date.now()/1000);
  // Exercise the current publisher identity flow, not legacy shared secrets.
  const { publicKey, privateKey } = generateKeyPairSync('ed25519');
  const rawPublicKey = Buffer.from(publicKey.export({format:'jwk'}).x, 'base64url');
  const publicKeyText = rawPublicKey.toString('base64');
  const fingerprint = 'dwo1-' + createHash('sha256').update(rawPublicKey).digest('hex').slice(0,24);
  const env={DB};
  db.prepare('INSERT INTO world_publishers(world_id,operator_fingerprint,public_key,registered_at,last_seen) VALUES(?,?,?,?,?)').run('test',fingerprint,publicKeyText,now-60,now-60);
  db.prepare('INSERT INTO worlds(world_id,world_name,last_seen) VALUES(?,?,?)').run('test','Test',now-60);
  db.prepare('INSERT INTO heartbeat_history(world_id,seen_at,status) VALUES(?,?,?)').run('test',now-86400*8,'online');
  const pending=[];const ctx={waitUntil(p){pending.push(p);}};
  const body=JSON.stringify({world_id:'test',world_name:'Test',status:'online'});
  const signature=sign(null,Buffer.from(`${now}.${body}`),privateKey).toString('base64');
  const response=await worker.fetch(new Request('https://test/api/v1/heartbeat',{method:'POST',body,headers:{'x-dws-timestamp':String(now),'x-dws-signature':signature,'x-dws-public-key':publicKeyText,'x-dws-operator':fingerprint}}),env,ctx);
  const result=await response.json();
  assert.equal(response.status,200,JSON.stringify(result));
  assert.equal(result.registration,'ed25519-self-registration');
  assert.equal(result.operator_fingerprint,fingerprint);
  await Promise.all(pending);
  assert.ok(!queries.some(sql=>/^DELETE/i.test(sql.trim())),'Healthy heartbeat must not run cleanup');
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM heartbeat_history').get().n,2);
  queries.length=0;
  await worker.scheduled({},env,ctx);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM heartbeat_history').get().n,1,'Cron keeps current history and expires old history');
  const plan=db.prepare('EXPLAIN QUERY PLAN DELETE FROM heartbeat_history WHERE seen_at < ?').all(now);
  assert.ok(plan.some(row=>row.detail.includes('idx_heartbeat_history_seen_at')),'Retention must use timestamp index');
  const unavailable=await worker.fetch(new Request('https://test/api/v1/worlds'),{DB:{prepare(){throw new Error('D1 quota exceeded secret SQL');}}},ctx);
  assert.equal(unavailable.status,503);
  assert.equal(unavailable.headers.get('retry-after'),'300');
  assert.ok(!(await unavailable.text()).includes('secret SQL'));
  db.close();
  console.log('Retention: heartbeat has no deletes; cron preserves fresh rows; timestamp index used; failures return safe retryable 503: PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
