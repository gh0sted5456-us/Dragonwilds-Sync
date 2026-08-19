const JSON_HEADERS = { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' };
const PUBLIC_HEADERS = { ...JSON_HEADERS, 'access-control-allow-origin': '*' };
const MAX_BODY = 64 * 1024;
const ACTIVE_WINDOW_SECONDS = 15 * 60;

const json = (value, status=200, headers=JSON_HEADERS) => new Response(JSON.stringify(value), { status, headers });
const now = () => Math.floor(Date.now()/1000);
const enc = new TextEncoder();
const dec = new TextDecoder();
const hex = (bytes) => [...new Uint8Array(bytes)].map((v)=>v.toString(16).padStart(2,'0')).join('');
const b64 = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes)));
const unb64 = (text) => Uint8Array.from(atob(String(text||'')), (c)=>c.charCodeAt(0));

async function sha256Text(text) { return hex(await crypto.subtle.digest('SHA-256', enc.encode(String(text)))); }
async function wrapKey(env) {
  if (!env.CREDENTIAL_WRAP_KEY) throw new Error('CREDENTIAL_WRAP_KEY is required');
  const digest = await crypto.subtle.digest('SHA-256', enc.encode(String(env.CREDENTIAL_WRAP_KEY)));
  return crypto.subtle.importKey('raw', digest, {name:'AES-GCM'}, false, ['encrypt','decrypt']);
}
async function sealCredential(env, credential) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await wrapKey(env);
  const cipher = await crypto.subtle.encrypt({name:'AES-GCM',iv}, key, enc.encode(String(credential)));
  return { verifier: await sha256Text(credential), cipher: b64(cipher), iv: b64(iv) };
}
async function openCredential(env, row) {
  const key = await wrapKey(env);
  const clear = await crypto.subtle.decrypt({name:'AES-GCM',iv:unb64(row.credential_iv)}, key, unb64(row.credential_ciphertext));
  return dec.decode(clear);
}
async function verifyHmac(secret, stamp, raw, supplied) {
  const timestamp = Number(stamp||0);
  if (!timestamp || Math.abs(now()-timestamp) > 300 || !/^[0-9a-f]{64}$/i.test(String(supplied||''))) return false;
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), {name:'HMAC',hash:'SHA-256'}, false, ['sign']);
  const signed = new Uint8Array(enc.encode(`${stamp}.`).length + raw.length);
  signed.set(enc.encode(`${stamp}.`),0); signed.set(raw,enc.encode(`${stamp}.`).length);
  const signature = hex(await crypto.subtle.sign('HMAC', key, signed));
  return signature.toLowerCase() === String(supplied).toLowerCase();
}
async function bodyBytes(request) {
  const claimed = Number(request.headers.get('content-length')||0);
  if (claimed > MAX_BODY) throw Object.assign(new Error('payload_too_large'),{status:413});
  const raw = new Uint8Array(await request.arrayBuffer());
  if (raw.length > MAX_BODY) throw Object.assign(new Error('payload_too_large'),{status:413});
  return raw;
}
function parsed(raw) {
  try { return JSON.parse(dec.decode(raw)); } catch { throw Object.assign(new Error('malformed_json'),{status:400}); }
}
function normalizedId(value, prefix) {
  const text=String(value||'').trim();
  const re = prefix==='installation' ? /^dws-install-[0-9a-f]{32}$/ : /^dws-world-[0-9a-f]{32}$/;
  if (!re.test(text)) throw Object.assign(new Error(`invalid_${prefix}_id`),{status:400});
  return text;
}
async function limited(env, scope, key, limit, seconds) {
  const bucket = Math.floor(now()/seconds);
  const id = `${scope}:${String(key||'anonymous').slice(0,160)}:${bucket}`;
  await env.DB.prepare('INSERT INTO rate_limits_v3 (bucket_id,count,expires_at) VALUES (?1,1,?2) ON CONFLICT(bucket_id) DO UPDATE SET count=count+1').bind(id,(bucket+2)*seconds).run();
  const row = await env.DB.prepare('SELECT count FROM rate_limits_v3 WHERE bucket_id=?1').bind(id).first();
  return Number(row?.count||0) > limit;
}
async function installationRow(env, installationId) {
  return env.DB.prepare('SELECT installation_id,credential_verifier,credential_ciphertext,credential_iv,revoked_at FROM installations WHERE installation_id=?1').bind(installationId).first();
}
async function worldCredentialRow(env, worldId) {
  return env.DB.prepare('SELECT world_id,installation_id,credential_verifier,credential_ciphertext,credential_iv,revoked_at FROM world_credentials WHERE world_id=?1').bind(worldId).first();
}
async function verifyInstallation(request, env, raw, installationId) {
  const row=await installationRow(env,installationId); if(!row||row.revoked_at)return null;
  const secret=await openCredential(env,row);
  return await verifyHmac(secret,request.headers.get('x-dws-timestamp'),raw,request.headers.get('x-dws-signature')) ? row : null;
}
async function verifyWorld(request, env, raw, worldId) {
  const row=await worldCredentialRow(env,worldId); if(!row||row.revoked_at)return null;
  const secret=await openCredential(env,row);
  return await verifyHmac(secret,request.headers.get('x-dws-timestamp'),raw,request.headers.get('x-dws-signature')) ? row : null;
}
function sanitizeWorld(input) {
  const status = ['active','stopping','offline'].includes(String(input.status||'').toLowerCase()) ? String(input.status).toLowerCase() : 'active';
  const connection = input.connection && typeof input.connection==='object' ? input.connection : null;
  return {
    world_id: normalizedId(input.world_id,'world'), name:String(input.name||'World').slice(0,160), description:String(input.description||'').slice(0,600),
    region:String(input.region||'').slice(0,80), cl:String(input.cl||'').slice(0,80), status,
    host_type: ['dedicated','coop'].includes(String(input.host_type||'')) ? String(input.host_type) : 'dedicated',
    player_count: Math.max(0,Math.min(Number(input.player_count||0),10000)), max_players:Math.max(0,Math.min(Number(input.max_players||0),10000)),
    tags:Array.isArray(input.tags)?input.tags.slice(0,24).map((v)=>String(v).slice(0,40)):[], mods:Array.isArray(input.mods)?input.mods.slice(0,64).map((v)=>String(v).slice(0,80)):[],
    badges:Array.isArray(input.badges)?input.badges.slice(0,32).map((v)=>String(v).slice(0,80)):[], rules:String(input.rules||'').slice(0,4000),
    connection: connection && connection.address ? {address:String(connection.address).slice(0,255),game_port:Math.max(1,Math.min(Number(connection.game_port||7777),65535))}:null,
  };
}

