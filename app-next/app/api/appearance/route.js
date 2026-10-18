const { handleAppearance } = require("@/lib/appearance-api");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export async function GET(req) { return handleAppearance(req, "read"); }
export async function POST(req) { return handleAppearance(req, "save"); }
