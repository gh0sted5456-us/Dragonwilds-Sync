const { handleAppearance } = require("@/lib/appearance-api");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export async function GET(req, { params }) { return handleAppearance(req, "image", params.id); }
