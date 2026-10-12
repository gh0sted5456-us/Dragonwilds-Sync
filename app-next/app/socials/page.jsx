"use client";
import { useEffect, useState } from "react";
import { Icon, api, toast } from "@/components/ui";

const DISCORD = "https://discord.gg/bQrVAbA7UC";
const PAGE_SIZE = 24;
const PROVIDERS = {
  nexus: { name: "Nexus Mods", browse: "https://www.nexusmods.com/games/runescapedragonwilds/mods?sort=downloads", color: "#d98f40" },
  curseforge: { name: "CurseForge", browse: "https://www.curseforge.com/runescape-dragonwilds", color: "#f16436" },
};

export default function SocialsPage() {
  const [catalog, setCatalog] = useState(null);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [community, setCommunity] = useState(null);
  const [query, setQuery] = useState("");
  const [author, setAuthor] = useState("");
  const [source, setSource] = useState("all");
  const [sort, setSort] = useState("popular");
  const [page, setPage] = useState(1);
  useEffect(() => {
    api("/api/socials/discord").then((result) => setCommunity(result.community)).catch(() => {});
  }, []);
  useEffect(() => setPage(1), [query, author, source, sort]);
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      setLoadingCatalog(true);
      try {
        const params = new URLSearchParams({ q: query.trim(), author: author.trim(), source, sort, page: String(page), pageSize: String(PAGE_SIZE) });
        const result = await api(`/api/socials/mods?${params}`);
        if (!cancelled) setCatalog(result);
      } catch (error) { if (!cancelled) toast(error.message, "error"); }
      finally { if (!cancelled) setLoadingCatalog(false); }
    }, 320);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, author, source, sort, page]);
  const visible = catalog?.items || [];
  const pages = catalog?.pages || 1;
  const currentPage = Math.min(page, pages);

  const openExternal = async (url) => {
    try {
      if (window.desktop?.openExternal) await window.desktop.openExternal(url);
      else window.open(url, "_blank", "noopener,noreferrer");
    } catch (error) { toast(error.message || "Could not open that link.", "error"); }
  };

  return <div className="socials-page">
    <section className="socials-hero">
      <img src="/rsdw/socials/discord-community.webp" alt="Dragonwilds Creative and Sharing Hub" />
      <div className="socials-hero-fade" />
      <div className="socials-hero-copy">
        <span className="eyebrow">RSDW COMMUNITY</span>
        <h1>Build, share, and explore Ashenfall together.</h1>
        <p>Meet World hosts, mod authors, builders, and players in the Dragonwilds Creative and Sharing Hub.</p>
        <button className="btn btn-primary" onClick={() => openExternal(DISCORD)}><DiscordIcon /> Join Discord</button>
      </div>
    </section>

    <DiscordCommunity community={community} onJoin={() => openExternal(DISCORD)} />

    <div className="socials-heading"><div><span className="eyebrow">COMMUNITY DISCOVERY</span><h2>Search Dragonwilds Mods</h2></div><p className="subtle">Search projects and authors across the connected CurseForge catalog and Nexus discovery feeds, then open the official listing in your default browser.</p></div>
    <section className="panel socials-catalog">
      <div className="socials-filters">
        <label className="socials-search"><Icon name="search" size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search mod name or feature" aria-label="Search Dragonwilds mods" /></label>
        <label className="socials-search"><Icon name="users" size={17} /><input value={author} onChange={(event) => setAuthor(event.target.value)} placeholder="Search by author name" aria-label="Search mods by author name" /></label>
        <div className="socials-source-filter" role="group" aria-label="Mod provider">
          <button className={source === "all" ? "active" : ""} onClick={() => setSource("all")}>All</button>
          {Object.entries(PROVIDERS).map(([key, meta]) => <button key={key} className={source === key ? "active" : ""} onClick={() => setSource(key)}><ProviderIcon provider={key} />{meta.name}</button>)}
        </div>
        <select className="input" value={sort} onChange={(event) => setSort(event.target.value)} aria-label="Sort mods"><option value="popular">Most Popular</option><option value="recent">Most Recent</option><option value="name">Name A–Z</option></select>
      </div>
      <div className="socials-provider-links">
        {Object.entries(PROVIDERS).map(([key, meta]) => <button key={key} className="btn btn-ghost" onClick={() => openExternal(catalog?.providers?.[key]?.searchUrl || meta.browse)}><ProviderIcon provider={key} /> {query || author ? `Search all on ${meta.name}` : `Browse ${meta.name}`}</button>)}
      </div>
      {catalog?.providers && <div className="socials-catalog-status">{Object.entries(catalog.providers).map(([provider, data]) => <div key={provider}><ProviderIcon provider={provider} /><strong>{PROVIDERS[provider].name}</strong><span className={`statdot ${data.live ? "bg-running" : "bg-stopped"}`} /><span>{data.fullCatalog ? `${Number(data.total || 0).toLocaleString()} live results` : data.note}</span>{!data.live && <button className="btn btn-ghost" onClick={() => { window.location.href = "/settings?section=integrations"; }}>Connect</button>}</div>)}</div>}
      <div className="socials-mod-grid">
        {visible.map((mod, index) => <ModCard key={`${mod.provider}:${mod.id}`} mod={mod} rank={(currentPage - 1) * PAGE_SIZE + index + 1} onOpen={openExternal} />)}
        {loadingCatalog && <div className="subtle socials-empty">Searching Dragonwilds catalogs…</div>}
        {!loadingCatalog && catalog && !visible.length && <div className="subtle socials-empty">No projects match those filters. Connect the provider in Settings or use its official catalog button above.</div>}
      </div>
      <footer className="socials-pagination"><span>{Number(catalog?.total || 0).toLocaleString()} catalog result{catalog?.total === 1 ? "" : "s"} · Page {currentPage} of {pages}</span><div><button className="btn btn-ghost" disabled={loadingCatalog || currentPage <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>Previous</button><button className="btn btn-ghost" disabled={loadingCatalog || currentPage >= pages} onClick={() => setPage((value) => Math.min(pages, value + 1))}>Next</button></div></footer>
    </section>
  </div>;
}

