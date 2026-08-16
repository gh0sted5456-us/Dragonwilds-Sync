from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any

from profile_store import APP_DATA_DIR
from process_utils import popen_hidden


RELEASE_API = "https://api.github.com/repos/cloudflare/cloudflared/releases/latest"
PUBLIC_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)


def _asset_name() -> str:
    machine = platform.machine().casefold()
    amd64 = machine in {"amd64", "x86_64", "x64"}
    arm64 = machine in {"arm64", "aarch64"}
    if os.name == "nt" and amd64:
        return "cloudflared-windows-amd64.exe"
    if platform.system().casefold() == "linux" and amd64:
        return "cloudflared-linux-amd64"
    if platform.system().casefold() == "linux" and arm64:
        return "cloudflared-linux-arm64"
    raise RuntimeError(f"Cloudflare Quick Tunnel is not packaged for {platform.system()} {platform.machine()}.")


class WebTunnel:
    """Bounded lifecycle wrapper for the optional official cloudflared helper.

    The helper is downloaded only after the operator selects Quick Tunnel. The
    GitHub release asset digest is required and verified before execution. This
    keeps the main application package small while allowing the helper to update
    independently on Windows and Linux.
    """

    def __init__(self):
        self.lock = threading.RLock()
        self.process: Any = None
        self.worker: threading.Thread | None = None
        self.reader: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.mode = "direct"
        self.state = "stopped"
        self.public_url = ""
        self.error = ""
        self.version = ""
        self.started_at: float | None = None
        self.lines: deque[str] = deque(maxlen=80)

    @property
    def root(self) -> Path:
        path = APP_DATA_DIR / "WebHost" / "cloudflared"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def binary(self) -> Path:
        name = "cloudflared.exe" if os.name == "nt" else "cloudflared"
        return self.root / name

    def _download_verified(self) -> Path:
        request = urllib.request.Request(RELEASE_API, headers={"User-Agent": "Dragonwilds-Sync/1", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(request, timeout=20) as response:
            release = json.loads(response.read(2_000_000).decode("utf-8"))
        wanted = _asset_name()
        asset = next((row for row in release.get("assets") or [] if str(row.get("name") or "") == wanted), None)
        if not asset:
            raise RuntimeError(f"The official cloudflared release does not contain {wanted}.")
        digest = str(asset.get("digest") or "")
        if not digest.startswith("sha256:"):
            raise RuntimeError("The official cloudflared release did not publish a verifiable SHA-256 digest.")
        expected = digest.split(":", 1)[1].casefold()
        version = str(release.get("tag_name") or "latest")[:80]
        marker = self.root / "release.json"
        if self.binary.is_file() and marker.is_file():
            try:
                saved = json.loads(marker.read_text(encoding="utf-8"))
                if saved.get("sha256") == expected and hashlib.sha256(self.binary.read_bytes()).hexdigest() == expected:
                    self.version = str(saved.get("version") or version)
                    return self.binary
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        url = str(asset.get("browser_download_url") or "")
        if not url.startswith("https://github.com/cloudflare/cloudflared/"):
            raise RuntimeError("The cloudflared download address was not an official GitHub release asset.")
        temp = self.root / (self.binary.name + ".download")
        download = urllib.request.Request(url, headers={"User-Agent": "Dragonwilds-Sync/1"})
        sha = hashlib.sha256(); size = 0
        with urllib.request.urlopen(download, timeout=60) as response, temp.open("wb") as target:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > 100 * 1024 * 1024:
                    raise RuntimeError("The cloudflared release asset exceeded the 100 MiB safety limit.")
                sha.update(chunk); target.write(chunk)
        if sha.hexdigest().casefold() != expected:
            temp.unlink(missing_ok=True)
            raise RuntimeError("The downloaded cloudflared SHA-256 digest did not match GitHub's release metadata.")
        os.replace(temp, self.binary)
        if os.name != "nt":
            self.binary.chmod(0o755)
        marker.write_text(json.dumps({"version": version, "sha256": expected, "asset": wanted}, indent=2), encoding="utf-8")
        self.version = version
        return self.binary

    def _read_output(self, process: Any) -> None:
        stream = process.stdout
        if stream is None:
            return
        for raw in stream:
            line = str(raw or "").strip()
            if not line:
                continue
            with self.lock:
                self.lines.append(line[-1000:])
                match = PUBLIC_URL_RE.search(line)
                if match:
                    self.public_url = match.group(0).rstrip("/")
                    self.state = "online"
                    self.error = ""
        code = process.poll()
        with self.lock:
            if self.process is process:
                self.process = None
                if not self.stop_event.is_set():
                    self.state = "error"
                    self.error = f"cloudflared stopped unexpectedly (exit {code})."

    def _launch_quick(self, port: int) -> None:
        try:
            binary = self._download_verified()
            if self.stop_event.is_set():
                return
            environment = dict(os.environ)
            # Quick Tunnels are incompatible with an unrelated user-level
            # cloudflared config.yaml. Isolate the optional module to its own
            # APPDATA directory so an existing administrator setup is untouched.
            environment["HOME"] = str(self.root)
            if os.name == "nt":
                environment["USERPROFILE"] = str(self.root)
            process = popen_hidden(
                [str(binary), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{int(port)}"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                bufsize=1, env=environment,
            )
            with self.lock:
                if self.stop_event.is_set():
                    process.terminate(); return
                self.process = process
                self.started_at = time.time()
                self.reader = threading.Thread(target=self._read_output, args=(process,), daemon=True, name="Dragonwilds-WebHost-Tunnel-Output")
                self.reader.start()
        except Exception as exc:
            with self.lock:
                if not self.stop_event.is_set():
                    self.state = "error"
                    self.error = str(exc)[:500]

    def start_quick(self, port: int) -> dict:
        self.stop()
        with self.lock:
            self.mode = "cloudflare_quick"
            self.state = "starting"
            self.public_url = ""
            self.error = ""
            self.lines.clear()
            self.stop_event.clear()
            self.worker = threading.Thread(target=self._launch_quick, args=(int(port),), daemon=True, name="Dragonwilds-WebHost-Tunnel")
            self.worker.start()
        return self.status()

    def stop(self) -> dict:
        with self.lock:
            self.stop_event.set()
            process = self.process
            self.process = None
        if process and process.poll() is None:
            try:
                process.terminate(); process.wait(timeout=3)
            except Exception:
                try: process.kill()
                except Exception: pass
        with self.lock:
            self.mode = "direct"
            self.state = "stopped"
            self.public_url = ""
            self.started_at = None
        return self.status()

    def ensure(self, mode: str, port: int, enabled: bool) -> dict:
        requested = str(mode or "direct").casefold()
        if not enabled or requested != "cloudflare_quick":
            return self.stop()
        with self.lock:
            running = self.mode == requested and self.state in {"starting", "online"} and (self.process is None or self.process.poll() is None)
        return self.status() if running else self.start_quick(port)

    def status(self) -> dict:
        with self.lock:
            return {
                "mode": self.mode, "state": self.state, "public_url": self.public_url,
                "error": self.error, "version": self.version,
                "started_at": self.started_at,
                "recent_output": list(self.lines)[-8:],
            }


WEB_TUNNEL = WebTunnel()
