import unittest
from pathlib import Path

from networking import (FIREWALL_GROUP, RULE_NAMES, effective_game_port,
                        firewall_spec, layer_status, manual_router_rule,
                        normalize_publication_mode, valid_port)


class NetworkingPolicyTests(unittest.TestCase):
    def test_instance_game_ports_increment_without_changing_protocol(self):
        self.assertEqual([effective_game_port(i) for i in range(1, 5)], [7777, 7778, 7779, 7780])
        self.assertEqual(manual_router_rule("dedicated_game", effective_game_port(3), "192.168.1.50")["protocol"], "UDP")

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
