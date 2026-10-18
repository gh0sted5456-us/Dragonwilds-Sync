const fs = require("fs");
const path = require("path");
const AdmZip = require("adm-zip");

const MAX_LOG_BYTES = 32 * 1024 * 1024;
const activeExports = globalThis.__RSDW_LOG_EXPORTS ||= new Set();
class LogExportError extends Error {
  constructor(message, status = 400) { super(message); this.status = status; }
}
const inside = (root, file) => {
  const relative = path.relative(root, file);
  return relative === "" || (!path.isAbsolute(relative) && relative !== ".." && !relative.startsWith(`..${path.sep}`));
};
const checkAbort = (signal) => { if (signal?.aborted) throw new LogExportError("Log export cancelled.", 499); };
const safeName = (name) => String(name || "world").replace(/[^a-zA-Z0-9_.-]/g, "_").replace(/^\.+/, "").slice(0, 100) || "world";
const isEOSLine = (line) => /\b(?:LogEOS\w*|EOSSDK|EOS_[A-Za-z0-9_]+|LogOnlineSubsystemRedpointEOS)\b|LogOnline\w*:[^\r\n]*\b(?:EOS|Redpoint)\b/i.test(line);
function decodeLog(bytes, encoding) { return encoding === "utf16le" || (bytes[0] === 0xff && bytes[1] === 0xfe) ? bytes.toString("utf16le").replace(/^\uFEFF/, "") : bytes.toString("utf8").replace(/^\uFEFF/, ""); }
function tailLines(text, filter, limit, skipFirst = false) {
  const ring = new Array(limit);
  let start = 0, count = 0, first = true;
  while (start < text.length) {
    const end = text.indexOf("\n", start);
    const line = text.slice(start, end < 0 ? text.length : end).replace(/\r$/, "");
    if (!(first && skipFirst) && (!filter || filter(line))) ring[count++ % limit] = line;
    first = false;
    if (end < 0) break;
    start = end + 1;
  }
  return { lines: count <= limit ? ring.slice(0, count) : [...ring.slice(count % limit), ...ring.slice(0, count % limit)], count };
}

function sourcesFor(kind, record, localAppData = process.env.LOCALAPPDATA) {
  let connection = {};
  try { connection = JSON.parse(record.connection_json || "{}"); } catch {}
  const install = kind === "server" ? record.install_dir : record.client_install;
  const platform = kind === "server" || (connection.service || connection.platform) !== "gamepass" ? "Win64" : "WinGDK";
  const native = [], ue4ss = [];
  const add = (list, anchor, relative, label) => { if (anchor) list.push({ anchor: path.resolve(anchor), relative, label }); };
  if (install) {
    add(native, install, "RSDragonwilds/Saved/Logs", "Profile installation");
    add(native, install, "Saved/Logs", "Legacy profile installation");
    add(ue4ss, install, `RSDragonwilds/Binaries/${platform}/ue4ss`, "Mapped game installation");
    add(ue4ss, install, `RSDragonwilds/Binaries/${platform}`, "Legacy loader log location");
  }
  if (kind === "player") {
    if (localAppData) add(native, path.join(localAppData, "RSDragonwilds", "Saved"), "Logs", "Local game save directory");
    if (connection.savePath && !/[\\/]systemappdata[\\/]wgs(?:[\\/]|$)/i.test(connection.savePath)) {
      let saved = path.resolve(connection.savePath);
      const base = path.basename(saved).toLowerCase();
      if (["savegames", "savecharacter", "savecharacters"].includes(base)) saved = path.dirname(saved);
      else if (base !== "saved") saved = path.join(saved, "Saved");
      add(native, saved, "Logs", "Configured game save directory");
    }
  }
  return { native, ue4ss };
}

async function discover(source, category, signal) {
  checkAbort(signal);
  const anchor = await fs.promises.realpath(source.anchor);
  const dir = path.join(source.anchor, ...source.relative.split("/"));
  const realDir = await fs.promises.realpath(dir);
  if (!inside(anchor, realDir)) return [];
  const candidates = [];
  const inspect = async (name, fallback = false) => {
    const file = path.join(dir, name);
    try {
      const stat = await fs.promises.lstat(file);
      if (!stat.isFile() || stat.isSymbolicLink()) return;
      const realFile = await fs.promises.realpath(file);
      if (!inside(anchor, realFile)) return;
      candidates.push({ file, anchor, stat, fallback, category, name, source: source.label });
    } catch { /* A live log may rotate between directory and file lookup. */ }
  };
  for (const name of category === "native" ? ["RSDragonwilds.log", "RSDragonwildsServer.log"] : ["UE4SS.log"]) await inspect(name);
  if (category === "native") {
    const directory = await fs.promises.opendir(dir);
    let visited = 0;
    for await (const entry of directory) {
      checkAbort(signal);
      if (++visited > 1024) break;
      if (entry.isFile() && /^RSDragonwilds(?:Server)?[-_].*\.log$/i.test(entry.name)) await inspect(entry.name, /[-_]backup[-_]/i.test(entry.name));
    }
  }
  return candidates;
}

