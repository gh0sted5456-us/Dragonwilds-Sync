import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import computer_profiles as profiles


defaults = profiles.normalize_computer_profile({"mode": "invalid", "server_priority": "realtime"})
assert defaults["mode"] == "automatic"
assert defaults["server_priority"] == "above_normal"
assert "realtime" not in profiles.PRIORITIES

assert profiles.recommend_computer_profile({"cpu_cores": 4, "cpu_threads": 8, "ram_total_gb": 8})["mode"] == "low_resource"
assert profiles.recommend_computer_profile({"cpu_cores": 8, "cpu_threads": 16, "ram_total_gb": 32})["mode"] == "dedicated_host"
assert profiles.recommend_computer_profile({"cpu_cores": 6, "cpu_threads": 12, "ram_total_gb": 16})["mode"] == "balanced"

automatic = profiles.resolve_computer_profile({"mode": "automatic", "power_plan": "high_performance"}, {"cpu_cores": 12, "cpu_threads": 24, "ram_total_gb": 64})
assert automatic["effective_mode"] == "balanced"
assert automatic["server_priority"] == "normal"
assert automatic["power_plan"] == "unchanged"

dedicated = profiles.resolve_computer_profile({"mode": "dedicated_host", "power_plan": "high_performance"}, {})
assert dedicated["server_priority"] == "above_normal"
assert dedicated["power_plan"] == "high_performance"
assert dedicated["background_multiplier"] > 1

custom = profiles.resolve_computer_profile({"mode": "custom", "server_priority": "high", "power_plan": "high_performance"}, {})
assert custom["server_priority"] == "high"

with tempfile.TemporaryDirectory() as temp_dir:
    recovery = Path(temp_dir) / "computer_profile_session.json"
    completed = SimpleNamespace(returncode=0, stdout="", stderr="")
    previous = "11111111-2222-3333-4444-555555555555"
    with patch.object(profiles.sys, "platform", "win32"), patch.object(profiles, "active_power_scheme", return_value=previous), patch.object(profiles, "run_hidden", return_value=completed) as run:
        result = profiles.begin_power_session(recovery, dedicated, 1234, "world-1")
        assert result["applied"] is True
        assert json.loads(recovery.read_text(encoding="utf-8"))["previous_scheme"] == previous
        run.assert_called_once_with(["powercfg.exe", "/setactive", "SCHEME_MIN"], capture_output=True, text=True, timeout=8)
    with patch.object(profiles.sys, "platform", "win32"), patch.object(profiles, "run_hidden", return_value=completed) as run:
        result = profiles.restore_power_session(recovery, force=True)
        assert result["restored"] is True
        assert not recovery.exists()
        run.assert_called_once_with(["powercfg.exe", "/setactive", previous], capture_output=True, text=True, timeout=8)

print("computer profile safety contracts passed")
