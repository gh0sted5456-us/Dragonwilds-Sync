// Presentation-only route metadata. No game inspection or background services.
const SETTINGS_SECTIONS = ["tools", "appearance", "server", "integrations", "updates", "backups", "desktop", "system"];

function readSettingsSection(search = "") {
  const section = new URLSearchParams(search).get("section");
  return SETTINGS_SECTIONS.includes(section) ? section : null;
}

function settingsSectionUrl(currentUrl, section) {
  const url = new URL(currentUrl, "http://rsdw.local");
  if (SETTINGS_SECTIONS.includes(section)) url.searchParams.set("section", section);
  else url.searchParams.delete("section");
  return `${url.pathname}${url.search}${url.hash}`;
}

function workspaceTrail(pathname) {
  if (pathname === "/host" || pathname.startsWith("/worlds/") || (pathname.startsWith("/profiles/") && pathname.endsWith("/server"))) return { area: "Host", href: "/host", label: pathname === "/host" ? "Hosting workspace" : "Server workspace" };
  if (pathname.startsWith("/profiles/")) return { area: "Worlds", href: "/", label: "World profile" };
  if (pathname === "/profile") return { area: "Worlds", href: "/", label: "Player identity" };
  if (pathname.startsWith("/downloads")) return { area: "Downloads", href: "/downloads", label: "Transfer center" };
  if (pathname.startsWith("/socials")) return { area: "Community", href: "/socials", label: "Discover & connect" };
  const tools = { "/setup": "Application Setup", "/save-cleaner": "Save tools", "/remote-access": "Sync access", "/usage": "Activity" };
  if (tools[pathname]) return { area: "Settings", href: "/settings?section=tools", label: tools[pathname] };
  if (pathname.startsWith("/settings")) return { area: "Settings", href: "/settings", label: "Launcher preferences" };
  return { area: "Worlds", href: "/", label: "Your library" };
}

module.exports = { SETTINGS_SECTIONS, readSettingsSection, settingsSectionUrl, workspaceTrail };
