const fs = require("fs");

// Windows scanners/editors can briefly hold a directory after its last write.
// Retry only lock-related errors; never overwrite an occupied destination.
async function renameWithRetry(from, to, { rename = fs.promises.rename, wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)), attempts = 6 } = {}) {
  for (let attempt = 0; ; attempt++) {
    try { await rename(from, to); return; }
    catch (error) {
      if (!["EPERM", "EACCES", "EBUSY"].includes(error.code) || attempt + 1 >= attempts) throw error;
      await wait(Math.min(50 * (2 ** attempt), 400));
    }
  }
}
module.exports = { renameWithRetry };