async function handleRegister(request, env, ip) {
  if(await limited(env,'register',ip,10,60)) return json({error:'rate_limited'},429);
  const raw=await bodyBytes(request), data=parsed(raw); const id=normalizedId(data.installation_id,'installation'); const credential=String(data.credential||'');
  if(credential.length<32||credential.length>256)return json({error:'invalid_credential'},400);
  const existing=await installationRow(env,id); const verifier=await sha256Text(credential);
  if(existing){ if(existing.revoked_at)return json({error:'revoked'},403); if(existing.credential_verifier!==verifier)return json({error:'installation_id_conflict'},409); return json({ok:true,registered:true,reused:true}); }
  const sealed=await sealCredential(env,credential);
  await env.DB.prepare('INSERT INTO installations (installation_id,credential_verifier,credential_ciphertext,credential_iv,created_at,last_seen,app_version,mode,revoked_at) VALUES (?1,?2,?3,?4,?5,?5,?6,?7,NULL)').bind(id,sealed.verifier,sealed.cipher,sealed.iv,now(),String(data.app_version||'').slice(0,80),'client').run();
  return json({ok:true,registered:true});
}
async function handlePresence(request,env) {
  const raw=await bodyBytes(request),data=parsed(raw);const id=normalizedId(data.installation_id,'installation');
  if(await limited(env,'presence',id,12,60))return json({error:'rate_limited'},429);
  if(!await verifyInstallation(request,env,raw,id))return json({error:'invalid_signature'},401);
  const mode=['client','dedicated_server','coop_host'].includes(String(data.mode||''))?String(data.mode):'client';
  await env.DB.prepare('UPDATE installations SET last_seen=?2,app_version=?3,mode=?4 WHERE installation_id=?1').bind(id,now(),String(data.app_version||'').slice(0,80),mode).run();
  await env.DB.prepare('INSERT INTO network_presence_v3 (installation_id,last_seen,app_version,mode) VALUES (?1,?2,?3,?4) ON CONFLICT(installation_id) DO UPDATE SET last_seen=excluded.last_seen,app_version=excluded.app_version,mode=excluded.mode').bind(id,now(),String(data.app_version||'').slice(0,80),mode).run();
  return json({ok:true});
}
async function handleWorldRegister(request,env) {
  const raw=await bodyBytes(request),data=parsed(raw); const installationId=normalizedId(data.installation_id,'installation'),worldId=normalizedId(data.world_id,'world');
  if(await limited(env,'world-register',installationId,20,60))return json({error:'rate_limited'},429);
  if(!await verifyInstallation(request,env,raw,installationId))return json({error:'invalid_installation_signature'},401);
  const credential=String(data.credential||''); if(credential.length<32||credential.length>256)return json({error:'invalid_credential'},400);
  const verifier=await sha256Text(credential),existing=await worldCredentialRow(env,worldId);
  if(existing){if(existing.revoked_at)return json({error:'revoked'},403);if(existing.installation_id!==installationId)return json({error:'world_owned_by_other_installation'},409);if(existing.credential_verifier!==verifier)return json({error:'world_id_conflict'},409);return json({ok:true,registered:true,reused:true});}
  const sealed=await sealCredential(env,credential);
  await env.DB.prepare('INSERT INTO world_credentials (world_id,installation_id,credential_verifier,credential_ciphertext,credential_iv,created_at,revoked_at) VALUES (?1,?2,?3,?4,?5,?6,NULL)').bind(worldId,installationId,sealed.verifier,sealed.cipher,sealed.iv,now()).run();
  return json({ok:true,registered:true});
}
async function handleHeartbeat(request,env) {
  const raw=await bodyBytes(request),data=sanitizeWorld(parsed(raw)),worldId=data.world_id;
  if(await limited(env,'heartbeat',worldId,12,600))return json({error:'rate_limited'},429);
  const credential=await verifyWorld(request,env,raw,worldId);if(!credential)return json({error:'invalid_signature'},401);
  const seen=now(),payload=JSON.stringify(data);
  await env.DB.prepare(`INSERT INTO worlds_v3 (world_id,name,description,region,cl,status,host_type,player_count,max_players,tags_json,mods_json,badges_json,rules,connection_json,last_seen,updated_at)
    VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,?15,?15)
    ON CONFLICT(world_id) DO UPDATE SET name=excluded.name,description=excluded.description,region=excluded.region,cl=excluded.cl,status=excluded.status,host_type=excluded.host_type,player_count=excluded.player_count,max_players=excluded.max_players,tags_json=excluded.tags_json,mods_json=excluded.mods_json,badges_json=excluded.badges_json,rules=excluded.rules,connection_json=excluded.connection_json,last_seen=excluded.last_seen,updated_at=excluded.updated_at`).bind(worldId,data.name,data.description,data.region,data.cl,data.status,data.host_type,data.player_count,data.max_players,JSON.stringify(data.tags),JSON.stringify(data.mods),JSON.stringify(data.badges),data.rules,JSON.stringify(data.connection),seen).run();
  await env.DB.prepare('INSERT INTO heartbeat_history_v3 (world_id,seen_at,status,player_count,cl,payload_json) VALUES (?1,?2,?3,?4,?5,?6)').bind(worldId,seen,data.status,data.player_count,data.cl,payload).run();
  return json({ok:true,world_id:worldId,received_at:seen});
}
function publicWorld(row) {
  const effectiveStatus = Number(row.last_seen||0) < now()-ACTIVE_WINDOW_SECONDS ? 'offline' : row.status;
  return {world_id:row.world_id,name:row.name,description:row.description,region:row.region,cl:row.cl,status:effectiveStatus,host_type:row.host_type,player_count:row.player_count,max_players:row.max_players,tags:JSON.parse(row.tags_json||'[]'),mods:JSON.parse(row.mods_json||'[]'),badges:JSON.parse(row.badges_json||'[]'),rules:row.rules,connection:JSON.parse(row.connection_json||'null'),last_seen:row.last_seen};
}
async function listWorlds(env) {
  const cutoff=now()-ACTIVE_WINDOW_SECONDS;const result=await env.DB.prepare("SELECT * FROM worlds_v3 WHERE last_seen>=?1 AND status!='offline' ORDER BY last_seen DESC LIMIT 500").bind(cutoff).all();
  return json({worlds:(result.results||[]).map(publicWorld),generated_at:now()},200,PUBLIC_HEADERS);
}
async function worldById(env,id) {const worldId=normalizedId(id,'world'),row=await env.DB.prepare('SELECT * FROM worlds_v3 WHERE world_id=?1').bind(worldId).first();return row?json(publicWorld(row),200,PUBLIC_HEADERS):json({error:'not_found'},404,PUBLIC_HEADERS);}
async function networkStats(env) {
  const cutoff=now()-ACTIVE_WINDOW_SECONDS;
  const worlds=await env.DB.prepare("SELECT COUNT(*) AS n, COALESCE(SUM(player_count),0) AS players FROM worlds_v3 WHERE last_seen>=?1 AND status='active'").bind(cutoff).first();
  const installations=await env.DB.prepare('SELECT COUNT(*) AS n FROM installations WHERE last_seen>=?1 AND revoked_at IS NULL').bind(cutoff).first();
  return json({active_worlds:Number(worlds?.n||0),active_players:Number(worlds?.players||0),active_installations:Number(installations?.n||0),generated_at:now()},200,PUBLIC_HEADERS);
}

