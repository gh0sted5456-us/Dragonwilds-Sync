import { NextResponse } from "next/server";
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json({ ok: true, token: process.env.APP_MANAGER_INSTANCE_TOKEN || "development", port: Number(process.env.APP_MANAGER_PORT || 4317) });
}
