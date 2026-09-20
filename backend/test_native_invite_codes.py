import tempfile
import time
import unittest
from pathlib import Path

from native_invite_codes import begin, clear, current, observe, public_status, scan_logs


class NativeInviteCodeTests(unittest.TestCase):
    def tearDown(self):
        clear("world", "coop")
        clear("server", "dedicated")

    def test_requires_explicit_context_and_normalizes_code(self):
        started = begin("world", "coop")
        self.assertFalse(observe("world", "coop", "Build 1ABC-234D", source="test", session_started_at=started))
        record = observe("world", "coop", "Invite Code: ab1c-23de", source="game", session_started_at=started)
        self.assertEqual(record["code"], "AB1C-23DE")
        self.assertTrue(public_status(record, hosting=True)["available"])

    def test_session_baseline_rejects_old_log_content(self):
        with tempfile.TemporaryDirectory() as folder:
            logs = Path(folder)
            log = logs / "RSDragonwilds.log"
            log.write_text("Invite Code: OLD1-CODE\n", encoding="utf-8")
            started = begin("world", "coop", logs)
            self.assertFalse(scan_logs("world", "coop", logs, session_started_at=started))
            with log.open("a", encoding="utf-8") as stream:
                stream.write("Online session registered\nInvite Code = NEW2-CODE\n")
            record = scan_logs("world", "coop", logs, session_started_at=started)
            self.assertEqual(record["code"], "NEW2-CODE")

    def test_old_observation_and_clear_do_not_cross_sessions(self):
        started = time.time()
        self.assertFalse(observe("server", "dedicated", "Join Code: ABCD-1234", source="old",
                                 observed_at=started - 30, session_started_at=started))
        observe("server", "dedicated", "Join Code: ABCD-1234", source="stdout",
                observed_at=started, session_started_at=started)
        self.assertEqual(current("server", "dedicated", session_started_at=started)["code"], "ABCD-1234")
        clear("server", "dedicated")
        self.assertFalse(current("server", "dedicated", session_started_at=started))


if __name__ == "__main__":
    unittest.main()
