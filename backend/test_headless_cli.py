from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

import headless_cli


class FakeLegacy:
    SINGLEPLAYER_ID = "singleplayer"

    def __init__(self):
        self.state = {"server": {"active_world_id": "srv-1"}, "client": {"worlds": []}}

    def list_server_profiles(self):
        return [
            {"id": "srv-1", "name": "Effing Desync"},
            {"id": "srv-2", "name": "Second World"},
        ]

    def load_state(self):
        return self.state

    def load_singleplayer_profile(self, _profile_id):
        return {}


class HeadlessCliTests(unittest.TestCase):
    def setUp(self):
        self.legacy = FakeLegacy()
        self.calls = []

    def handle(self, method, params):
        self.calls.append((method, dict(params)))
        if method == "quick.status":
            return {
                "profile_id": params["profile_id"], "world_name": "Effing Desync",
                "active": True, "sync": {"serving": True}, "runtime": {"running": True},
            }
        if method == "quick.console.get":
            return {"entries": [{"ts": 1, "source": "server", "message": "ready"}]}
        return {"ok": True}

    def test_status_defaults_to_active_server_profile(self):
        output = io.StringIO()
        with redirect_stdout(output):
            rc = headless_cli.run(self.handle, self.legacy, ["status", "--json"])
        self.assertEqual(rc, 0)
        self.assertIn('"profile_id": "srv-1"', output.getvalue())
        self.assertEqual(self.calls[0][0], "quick.status")

    def test_exact_case_insensitive_name_resolves_to_id(self):
        output = io.StringIO()
        with redirect_stdout(output):
            rc = headless_cli.run(self.handle, self.legacy, ["status", "--profile", "effing desync"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.calls[0][1]["profile_id"], "srv-1")

    def test_stop_uses_same_quick_rpc_as_electron(self):
        output = io.StringIO()
        with redirect_stdout(output):
            rc = headless_cli.run(self.handle, self.legacy, ["stop", "--profile", "srv-2", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.calls[0], ("quick.stop", {"profile_id": "srv-2", "id": "srv-2", "mode": "server"}))

    def test_logs_do_not_stop_runtime(self):
        output = io.StringIO()
        with redirect_stdout(output):
            rc = headless_cli.run(self.handle, self.legacy, ["logs", "--profile", "srv-1"])
        self.assertEqual(rc, 0)
        self.assertEqual([method for method, _ in self.calls], ["quick.console.get"])


if __name__ == "__main__":
    unittest.main()

