import { NextResponse } from "next/server";
const discovery = require("@/lib/sync/discovery");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req) {
  try {
    const body = await req.json();
    const address = String(body.address || "").trim();
    const worlds = !address || address === "255.255.255.255"
      ? await discovery.probe("255.255.255.255", body)
      : await discovery.probeDirect(address, body);
    return NextResponse.json({ ok: true, worlds });
  } catch (e) { return NextResponse.json({ ok: false, error: e.message }, { status: 400 }); }
}
