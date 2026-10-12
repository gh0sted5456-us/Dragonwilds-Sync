const assert = require("assert");
const path = require("path");
const guard = require("../lib/server-process-guard");

const root = path.join(process.cwd(), "server-process-guard-fixture");
const template = path.join(root, "steamcmd", "server");
const privateInstall = path.join(root, "profiles", "one");
const otherInstall = path.join(root, "profiles", "two");
const world = { install_dir: privateInstall };
const processAt = (pid, install) => ({ pid, executablePath: path.join(install, "RSDragonwildsServer.exe"), commandLine: "" });

assert.deepStrictEqual(guard.findConflicts(world, [processAt(101, otherInstall)], template), [], "another private profile should be allowed");
assert.strictEqual(guard.findConflicts(world, [processAt(102, template)], template).length, 1, "native template process was not detected");
assert.strictEqual(guard.findConflicts(world, [processAt(103, privateInstall)], template).length, 1, "untracked process inside this fork was not detected");
assert.throws(() => guard.assertNoConflictingServer(world, { template, processes: [processAt(104, template)] }), /Another Dragonwilds server/);
assert.deepStrictEqual(guard.assertNoConflictingServer(world, { template, processes: [processAt(105, otherInstall)] }), []);
console.log("Server process isolation: OK");
