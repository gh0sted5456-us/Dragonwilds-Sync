const logs = require("@/lib/log-api");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export async function GET(req, { params }) { return logs.handleRequest(req, params.id, "server", "view"); }
