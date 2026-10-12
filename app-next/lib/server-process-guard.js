const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const dbm = require("./db");

function normalized(value) {
  if (!value) return "";
  let resolved = path.resolve(String(value));
  try { resolved = fs.realpathSync.native(resolved); } catch {}
  return process.platform === "win32" ? resolved.toLowerCase() : resolved;
}

function within(root, candidate) {
  const parent = normalized(root);
  const child = normalized(candidate);
  return !!parent && !!child && (child === parent || child.startsWith(parent + path.sep));
}

function windowsServerProcesses() {
  // Query the OS, not only our persisted PID: a manual SteamCMD launch or a
  // previous app crash can leave a server outside this process's child map.
  const script = "$ErrorActionPreference='Stop'; Get-CimInstance Win32_Process -Filter \"Name LIKE '%Dragonwilds%'\" | Where-Object { $_.Name -match 'Server' -or $_.CommandLine -match '(^|\\s)-server(\\s|$)' } | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress";
  const result = spawnSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script], {
    encoding: "utf8", timeout: 8000, windowsHide: true, maxBuffer: 1024 * 1024,
  });
  if (result.error || result.status !== 0) {
    // Some locked-down Windows hosts deny CIM while allowing process names.
    // With no command line available, any server process is conservatively a
    // conflict rather than risking a second launch against the same save.
    const fallback = spawnSync("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", "$ErrorActionPreference='Stop'; Get-Process -Name '*Dragonwilds*' -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match 'Server' } | Select-Object Id,Path | ConvertTo-Json -Compress"], {
      encoding: "utf8", timeout: 8000, windowsHide: true, maxBuffer: 1024 * 1024,
    });
    if (fallback.error || fallback.status !== 0) throw new Error(`Could not inspect running Dragonwilds servers: ${fallback.error?.message || fallback.stderr?.trim() || "process query failed"}`);
    const text = String(fallback.stdout || "").replace(/^\uFEFF/, "").trim();
    if (!text) return [];
    const value = JSON.parse(text);
    return (Array.isArray(value) ? value : [value]).map((item) => ({ pid: Number(item.Id), executablePath: item.Path || "", commandLine: "" }));
  }
  const output = String(result.stdout || "").replace(/^\uFEFF/, "").trim();
  if (!output) return [];
  const parsed = JSON.parse(output);
  return (Array.isArray(parsed) ? parsed : [parsed]).map((item) => ({
    pid: Number(item.ProcessId), executablePath: item.ExecutablePath || "", commandLine: item.CommandLine || "",
  }));
}

function linuxServerProcesses() {
  const rows = [];
  for (const entry of fs.readdirSync("/proc", { withFileTypes: true })) {
    if (!entry.isDirectory() || !/^\d+$/.test(entry.name)) continue;
    const pid = Number(entry.name);
    if (pid === process.pid) continue;
    try {
      const commandLine = fs.readFileSync(`/proc/${pid}/cmdline`, "utf8").replace(/\0/g, " ").trim();
      if (!/RSDragonwildsServer(?:\.exe|\.sh)?|RSDragonwilds[^\s]*Shipping[^\s]*\s.*-server/i.test(commandLine)) continue;
      let executablePath = "";
      try { executablePath = fs.readlinkSync(`/proc/${pid}/exe`); } catch {}
      rows.push({ pid, executablePath, commandLine });
    } catch { /* process exited or is not visible to this user */ }
  }
  return rows;
}

function runningServerProcesses() {
  if (process.platform === "win32") return windowsServerProcesses();
  if (process.platform === "linux") return linuxServerProcesses();
  return [];
}

function executableFromCommandLine(commandLine) {
  const value = String(commandLine || "");
  const quoted = value.match(/^\s*"([^"]+)"/);
  if (quoted) return quoted[1];
  return value.trim().split(/\s+/)[0] || "";
}

function findConflicts(world, processes, template) {
  const install = normalized(world.install_dir);
  const source = template ? normalized(template) : "";
  return processes.filter((item) => {
    if (!item.pid || item.pid === process.pid) return false;
    const executable = item.executablePath || executableFromCommandLine(item.commandLine);
    if (!executable) return true; // A hidden path cannot be proved safe.
    if (within(install, executable)) return true;
    if (source && source !== install && within(source, executable)) return true;
    // Wine may report wine64 as the process executable; its command line still
    // includes the actual Dragonwilds binary beneath the relevant install.
    const command = String(item.commandLine || "").toLowerCase();
    return command.includes(install.toLowerCase() + path.sep)
      || !!(source && source !== install && command.includes(source.toLowerCase() + path.sep));
  });
}

function assertNoConflictingServer(world, options = {}) {
  const template = options.template === undefined ? dbm.getSetting("applicationSetup:serverDir", null) : options.template;
  const processes = options.processes || runningServerProcesses();
  const conflicts = findConflicts(world, processes, template);
  if (!conflicts.length) return [];
  const item = conflicts[0];
  throw new Error(`Another Dragonwilds server is already running from ${item.executablePath || "an unreadable location"} (PID ${item.pid}). Stop it before launching this profile; RSDW will not terminate it automatically.`);
}

module.exports = { assertNoConflictingServer, findConflicts, runningServerProcesses, within };
