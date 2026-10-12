// Each hosted Server gets a private install tree. SteamCMD's machine-level
// installation is a template, never the writable runtime for a new profile.
const fs = require("fs");
const path = require("path");
const dbm = require("./db");
const detect = require("./detect");
const { contains } = require("./installdir");

const ROOT_KEY = "applicationSetup:serverProfilesDir";

function realDestination(candidate) {
  let current = path.resolve(candidate);
  const missing = [];
  while (!fs.existsSync(current)) {
    const parent = path.dirname(current);
    if (parent === current) break;
    missing.unshift(path.basename(current));
    current = parent;
  }
  return path.join(fs.realpathSync(current), ...missing);
}

function profileRoot(templateDir) {
  const saved = String(dbm.getSetting(ROOT_KEY, "") || "").trim();
  return path.resolve(saved || path.join(path.dirname(path.resolve(templateDir)), "RSDW-Server-Profiles"));
}

function validateRoot(root, templateDir) {
  const resolved = path.resolve(String(root || ""));
  const template = path.resolve(String(templateDir || ""));
  if (!root || !path.isAbsolute(String(root))) throw new Error("Choose an absolute Server profiles folder.");
  if (resolved === path.parse(resolved).root) throw new Error("The Server profiles folder cannot be a drive root.");
  const realRoot = realDestination(resolved);
  const realTemplate = realDestination(template);
  if (contains(realRoot, realTemplate) || contains(realTemplate, realRoot)) {
    throw new Error("Server profiles must be outside the shared SteamCMD installation folder.");
  }
  for (const world of dbm.listWorlds()) {
    if (world.install_dir && contains(realDestination(world.install_dir), realRoot)) {
      throw new Error(`The profile folder cannot be inside ${world.display_name}'s server files.`);
    }
  }
  return resolved;
}

function forkPath(templateDir, worldId) {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(worldId))) throw new Error("Invalid Server profile ID.");
  const root = validateRoot(profileRoot(templateDir), templateDir);
  return path.join(root, worldId);
}

async function forkInstall(templateDir, worldId, { includeSaved = false, onLog = () => {} } = {}) {
  const source = path.resolve(templateDir);
  const info = detect.inspect(source);
  if (!info.valid) throw new Error(info.reason || "The shared dedicated-server installation is incomplete.");
  const target = forkPath(source, worldId);
  const targetParent = path.dirname(target);
  if (fs.existsSync(target)) throw new Error(`Server profile folder already exists: ${target}`);
  await fs.promises.mkdir(targetParent, { recursive: true });
  onLog(`Forking server files from ${source}`);
  onLog(`Private Server profile: ${target}`);
  try {
    await fs.promises.cp(source, target, {
      recursive: true,
      force: false,
      errorOnExist: true,
      filter: async (entry) => {
        const relative = path.relative(source, entry).split(path.sep).join("/").toLowerCase();
        if (relative === "rsdragonwilds/activeworld.txt") return false;
        if (!includeSaved && relative === "rsdragonwilds/saved") return false;
        if (relative === "steamapps/downloading" || relative === "steamapps/temp") return false;
        if ((await fs.promises.lstat(entry)).isSymbolicLink()) throw new Error(`Cannot fork linked server file: ${entry}`);
        return true;
      },
    });
    const fork = detect.inspect(target);
    if (!fork.valid) throw new Error(`The private Server profile did not validate: ${fork.reason}`);
    onLog(`Verified private server executable: ${fork.binary}`);
    return { installDir: target, platform: fork.platform, buildId: fork.buildId };
  } catch (error) {
    // This target was created only for this UUID and is still inside the
    // validated profile root. Never remove the template or another profile.
    if (path.dirname(target) === targetParent && path.basename(target) === worldId) {
      await fs.promises.rm(target, { recursive: true, force: true }).catch(() => {});
    }
    throw error;
  }
}

module.exports = { ROOT_KEY, profileRoot, validateRoot, forkPath, forkInstall };
