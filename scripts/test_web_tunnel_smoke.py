from __future__ import annotations

import socket
import sys
import time
import urllib.request
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import directory_host  # noqa: E402


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hold", type=int, default=0, help="Keep the verified test tunnel open for browser QA")
    args = parser.parse_args()
    original_firewall = directory_host.configure_directory_firewall
    directory_host.configure_directory_firewall = lambda port, profiles="private,public": {
        "ok": True, "changed": False, "message": "smoke test; firewall unchanged", "profiles": profiles,
    }
    controller = directory_host.DirectoryHost()
    try:
        controller.start({
            "enabled": True, "bind_host": "127.0.0.1", "port": free_port(),
            "upnp_enabled": False, "public_transport": "cloudflare_quick",
        })
        deadline = time.time() + 90
        status = controller.status()
        while time.time() < deadline and (status.get("tunnel") or {}).get("state") == "starting":
            time.sleep(1)
            status = controller.status()
        tunnel = status.get("tunnel") or {}
        if tunnel.get("state") != "online" or not tunnel.get("public_url"):
            raise RuntimeError(tunnel.get("error") or "Cloudflare Quick Tunnel did not publish an address within 90 seconds")
        public_url = str(tunnel["public_url"]).rstrip("/")
        probe_deadline = time.time() + 45
        last_error: Exception | None = None
        while time.time() < probe_deadline:
            try:
                with urllib.request.urlopen(public_url + "/health", timeout=10) as response:
                    body = response.read().decode("utf-8")
                    if response.status == 200 and '"ok": true' in body.lower():
                        last_error = None
                        break
                    last_error = RuntimeError("The public endpoint returned a non-Dragonwilds health response")
            except Exception as exc:
                last_error = exc
            time.sleep(2)
        if last_error:
            raise RuntimeError(f"The temporary hostname was issued but did not resolve within 45 seconds: {last_error}")
        print(f"WebHost public HTTPS smoke test passed: {public_url}")
        sys.stdout.flush()
        if args.hold > 0:
            time.sleep(min(args.hold, 300))
    finally:
        controller.stop()
        directory_host.configure_directory_firewall = original_firewall


if __name__ == "__main__":
    main()
