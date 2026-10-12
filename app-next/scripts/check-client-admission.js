const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const manifest = require("../lib/sync/manifest");

const root = fs.mkdtempSync(path.join(os.tmpdir(), "rsdw-admission-"));
try {
  fs.mkdirSync(path.join(root, "RSDragonwilds", "Binaries", "Win64"), { recursive: true });
  const target = "RSDragonwilds/Content/Paks/~mods/Admission.pak";
  const local = path.join(root, ...target.split("/"));
  fs.mkdirSync(path.dirname(local), { recursive: true });
  fs.writeFileSync(local, "verified admission content", "utf8");
  const file = { target, size: fs.statSync(local).size, sha256: manifest.sha256File(local) };
  const required = { protocol: manifest.PROTOCOL, protocolVersion: manifest.PROTOCOL_VERSION, revision: "admission-revision", units: [{ key: "admission", name: "Admission", type: "pak", files: [file] }] };
  const attestation = manifest.createClientAttestation(required, root);
  const approved = manifest.verifyClientAttestation(required, attestation);
  assert.equal(approved.approved, true);
  assert.equal(approved.fileCount, 1);
  assert.throws(() => manifest.verifyClientAttestation(required, { ...attestation, revision: "stale" }), /revision/, "Stale client revision was approved");
  assert.throws(() => manifest.verifyClientAttestation(required, { ...attestation, files: [{ ...file, sha256: "0".repeat(64) }] }), /does not match/, "Incorrect client hash was approved");
  fs.writeFileSync(local, "tampered", "utf8");
  assert.throws(() => manifest.createClientAttestation(required, root), /not installed exactly/, "Client attested without hashing installed files");
  console.log("Client manifest admission: OK");
} finally { fs.rmSync(root, { recursive: true, force: true }); }