export default {
  async fetch(request,env) {
    const url=new URL(request.url),path=url.pathname.replace(/\/$/,'')||'/';
    if(request.method==='OPTIONS')return new Response(null,{status:204,headers:{'access-control-allow-origin':'*','access-control-allow-methods':'GET,POST,OPTIONS','access-control-allow-headers':'content-type,x-dws-timestamp,x-dws-signature,x-dws-installation-id,x-dws-world-id'}});
    try {
      if(request.method==='GET'&&path==='/health')return json({ok:true,service:'dragonwilds-sync-directory',version:3},200,PUBLIC_HEADERS);
      if(request.method==='GET'&&(path==='/api/v1/capabilities'||path==='/.well-known/dragonwilds-sync'))return json({available:true,protocol:'dragonwilds-sync-directory',protocol_version:1,registration:true,presence:true,world_registration:true,heartbeat:true,network:true,worlds:true},200,PUBLIC_HEADERS);
      if(request.method==='GET'&&path==='/api/v1/worlds')return listWorlds(env);
      if(request.method==='GET'&&path==='/api/v1/network')return networkStats(env);
      if(request.method==='GET'&&path.startsWith('/api/v1/worlds/'))return worldById(env,decodeURIComponent(path.slice('/api/v1/worlds/'.length)));
      const ip=request.headers.get('cf-connecting-ip')||'unknown';
      if(request.method==='POST'&&path==='/api/v1/register')return handleRegister(request,env,ip);
      if(request.method==='POST'&&path==='/api/v1/presence')return handlePresence(request,env);
      if(request.method==='POST'&&path==='/api/v1/worlds/register')return handleWorldRegister(request,env);
      if(request.method==='POST'&&path==='/api/v1/heartbeat')return handleHeartbeat(request,env);
      return json({error:'not_found'},404,PUBLIC_HEADERS);
    } catch(error) {
      const status=Number(error?.status||500);return json({error:status===500?'internal_error':String(error?.message||'request_failed')},status);
    }
  }
};
