from __future__ import annotations

import tempfile
import time
from pathlib import Path

import profile_store
import server_systems


def test_review_integrity_and_visibility() -> None:
    with tempfile.TemporaryDirectory() as td:
        original = server_systems.APP_DATA_DIR
        server_systems.APP_DATA_DIR = Path(td)
        try:
            entry = {
                "id": "review-1", "world_id": "world-1", "client_id": "player",
                "rating": 5, "report": "Stable and friendly", "ip_hash": "abc",
                "received_at": time.time(),
            }
            entry["integrity"] = server_systems.review_integrity(entry)
            profile = {"feedback": [entry], "hidden_review_ids": []}
            assert server_systems.review_integrity_valid(entry)
            assert server_systems.profile_rating_summary(profile) == (5.0, 1)
            assert len(server_systems.public_reviews(profile, 30)) == 1
            profile["hidden_review_ids"] = ["review-1"]
            assert server_systems.public_reviews(profile, 30) == []
            assert server_systems.profile_rating_summary(profile) == (5.0, 1), "hiding text must not rewrite stars"
            entry["rating"] = 1
            assert not server_systems.review_integrity_valid(entry)
            assert server_systems.profile_rating_summary(profile) == (0.0, 0)
        finally:
            server_systems.APP_DATA_DIR = original


def test_world_browser_contract() -> None:
    state = profile_store.default_state()
    assert state["client"]["world_browser"]["page"] == 1
    renderer = Path(__file__).parents[1].joinpath("renderer", "app-v2.js").read_text(encoding="utf-8")
    styles = Path(__file__).parents[1].joinpath("renderer", "styles.css").read_text(encoding="utf-8")
    assert "const pageSize=10" in renderer
    assert "data-private-page" in renderer and "data-server-page" in renderer
    assert "data-world-launch" in renderer and "data-world-details" in renderer
    assert "worldMenuButton(worldId" in renderer and "return '';" in renderer
    assert "openCardMenu(card" in renderer
    assert "maxlength=\"250\"" in renderer and "data-review-window" in renderer
    assert "server.feedback.visibility" in renderer
    assert "approve-character-backup" in renderer and "world.character.backup.consent" in renderer
    assert "`Player Save Backup`" not in renderer, "backup enablement must not interrupt Play with a confirmation"
    assert "24-world-browser-pagination.jpg" in renderer
    assert "25-world-ratings.jpg" in renderer
    assert "26-hosted-worlds.jpg" in renderer
    assert "Fast paginated discovery" in renderer and "Ratings and reviews" in renderer
    assert "Primary Launch/Manage actions stay visible; right-click a card" in renderer
    assert "world-community-badge" in styles and "world-rating" in styles
    assert ".world-card .card-title h3" in styles
    assert ".detail-hero .hero-main h1" in styles
    assert 'body[data-theme="light"] .context-menu button' in styles


if __name__ == "__main__":
    test_review_integrity_and_visibility()
    test_world_browser_contract()
    print("release 1.5 World browser tests passed")
