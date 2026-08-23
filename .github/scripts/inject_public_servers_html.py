from __future__ import annotations

import argparse
import html
import json
import time
from pathlib import Path

START = "<!-- PUBLIC_SERVER_SNAPSHOT_START -->"
END = "<!-- PUBLIC_SERVER_SNAPSHOT_END -->"
PAGE_SIZE = 10
SYNC_FORGET_SECONDS = 6 * 60 * 60
ONLINE_STATUSES = {"online", "starting", "maintenance"}


def esc(value: object) -> str:
    return html.escape(str(value or "").strip(), quote=True)


def intish(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def timestamp_seconds(value: object) -> int:
    try:
        number = int(float(value or 0))
    except (TypeError, ValueError):
        return 0
    return number // 1000 if number > 1_000_000_000_000 else number


def is_sync(row: dict) -> bool:
    return bool(row.get("is_sync_world") or row.get("directory_source") == "dragonwilds-sync")


def is_online(row: dict) -> bool:
    return str(row.get("status") or "").strip().lower() in ONLINE_STATUSES


def is_visible(row: dict, now: int) -> bool:
    # The website is a Dragonwilds Sync World directory, not a generic
    # Dragonwilds server browser. Third-party/public observations are excluded.
    if not is_sync(row):
        return False
    seen = timestamp_seconds(row.get("last_seen"))
    return bool(seen and now - seen <= SYNC_FORGET_SECONDS)


def sort_key(row: dict) -> tuple:
    players = row.get("players") if isinstance(row.get("players"), dict) else {}
    return (
        -int(is_online(row)),
        -timestamp_seconds(row.get("last_seen")),
        -intish(players.get("current") if players else row.get("players_current")),
        str(row.get("world_name") or row.get("name") or "").casefold(),
    )


def world_markup(row: dict) -> str:
    players = row.get("players") if isinstance(row.get("players"), dict) else {}
    name = esc(row.get("world_name") or row.get("name") or "Unnamed World")
    description = esc(row.get("description") or "Public Dragonwilds Sync World")
    source = esc(row.get("source_name") or "Dragonwilds Sync")
    status = str(row.get("status") or "offline").strip().lower()
    status_label = esc(status.upper())
    region = esc(row.get("country_name") or row.get("region") or row.get("country_code") or "Unknown")
    version = esc(row.get("version") or "Build unknown")
    current = intish(players.get("current") if players else row.get("players_current"))
    maximum = intish(players.get("max") if players else row.get("players_max"))
    tags = row.get("tags") if isinstance(row.get("tags"), list) else []
    tag_markup = "".join(f'<span>{esc(tag)}</span>' for tag in tags[:6] if str(tag or "").strip())
    online_class = "online" if status in ONLINE_STATUSES else "offline"

    return f'''<article class="directory-static-world" data-static-public-world="1">
  <div class="directory-static-main">
    <div class="directory-static-title"><h3>{name}</h3><span class="directory-static-kind sync">SYNC WORLD</span></div>
    <p>{description}</p>
    <div class="directory-static-tags">{tag_markup}</div>
  </div>
  <div class="directory-static-metrics">
    <span class="directory-static-status {online_class}">{status_label}</span>
    <span><small>Region</small><b>{region}</b></span>
    <span><small>Players</small><b>{current} / {maximum if maximum else '—'}</b></span>
    <span><small>Build</small><b>{version}</b></span>
  </div>
  <div class="directory-static-source"><small>Source</small><strong>{source}</strong></div>
</article>'''


def inject(snapshot: Path, page: Path) -> None:
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    worlds = payload.get("worlds") if isinstance(payload, dict) else None
    rows = [row for row in (worlds or []) if isinstance(row, dict)] if isinstance(worlds, list) else []
    if not rows:
        raise SystemExit(f"Public server snapshot is empty: {snapshot}")

    now = int(time.time())
    visible_rows = sorted((row for row in rows if is_visible(row, now)), key=sort_key)
    if not visible_rows:
        raise SystemExit(f"Public server snapshot has no currently visible Dragonwilds Sync Worlds: {snapshot}")
    first_page = visible_rows[:PAGE_SIZE]

    source = page.read_text(encoding="utf-8")
    start = source.find(START)
    end = source.find(END)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit(f"Snapshot markers missing from {page}")

    summary = (
        f'<div class="directory-static-summary" data-static-public-summary="1">'
        f'<strong>Showing the first {len(first_page):,} of {len(visible_rows):,} public Sync Worlds.</strong>'
        f'<span>Only Worlds broadcasting through Dragonwilds Sync are shown. The browser hydrates the full Sync roster and paginates it at {PAGE_SIZE} Worlds per page.</span>'
        f'</div>'
    )
    body = summary + "\n" + "\n".join(world_markup(row) for row in first_page)
    rendered = source[: start + len(START)] + "\n" + body + "\n" + source[end:]
    page.write_text(rendered, encoding="utf-8")
    print(f"Baked {len(first_page)} of {len(visible_rows)} visible Dragonwilds Sync World records directly into {page}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("page", type=Path)
    args = parser.parse_args()
    inject(args.snapshot, args.page)


if __name__ == "__main__":
    main()