function DiscordCommunity({ community, onJoin }) {
  return <section className="panel discord-community">
    <div className="discord-community-summary"><div className="discord-community-mark"><DiscordIcon /></div><div><span className="eyebrow">LIVE COMMUNITY</span><h2>{community?.guild?.name || "Dragonwilds Creative and Sharing Hub"}</h2></div><div className="discord-community-counts"><strong>{community ? community.online.toLocaleString() : "—"}<small>online</small></strong><strong>{community ? community.members.toLocaleString() : "—"}<small>members</small></strong></div></div>
    <div className="discord-community-columns">
      <Roster title="Active now" members={community?.active || []} empty={community ? (community.widgetEnabled ? "No public presences are visible right now." : "Enable the Discord server widget to show active members here.") : "Loading Discord activity…"} />
      <Roster title="Community team" members={community?.moderators || []} empty={community?.moderatorNote || "Loading community team…"} />
    </div>
    <div className="discord-community-footer"><span className="subtle">Presence is refreshed from Discord when this page opens.</span><button className="btn btn-primary" onClick={onJoin}><DiscordIcon /> Open Discord</button></div>
  </section>;
}

function Roster({ title, members, empty }) {
  return <div><h3>{title}</h3>{members.length ? <div className="discord-roster">{members.map((member) => <div key={member.id} className="discord-person">{member.avatar ? <img src={member.avatar} alt="" /> : <span>{member.name.slice(0, 1)}</span>}<div><strong>{member.name}</strong><small>{member.role || member.status || "online"}</small></div></div>)}</div> : <p className="subtle">{empty}</p>}</div>;
}

function ModCard({ mod, rank, onOpen }) {
  const meta = PROVIDERS[mod.provider];
  return <article className="socials-mod-card" style={{ "--provider": meta.color }}>
    <div className="socials-mod-card-head"><span className="socials-mod-rank">{mod.image ? <img src={mod.image} alt="" /> : String(rank).padStart(2, "0")}</span><span className="socials-provider-chip"><ProviderIcon provider={mod.provider} />{meta.name}</span></div>
    <h3>{mod.name}</h3><small>{mod.author || meta.name}</small><p>{mod.summary || "Open the provider listing for details, requirements, and files."}</p>
    <footer><span>{formatDownloads(mod.downloads)}{mod.updatedAt ? ` · Updated ${formatDate(mod.updatedAt)}` : ""}</span><button className="btn btn-ghost" onClick={() => onOpen(mod.url)}>View mod <Icon name="upload" size={14} /></button></footer>
  </article>;
}

function ProviderIcon({ provider }) {
  if (provider === "nexus") return <img className="provider-icon" src="/rsdw/providers/nexusmods.svg" alt="Nexus Mods" />;
  return <img className="provider-icon" src="/rsdw/providers/curseforge.svg" alt="CurseForge" />;
}

function formatDownloads(value) {
  const count = Number(value || 0);
  if (!count) return "Provider listing";
  return `${Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(count)} downloads`;
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "recently" : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(date);
}

function DiscordIcon() {
  return <svg aria-hidden viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M19.5 5.3A16.3 16.3 0 0 0 15.4 4l-.5 1a15 15 0 0 0-5.8 0l-.5-1a16.3 16.3 0 0 0-4.1 1.3C1.9 9.1 1.2 12.8 1.5 16.4A16.6 16.6 0 0 0 6.6 19l1.2-1.6a10.5 10.5 0 0 1-1.8-.9l.4-.3c3.5 1.6 7.7 1.6 11.2 0l.4.3c-.6.4-1.2.7-1.8.9l1.2 1.6a16.6 16.6 0 0 0 5.1-2.6c.4-4.2-.7-7.8-3-11.1zM8.6 14.5c-1 0-1.9-1-1.9-2.2s.8-2.2 1.9-2.2 1.9 1 1.9 2.2-.9 2.2-1.9 2.2zm6.8 0c-1 0-1.9-1-1.9-2.2s.8-2.2 1.9-2.2 1.9 1 1.9 2.2-.9 2.2-1.9 2.2z" /></svg>;
}
