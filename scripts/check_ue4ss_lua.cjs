const fs = require('node:fs');
const path = require('node:path');
const luaparse = require('luaparse');

const resourcesRoot = path.join(__dirname, '..', 'resources');
const files = [];

function collectLua(directory) {
  if (!fs.existsSync(directory)) return;
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const candidate = path.join(directory, entry.name);
    if (entry.isDirectory()) collectLua(candidate);
    else if (entry.isFile() && path.extname(entry.name).toLowerCase() === '.lua') files.push(candidate);
  }
}

collectLua(resourcesRoot);

for (const file of files) {
  const source = fs.readFileSync(file, 'utf8');
  luaparse.parse(source, { luaVersion: '5.3', locations: true });
  console.log(`[OK] Lua syntax: ${path.relative(path.join(__dirname, '..'), file)}`);
}

if (!files.length) console.log('[OK] No loose bundled UE4SS Lua sources are present.');
