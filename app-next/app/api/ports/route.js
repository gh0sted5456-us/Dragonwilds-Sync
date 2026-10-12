import { NextResponse } from "next/server";
const { suggestPorts, isPortFree } = require("@/lib/ports");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  const ports = suggestPorts();
  const restFree = await isPortFree(ports.rest_api_port);
  return NextResponse.json({ ok: true, ports, restFree });
}
