const { jobsResponse } = require("@/lib/jobs-response");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Downloads tray polls this for all active + recently-finished install/update jobs.
export async function GET(req) {
  return jobsResponse(req);
}
