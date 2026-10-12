const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const runtime = require("../electron/stable-runtime");

const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-stable-runtime-"));
try {
  const source = path.join(sandbox, "portable-temp", "resources", "app");
  const data = path.join(sandbox, "user-data");
  for (const relative of runtime.REQUIRED) {
    const file = path.join(source, relative);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, relative.endsWith("BUILD_ID") ? "test-build-id" : "module.exports = {};");
  }
  fs.writeFileSync(path.join(source, "build-info.json"), JSON.stringify({ version: "test", commit: "abc123" }));
  const stable = runtime.materializeRuntime(source, data);
  assert(stable.startsWith(path.join(data, "interface-runtime")));
  runtime.verifyRuntime(stable);
  fs.rmSync(path.join(sandbox, "portable-temp"), { recursive: true, force: true });
  runtime.verifyRuntime(stable);
  assert.equal(runtime.materializeRuntime(stable, data), stable, "cached runtime should be reused without another copy");
  console.log("Persistent portable interface runtime: OK");
} finally {
  fs.rmSync(sandbox, { recursive: true, force: true });
}
