import { NextResponse } from "next/server";
const { publicIPv4 } = require("@/lib/netinfo");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  const address = await publicIPv4();
  return NextResponse.json({ ok: true, address, reachable: null, source: "ipify" });
}
