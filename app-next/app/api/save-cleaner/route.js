import { NextResponse } from "next/server";
const remoteauth = require("@/lib/remoteauth");
const cleaner = require("@/lib/save-cleaner");
const jobs = require("@/lib/jobs");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(req) {
  if (!remoteauth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  try {
    const url = new URL(req.url);
    const jobId = url.searchParams.get("jobId");
    if (jobId) {
      const job = jobs.getJob(jobId);
      if (!job) throw new Error("Save cleaner job was not found");
      return NextResponse.json({ ok: true, job });
    }
    const kind = url.searchParams.get("kind") || "player";
    const catalog = cleaner.readCachedCatalog();
    return NextResponse.json({
      ok: true,
      candidates: cleaner.listCandidates(kind),
      catalog: catalog ? {
        version: catalog.version, generatedAt: catalog.generatedAt, fetchedAt: catalog.fetchedAt,
        source: catalog.source, counts: { items: catalog.items.length, recipes: catalog.recipes.length, quests: catalog.quests.length },
      } : null,
    });
  } catch (error) { return NextResponse.json({ ok: false, error: error.message }, { status: 400 }); }
}

export async function POST(req) {
  if (!remoteauth.requireAdmin(req)) return NextResponse.json({ ok: false, error: "Administrator access required." }, { status: 403 });
  try {
    const body = await req.json();
    if (body.action === "preview") return NextResponse.json({ ok: true, jobId: cleaner.startPreview(body.kind, body.path) });
    if (body.action === "clean") return NextResponse.json({ ok: true, jobId: cleaner.startClean(body.previewId) });
    throw new Error("Unsupported save cleaner action");
  } catch (error) { return NextResponse.json({ ok: false, error: error.message }, { status: 400 }); }
}
