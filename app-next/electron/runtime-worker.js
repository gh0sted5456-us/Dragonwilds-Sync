const { parentPort, workerData } = require("worker_threads");
const { materializeRuntime } = require("./stable-runtime");

try {
  const root = materializeRuntime(workerData.source, workerData.dataDirectory);
  parentPort.postMessage({ root });
} catch (error) { parentPort.postMessage({ error: error.message || String(error) }); }