async function snapshot(candidate, maxBytes, signal) {
  checkAbort(signal);
  // Check both the path and opened file identity. Never follow a log-file link
  // into settings, saves, or another installation, including after rotation.
  const before = await fs.promises.lstat(candidate.file);
  if (!before.isFile() || before.isSymbolicLink()) throw new Error("Unsafe log file");
  if (!inside(candidate.anchor, await fs.promises.realpath(candidate.file))) throw new Error("Unsafe log path");
  const noFollow = process.platform === "win32" ? 0 : (fs.constants.O_NOFOLLOW || 0);
  const handle = await fs.promises.open(candidate.file, fs.constants.O_RDONLY | noFollow);
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || stat.ino !== before.ino || stat.dev !== before.dev) throw new Error("Log rotated before snapshot");
    if (!inside(candidate.anchor, await fs.promises.realpath(candidate.file))) throw new Error("Unsafe log path");
    const length = Math.min(stat.size, maxBytes);
    const start = Math.max(0, stat.size - length);
    const bom = Buffer.alloc(2);
    await handle.read(bom, 0, 2, 0);
    const encoding = bom[0] === 0xff && bom[1] === 0xfe ? "utf16le" : "utf8";
    const bytes = Buffer.alloc(length);
    let read = 0;
    while (read < length) {
      checkAbort(signal);
      const result = await handle.read(bytes, read, Math.min(256 * 1024, length - read), start + read);
      if (!result.bytesRead) break;
      read += result.bytesRead;
    }
    return { bytes: bytes.subarray(0, read), originalBytes: stat.size, truncated: start > 0 || read < length, offset: start, encoding, modifiedAt: stat.mtime.toISOString() };
  } finally { await handle.close(); }
}

