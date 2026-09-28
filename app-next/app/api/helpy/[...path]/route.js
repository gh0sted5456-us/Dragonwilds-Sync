import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const RAW_ROOT = "https://raw.githubusercontent.com/gh0sted5456-us/Dragonwilds-Sync/codex/super-experimental/";
const MIME = {
  html: "text/html; charset=utf-8",
  css: "text/css; charset=utf-8",
  js: "text/javascript; charset=utf-8",
  json: "application/json; charset=utf-8",
  svg: "image/svg+xml",
  png: "image/png",
  webp: "image/webp",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  gif: "image/gif",
  ico: "image/x-icon",
  txt: "text/plain; charset=utf-8",
  md: "text/markdown; charset=utf-8",
};

function repoPath(parts) {
  const clean = (parts || []).map((part) => decodeURIComponent(part)).filter(Boolean);
  if (!clean.length) return "website/helpy.html";
  if (clean.some((part) => part === ".." || part.includes("\\") || part.includes(":"))) {
    throw new Error("invalid path");
  }
  const joined = clean.join("/");
  if (joined.startsWith("help/") || joined.startsWith("renderer/")) return joined;
  return `website/${joined}`;
}

export async function GET(_req, { params }) {
  try {
    const target = repoPath(params.path);
    const upstream = await fetch(RAW_ROOT + target, {
      cache: "no-store",
      headers: { "user-agent": "RSDW-Sync-Helpy/1.0" },
    });
    if (!upstream.ok) {
      return new NextResponse("Helpy resource unavailable", { status: upstream.status });
    }

    const body = await upstream.arrayBuffer();
    const ext = target.split(".").pop().toLowerCase();
    return new NextResponse(body, {
      headers: {
        "content-type": MIME[ext] || upstream.headers.get("content-type") || "application/octet-stream",
        "cache-control": "no-store, max-age=0",
        "x-rsdw-helpy-source": "github:codex/super-experimental",
      },
    });
  } catch {
    return new NextResponse("Invalid Helpy resource path", { status: 400 });
  }
}
