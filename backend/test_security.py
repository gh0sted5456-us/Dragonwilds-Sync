from __future__ import annotations

import tempfile
from pathlib import Path

from security_policy import direct_policy_match, merge_access_policies, normalize_access_policy, trusted_ip_match
from security_scanner import defender_scan, defender_status


def main():
    policy = normalize_access_policy({
        "trusted_ips": ["192.168.50.22", "2001:db8::/64", "invalid"],
        "blocked_ips": ["203.0.113.8", "198.51.100.7/24", "not-a-range"],
        "blocked_profile_ids": ["profile-luke", "profile-luke", ""],
        "blocked_countries": ["us", "DE", "bad"],
        "blocked_regions": ["EU", "na", "XX"],
        "blocked_vpn_providers": ["nordvpn", "protonvpn", "unknown"],
        "vpn_provider_ranges": {"nordvpn": ["192.0.2.0/24"]},
    })
    assert "203.0.113.8/32" in policy["blocked_ips"]
    assert "198.51.100.0/24" in policy["blocked_ips"]
    assert policy["blocked_countries"] == ["US", "DE"]
    assert policy["blocked_regions"] == ["EU", "NA"]
    assert policy["blocked_vpn_providers"] == ["nordvpn", "protonvpn"]
    assert policy["blocked_profile_ids"] == ["profile-luke"]
    assert trusted_ip_match("192.168.50.22", policy)[0]
    assert trusted_ip_match("2001:db8::42", policy)[0]
    assert not trusted_ip_match("192.168.50.23", policy)[0]

    merged = merge_access_policies(
        {"trusted_ips": ["10.2.0.0/16"], "blocked_ips": ["10.1.0.0/16"], "blocked_regions": ["EU"], "blocked_profile_ids": ["global-profile"]},
        {"trusted_ips": ["203.0.114.9"], "blocked_ips": ["203.0.113.0/24"], "blocked_countries": ["CA"], "blocked_profile_ids": ["world-profile"],
         "blocked_vpn_providers": ["nordvpn"], "vpn_provider_ranges": {"nordvpn": ["192.0.2.0/24"]}},
    )
    assert direct_policy_match("10.1.2.3", merged)[0]
    assert direct_policy_match("203.0.113.55", merged)[0]
    matched, reason = direct_policy_match("192.0.2.10", merged)
    assert matched and "NordVPN" in reason
    assert not direct_policy_match("8.8.8.8", merged)[0]
    assert merged["blocked_profile_ids"] == ["global-profile", "world-profile"]
    assert trusted_ip_match("10.2.5.6", merged)[0]
    assert trusted_ip_match("203.0.114.9", merged)[0]

    status = defender_status()
    assert "available" in status and "enabled" in status
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "safe.txt"
        path.write_text("Dragonwilds Sync security smoke test", encoding="utf-8")
        review = defender_scan(path)
        assert "blocked" in review and "skipped" in review and "clean" in review
        if not status.get("enabled"):
            assert review.get("blocked") is False

    print("security tests passed")


if __name__ == "__main__":
    main()