async function buildLogExport({ kind, record, localAppData, signal, maxLogBytes = MAX_LOG_BYTES }) {
  if (!["server", "player"].includes(kind)) throw new LogExportError("Unsupported log export.");
  const id = record?.[kind === "server" ? "world_id" : "profile_id"];
  if (!id) throw new LogExportError("World profile not found.", 404);
  const key = `${kind}:${id}`;
  if (activeExports.has(key) || activeExports.size >= 2) throw new LogExportError("A log export is already being prepared. Please try again shortly.", 409);
  activeExports.add(key);
  try {
    checkAbort(signal);
    const cap = Math.max(1, Math.min(MAX_LOG_BYTES, Number(maxLogBytes) || MAX_LOG_BYTES));
    const sources = sourcesFor(kind, record, localAppData);
    const zip = new AdmZip();
    const files = [], missing = [], warnings = [];
    let eosInfo = { file: null, source: "EOS-tagged messages extracted from the included native game log; not a separate SDK capture." };
    for (const category of ["native", "ue4ss"]) {
      const candidates = [];
      for (const source of sources[category]) {
        try { candidates.push(...await discover(source, category, signal)); }
        catch (error) { checkAbort(signal); /* Missing or inaccessible optional location. */ }
      }
      candidates.sort((a, b) => Number(a.fallback) - Number(b.fallback) || b.stat.mtimeMs - a.stat.mtimeMs);
      let included = false;
      for (const candidate of candidates) {
        try {
          const copy = await snapshot(candidate, cap, signal);
          const name = `${category}/${safeName(candidate.name)}`;
          zip.addFile(name, copy.bytes);
          files.push({ file: name, source: candidate.source, bytes: copy.bytes.length, originalBytes: copy.originalBytes, truncated: copy.truncated, modifiedAt: copy.modifiedAt });
          if (copy.truncated) warnings.push(`${category}: only the latest ${copy.bytes.length} bytes could be captured; see originalBytes.`);
          if (candidate.fallback) warnings.push("Native log: the current log was unavailable; the newest available backup was included.");
          if (category === "native") {
            const eos = tailLines(decodeLog(copy.bytes, copy.encoding), isEOSLine, 10000, copy.offset > 0);
            zip.addFile("eos/EOS.log", Buffer.from(eos.lines.length ? eos.lines.join("\n") + "\n" : "No EOS-tagged messages were found in the captured native log.\n"));
            eosInfo = { ...eosInfo, file: "eos/EOS.log", lines: eos.lines.length, messagesInCapturedNativeLog: eos.count, truncated: eos.count > eos.lines.length || copy.truncated };
            if (eos.count > eos.lines.length) warnings.push("EOS.log contains the latest 10000 EOS messages; the captured native log retains the other messages.");
          }
          included = true;
          break;
        } catch { checkAbort(signal); /* Try a rotation/alternate location without stopping the game. */ }
      }
      if (!included) missing.push(category);
    }
    if (!files.length) throw new LogExportError("No native game or UE4SS logs were found for this profile. Launch the game/server once, or check its installation and log permissions, then try again.", 404);
    const exportedAt = new Date().toISOString();
    const info = { schema: "RSDWSync.LogExport.v1", kind, profileId: id, name: record.display_name || "World", exportedAt, files, missing, warnings, maxBytesPerLog: cap,
      eos: eosInfo,
      note: kind === "player" ? "These are local client logs, not the connected host's logs. The native game log can be shared across player World profiles on this PC." : "Logs were snapshotted from this server profile without stopping or restarting it." };
    zip.addFile("export-info.json", Buffer.from(JSON.stringify(info, null, 2)));
    zip.addFile("README.txt", Buffer.from("RSDW Sync log export\r\n\r\nNative game and UE4SS logs only; no INI files, saves, or launcher credentials are added.\r\nLogs themselves may contain names, IP addresses, passwords or tokens. Review them before sharing.\r\nRunning logs are point-in-time snapshots and may continue growing after export.\r\nSee export-info.json for missing files, backup fallback, or size-limited tails.\r\n"));
    checkAbort(signal);
    const buffer = await zip.toBufferPromise();
    checkAbort(signal);
    const filename = `${safeName(record.display_name)}_logs_${exportedAt.replace(/[:.]/g, "-")}.zip`;
    return { buffer, filename, info };
  } finally { activeExports.delete(key); }
}

function downloadHeaders(result) {
  return { "Content-Type": "application/zip", "Content-Disposition": `attachment; filename="${result.filename}"`, "Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff", "X-RSDW-Log-Files": String(result.info.files.length), "X-RSDW-Log-Warnings": String(result.info.missing.length + result.info.warnings.length) };
}

async function readLogView({ kind, record, channel = "eos", localAppData, signal }) {
  if (!["server", "player"].includes(kind) || !["native", "ue4ss", "eos"].includes(channel)) throw new LogExportError("Unknown log channel.");
  const category = channel === "ue4ss" ? "ue4ss" : "native";
  const candidates = [];
  for (const source of sourcesFor(kind, record, localAppData)[category]) {
    try { candidates.push(...await discover(source, category, signal)); } catch { checkAbort(signal); }
  }
  candidates.sort((a, b) => Number(a.fallback) - Number(b.fallback) || b.stat.mtimeMs - a.stat.mtimeMs);
  for (const candidate of candidates) {
    try {
      const copy = await snapshot(candidate, 2 * 1024 * 1024, signal);
      const tail = tailLines(decodeLog(copy.bytes, copy.encoding), channel === "eos" ? isEOSLine : null, 800, copy.offset > 0);
      return { ok: true, channel, lines: tail.lines, logName: candidate.name, source: candidate.source, modifiedAt: copy.modifiedAt, originalBytes: copy.originalBytes, sampledBytes: copy.bytes.length, truncated: copy.truncated || tail.count > 800, backup: candidate.fallback, missing: false,
        note: channel === "eos" ? "EOS messages from the game's native log. This is not a separate EOS SDK session." : kind === "player" ? "Local client log; not the connected host's log. Native logs can be shared across player profiles." : "Native log snapshot from this server profile." };
    } catch { checkAbort(signal); }
  }
  return { ok: true, channel, lines: [], missing: true, truncated: false, note: `No readable ${category === "native" ? "native game" : "UE4SS"} log was found. Start the game/server once and check its configured installation.` };
}
module.exports = { buildLogExport, readLogView, downloadHeaders, sourcesFor, isEOSLine, LogExportError, MAX_LOG_BYTES };
