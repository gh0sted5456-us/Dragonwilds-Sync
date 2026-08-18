from __future__ import annotations

import runtime_manager


class FakeProc:
    def __init__(self, pid=4242):
        self.pid = pid

    def poll(self):
        return None


def exercise(platform_name: str) -> tuple[list[str], dict, dict]:
    captured = {}
    old_platform = runtime_manager.sys.platform
    old_getpid = runtime_manager.os.getpid
    old_popen = runtime_manager.subprocess.Popen
    old_sleep = runtime_manager.time.sleep
    try:
        runtime_manager.sys.platform = platform_name
        runtime_manager.os.getpid = lambda: 1111
        runtime_manager.time.sleep = lambda _seconds: None

        def fake_popen(command, **kwargs):
            captured["command"] = list(command)
            captured["kwargs"] = dict(kwargs)
            return FakeProc()

        runtime_manager.subprocess.Popen = fake_popen
        evidence = runtime_manager._launch_orphan_watchdog(2222)
        return captured["command"], captured["kwargs"], evidence
    finally:
        runtime_manager.sys.platform = old_platform
        runtime_manager.os.getpid = old_getpid
        runtime_manager.subprocess.Popen = old_popen
        runtime_manager.time.sleep = old_sleep


def main() -> None:
    command, kwargs, evidence = exercise("win32")
    assert command[0].lower() == "powershell.exe"
    script = command[-1]
    assert "$parentPid=1111" in script and "$serverPid=2222" in script
    assert "taskkill.exe /PID $serverPid /T /F" in script
    assert evidence["armed"] and evidence["mode"] == "powershell-taskkill"
    assert evidence["server_pid"] == 2222 and evidence["parent_pid"] == 1111
    assert "creationflags" in kwargs

    command, kwargs, evidence = exercise("linux")
    assert command[:2] == ["/bin/sh", "-c"]
    script = command[-1]
    assert "parent=1111" in script and "target=2222" in script
    assert 'kill -TERM "$target"' in script and 'kill -KILL "$target"' in script
    assert kwargs.get("start_new_session") is True
    assert evidence["armed"] and evidence["mode"] == "posix-process-tree"

    print("catastrophic dedicated-server orphan watchdog contract passed")


if __name__ == "__main__":
    main()
