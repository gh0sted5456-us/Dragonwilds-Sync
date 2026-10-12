import { NextResponse } from "next/server";
const socialMods = require("@/lib/social-mods");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req) {
  try {
    const params = new URL(req.url).searchParams;
    const result = await socialMods.searchMods({
      query: params.get("q"),
      author: params.get("author"),
      source: params.get("source"),
      sort: params.get("sort"),
      page: params.get("page"),
      pageSize: params.get("pageSize"),
    });
    return NextResponse.json({ ok: true, ...result });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  }
}
