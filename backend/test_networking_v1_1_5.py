import unittest
from pathlib import Path
from unittest.mock import patch

import server_systems
from networking import (DEFAULT_SYNC_DISCOVERY_PORT, FIREWALL_GROUP, RULE_NAMES, effective_game_port,
                        firewall_spec, layer_status, manual_router_rule,
                        normalize_publication_mode, valid_port)


class NetworkingPolicyTests(unittest.TestCase):
    def test_instance_game_ports_increment_without_changing_protocol(self):
        self.assertEqual([effective_game_port(i) for i in range(1, 5)], [7777, 7778, 7779, 7780])
        self.assertEqual(manual_router_rule("dedicated_game", effective_game_port(3), "192.168.1.50")["protocol"], "UDP")
        first = firewall_spec("pc_game", 7777, program="C:/Game/client.exe", mode="local", instance_id="local-1")
        second = firewall_spec("pc_game", 7778, program="C:/Game/client.exe", mode="local", instance_id="local-2")
        self.assertNotEqual(first["display_name"], second["display_name"])

    def test_ports_are_bounded(self):
        self.assertEqual(valid_port(27051), 27051)
        with self.assertRaises(ValueError):
            valid_port(0)
        with self.assertRaises(ValueError):
            effective_game_port(10, 65530)

    def test_modes_are_mutually_exclusive_values(self):
        self.assertEqual(normalize_publication_mode("manual_forwarding", service="webhost"), "manual")
        self.assertEqual(normalize_publication_mode("automatic_upnp", service="webhost"), "upnp")
        self.assertEqual(normalize_publication_mode("cloudflare_quick", service="webhost"), "tunnel")
        with self.assertRaises(ValueError):
            normalize_publication_mode("manual+upnp", service="webhost")

    def test_public_and_lan_firewall_scopes_are_distinct(self):
        public = firewall_spec("world_sync", 27051, program="C:/Runtime/backend.exe", mode="manual", instance_id="server-1")
        local = firewall_spec("world_sync", 27051, program="C:/Runtime/backend.exe", mode="local", instance_id="server-1")
        self.assertEqual(public["group"], FIREWALL_GROUP)
        self.assertTrue(public["display_name"].startswith(RULE_NAMES["world_sync"]))
        self.assertEqual((public["profiles"], public["remote_address"]), ("Any", "Any"))
        self.assertEqual((local["profiles"], local["remote_address"]), ("Domain,Private", "LocalSubnet"))

        public_discovery = firewall_spec("sync_discovery", DEFAULT_SYNC_DISCOVERY_PORT,
                                         program="C:/Runtime/backend.exe", mode="manual")
        local_discovery = firewall_spec("sync_discovery", DEFAULT_SYNC_DISCOVERY_PORT,
                                        program="C:/Runtime/backend.exe", mode="local")
        self.assertEqual((public_discovery["protocol"], public_discovery["port"]), ("UDP", 8422))
        self.assertEqual((public_discovery["profiles"], public_discovery["remote_address"]), ("Any", "Any"))
        self.assertEqual((local_discovery["profiles"], local_discovery["remote_address"]), ("Domain,Private", "LocalSubnet"))

    def test_manual_sync_forward_includes_fixed_discovery_companion(self):
        rule = manual_router_rule("world_sync", 27051, "192.168.1.50")
        self.assertEqual(rule["protocol"], "TCP")
        self.assertEqual(rule["external_port"], 27051)
        self.assertEqual(rule["companion_rules"], [{
            "service": "Dragonwilds Sync Direct Connect discovery", "protocol": "UDP",
            "external_port": 8422, "internal_address": "192.168.1.50",
            "internal_port": 8422, "source": "Any",
            "purpose": "Allows remote Direct Connect to query every Sync World announced by this host.",
        }])
        fixed = manual_router_rule("sync_discovery", None, "192.168.1.50")
        self.assertEqual((fixed["protocol"], fixed["external_port"]), ("UDP", 8422))

    def test_host_firewall_uses_one_fixed_discovery_rule(self):
        def accepted(spec, **_kwargs):
            return {**spec, "ok": True, "changed": True}

        with patch.object(server_systems, "apply_firewall_spec", side_effect=accepted):
            result = server_systems.configure_server_firewall_ports([27051, 27052], [7777, 7778], mode="manual")
        discovery = [row for row in result["rules"] if row.get("service") == "sync_discovery"]
        transfers = [row for row in result["rules"] if row.get("service") == "world_sync"]
        self.assertEqual(result["sync_discovery_port"], 8422)
        self.assertEqual([(row["protocol"], row["port"]) for row in discovery], [("UDP", 8422)])
        self.assertEqual([(row["protocol"], row["port"]) for row in transfers], [("TCP", 27051), ("TCP", 27052)])

    def test_host_wide_firewall_covers_every_external_listener(self):
        services = [
            {"service": "pc_game", "port": 7777, "program": "C:/Game/client.exe", "mode": "local"},
            {"service": "dedicated_game", "port": 7778, "program": "C:/Server/server.exe", "mode": "manual", "instance_id": "server-2"},
            {"service": "world_sync", "port": 27051, "program": "C:/Runtime/backend.exe", "mode": "local", "instance_id": "local-1"},
            {"service": "world_sync", "port": 27051, "program": "C:/Runtime/backend.exe", "mode": "manual", "instance_id": "server-1"},
            {"service": "sync_discovery", "port": 8422, "program": "C:/Runtime/backend.exe", "mode": "manual"},
            {"service": "webhost", "port": 27080, "program": "C:/Runtime/backend.exe", "mode": "manual"},
        ]
        def accepted(spec, **_kwargs):
            return {**spec, "ok": True, "changed": True}
        with patch.object(server_systems, "apply_firewall_spec", side_effect=accepted):
            result = server_systems.configure_firewall_services(services)
        self.assertTrue(result["ok"])
        self.assertEqual(result["rule_count"], 5)
        self.assertEqual({(row["service"], row["protocol"], row["port"]) for row in result["ports"]}, {
            ("pc_game", "UDP", 7777), ("dedicated_game", "UDP", 7778),
            ("world_sync", "TCP", 27051), ("sync_discovery", "UDP", 8422),
            ("webhost", "TCP", 27080),
        })
        sync = next(row for row in result["rules"] if row["service"] == "world_sync")
        self.assertEqual((sync["mode"], sync["profiles"], sync["remote_address"]), ("manual", "Any", "Any"))

    def test_cloudflare_requires_no_public_firewall_rule(self):
        spec = firewall_spec("webhost", 27080, program="C:/Runtime/backend.exe", mode="tunnel")
        self.assertFalse(spec["required"])

    def test_public_status_requires_external_verification(self):
        self.assertFalse(layer_status(listener="running", firewall="allowed", router_method="upnp", mapping="confirmed")["public"])
        self.assertTrue(layer_status(listener="running", firewall="allowed", router_method="manual", mapping="unverified", external="reachable")["public"])

    def test_server_engine_never_bypasses_explicit_upnp_mode(self):
        source = Path(__file__).with_name("server_engine.py").read_text(encoding="utf-8")
        schedule = source.split("def _schedule_network_setup", 1)[1].split("def _remove_network_mappings", 1)[0]
        cleanup = source.split("def _remove_network_mappings", 1)[1].split("def stop_share", 1)[0]
        self.assertNotIn("try_upnp_mapping", schedule)
        self.assertIn("publication_mode", schedule)
        self.assertIn('description=f"DragonwildsSync:{profile_id[:32]}:{suffix}"', cleanup)
        self.assertNotIn('description="Dragonwilds Dedicated Server"', source)
        self.assertNotIn('description="Dragonwilds Sync World Share"', source)


if __name__ == "__main__":
    unittest.main()
