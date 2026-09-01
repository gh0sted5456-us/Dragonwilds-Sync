from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import recommendation_feeds as feeds


def test_default_feed_identity_and_target_discrimination() -> None:
    result = feeds.builtin_recommendations()
    assert result["name"] == "Dragonwilds Sync Recommended Mods"
    assert result["source_url"] == feeds.OFFICIAL_FEED_URL
    assert result["mods"]
    assert any("client" in row.get("targets", []) for row in result["mods"])
    assert any("server" in row.get("targets", []) for row in result["mods"])


def test_normalize_preserves_public_art_and_opt_in_download() -> None:
    row = feeds.normalize_mod({
        "name": "Example",
        "page_url": "https://github.com/example/example/releases/tag/v1",
        "targets": ["CLIENT", "SERVER"],
        "banner_url": "https://raw.githubusercontent.com/example/example/main/banner.png",
        "download_url": "https://github.com/example/example/releases/download/v1/example.zip",
        "mod_type": "ue4ss",
    }, source_name="Dragonwilds Sync Recommended Mods", source_url=feeds.OFFICIAL_FEED_URL)
    assert row is not None
    assert row["targets"] == ["client", "server"]
    assert row["side"] == "CLIENT/SERVER"
    assert row["provider"] == "github"
    assert row["artwork_url"].endswith("banner.png")
    assert row["install_capable"] is True
    assert row["download_url"].endswith("example.zip")


def test_hidden_runtime_never_becomes_a_recommendation() -> None:
    for name in ("DragonLink", "RSDW Toolkit", "RSDWTools", "RSDWDevKit", "RuneSchema"):
        row = feeds.normalize_mod({
            "name": name,
            "page_url": f"https://github.com/example/{name.replace(' ', '-')}",
            "targets": ["client", "server"],
        }, source_name="Test", source_url="https://example.invalid/feed.json")
        assert row is None, f"managed infrastructure leaked into Recommended Mods: {name}"


def test_nexus_page_artwork_is_public_metadata_only() -> None:
    body = b'''<html><head>
      <meta property="og:image" content="https://staticdelivery.nexusmods.com/example.jpg">
      <meta property="og:description" content="Public description">
    </head></html>'''

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self, _limit): return body

    with mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as opened:
        meta = feeds._public_page_metadata("https://www.nexusmods.com/runescapedragonwilds/mods/450")
    assert meta["artwork_url"] == "https://staticdelivery.nexusmods.com/example.jpg"
    assert meta["page_description"] == "Public description"
    request = opened.call_args.args[0]
    # No account cookies/API token/authorization are supplied by this scraper.
    headers = {key.casefold(): value for key, value in request.header_items()}
    assert "authorization" not in headers
    assert "cookie" not in headers


def test_invalid_direct_download_is_not_install_capable() -> None:
    row = feeds.normalize_mod({
        "name": "Example",
        "page_url": "https://www.nexusmods.com/runescapedragonwilds/mods/450",
        "targets": ["client"],
        "download_url": "file:///tmp/example.zip",
    }, source_name="Test", source_url="https://example.invalid/feed.json")
    assert row is not None
    assert row["download_url"] == ""
    assert row["install_capable"] is False


if __name__ == "__main__":
    test_default_feed_identity_and_target_discrimination()
    test_normalize_preserves_public_art_and_opt_in_download()
    test_hidden_runtime_never_becomes_a_recommendation()
    test_nexus_page_artwork_is_public_metadata_only()
    test_invalid_direct_download_is_not_install_capable()
    print("recommendation feed contract: PASS")
