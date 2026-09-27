import { NextResponse } from "next/server";

// Page-level redirect for Remote Access — defense-in-depth on top of the authoritative
// per-route API guard (lib/remoteauth.authorize). This runs in the edge runtime, so it can
// only read cookies + env, never the DB. It therefore gates purely on the admin token:
//
//   • No DWSM_ADMIN_TOKEN configured (plain loopback dev, or the desktop app never armed
//     Remote Access this launch) → do nothing. The server is loopback-only anyway.
//   • Token configured → a navigation without the matching `dwsm_admin` cookie is a remote
//     guest; send page loads to /remote instead of the admin shell. API calls are left to
//     answer so their own guard returns a proper 403 (and disabled/revoked codes are caught
//     there, which the edge can't check).
export function middleware(req) {
  const token = process.env.DWSM_ADMIN_TOKEN;
  if (!token) return NextResponse.next();

  const { pathname } = req.nextUrl;
  if (
    pathname.startsWith("/remote") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/locales") ||
    pathname === "/icon.png" ||
    pathname === "/favicon.ico"
  ) return NextResponse.next();

  if (req.cookies.get("dwsm_admin")?.value === token) return NextResponse.next();

  const url = req.nextUrl.clone();
  url.pathname = "/remote";
  url.search = "";
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
