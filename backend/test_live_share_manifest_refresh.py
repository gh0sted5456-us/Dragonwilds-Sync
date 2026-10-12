"""Regression coverage for republishing mods through a live runtime worker."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    source = (ROOT / "backend" / "runtime_worker.py").read_text(encoding="utf-8")
    live_branch = source[source.index('if existing.get("serving"):'):source.index("published = engine.publish(self.profile_id)", source.index('if existing.get("serving"):')) + len("published = engine.publish(self.profile_id)")]
    assert "engine.publish(self.profile_id)" in live_branch
    assert '"manifest_refreshed": True' in source
    assert "FILE_SHARE_MANIFEST_REFRESHED" in source
    assert "manifest_file_count" in source
    print("live worker manifest refresh regression passed")


if __name__ == "__main__":
    main()
