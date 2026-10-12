from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

import sync_engine


class Response:
    def __init__(self, body: bytes, url: str):
        self.body = body
        self.url = url
        self.offset = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.body) - self.offset
        chunk = self.body[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk

    def geturl(self) -> str:
        return self.url

    def close(self) -> None:
        pass


def main() -> None:
    content = b"authoritative payload"
    entry = {"path": "Binaries/Win64/ue4ss/Mods/Example/main.lua", "size": len(content),
             "sha256": hashlib.sha256(content).hexdigest()}
    index = ("{\"schema\":\"DragonwildsSync.FileMirror.v1\",\"files\":["
             "{\"path\":\"Binaries/Win64/ue4ss/Mods/Example/main.lua\",\"url\":\"https://cdn.example/file\"},"
             "{\"path\":\"not/in/the/server/manifest\",\"url\":\"https://cdn.example/extra\"}]}").encode()
    original_urlopen = sync_engine.urllib.request.urlopen
    original_request = sync_engine.request
    try:
        sync_engine.urllib.request.urlopen = lambda url, timeout=0: Response(index, url)
        mirror = sync_engine.resolve_file_mirror({"files": [entry], "file_mirror": {
            "schema": "DragonwildsSync.FileMirror.v1", "index_url": "https://cdn.example/index.json"}})
        assert mirror == {entry["path"]: "https://cdn.example/file"}

        with TemporaryDirectory(prefix="dws-mirror-") as temporary:
            target = Path(temporary) / "payload.download"
            sync_engine.urllib.request.urlopen = lambda url, timeout=0: Response(content, url)
            sync_engine.request = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("server fallback was not needed"))
            sync_engine.download_entry("http://server", "secret", entry, target, mirror_url=mirror[entry["path"]])
            assert target.read_bytes() == content

            bad = b"stale mirror payload"
            sync_engine.urllib.request.urlopen = lambda url, timeout=0: Response(bad, url)
            sync_engine.request = lambda *args, **kwargs: Response(content, "http://server/files/payload")
            target.unlink()
            sync_engine.download_entry("http://server", "secret", entry, target, mirror_url=mirror[entry["path"]])
            assert target.read_bytes() == content
    finally:
        sync_engine.urllib.request.urlopen = original_urlopen
        sync_engine.request = original_request

    root = Path(__file__).resolve().parent.parent
    service = (root / "backend/dragonwilds_service_compat.py").read_text(encoding="utf-8")
    renderer = (root / "renderer/app-v2.js").read_text(encoding="utf-8")
    publisher = (root / "backend/server_systems.py").read_text(encoding="utf-8")
    assert 'sync["file_mirror_index_url"] = mirror_url' in service
    assert 'id="se-file-mirror-index"' in renderer
    assert '"file_mirror": ({"schema": "DragonwildsSync.FileMirror.v1"' in publisher

    print("verified external file mirror fallback: PASS")


if __name__ == "__main__":
    main()
