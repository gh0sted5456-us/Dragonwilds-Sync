from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import os
import platform
import re
import secrets
import shutil
import stat
import socket
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import quote, quote_plus, unquote, urlparse

from profile_store import APP_DATA_DIR, SERVER_PROFILES_DIR, load_server_profile, load_state, save_server_profile
from process_utils import check_output_hidden, popen_hidden, run_hidden
from integrations import normalize_mod_source
from network_health import summarize_client_reports
from health_model import normalize_health_config, public_health_config, score_server_health
from security_policy import direct_policy_match, merge_access_policies, normalize_access_policy, trusted_ip_match, REGION_LABELS
from runtime_versions import normalize_cl_version, server_runtime_stack
from server_layout import resolve_server_layout
from client_layout import resolve_client_layout
from world_save_distribution import build_worldsave_zip, record_download, status_for_ip
from server_scheduler import normalize_notice
from player_tracker import PLAYER_SERVICE
from character_profiles import list_starter_characters, starter_character_path
from character_submissions import quarantine_submission_bytes
from player_backups import latest_player_backup, player_backup_status, store_player_backup
from mod_archive_layout import inspect_mod_payloads, locate_mod_payload
from mod_tags import discover_packaged_metadata, normalize_tags, parse_tags_file, tags_from_mod_root, tags_from_sidecar, hotload_capable_from_root, set_hotload_marker, set_tags_file, ensure_mod_contract_files, identity_from_mod_root, ensure_baked_in_ue4ss_enabled, UE4SS_BAKED_IN_DEFAULT_MODS
from runtime_platforms import (ALL_CLIENT_PLATFORMS, WIN64_RUNTIME_PLATFORMS,
                               detect_server_host,
                               entry_allowed_for_platform, filtered_manifest,
                               normalize_client_platform, runtime_variant_catalog)
from sync_manifest import build_client_meta
from world_classification import normalize_world_classification
from operator_identity import sign_world_identity
from networking import (DEFAULT_SYNC_PORT, DEFAULT_SYNC_DISCOVERY_PORT, apply_firewall_spec, backend_program,
                        firewall_spec)

SYNC_PORT_DEFAULT = DEFAULT_SYNC_PORT
DISCOVERY_PORT = 8421
DISCOVERY_QUERY_PORT = DEFAULT_SYNC_DISCOVERY_PORT


def _sync_tls_material(profile_id: str, host_values: list[str] | None = None) -> tuple[Path, Path, str]:
    """Create/reuse an app-owned self-signed certificate for pinned Sync TLS."""
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(profile_id or "world"))[:96] or "world"
    root = SERVER_PROFILES_DIR / safe_id / "sync_tls"
    cert_path, key_path = root / "certificate.pem", root / "private-key.pem"
    if cert_path.is_file() and key_path.is_file():
        try:
            cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
            if cert.not_valid_after.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) + timedelta(days=7):
                return cert_path, key_path, cert.fingerprint(hashes.SHA256()).hex()
        except Exception:
            pass
    root.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"Dragonwilds Sync {safe_id}"[:64])])
    san: list[x509.GeneralName] = [x509.DNSName("localhost")]
    for value in host_values or []:
        host = str(value or "").strip().split(":", 1)[0]
        try: san.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            if host and re.fullmatch(r"[A-Za-z0-9.-]+", host): san.append(x509.DNSName(host))
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=825)).add_extension(x509.SubjectAlternativeName(san), critical=False)
            .sign(key, hashes.SHA256()))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    try: os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError: pass
    return cert_path, key_path, cert.fingerprint(hashes.SHA256()).hex()


def _remove_generated_path(path: Path) -> None:
    """Remove app-generated staging even when managed sources were read-only.

    Config files are intentionally locked after the Monaco editor writes them.
    ``copy2`` preserves that mode in the publish cache, so a later republish must
    unlock its own cache before replacing it.
    """
    path = Path(path)
    if not path.exists():
        return

    def unlock_and_retry(operation, target, _error):
        try:
            os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
            operation(target)
        except OSError:
            raise

    if path.is_dir():
        shutil.rmtree(path, onerror=unlock_and_retry)
    else:
        try:
            path.unlink()
        except PermissionError:
            path.chmod(stat.S_IWRITE | stat.S_IREAD)
            path.unlink()


def _write_launcher_control_file(path: Path, data: bytes = b"") -> None:
    """Atomically replace a launcher-owned marker, repairing legacy read-only state."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".dragonwilds.tmp")
    temporary.write_bytes(data)
    if path.exists():
        try:
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
        except OSError:
            pass
    try:
        os.replace(temporary, path)
    except PermissionError:
        # Windows represents chmod's missing owner-write bit as the read-only
        # attribute. Retry once after explicitly clearing it on the destination.
        if path.exists():
            path.chmod(stat.S_IWRITE | stat.S_IREAD)
        os.replace(temporary, path)
DISCOVERY_MAGIC = "dragonwilds-sync-v1"
WORLD_SYNC_PROTOCOL = "dragonwilds-world-sync"
WORLD_SYNC_VERSION = 1
NONCE_TTL_SECONDS = 60
TOKEN_TTL_SECONDS = 6 * 60 * 60
PUBLISH_DIR = APP_DATA_DIR / "published"
RUNTIME_LIBRARY_DIR = APP_DATA_DIR / "runtime_library"
UE4SS_RUNTIME_DIR = RUNTIME_LIBRARY_DIR / "ue4ss"
RUNESCHEMA_RUNTIME_DIR = RUNTIME_LIBRARY_DIR / "runeschema"
RUNESCHEMA_UPLOAD_DIR = APP_DATA_DIR / "runeschema_uploads"
RUNESCHEMA_CORE_CACHE_ZIP = RUNESCHEMA_UPLOAD_DIR / "RuneSchema-core-latest.zip"
CLIENT_RUNTIME_OVERRIDE_DIR = APP_DATA_DIR / "client_runtime_overrides"
CLIENT_UE4SS_OVERRIDE_ZIP = CLIENT_RUNTIME_OVERRIDE_DIR / "UE4SS-client-custom.zip"
CLIENT_RUNESCHEMA_CORE_CACHE_ZIP = CLIENT_RUNTIME_OVERRIDE_DIR / "RuneSchema-client-custom.zip"
CLIENT_RUNESCHEMA_RUNTIME_DIR = CLIENT_RUNTIME_OVERRIDE_DIR / "runeschema"
BUNDLED_UE4SS_RESOURCE = ("DragonwildsServerRuntime", "UE4SS-core-latest.zip")
BUNDLED_RSDWTOOLS_RESOURCE = ("RSDWTools-baseline.zip",)
def user_visible_mod_unit(unit: "ModUnit") -> bool:
    """Hide shared upstream runtimes while exposing every World-owned mod."""
    return (unit.group not in {"ue4ss_core", "runeschema"}
            and unit.name.casefold() not in {"mods.txt", "dwmapi.dll", "rsdwtools", "persistentdirectconnectip"})
RUNTIME_MUTATION_LOCK = threading.RLock()


def world_sync_fingerprint(profile_id: str) -> str:
    """Stable, domain-separated public identity for one Sync World profile."""
    raw = f"DragonwildsWorldSync|{str(profile_id or '').strip()}".encode("utf-8")
    return "dws1-" + hashlib.sha256(raw).hexdigest()[:24]


def signed_operator_world_identity(manifest: dict) -> dict:
    world_sync = manifest.get("world_sync") if isinstance(manifest.get("world_sync"), dict) else {}
    return sign_world_identity({
        "schema": "DragonwildsSync.OperatorWorldIdentity.v1",
        "world_fingerprint": str(world_sync.get("fingerprint") or manifest.get("launcher_fingerprint") or ""),
        "world_name": str(manifest.get("profile_name") or "World")[:120],
        "profile_id": str(manifest.get("profile_id") or "")[:128],
        "classification": manifest.get("classification") or {},
        "tags": list(manifest.get("tags") or [])[:24],
        "mod_badges": list(manifest.get("mod_badges") or [])[:12],
    })

GROUP_DEST_BASE = {
    "ue4ss_core": "Binaries/Win64",
    "ue4ss_mod": "Binaries/Win64/ue4ss/Mods",
    "runeschema": "Binaries/Win64/ue4ss/Mods",
    "runeschema_mod": "Binaries/Win64/ue4ss/Mods/RuneSchema/mods",
    "pak_mod": "Content/Paks/~mods",
}
GROUP_LABELS = {
    "ue4ss_core": "UE4SS Core",
    "ue4ss_mod": "UE4SS LUA",
    "runeschema": "RuneSchema",
    "runeschema_mod": "RuneSchema Mods",
    "pak_mod": "Paks",
}
UNIT_GROUP_SECTION = {
    "pak_mod": ("paks", ""),
    "ue4ss_core": ("ue4ss", "master"),
    "ue4ss_mod": ("ue4ss", "slave"),
    "runeschema": ("runeschema", "master"),
    "runeschema_mod": ("runeschema", "slave"),
}
CATEGORY_OF_GROUP = {
    "pak_mod": "paks", "ue4ss_mod": "ue4ss_lua", "runeschema": "runeschema", "runeschema_mod": "runeschema"
}
CATEGORY_ORDER = ["paks", "ue4ss_lua", "runeschema"]
_UE4SS_CORE_HINTS = ("ue4ss", "dwmapi")
_DISTRIBUTABLE_EXTENSIONS = {".pak", ".lua"}

DEDICATED_STEAMCMD_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
DEDICATED_STEAMCMD_LINUX_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
DEDICATED_STEAM_APP_ID = "4019830"
CLIENT_STEAM_APP_ID = "1374490"
DEDICATED_SERVER_EXE = "RSDragonwilds.exe"
DEDICATED_SERVER_EXE_ALIASES = ("RSDragonwildsServer.sh", "RSDragonwildsServer", "RSDragonwilds.exe", "RSDragonwildsServer.exe")
DEDICATED_STEAM_APP_DIR = "RuneScape Dragonwilds Dedicated Server"
STEAMCMD_INFO_URL = "https://api.steamcmd.net/v1/info/{appid}"
DEFAULT_UE4SS_RELEASES_URL = "https://github.com/UE4SS-RE/RE-UE4SS/releases/tag/experimental-latest"
SERVER_LOADER_FILENAME = "version.dll"
_GITHUB_RELEASE_TAG_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/releases/tag/([^/?#]+)/?$")
_GITHUB_REPO_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?$")
_GITHUB_RELEASES_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/releases/?$")
_GITHUB_RELEASES_LATEST_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/releases/latest/?$")
_GITHUB_TAGS_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/tags/?$")
_GITHUB_ASSET_HREF_RE = re.compile(r'href="(/[^"]+/releases/download/[^"]+\.zip)"')
_DEDICATED_JOIN_RE = re.compile(r"Join succeeded:\s*(.+)")
_DEDICATED_LEAVE_RE = re.compile(r"Player Removed from session \[[^\]]+\]-\[(.+)\]")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_extract_zip(zf: zipfile.ZipFile, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    for info in zf.infolist():
        pure = PurePosixPath(info.filename.replace("\\", "/"))
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            raise zipfile.BadZipFile(f"Unsafe archive path: {info.filename}")
        if ((info.external_attr >> 16) & 0o170000) == 0o120000:
            raise zipfile.BadZipFile(f"Archive links are not supported: {info.filename}")
        target = (root / Path(*pure.parts)).resolve()
        if target != root and root not in target.parents:
            raise zipfile.BadZipFile(f"Archive path escapes destination: {info.filename}")
    zf.extractall(root)




def review_with_defender(path: str, label: str = "content") -> dict:
    """Compatibility no-op: Defender integration retired in RC2.

    Archive path validation, hashes, staging and rollback remain launcher-owned;
    OS antivirus products can continue scanning files normally outside Sync.
    """
    return {"available": False, "enabled": False, "blocked": False, "skipped": True,
            "reason": "Defender integration retired in RC2", "path": str(path or ""), "label": str(label or "content")}


def _is_launcher_bundled_ue4ss(path: str | Path) -> bool:
    """Identify the immutable UE4SS asset already shipped in this release.

    Defender real-time protection still reviews extracted DLLs. Avoiding a
    second explicit scan of the 100+ MB signed release container prevents
    MpCmdRun code-2 archive errors from making the built-in baseline unusable;
    user-selected and downloaded archives retain the full pre-install scan.
    """
    try:
        return Path(path).resolve() == _bundled_app_resource(*BUNDLED_UE4SS_RESOURCE).resolve()
    except OSError:
        return False


def review_mod_unit_with_defender(unit: "ModUnit") -> list[dict]:
    targets = [unit.source_dir] if unit.source_dir is not None else list(unit.source_files)
    reviews = []
    for target in targets:
        if target is None or not Path(target).exists():
            continue
        review = review_with_defender(target, f"mod '{unit.name}'")
        reviews.append({
            "unit_key": unit.key, "name": unit.name, "clean": review.get("clean"),
            "skipped": bool(review.get("skipped")), "reason": review.get("reason") or "",
            "mode": review.get("mode") or "", "signature_version": review.get("signature_version") or "",
        })
    return reviews

def local_ip_guess() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"


def local_interface_addresses(default: str = "") -> list:
    """Return every usable local interface address visible to this host."""
    found = []
    seen = set()

    def add(value: str) -> None:
        text = str(value or "").split("%", 1)[0].strip()
        if not text or text in seen:
            return
        seen.add(text)
        try:
            found.append(ipaddress.ip_address(text))
        except ValueError:
            pass

    add(default)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            add(info[4][0])
    except (socket.gaierror, OSError, UnicodeError):
        pass
    add(local_ip_guess())
    return found


def detect_public_ip(timeout: float = 4.0) -> str | None:
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com"):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                value = response.read().decode().strip()
                if value:
                    ipaddress.ip_address(value)
                    return value
        except (urllib.error.URLError, OSError, ValueError):
            continue
    return None


def compute_mod_badges(units: list["ModUnit"]) -> list[str]:
    # Badges describe player-facing mod families, not invisible runtime plumbing.
    present = {CATEGORY_OF_GROUP.get(u.group) for u in units
               if u.classification == "player_required" and u.group not in ("ue4ss_core", "runeschema")
               and u.name.lower() not in {"mods.txt", "dwmapi.dll"}}
    present.discard(None)
    if not present:
        return ["VANILLA"]
    labels = {"paks": "PAKS", "ue4ss_lua": "UE4SS", "runeschema": "RUNESCHEMA"}
    return [labels[c] for c in CATEGORY_ORDER if c in present]


def profile_rating_summary(profile: dict) -> tuple[float, int]:
    entries = profile.get("feedback") or []
    ratings = [int(x.get("rating")) for x in entries if isinstance(x.get("rating"), int) and 1 <= x["rating"] <= 5 and review_integrity_valid(x)]
    return ((sum(ratings) / len(ratings), len(ratings)) if ratings else (0.0, 0))


def _review_secret() -> bytes:
    target = APP_DATA_DIR / "security" / "review-integrity.key"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(secrets.token_bytes(32))
        try: os.chmod(target, stat.S_IREAD | stat.S_IWRITE)
        except OSError: pass
    return target.read_bytes()


def _review_canonical(entry: dict) -> bytes:
    fields = {key: entry.get(key) for key in ("id", "world_id", "client_id", "rating", "report", "ip_hash", "received_at")}
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def review_integrity(entry: dict) -> str:
    return hmac.new(_review_secret(), _review_canonical(entry), hashlib.sha256).hexdigest()


def review_integrity_valid(entry: dict) -> bool:
    signature = str(entry.get("integrity") or "")
    # Legacy records remain readable; all newly accepted reviews are signed.
    return not signature or hmac.compare_digest(signature, review_integrity(entry))


def public_reviews(profile: dict, days: int = 30) -> list[dict]:
    cutoff = time.time() - max(1, min(int(days or 30), 90)) * 86400
    hidden = {str(value) for value in (profile.get("hidden_review_ids") or [])}
    rows = []
    for entry in reversed(profile.get("feedback") or []):
        if float(entry.get("received_at") or 0) < cutoff or str(entry.get("id") or "") in hidden or not review_integrity_valid(entry):
            continue
        rows.append({key: entry.get(key) for key in ("id", "client_id", "rating", "report", "received_at", "integrity")})
    return rows[:200]


def _profile_backups_dir(profile_id: str) -> Path:
    return SERVER_PROFILES_DIR / profile_id / "backups"


def list_profile_backups(profile_id: str) -> list[dict]:
    root = _profile_backups_dir(profile_id)
    if not root.exists():
        return []
    result = []
    for path in sorted(root.glob("backup-*.zip"), reverse=True):
        try:
            result.append({"name": path.name, "size": path.stat().st_size, "mtime": path.stat().st_mtime})
        except OSError:
            pass
    return result


def _suggested_classification(name: str, manual: bool = False) -> str:
    if not manual:
        return "player_required"
    p = Path(name)
    lower = p.name.lower()
    if p.suffix.lower() in _DISTRIBUTABLE_EXTENSIONS:
        return "player_required"
    if p.suffix.lower() in (".dll", ".ini") and any(h in lower for h in _UE4SS_CORE_HINTS):
        return "player_required"
    return "server_only"


@dataclass
class ModUnit:
    name: str
    group: str
    source_dir: Path | None = None
    source_files: list[Path] = field(default_factory=list)
    exclude_top_level_dirs: set[str] = field(default_factory=set)
    classification: str = "player_required"
    category: str = "permanent"
    manual: bool = False
    source: dict = field(default_factory=lambda: normalize_mod_source({}))
    hotload_capable: bool = False
    tags: list[str] = field(default_factory=list)
    identity: dict | None = None
    _content_cache: tuple[int, int, str] | None = field(default=None, init=False, repr=False)

    @property
    def key(self) -> str:
        return f"{self.group}::{self.name}"

    @property
    def is_dir(self) -> bool:
        return self.source_dir is not None

    def iter_files(self):
        base = GROUP_DEST_BASE[self.group]
        if self.source_dir is not None:
            for root, dirs, files in os.walk(self.source_dir):
                if Path(root) == self.source_dir and self.exclude_top_level_dirs:
                    dirs[:] = [d for d in dirs if d.lower() not in {x.lower() for x in self.exclude_top_level_dirs}]
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for filename in files:
                    if filename.startswith("."):
                        continue
                    source = Path(root) / filename
                    rel = source.relative_to(self.source_dir).as_posix()
                    yield f"{base}/{self.name}/{rel}", source
        else:
            for source in self.source_files:
                yield f"{base}/{source.name}", source

    def file_count(self) -> int:
        return sum(1 for _ in self.iter_files())

    def total_size(self) -> int:
        total = 0
        for _, source in self.iter_files():
            try:
                total += source.stat().st_size
            except OSError:
                pass
        return total

    def content_summary(self) -> tuple[int, int, str]:
        """Return count, size, and a stable SHA-256 identity for this mod only."""
        if self._content_cache is not None:
            return self._content_cache
        digest = hashlib.sha256()
        count = 0
        size = 0
        rows = []
        for _, source in self.iter_files():
            relative = source.relative_to(self.source_dir).as_posix() if self.source_dir is not None else source.name
            rows.append((relative, source))
        for relative, source in sorted(rows, key=lambda item: item[0].casefold()):
            try:
                file_size = source.stat().st_size
                digest.update(relative.replace("\\", "/").encode("utf-8"))
                digest.update(b"\0")
                with source.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                digest.update(b"\0")
                count += 1
                size += file_size
            except OSError:
                continue
        self._content_cache = (count, size, digest.hexdigest())
        return self._content_cache

    def public(self, live_keys: set[str] | None = None) -> dict:
        file_count, size, content_hash = self.content_summary()
        return {
            "key": self.key, "name": self.name, "group": self.group,
            "section": UNIT_GROUP_SECTION.get(self.group, ("other", ""))[0],
            "subsection": UNIT_GROUP_SECTION.get(self.group, ("other", ""))[1],
            "classification": self.classification, "category": self.category,
            "distribution": "client_required" if self.classification == "player_required" else "server_retained",
            "file_count": file_count, "size": size, "content_hash": content_hash, "manual": self.manual,
            "source": normalize_mod_source(self.source),
            "hotload_capable": bool(self.hotload_capable),
            "tags": list(self.tags),
            "identity": self.identity if isinstance(self.identity, dict) else None,
            "live": self.key in (live_keys or set()),
        }


_LAST_SCAN_WARNINGS: list[str] = []


def pop_scan_warnings() -> list[str]:
    """Return and clear the non-fatal problems from the most recent scan_mod_units()/
    scan_profile_snapshot_units() call. A single unreadable/locked mod folder must
    never fail the whole scan -- it's recorded here and skipped instead."""
    global _LAST_SCAN_WARNINGS
    warnings, _LAST_SCAN_WARNINGS = _LAST_SCAN_WARNINGS, []
    return warnings


def _iter_top_level(root: Path):
    if not root.exists():
        return []
    try:
        entries = list(root.iterdir())
    except OSError as exc:
        _LAST_SCAN_WARNINGS.append(f"Could not list {root.name or root}: {exc}")
        return []
    return [(p.name, p.is_dir(), p) for p in sorted(entries, key=lambda x: x.name.lower()) if not p.name.startswith(".")]


def _group_pak_siblings(entries):
    dirs = [(name, path) for name, is_dir, path in entries if is_dir]
    files: dict[str, list[Path]] = {}
    for _name, is_dir, path in entries:
        if not is_dir:
            files.setdefault(path.stem, []).append(path)
    return dirs, files


def scan_mod_units(profile_id: str, game_root: str) -> list[ModUnit]:
    layout = resolve_server_layout(game_root)
    root = layout.game_root
    if not root.exists():
        raise ValueError(f"Server game root does not exist: {root}")
    profile = load_server_profile(profile_id)
    overrides = profile.get("unit_overrides") or {}
    units: list[ModUnit] = []
    keys: set[str] = set()

    def add(name: str, group: str, *, source_dir=None, source_files=None, exclude=None, manual=False):
        key = f"{group}::{name}"
        if key in keys:
            return
        # A single mod folder's I/O problem (locked file, OneDrive placeholder
        # still hydrating, permission-restricted install path, antivirus lock)
        # must skip only that mod, never abort the rest of the scan.
        try:
            if source_dir is not None and group in {"ue4ss_mod", "runeschema_mod"}:
                ensure_mod_contract_files(source_dir)
            unit = ModUnit(name=name, group=group, source_dir=source_dir,
                           source_files=list(source_files or []), exclude_top_level_dirs=set(exclude or []),
                           classification=_suggested_classification(name, manual), manual=manual)
            override = overrides.get(key) or {}
            if override.get("classification") in ("player_required", "server_only"):
                unit.classification = override["classification"]
            if override.get("category") in ("permanent", "temporary"):
                unit.category = override["category"]
            unit.source = normalize_mod_source(override.get("source"))
            unit.hotload_capable = bool(override["hotload_capable"] if "hotload_capable" in override else (hotload_capable_from_root(source_dir) if source_dir is not None else False))
            discovered_tags = tags_from_mod_root(source_dir) if source_dir is not None else []
            if not discovered_tags and source_files:
                # Normal PAKs can carry launcher-persisted tags in profile metadata or an optional <stem>.tags.txt sidecar.
                first = Path(list(source_files)[0])
                discovered_tags = tags_from_sidecar(first, clean_stem=name)
            unit.tags = normalize_tags(override["tags"] if "tags" in override else discovered_tags)
            unit.identity = identity_from_mod_root(source_dir) if source_dir is not None else None
        except OSError as exc:
            _LAST_SCAN_WARNINGS.append(f"Skipped mod \"{name}\": {exc}")
            return
        units.append(unit); keys.add(key)

    mods = layout.ue4ss_mods_dir
    _LAST_SCAN_WARNINGS.extend(ensure_baked_in_ue4ss_enabled(mods))
    for name, is_dir, path in _iter_top_level(mods):
        lower = name.lower()
        if not is_dir and lower == "mods.txt":
            # Launcher-owned UE4SS control state is not a user-manageable mod.
            continue
        if is_dir and lower in UE4SS_BAKED_IN_DEFAULT_MODS:
            # Baked into UE4SS's own default distribution -- exists on disk,
            # nothing here for an operator to manage, so it isn't listed.
            continue
        if is_dir and lower == "runeschema":
            add(name, "runeschema", source_dir=path, exclude={"mods"})
            rs_mod_root = layout.runeschema_mods_dir
            if rs_mod_root != layout.runeschema_root:
                for sub_name, sub_is_dir, sub_path in _iter_top_level(rs_mod_root):
                    add(sub_name, "runeschema_mod", source_dir=sub_path if sub_is_dir else None,
                        source_files=[] if sub_is_dir else [sub_path])
            else:
                core_names = {"config", "dlls", "enabled.txt", "mods"}
                for sub_name, sub_is_dir, sub_path in _iter_top_level(path):
                    if sub_name.lower() in core_names:
                        continue
                    if sub_is_dir:
                        add(sub_name, "runeschema_mod", source_dir=sub_path)
        elif is_dir:
            add(name, "ue4ss_mod", source_dir=path)
        else:
            add(name, "ue4ss_mod", source_files=[path])

    paks = layout.paks_mods_dir
    dirs, grouped = _group_pak_siblings(_iter_top_level(paks))
    for name, path in dirs:
        _order, clean_name = _strip_pak_load_prefix(name)
        add(clean_name, "pak_mod", source_dir=path)
    for stem, files in grouped.items():
        _order, clean_stem = _strip_pak_load_prefix(stem)
        add(clean_stem, "pak_mod", source_files=files)

    units.sort(key=lambda u: (overrides.get(u.key) or {}).get("order", 10**9))
    return units


def scan_profile_snapshot_units(profile_id: str) -> list[ModUnit]:
    """Scan an inactive World's APPDATA-owned mod snapshot without touching live files."""
    stored = SERVER_PROFILES_DIR / profile_id / "mods"
    mods = stored / "ue4ss_mods"
    paks = stored / "pak_mods"
    profile = load_server_profile(profile_id)
    overrides = profile.get("unit_overrides") or {}
    units: list[ModUnit] = []
    keys: set[str] = set()

    def add(name: str, group: str, *, source_dir=None, source_files=None, exclude=None, manual=False):
        key = f"{group}::{name}"
        if key in keys:
            return
        # A single mod folder's I/O problem (locked file, OneDrive placeholder
        # still hydrating, permission-restricted install path, antivirus lock)
        # must skip only that mod, never abort the rest of the scan.
        try:
            if source_dir is not None and group in {"ue4ss_mod", "runeschema_mod"}:
                ensure_mod_contract_files(source_dir)
            unit = ModUnit(name=name, group=group, source_dir=source_dir,
                           source_files=list(source_files or []), exclude_top_level_dirs=set(exclude or []),
                           classification=_suggested_classification(name, manual), manual=manual)
            override = overrides.get(key) or {}
            if override.get("classification") in ("player_required", "server_only"):
                unit.classification = override["classification"]
            if override.get("category") in ("permanent", "temporary"):
                unit.category = override["category"]
            unit.source = normalize_mod_source(override.get("source"))
            unit.hotload_capable = bool(override["hotload_capable"] if "hotload_capable" in override else (hotload_capable_from_root(source_dir) if source_dir is not None else False))
            discovered_tags = tags_from_mod_root(source_dir) if source_dir is not None else []
            if not discovered_tags and source_files:
                # Normal PAKs can carry launcher-persisted tags in profile metadata or an optional <stem>.tags.txt sidecar.
                first = Path(list(source_files)[0])
                discovered_tags = tags_from_sidecar(first, clean_stem=name)
            unit.tags = normalize_tags(override["tags"] if "tags" in override else discovered_tags)
            unit.identity = identity_from_mod_root(source_dir) if source_dir is not None else None
        except OSError as exc:
            _LAST_SCAN_WARNINGS.append(f"Skipped mod \"{name}\": {exc}")
            return
        units.append(unit); keys.add(key)

    _LAST_SCAN_WARNINGS.extend(ensure_baked_in_ue4ss_enabled(mods))
    for name, is_dir, path in _iter_top_level(mods):
        lower = name.lower()
        if not is_dir and lower == "mods.txt":
            continue
        if is_dir and lower in UE4SS_BAKED_IN_DEFAULT_MODS:
            continue
        if is_dir and lower == "runeschema":
            add(name, "runeschema", source_dir=path, exclude={"mods"})
            for sub_name, sub_is_dir, sub_path in _iter_top_level(path / "mods"):
                add(sub_name, "runeschema_mod", source_dir=sub_path if sub_is_dir else None,
                    source_files=[] if sub_is_dir else [sub_path])
        elif is_dir:
            add(name, "ue4ss_mod", source_dir=path)
        else:
            add(name, "ue4ss_mod", source_files=[path])

    dirs, grouped = _group_pak_siblings(_iter_top_level(paks))
    for name, path in dirs:
        _order, clean_name = _strip_pak_load_prefix(name)
        add(clean_name, "pak_mod", source_dir=path)
    for stem, files in grouped.items():
        _order, clean_stem = _strip_pak_load_prefix(stem)
        add(clean_stem, "pak_mod", source_files=files)

    # UE4SS loader files are machine-level authoritative runtime files in the
    # current storage model and therefore are not duplicated into each inactive
    # World snapshot. Their saved classification/order remains in profile.json.
    units.sort(key=lambda u: (overrides.get(u.key) or {}).get("order", 10**9))
    return units

def _unit_has_enabled_txt(unit: ModUnit) -> bool:
    """True when UE4SS will auto-enable this directory from its own enabled.txt."""
    return bool(unit.source_dir is not None and (unit.source_dir / "enabled.txt").is_file())


def client_ue4ss_enablement(units: list[ModUnit], existing_text: str = "", mode: str = "auto") -> list[str]:
    """Return client-required UE4SS names that actually need mods.txt entries.

    In auto mode every eligible Client Required mod is selected. In manual mode
    the server operator's live mods.txt is projected onto that safe set. Mods
    carrying enabled.txt (including launcher-owned/runtime helpers) are omitted.
    """
    allowed: list[str] = []
    seen: set[str] = set()
    for unit in units:
        if unit.classification != "player_required" or unit.group != "ue4ss_mod" or not unit.is_dir:
            continue
        if unit.name.casefold() in {"mods.txt", "dwmapi.dll", "runeschema"}:
            continue
        if _unit_has_enabled_txt(unit):
            continue
        key = unit.name.casefold()
        if key not in seen:
            seen.add(key)
            allowed.append(unit.name)
    if str(mode or "auto").casefold() != "manual":
        return allowed
    allowed_by_name = {name.casefold(): name for name in allowed}
    selected: list[str] = []
    for raw in str(existing_text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith((";", "#")) or ":" not in line:
            continue
        name, value = (part.strip() for part in line.split(":", 1))
        if value.casefold() not in {"1", "true", "enabled", "on"}:
            continue
        canonical = allowed_by_name.get(name.casefold())
        if canonical and canonical not in selected:
            selected.append(canonical)
    return selected


def _mods_txt_lines(names: list[str], existing_text: str = "") -> str:
    desired = []
    seen = set()
    for name in names:
        clean = str(name or "").strip()
        if not clean or clean.lower() in {"mods.txt", "dwmapi.dll"} or clean.lower() in seen:
            continue
        seen.add(clean.lower()); desired.append(clean)
    lines = ["; Managed by Dragonwilds Sync. Edit in World Maintenance or switch mods.txt mode to Manual."]
    lines.extend(f"{name} : 1" for name in desired)
    # UE4SS documents Keybinds as a built-in entry that should remain near the
    # bottom when present. Preserve it without copying arbitrary server-only mods.
    if any(line.strip().lower().startswith("keybinds") for line in str(existing_text or "").splitlines()):
        lines.extend(["", "; Built-in keybinds", "Keybinds : 1"])
    return "\n".join(lines).rstrip() + "\n"


def _client_mods_txt_lines(names: list[str], existing_text: str = "") -> str:
    desired = []
    seen = set()
    for name in names:
        clean = str(name or "").strip()
        key = clean.casefold()
        if not clean or key in {"mods.txt", "dwmapi.dll", "runeschema"} or key in seen:
            continue
        seen.add(key); desired.append(clean)
    lines = ["; Managed by the selected Dragonwilds Sync World. Server-authored client mods.txt."]
    lines.extend(f"{name} : 1" for name in desired)
    if any(line.strip().casefold().startswith("keybinds") for line in str(existing_text or "").splitlines()):
        lines.extend(["", "; Built-in keybinds", "Keybinds : 1"])
    return "\n".join(lines).rstrip() + "\n"


def generate_server_mods_txt(profile_id: str, game_root: str, units: list[ModUnit] | None = None) -> dict:
    layout = resolve_server_layout(game_root)
    # Callers that are already publishing/scanning may pass the authoritative
    # inventory.  This avoids a second full walk of every mod file on Start.
    units = units if units is not None else scan_mod_units(profile_id, str(layout.game_root))
    names = []
    for unit in units:
        if unit.group != "ue4ss_mod" or not unit.is_dir or unit.name.casefold() in {"mods.txt", "dwmapi.dll"}:
            continue
        # UE4SS automatically starts a mod directory that carries enabled.txt.
        # Keep those launcher/runtime-managed mods out of the generated control file.
        if _unit_has_enabled_txt(unit):
            continue
        names.append(unit.name)
    target = layout.mods_txt
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8", errors="ignore") if target.exists() else ""
    previous_mode = target.stat().st_mode if target.exists() else None
    if previous_mode is not None:
        try:
            target.chmod(previous_mode | 0o200)
        except OSError:
            pass
    tmp = target.with_suffix(target.suffix + ".dragonwilds.tmp")
    try:
        tmp.write_text(_mods_txt_lines(names, existing), encoding="utf-8")
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    # Launcher-owned control state remains editable by the runtime and operator.
    try:
        target.chmod(target.stat().st_mode | 0o222)
    except OSError:
        pass
    return {"ok": True, "path": str(target), "enabled": names, "count": len(names)}


def build_client_mods_txt(units: list[ModUnit], existing_text: str = "", mode: str = "auto") -> str:
    # This file controls only mods that need an explicit mods.txt entry.
    # RuneSchema and any mod carrying enabled.txt self-enable and are omitted.
    selected = client_ue4ss_enablement(units, existing_text, mode)
    return _mods_txt_lines(selected, existing_text)


def persist_unit_overrides(profile_id: str, units: list[ModUnit]) -> None:
    profile = load_server_profile(profile_id)
    overrides = profile.setdefault("unit_overrides", {})
    for order, unit in enumerate(units):
        current = dict(overrides.get(unit.key) or {})
        current.update({"classification": unit.classification, "category": unit.category, "order": order,
                        "source": normalize_mod_source(unit.source), "hotload_capable": bool(getattr(unit, "hotload_capable", False)),
                        "tags": list(getattr(unit, "tags", []) or [])[:24]})
        overrides[unit.key] = current
    save_server_profile(profile_id, profile)


def set_mod_classification_fast(profile_id: str, key: str, classification: str) -> dict:
    """Persist a presentation/distribution mode without rescanning a live share.

    World Management already obtained the unit from inventory. Mode changes only
    affect profile metadata, so walking every file on a remote server again makes
    the click needlessly expensive. Publish & Push performs the authoritative
    rescan before exposing the new manifest.
    """
    if classification not in {"player_required", "server_only"}:
        raise ValueError("classification must be player_required or server_only")
    group, separator, name = str(key or "").partition("::")
    if separator != "::" or group not in {"ue4ss_mod", "runeschema_mod", "pak_mod"} or not name.strip():
        raise ValueError("A user-manageable mod key is required")
    if len(name) > 240 or name.casefold() in {"mods.txt", "dwmapi.dll"}:
        raise ValueError("Runtime/control infrastructure cannot be assigned a mod mode")
    profile = load_server_profile(profile_id)
    if not profile:
        raise KeyError("Server World not found")
    overrides = profile.setdefault("unit_overrides", {})
    current = dict(overrides.get(key) or {})
    current["classification"] = classification
    overrides[key] = current
    save_server_profile(profile_id, profile)
    return {"key": key, "classification": classification, "pending_publish": True}


def apply_unit_update(profile_id: str, game_root: str, key: str, classification: str | None = None,
                      category: str | None = None, hotload_capable: bool | None = None, tags=None) -> list[ModUnit]:
    units = scan_mod_units(profile_id, game_root)
    unit = next((u for u in units if u.key == key), None)
    if unit is None:
        raise KeyError("Mod unit not found")
    if classification is not None:
        if classification not in ("player_required", "server_only"):
            raise ValueError("classification must be player_required or server_only")
        unit.classification = classification
    if category is not None:
        if category not in ("permanent", "temporary"):
            raise ValueError("category must be permanent or temporary")
        unit.category = category
    if hotload_capable is not None:
        if unit.group not in ("ue4ss_mod", "runeschema_mod"):
            raise ValueError("Hotload capability applies to UE4SS Lua and RuneSchema mod units.")
        unit.hotload_capable = bool(hotload_capable)
        if unit.source_dir is not None:
            set_hotload_marker(unit.source_dir, unit.hotload_capable)
    if tags is not None:
        unit.tags = normalize_tags(tags)
        if unit.group in ("ue4ss_mod", "runeschema_mod") and unit.source_dir is not None:
            set_tags_file(unit.source_dir, unit.tags)
    persist_unit_overrides(profile_id, units)
    return units


def move_mod_unit(profile_id: str, game_root: str, key: str, direction: int = 0,
                  target_index: int | None = None) -> list[ModUnit]:
    units = scan_mod_units(profile_id, game_root)
    unit = next((u for u in units if u.key == key), None)
    if unit is None:
        raise KeyError("Mod unit not found")
    if unit.group == "runeschema_mod":
        raise ValueError("RuneSchema mods do not have a launcher-managed load order.")
    if unit.group not in {"pak_mod", "ue4ss_mod"}:
        raise ValueError("This runtime unit does not support load ordering.")
    group_units = [u for u in units if u.group == unit.group]
    index = next(i for i, item in enumerate(group_units) if item.key == key)
    target = (index + (1 if direction > 0 else -1)) if target_index is None else int(target_index)
    target = max(0, min(len(group_units) - 1, target))
    if target != index:
        moved = group_units.pop(index)
        group_units.insert(target, moved)
    ordered_keys = [u.key for u in group_units]
    ordered_group = {u.key: u for u in group_units}
    # Persist an order that is stable inside each runtime family without crossing categories.
    profile = load_server_profile(profile_id)
    overrides = profile.setdefault("unit_overrides", {})
    for order, item in enumerate(group_units):
        current = dict(overrides.get(item.key) or {})
        current.update({"classification": item.classification, "category": item.category, "order": order,
                        "source": normalize_mod_source(item.source), "hotload_capable": bool(getattr(item, "hotload_capable", False)),
                        "tags": list(getattr(item, "tags", []) or [])[:24]})
        overrides[item.key] = current
    save_server_profile(profile_id, profile)
    if unit.group == "pak_mod":
        layout = resolve_server_layout(game_root)
        _materialize_pak_order(layout.paks_mods_dir, [ordered_group[k].name for k in ordered_keys])
    elif unit.group == "ue4ss_mod":
        generate_server_mods_txt(profile_id, game_root)
    return scan_mod_units(profile_id, game_root)


def bulk_set_classification(profile_id: str, game_root: str, section: str,
                            classification: str = "player_required") -> list[ModUnit]:
    if classification not in ("player_required", "server_only"):
        raise ValueError("classification must be player_required or server_only")
    section = str(section or "").strip().lower()
    groups = {
        "paks": {"pak_mod"},
        "ue4ss": {"ue4ss_core", "ue4ss_mod"},
        "runeschema": {"runeschema", "runeschema_mod"},
        "all": set(UNIT_GROUP_SECTION),
    }.get(section)
    if not groups:
        raise ValueError("section must be paks, ue4ss, runeschema, or all")
    units = scan_mod_units(profile_id, game_root)
    matched = [unit for unit in units if unit.group in groups]
    if not matched:
        raise ValueError(f"No {section} mod units are installed for this World.")
    for unit in matched:
        unit.classification = classification
    persist_unit_overrides(profile_id, units)
    return units


class SyncState:
    STATUS_PER_IP_MIN_INTERVAL = 2.0
    STATUS_GLOBAL_MAX_PER_SEC = 10

    def __init__(self):
        self.lock = threading.RLock()
        self.password = ""
        self.server_key = ""
        self.share_access_key = ""
        self.allow_shared_access = True
        self.manifest = {"profile_id": "", "profile_name": "", "version": 0, "files": [],
                         "manifest_fingerprint": "", "component_fingerprints": {},
                         "description": "", "tags": [], "mod_badges": ["VANILLA"], "icon_b64": "",
                         "banner_b64": "", "mod_summary": [], "game_port": 7777,
                         "rating_average": 0.0, "rating_count": 0, "hw_stats": {}, "network_health": {},
                         "runtime_stack": {}, "connection": {}, "external_hierarchy": {}, "service_notice": {}, "player_map": {}, "world_save_download": {}}
        self.tokens: set[str] = set()
        self.token_sources: dict[str, dict] = {}
        self.pending_nonces: dict[str, float] = {}
        self._auth_attempts: dict[str, list[float]] = {}
        self._nonce_attempts: dict[str, list[float]] = {}
        self.client_reports: dict[str, dict] = {}
        self.activities: list[dict] = []
        self.server_online: bool | None = None
        self.player_count: int | None = None
        self.server_start_ts: float | None = None
        self.active_profile_id: str | None = None
        self._feedback_last: dict[str, float] = {}
        self.worldsave_source_dir: str = ""
        # Metadata heartbeat revision is intentionally separate from the file-manifest
        # version. Presentation/health/runtime notices can change without forcing a
        # client file sync. Clients poll /status lightly and fetch /metadata only when
        # this revision changes.
        self.metadata_revision: int = 0
        self._status_last_served: dict[str, float] = {}
        self._status_recent: list[float] = []
        self.access_policy: dict = normalize_access_policy({})
        self._country_cache: dict[str, tuple[float, dict]] = {}
        self.lan_trust_enabled: bool = True
        self.tls_active: bool = False
        self.tls_cert_fingerprint: str = ""
        self.allow_tls_password_fallback: bool = False

    def activity(self, ip: str, message: str):
        with self.lock:
            self.activities.append({"ts": time.time(), "ip": ip, "message": message})
            self.activities = self.activities[-500:]

    def touch_metadata(self) -> int:
        """Advance the lightweight World metadata heartbeat revision.

        This never changes the file manifest version and therefore never implies
        that clients need to download files.
        """
        with self.lock:
            self.metadata_revision = max(self.metadata_revision, int(self.manifest.get("metadata_revision") or 0)) + 1
            self.manifest["metadata_revision"] = self.metadata_revision
            return self.metadata_revision

    def configure_access_policy(self, global_policy=None, world_policy=None):
        with self.lock:
            self.access_policy = merge_access_policies(global_policy, world_policy)

    def configure_access_blocks(self, blocked_ips: list[str], blocked_countries: list[str]):
        # Backward-compatible bridge for older callers/profiles.
        self.configure_access_policy({}, {"blocked_ips": blocked_ips, "blocked_countries": blocked_countries})

    def _geo_for(self, client_ip: str, *, allow_lookup: bool = True) -> dict:
        """Best-effort country/region for an IP, shared by policy checks and
        the connected-clients display. Private/loopback addresses never leave
        the machine (there's nothing to look up); results are cached 24h."""
        try:
            address = ipaddress.ip_address(client_ip)
        except ValueError:
            return {}
        if address.is_private or address.is_loopback:
            return {"country": "", "region": "", "lan": True}
        now = time.time(); cached = self._country_cache.get(client_ip)
        if cached and now - cached[0] < 86400:
            return dict(cached[1])
        if not allow_lookup:
            return {}
        try:
            req = urllib.request.Request(f"https://ipapi.co/{client_ip}/json/", headers={"User-Agent": "DragonwildsSync/2"})
            with urllib.request.urlopen(req, timeout=2.5) as response:
                data = json.loads(response.read().decode("utf-8", "replace"))
            country = str(data.get("country_code") or data.get("country") or "").strip().upper()
            continent = str(data.get("continent_code") or "").strip().upper()
            city = str(data.get("city") or "").strip()
            geo = {"country": country if len(country) == 2 else "", "region": continent if continent in REGION_LABELS else "", "city": city, "lan": False}
            self._country_cache[client_ip] = (now, geo)
            return dict(geo)
        except Exception:
            # Geo/reputation lookups fail open/blank. Direct IP/CIDR policy remains authoritative for blocking.
            return {}

    def connection_blocked(self, client_ip: str) -> tuple[bool, str]:
        try:
            address = ipaddress.ip_address(client_ip)
        except ValueError:
            return False, ""
        with self.lock:
            policy = normalize_access_policy(self.access_policy)
        matched, reason = direct_policy_match(client_ip, policy)
        if matched:
            return True, reason
        country_rules = set(policy.get("blocked_countries") or [])
        region_rules = set(policy.get("blocked_regions") or [])
        if (not country_rules and not region_rules) or not policy.get("geo_lookup_enabled", True) or address.is_private or address.is_loopback:
            return False, ""
        geo = self._geo_for(client_ip)
        if not geo:
            return False, ""
        if geo.get("country") in country_rules:
            return True, f"country policy {geo['country']}"
        if geo.get("region") in region_rules:
            return True, f"region policy {REGION_LABELS.get(geo['region'], geo['region'])}"
        return False, ""

    def connected_clients(self) -> list[dict]:
        """Currently-authenticated clients, one entry per distinct IP.

        Backed by live session tokens (issued on /auth or /lan-auth and
        refreshed on every authenticated request), not the opt-in network
        health samples in ``client_reports`` -- so this reflects who can
        actually reach this World right now, not just who chose to submit a
        diagnostic. Location is best-effort and never looked up live here
        (cache-only) so listing connections never blocks on a network call.
        """
        now = time.time()
        with self.lock:
            sources = dict(self.token_sources)
            reports = dict(self.client_reports)
        by_ip: dict[str, dict] = {}
        for token, ctx in sources.items():
            ip = str(ctx.get("client_ip") or "").strip()
            if not ip:
                continue
            issued_at = float(ctx.get("issued_at") or 0)
            if not issued_at or now - issued_at > TOKEN_TTL_SECONDS:
                continue
            last_seen = float(ctx.get("last_seen") or issued_at)
            existing = by_ip.get(ip)
            if existing and existing["last_seen"] >= last_seen:
                continue
            geo = self._geo_for(ip, allow_lookup=False)
            network = next((r.get("network") for r in reports.values() if isinstance(r, dict) and r.get("ip") == ip and r.get("network")), None)
            by_ip[ip] = {
                "ip": ip, "profile_id": ctx.get("client_profile_id") or "", "credential_source": ctx.get("credential_source") or "", "auth_mode": ctx.get("auth_mode") or "",
                "connected_since": issued_at, "last_seen": last_seen,
                "country": geo.get("country") or "", "region": geo.get("region") or "", "city": geo.get("city") or "",
                "lan": bool(geo.get("lan")), "network": network or {},
            }
        return sorted(by_ip.values(), key=lambda item: -item["last_seen"])

    def kick(self, client_ip: str) -> int:
        """Revoke every active session token for this IP.

        This is a soft kick: the client's *next* poll/request gets a 401 and
        must re-authenticate (there is no persistent socket to sever -- Sync
        is a polling REST API), so a re-entered password/key reconnects them
        immediately. Combine with an access-policy IP block for a hard kick
        that also refuses reconnection.
        """
        target = str(client_ip or "").strip()
        if not target:
            return 0
        with self.lock:
            stale = [token for token, ctx in self.token_sources.items() if str(ctx.get("client_ip") or "") == target]
            for token in stale:
                self.tokens.discard(token)
                self.token_sources.pop(token, None)
        if stale:
            self.activity(target, f"kicked by host ({len(stale)} session(s) revoked)")
        return len(stale)

    def allow_status_request(self, client_ip: str) -> bool:
        now = time.time()
        with self.lock:
            if now - self._status_last_served.get(client_ip, 0) < self.STATUS_PER_IP_MIN_INTERVAL:
                return False
            self._status_recent = [t for t in self._status_recent if now - t < 1]
            if len(self._status_recent) >= self.STATUS_GLOBAL_MAX_PER_SEC:
                return False
            self._status_recent.append(now); self._status_last_served[client_ip] = now
            if len(self._status_last_served) > 500:
                self._status_last_served = {ip: t for ip, t in self._status_last_served.items() if now - t < 300}
            return True

    def _rate_allow(self, store: dict[str, list[float]], client_ip: str, *, limit: int, window: float) -> bool:
        now = time.time(); key = str(client_ip or "unknown")
        with self.lock:
            recent = [ts for ts in store.get(key, []) if now - ts < window]
            if len(recent) >= limit:
                store[key] = recent
                return False
            recent.append(now); store[key] = recent
            if len(store) > 2000:
                store_keys = list(store.keys())[:500]
                for stale in store_keys:
                    if stale != key and not any(now - ts < window for ts in store.get(stale, [])):
                        store.pop(stale, None)
            return True

    def allow_auth_attempt(self, client_ip: str) -> bool:
        return self._rate_allow(self._auth_attempts, client_ip, limit=12, window=60.0)

    def allow_nonce_request(self, client_ip: str) -> bool:
        return self._rate_allow(self._nonce_attempts, client_ip, limit=30, window=60.0)

    def issue_nonce(self) -> str:
        nonce = secrets.token_hex(16)
        with self.lock:
            cutoff = time.time() - NONCE_TTL_SECONDS
            self.pending_nonces = {n: ts for n, ts in self.pending_nonces.items() if ts >= cutoff}
            if len(self.pending_nonces) >= 4096:
                for key, _ts in sorted(self.pending_nonces.items(), key=lambda item: item[1])[:1024]:
                    self.pending_nonces.pop(key, None)
            self.pending_nonces[nonce] = time.time()
        return nonce

    def check_proof(self, nonce: str, proof: str, *, mode: str = "world_password", credential_source: str = "linked", client_ip: str = "", client_profile_id: str = "") -> dict | None:
        source = str(credential_source or "linked").strip().lower()[:32]
        if source not in {"linked", "manual", "imported-rsdwl", "online-feed", "legacy-linked", "shared"}:
            source = "linked"
        mode = "world_password"
        with self.lock:
            issued = self.pending_nonces.pop(nonce, None)
            if issued is None or time.time() - issued > NONCE_TTL_SECONDS:
                return None
            # STATE.password is hot-applied from the active profile's exact
            # dedicated_config.world_pass when its Sync share is published.
            # Never mix it with legacy sync passwords or saved client fields.
            world_password = str(self.password or "").strip()
        expected = hmac.new(world_password.encode(), nonce.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(proof or "")):
            return None
        profile_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(client_profile_id or "").strip())[:96]
        with self.lock:
            if profile_id and profile_id in set(normalize_access_policy(self.access_policy).get("blocked_profile_ids") or []):
                return {"blocked": True, "reason": f"profile policy {profile_id}", "client_profile_id": profile_id}
        with self.lock:
            scope = "world-sync"
            token = secrets.token_hex(16)
            self.tokens.add(token)
            self.token_sources[token] = {"credential_source": source, "auth_mode": mode, "scope": scope, "client_ip": str(client_ip or ""),
                                         "client_profile_id": profile_id, "issued_at": time.time()}
            # The same World Password protects Sync payloads and Dragonwilds.
            # Public heartbeat/identity metadata does not require this token.
            return {"token": token, **self.token_sources[token]}

    def check_tls_password(self, password: str, *, credential_source: str = "linked", client_ip: str = "", client_profile_id: str = "") -> dict | None:
        """TLS-only compatibility authentication; caller must enforce TLS."""
        with self.lock:
            if not self.tls_active or not self.allow_tls_password_fallback:
                return None
            expected = str(self.password or "").strip()
        supplied = str(password or "").strip()
        if not hmac.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8")):
            return None
        profile_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(client_profile_id or "").strip())[:96]
        with self.lock:
            if profile_id and profile_id in set(normalize_access_policy(self.access_policy).get("blocked_profile_ids") or []):
                return {"blocked": True, "reason": f"profile policy {profile_id}", "client_profile_id": profile_id}
            source = str(credential_source or "linked").strip().lower()[:32]
            if source not in {"linked", "manual", "imported-rsdwl", "online-feed", "legacy-linked", "shared"}: source = "linked"
            token = secrets.token_hex(16)
            self.tokens.add(token)
            self.token_sources[token] = {"credential_source": source, "auth_mode": "tls_password_fallback", "scope": "world-sync",
                                         "client_ip": str(client_ip or ""), "client_profile_id": profile_id, "issued_at": time.time()}
            return {"token": token, **self.token_sources[token]}

    def check_token(self, token: str) -> bool:
        with self.lock:
            if token not in self.tokens:
                return False
            context = self.token_sources.get(token) or {}
            issued_at = float(context.get("issued_at") or 0)
            if not issued_at or time.time() - issued_at > TOKEN_TTL_SECONDS:
                self.tokens.discard(token)
                self.token_sources.pop(token, None)
                return False
            context["last_seen"] = time.time()
            self.token_sources[token] = context
            return True

    def token_context(self, token: str) -> dict:
        if not self.check_token(token):
            return {}
        with self.lock:
            return dict(self.token_sources.get(token) or {})

    def issue_lan_token(self, client_ip: str, client_profile_id: str = "") -> str | None:
        """Issue a bearer token to a same-LAN or explicitly trusted IP.

        This is the password/key bypass used by LAN placards. It is deliberately
        constrained to private/link-local addresses and the host's own LAN subnet;
        WAN clients still require the saved World password + Server Key.
        """
        with self.lock:
            enabled = bool(self.lan_trust_enabled)
            policy = normalize_access_policy(self.access_policy)
        trusted, trusted_reason = trusted_ip_match(str(client_ip or ""), policy)
        try:
            client = ipaddress.ip_address(str(client_ip).split('%', 1)[0])
            local = ipaddress.ip_address(local_ip_guess().split('%', 1)[0])
        except ValueError:
            return None
        same_lan = False
        if enabled and client.is_loopback:
            same_lan = True
        elif enabled and (client.is_private or client.is_link_local):
            # VPN and virtual adapters can own the default route. Compare the
            # client against every local interface instead of one guessed NIC.
            for host_address in local_interface_addresses(default=str(local)):
                if host_address.version != client.version:
                    continue
                prefix = 24 if client.version == 4 else 64
                if client in ipaddress.ip_network(f"{host_address}/{prefix}", strict=False):
                    same_lan = True
                    break
        if not same_lan and not trusted:
            return None
        token = secrets.token_hex(16)
        source = "lan" if same_lan else "ip_allowlist"
        profile_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(client_profile_id or "").strip())[:96]
        with self.lock:
            self.tokens.add(token)
            self.token_sources[token] = {"credential_source": source, "auth_mode": source, "scope": "world-sync",
                                         "client_ip": str(client_ip or ""), "trust_reason": trusted_reason if trusted else "same LAN subnet",
                                         "client_profile_id": profile_id, "issued_at": time.time()}
        return token

    def record_client_network(self, client_id: str, client_ip: str, network: dict | None) -> dict:
        clean = {}
        incoming = network if isinstance(network, dict) else {}
        for key in ("ping_ms", "host_to_client_mbps", "client_to_host_mbps", "client_internet_down_mbps", "client_internet_up_mbps"):
            try:
                value = float(incoming.get(key))
                if 0 <= value < 1_000_000:
                    clean[key] = round(value, 3)
            except (TypeError, ValueError):
                pass
        with self.lock:
            current = dict(self.client_reports.get(client_id) or {})
            current.update({"ts": time.time(), "ip": client_ip})
            if clean:
                current["network"] = {**(current.get("network") or {}), **clean}
            self.client_reports[client_id] = current
            return dict(current)

    def network_summary(self, uptime_seconds=None) -> dict:
        with self.lock:
            reports = dict(self.client_reports)
            online = self.server_online
        return summarize_client_reports(reports, uptime_seconds=uptime_seconds, online=online)

    def server_health_summary(self, uptime_seconds=None) -> dict:
        with self.lock:
            profile_id = self.active_profile_id
            hw_stats = dict(self.manifest.get("hw_stats") or {})
            online = self.server_online
        profile = load_server_profile(profile_id) if profile_id else {}
        config = normalize_health_config((profile or {}).get("health_config"))
        hierarchy = (profile or {}).get("hierarchy") if isinstance((profile or {}).get("hierarchy"), dict) else {}
        compatibility = (profile or {}).get("compatibility_reports") or []
        valid_reports = sum(1 for item in compatibility if isinstance(item, dict) and item.get("success") is True)
        config["external_validation"] = {
            "provider": str(hierarchy.get("provider") or "shrug.games"),
            "hierarchy_confirmed": bool(hierarchy.get("confirmed")),
            "hierarchy_confirmed_at": hierarchy.get("confirmed_at"),
            "validated_client_reports": valid_reports,
        }
        result = score_server_health(
            hw_stats=hw_stats, network_health=self.network_summary(uptime_seconds),
            health_config=config, uptime_seconds=uptime_seconds, online=online,
            runtime_stack=dict(self.manifest.get("runtime_stack") or {}))
        if isinstance(result.get("hardware"), dict):
            result["hardware"]["references"] = public_health_config(config).get("hardware_reference") or {}
        return result


STATE = SyncState()


class SyncHandler(BaseHTTPRequestHandler):
    server_version = "DragonwildsSync/2"

    def _send_json(self, obj, status=200, extra_headers=None):
        body = json.dumps(obj).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json")
        for key, value in (extra_headers or {}).items():
            self.send_header(str(key), str(value))
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _auth_token(self) -> str:
        auth = self.headers.get("Authorization", "")
        return auth[7:] if auth.startswith("Bearer ") else ""

    def _auth_ok(self):
        token = self._auth_token()
        return bool(token and STATE.check_token(token))

    def _auth_context(self) -> dict:
        return STATE.token_context(self._auth_token())

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length < 0 or length > 64 * 1024:
            raise ValueError("request body too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def _read_bytes(self, max_bytes: int = 512 * 1024):
        length = int(self.headers.get("Content-Length", 0))
        if length < 0 or length > max_bytes:
            raise ValueError("diagnostic payload too large")
        return self.rfile.read(length)

    def _blocked(self):
        blocked, reason = STATE.connection_blocked(self.client_address[0])
        if blocked:
            STATE.activity(self.client_address[0], f"blocked before authentication ({reason})")
            kind = "country" if reason.startswith("country policy") else "region" if reason.startswith("region policy") else "ip"
            self._send_json({"error": "blocked by server access policy", "blocked": True, "reason": reason, "reason_kind": kind}, 403)
            return True
        return False

    def do_POST(self):
        if self._blocked(): return
        path = urlparse(self.path).path
        try:
            if path == "/auth":
                if not STATE.allow_auth_attempt(self.client_address[0]):
                    STATE.activity(self.client_address[0], "authentication rate limited")
                    self._send_json({"error": "too many authentication attempts"}, 429); return
                body = self._read_json()
                result = STATE.check_proof(str(body.get("nonce", "")), str(body.get("proof", "")),
                                           mode="world_password",
                                           credential_source=str(body.get("credential_source") or "linked"),
                                           client_ip=self.client_address[0], client_profile_id=str(body.get("client_profile_id") or ""))
                if result and result.get("blocked"):
                    STATE.activity(self.client_address[0], f"blocked authenticated profile ({result.get('client_profile_id')})")
                    self._send_json({"error": "blocked by server access policy", "blocked": True,
                                     "reason": result.get("reason"), "reason_kind": "profile"}, 403); return
                if result:
                    STATE.activity(self.client_address[0], f"authenticated via {result.get('credential_source')} ({result.get('auth_mode')})")
                    self._send_json({"token": result.get("token"), "credential_source": result.get("credential_source"), "scope": result.get("scope"),
                                     "auth_mode": "hmac_sha256_nonce"})
                else:
                    STATE.activity(self.client_address[0], "failed authentication")
                    self._send_json({"error": "invalid or expired proof"}, 401)
                return
            if path == "/auth/password-fallback":
                if not isinstance(self.connection, ssl.SSLSocket):
                    self._send_json({"error": "TLS is required for password fallback"}, 426, {"Cache-Control": "no-store"}); return
                if not STATE.allow_auth_attempt(self.client_address[0]):
                    self._send_json({"error": "too many authentication attempts"}, 429, {"Cache-Control": "no-store"}); return
                body = self._read_json()
                result = STATE.check_tls_password(str(body.get("password") or ""), credential_source=str(body.get("credential_source") or "linked"),
                                                  client_ip=self.client_address[0], client_profile_id=str(body.get("client_profile_id") or ""))
                if result and result.get("blocked"):
                    self._send_json({"error": "blocked by server access policy", "blocked": True, "reason": result.get("reason"),
                                     "reason_kind": "profile"}, 403, {"Cache-Control": "no-store"}); return
                if not result:
                    STATE.activity(self.client_address[0], "failed TLS password fallback")
                    self._send_json({"error": "invalid password or fallback disabled"}, 401, {"Cache-Control": "no-store"}); return
                STATE.activity(self.client_address[0], f"authenticated via TLS password fallback ({result.get('client_profile_id') or 'legacy client'})")
                self._send_json({"token": result.get("token"), "credential_source": result.get("credential_source"),
                                 "scope": result.get("scope"), "auth_mode": "tls_password_fallback"}, 200, {"Cache-Control": "no-store"})
                return
            if not self._auth_ok():
                self._send_json({"error": "unauthorized"}, 401); return
            if path == "/character-submissions":
                with STATE.lock: profile_id = STATE.active_profile_id
                profile = load_server_profile(profile_id) if profile_id else {}
                sharing = profile.get("character_sharing") if isinstance(profile.get("character_sharing"), dict) else {}
                if not profile_id or not sharing.get("allow_submissions"):
                    self._send_json({"error": "This World is not accepting character submissions."}, 403); return
                payload = self._read_bytes(32 * 1024 * 1024)
                result = quarantine_submission_bytes(profile_id, payload, file_name=str(self.headers.get("X-DWS-File-Name") or "character.rsdwl"),
                                                     client_id=str(self.headers.get("X-DWS-Client") or ""), remote_ip=self.client_address[0])
                STATE.activity(self.client_address[0], f"submitted character '{result.get('player_name') or result.get('file_name')}' to quarantine")
                self._send_json({"ok": True, "status": "quarantined", "submission": result}, 202); return
            if path == "/player-backups":
                with STATE.lock: profile_id = STATE.active_profile_id
                profile = load_server_profile(profile_id) if profile_id else {}
                sharing = profile.get("character_sharing") if isinstance(profile.get("character_sharing"), dict) else {}
                player_profile_id = str(self._auth_context().get("client_profile_id") or "").strip()
                if not profile_id or not sharing.get("request_backups"):
                    self._send_json({"error": "This World is not retaining player save backups."}, 403); return
                if not player_profile_id:
                    self._send_json({"error": "An authenticated player profile is required for backup recovery."}, 403); return
                payload = self._read_bytes(32 * 1024 * 1024)
                result = store_player_backup(profile_id, player_profile_id, payload, remote_ip=self.client_address[0])
                STATE.activity(self.client_address[0], f"retained player save backup for profile {player_profile_id}")
                self._send_json({"ok": True, "status": "retained", "backup": result}, 201); return
            if path == "/diagnostics/upload":
                data = self._read_bytes(); client_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(self.headers.get("X-DWS-Client") or self.client_address[0]))[:64]
                STATE.activity(self.client_address[0], f"network diagnostic upload ({len(data)} bytes)")
                self._send_json({"ok": True, "bytes_received": len(data), "client_id": client_id}); return
            if path == "/diagnostics/report":
                body = self._read_json(); client_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(body.get("client_id") or self.client_address[0]))[:64] or "client"
                STATE.record_client_network(client_id, self.client_address[0], body.get("network") if isinstance(body.get("network"), dict) else {})
                if isinstance(body.get("client_runtime"), dict):
                    with STATE.lock:
                        current = dict(STATE.client_reports.get(client_id) or {})
                        current["client_runtime"] = dict(body.get("client_runtime") or {})
                        STATE.client_reports[client_id] = current
                uptime = max(0, time.time() - STATE.server_start_ts) if STATE.server_online and STATE.server_start_ts else None
                network_health = STATE.network_summary(uptime); server_health = STATE.server_health_summary(uptime)
                STATE.activity(self.client_address[0], f"client '{client_id}' completed a network health sample")
                self._send_json({"ok": True, "network_health": network_health, "server_health": server_health}); return
            if path == "/report":
                body = self._read_json(); client_id = str(body.get("client_id") or self.client_address[0])
                client_platform = normalize_client_platform(body.get("client_platform") or self.headers.get("X-DWS-Client-Platform"))
                client_files = {f["path"]: f.get("sha256") for f in body.get("files", []) if isinstance(f, dict) and f.get("path")}
                with STATE.lock:
                    expected = filtered_manifest(STATE.manifest, client_platform)
                    server_files = {f["path"]: f.get("sha256") for f in expected.get("files", [])}
                missing = [p for p in server_files if p not in client_files]
                extra = [p for p in client_files if p not in server_files]
                mismatched = [p for p in server_files if p in client_files and client_files[p] != server_files[p]]
                result = {"status": "match" if not (missing or extra or mismatched) else "mismatch",
                          "missing": missing, "extra": extra, "mismatched": mismatched}
                network = body.get("network") if isinstance(body.get("network"), dict) else {}
                with STATE.lock:
                    previous = dict(STATE.client_reports.get(client_id) or {})
                    STATE.client_reports[client_id] = {**previous, **result, "ts": time.time(), "ip": self.client_address[0],
                                                       "client_platform": client_platform}
                    if isinstance(body.get("client_runtime"), dict):
                        STATE.client_reports[client_id]["client_runtime"] = dict(body.get("client_runtime") or {})
                if network:
                    STATE.record_client_network(client_id, self.client_address[0], network)
                STATE.activity(self.client_address[0], f"client '{client_id}' reported {result['status']}")
                self._send_json(result); return
            if path == "/compatibility":
                body = self._read_json()
                client_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(body.get("client_id") or self.client_address[0]))[:64] or "client"
                success = bool(body.get("success", True))
                note = unicodedata.normalize("NFKC", str(body.get("note") or "")).strip()[:400]
                runtime = body.get("client_runtime") if isinstance(body.get("client_runtime"), dict) else {}
                with STATE.lock:
                    profile_id = STATE.active_profile_id
                if not profile_id:
                    raise ValueError("no active World")
                profile = load_server_profile(profile_id)
                entries = profile.setdefault("compatibility_reports", [])
                entries.append({
                    "client_id": client_id, "success": success, "note": note,
                    "client_runtime": runtime, "ip": self.client_address[0], "received_at": time.time(),
                })
                profile["compatibility_reports"] = entries[-200:]
                save_server_profile(profile_id, profile)
                STATE.activity(self.client_address[0], f"client '{client_id}' {'validated' if success else 'reported a compatibility issue with'} the World")
                uptime = max(0, time.time() - STATE.server_start_ts) if STATE.server_online and STATE.server_start_ts else None
                self._send_json({"ok": True, "validated_reports": sum(1 for x in profile["compatibility_reports"] if x.get("success") is True),
                                 "server_health": STATE.server_health_summary(uptime)})
                return
            if path == "/feedback":
                body = self._read_json(); rating = body.get("rating"); client_id = str(body.get("client_id") or "")
                report = unicodedata.normalize("NFKC", str(body.get("report") or "")).strip()
                if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
                    raise ValueError("rating must be an integer from 1 to 5")
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", client_id): raise ValueError("invalid client id")
                if len(report) > 250 or any(ord(ch) < 32 and ch not in "\n\t" for ch in report): raise ValueError("review must be 250 characters or fewer")
                now = time.time(); ip = self.client_address[0]
                with STATE.lock:
                    if now - STATE._feedback_last.get(ip, 0) < 10:
                        self._send_json({"error": "feedback rate limited"}, 429); return
                    STATE._feedback_last[ip] = now; profile_id = STATE.active_profile_id
                if not profile_id:
                    self._send_json({"error": "no active World"}, 404); return
                if profile_id:
                    profile = load_server_profile(profile_id)
                    entries = profile.setdefault("feedback", [])
                    ip_hash = hmac.new(_review_secret(), f"{profile_id}|{ip}".encode(), hashlib.sha256).hexdigest()
                    prior = next((entry for entry in reversed(entries) if entry.get("ip_hash") == ip_hash and review_integrity_valid(entry)), None)
                    if prior and now - float(prior.get("received_at") or 0) < 30 * 86400:
                        self._send_json({"error": "one review per network per World every 30 days"}, 429); return
                    entry = {"id": secrets.token_hex(12), "world_id": profile_id, "client_id": client_id,
                             "rating": rating, "report": report, "ip_hash": ip_hash, "received_at": now}
                    entry["integrity"] = review_integrity(entry); entries.append(entry)
                    avg, count = profile_rating_summary(profile); profile["rating_average"] = avg; profile["rating_count"] = count
                    save_server_profile(profile_id, profile)
                    with STATE.lock:
                        STATE.manifest["rating_average"] = avg; STATE.manifest["rating_count"] = count
                        STATE.touch_metadata()
                STATE.activity(ip, f"submitted a {rating}/5 World rating"); self._send_json({"ok": True, "review": {key: entry.get(key) for key in ("id", "rating", "received_at", "integrity")}}); return
            self._send_json({"error": "not found"}, 404)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._send_json({"error": str(exc)}, 400)

    def do_GET(self):
        if self._blocked(): return
        path = urlparse(self.path).path
        if path == "/ping": self._send_json({"ok": True}); return
        if path == "/status":
            compact = "compact=1" in urlparse(self.path).query
            if not STATE.allow_status_request(self.client_address[0]): self._send_json({"error": "poll_backoff", "retry_after": self.STATUS_PER_IP_MIN_INTERVAL}, 429, {"Retry-After": str(int(max(1, self.STATUS_PER_IP_MIN_INTERVAL)))}); return
            with STATE.lock:
                uptime = max(0, time.time() - STATE.server_start_ts) if STATE.server_online and STATE.server_start_ts else None
                network_health = STATE.network_summary(uptime)
                server_health = STATE.server_health_summary(uptime)
                self._send_json({"ok": True, "server_online": STATE.server_online, "player_count": STATE.player_count,
                                 "uptime_seconds": uptime, "profile_id": STATE.manifest.get("profile_id"),
                                 "profile_name": STATE.manifest.get("profile_name"), "manifest_version": STATE.manifest.get("version", 0),
                                 "metadata_revision": STATE.manifest.get("metadata_revision", STATE.metadata_revision),
                                 "launcher_fingerprint": STATE.manifest.get("launcher_fingerprint") or "",
                                 "world_sync": STATE.manifest.get("world_sync") or {},
                                 "classification": STATE.manifest.get("classification") or {},
                                 "audience": STATE.manifest.get("audience") or "general",
                                 "platform_compatibility": STATE.manifest.get("platform_compatibility") or {"pc": True},
                                 "console_policy": STATE.manifest.get("console_policy") or {},
                                 "tags": STATE.manifest.get("tags") or [],
                                 "mod_badges": STATE.manifest.get("mod_badges") or [],
                                 "mod_summary": [] if compact else (STATE.manifest.get("mod_summary") or []),
                                 "description": STATE.manifest.get("description") or "",
                                 "icon_b64": "" if compact else (STATE.manifest.get("icon_b64") or ""),
                                 "banner_b64": "" if compact else (STATE.manifest.get("banner_b64") or ""),
                                 "placard_background": STATE.manifest.get("placard_background") or "1",
                                 "rating_average": STATE.manifest.get("rating_average") or 0,
                                 "rating_count": STATE.manifest.get("rating_count") or 0,
                                 "community": STATE.manifest.get("community") or {},
                                 "community_rules": STATE.manifest.get("community_rules") or "",
                                 "shared_character_count": len(STATE.manifest.get("starter_characters") or []),
                                 "character_submissions_open": bool((STATE.manifest.get("character_sharing") or {}).get("allow_submissions")),
                                 "character_backup_requested": bool((STATE.manifest.get("character_sharing") or {}).get("request_backups")),
                                 "network_health": network_health, "server_health": server_health,
                                 "runtime_stack": STATE.manifest.get("runtime_stack") or {},
                                 "connection": STATE.manifest.get("connection") or {},
                                 "external_hierarchy": STATE.manifest.get("external_hierarchy") or {},
                                 "service_notice": STATE.manifest.get("service_notice") or {},
                                 "operator_identity": signed_operator_world_identity(STATE.manifest),
                                 "world_save_download": STATE.manifest.get("world_save_download") or {}})
            return
        if path == "/identity":
            # Public, bounded presentation metadata. The directory only points at
            # this endpoint; the launcher validates the live fingerprint and exact
            # World name before caching anything. Credentials and file manifests
            # are never included here.
            with STATE.lock:
                compact = "compact=1" in urlparse(self.path).query
                payload = {
                    "schema": "DragonwildsSync.WorldIdentity.v1",
                    "profile_id": STATE.manifest.get("profile_id"),
                    "profile_name": STATE.manifest.get("profile_name"),
                    "description": STATE.manifest.get("description") or "",
                    "classification": STATE.manifest.get("classification") or {},
                    "audience": STATE.manifest.get("audience") or "general",
                    "platform_compatibility": STATE.manifest.get("platform_compatibility") or {"pc": True},
                    "console_policy": STATE.manifest.get("console_policy") or {},
                    "tags": STATE.manifest.get("tags") or [],
                    "mod_badges": STATE.manifest.get("mod_badges") or [],
                    "mod_summary": STATE.manifest.get("mod_summary") or [],
                    "icon_b64": STATE.manifest.get("icon_b64") or "",
                    "banner_b64": STATE.manifest.get("banner_b64") or "",
                    "rating_average": STATE.manifest.get("rating_average") or 0,
                    "rating_count": STATE.manifest.get("rating_count") or 0,
                    "community": STATE.manifest.get("community") or {},
                    "community_rules": STATE.manifest.get("community_rules") or "",
                    "password_required": bool(STATE.manifest.get("password_required")),
                    "authentication": STATE.manifest.get("authentication") or {"mode": "world_password", "scope": "world-sync", "challenge": "hmac-sha256-nonce"},
                    "world_sync": STATE.manifest.get("world_sync") or {},
                    "launcher_fingerprint": STATE.manifest.get("launcher_fingerprint") or "",
                    "connection": STATE.manifest.get("connection") or {},
                    "shared_characters": STATE.manifest.get("starter_characters") or [],
                    "shared_character_count": len(STATE.manifest.get("starter_characters") or []),
                    "character_submissions_open": bool((STATE.manifest.get("character_sharing") or {}).get("allow_submissions")),
                    "character_backup_requested": bool((STATE.manifest.get("character_sharing") or {}).get("request_backups")),
                    "operator_identity": signed_operator_world_identity(STATE.manifest),
                }
                if compact:
                    payload["icon_b64"] = ""
                    payload["banner_b64"] = ""
                    payload["shared_characters"] = []
            STATE.activity(self.client_address[0], "downloaded public World identity metadata")
            self._send_json(payload); return
        if path == "/lan-auth":
            token = STATE.issue_lan_token(self.client_address[0], str(self.headers.get("X-DWS-Client-Profile") or ""))
            if not token:
                self._send_json({"error": "LAN trust unavailable"}, 401); return
            with STATE.lock:
                context = STATE.token_sources.get(token) or {}
                payload = {"token": token, "credential_source": context.get("credential_source") or "lan",
                           "auth_mode": context.get("auth_mode") or "lan", "profile_id": STATE.manifest.get("profile_id"),
                           "profile_name": STATE.manifest.get("profile_name"), "connection": STATE.manifest.get("connection") or {}}
            STATE.activity(self.client_address[0], f"authenticated by {payload['auth_mode']} trust")
            self._send_json(payload); return
        if path == "/nonce":
            if not STATE.allow_nonce_request(self.client_address[0]): self._send_json({"error": "too many nonce requests"}, 429); return
            STATE.activity(self.client_address[0], "connecting (requested nonce)"); self._send_json({"nonce": STATE.issue_nonce()}); return
        if not self._auth_ok(): self._send_json({"error": "unauthorized"}, 401); return
        if path == "/metadata":
            with STATE.lock:
                payload = {k: v for k, v in STATE.manifest.items() if k != "files"}
            uptime = max(0, time.time() - STATE.server_start_ts) if STATE.server_online and STATE.server_start_ts else None
            payload["uptime_seconds"] = uptime
            payload["player_count"] = STATE.player_count
            payload["network_health"] = STATE.network_summary(uptime)
            payload["server_health"] = STATE.server_health_summary(uptime)
            STATE.activity(self.client_address[0], f"refreshed World metadata v{payload.get('version', 0)}"); self._send_json(payload); return
        if path == "/reviews":
            with STATE.lock: profile_id = STATE.active_profile_id
            if not profile_id: self._send_json({"reviews": [], "days": 30}); return
            query = urlparse(self.path).query
            try: days = int(next((part.split("=", 1)[1] for part in query.split("&") if part.startswith("days=")), "30"))
            except ValueError: days = 30
            profile = load_server_profile(profile_id); avg, count = profile_rating_summary(profile)
            self._send_json({"reviews": public_reviews(profile, days), "days": max(1, min(days, 90)), "rating_average": avg, "rating_count": count}); return
        if path == "/manifest":
            client_platform = normalize_client_platform(self.headers.get("X-DWS-Client-Platform"))
            with STATE.lock: payload = filtered_manifest(STATE.manifest, client_platform)
            uptime = max(0, time.time() - STATE.server_start_ts) if STATE.server_online and STATE.server_start_ts else None
            payload["network_health"] = STATE.network_summary(uptime)
            payload["server_health"] = STATE.server_health_summary(uptime)
            STATE.activity(self.client_address[0], f"fetched manifest v{payload.get('version', 0)}"); self._send_json(payload); return
        if path == "/players":
            with STATE.lock: allow_remote = bool((STATE.manifest.get("player_map") or {}).get("allow_remote_clients", False))
            if not allow_remote:
                self._send_json({"error": "live player map is server-only"}, 403); return
            self._send_json(PLAYER_SERVICE.status()); return
        if path == "/worldsave/status":
            with STATE.lock: profile_id = STATE.active_profile_id
            if not profile_id: self._send_json({"error": "no active World"}, 404); return
            self._send_json(status_for_ip(profile_id, self.client_address[0])); return
        if path in {"/player-backups/status", "/player-backups/latest"}:
            with STATE.lock: profile_id = STATE.active_profile_id
            profile = load_server_profile(profile_id) if profile_id else {}
            sharing = profile.get("character_sharing") if isinstance(profile.get("character_sharing"), dict) else {}
            player_profile_id = str(self._auth_context().get("client_profile_id") or "").strip()
            if not profile_id or not sharing.get("request_backups"):
                self._send_json({"error": "This World is not retaining player save backups."}, 403); return
            if not player_profile_id:
                self._send_json({"error": "An authenticated player profile is required for backup recovery."}, 403); return
            if path.endswith("/status"):
                self._send_json(player_backup_status(profile_id, player_profile_id)); return
            try: target, record = latest_player_backup(profile_id, player_profile_id)
            except FileNotFoundError as exc:
                self._send_json({"error": str(exc)}, 404); return
            data = target.read_bytes()
            STATE.activity(self.client_address[0], f"restored latest player save backup for profile {player_profile_id}")
            self.send_response(200); self.send_header("Content-Type", "application/vnd.dragonwilds.rsdwl")
            self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
            self.send_header("X-DWS-SHA256", str(record.get("sha256") or ""))
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        if path == "/worldsave/download":
            with STATE.lock:
                profile_id = STATE.active_profile_id
                source_dir = STATE.worldsave_source_dir
            if not profile_id: self._send_json({"error": "no active World"}, 404); return
            access = status_for_ip(profile_id, self.client_address[0])
            if not access.get("enabled"):
                self._send_json({"error": "World save downloads are disabled by the server maintainer", **access}, 403); return
            if not access.get("allowed"):
                self._send_json({"error": "World save download cooldown is active", **access}, 429); return
            try:
                target = build_worldsave_zip(profile_id, source_dir)
                data = target.read_bytes()
                record_download(profile_id, self.client_address[0])
                STATE.activity(self.client_address[0], f"downloaded World save ({len(data)} bytes)")
                self.send_response(200); self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", f'attachment; filename="{profile_id}-world-save.zip"')
                self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
            except FileNotFoundError as exc:
                self._send_json({"error": str(exc)}, 404); return
        if path == "/diagnostics/download":
            query = urlparse(self.path).query
            requested = 256 * 1024
            for part in query.split("&"):
                if part.startswith("size="):
                    try: requested = int(part.split("=", 1)[1])
                    except ValueError: pass
            size = max(1024, min(requested, 512 * 1024)); data = b"\0" * size
            STATE.activity(self.client_address[0], f"network diagnostic download ({size} bytes)")
            self.send_response(200); self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size)); self.end_headers(); self.wfile.write(data); return
        if path == "/backups":
            with STATE.lock: profile_id = STATE.active_profile_id
            if not profile_id: self._send_json({"backups": []}); return
            access = status_for_ip(profile_id, self.client_address[0])
            self._send_json({"backups": list_profile_backups(profile_id) if access.get("enabled") else [], "download_policy": access}); return
        if path.startswith("/backups/"):
            with STATE.lock: profile_id = STATE.active_profile_id
            name = unquote(path[len("/backups/"):])
            if not profile_id or "/" in name or "\\" in name: self._send_json({"error": "not found"}, 404); return
            access = status_for_ip(profile_id, self.client_address[0])
            if not access.get("enabled"): self._send_json({"error": "World save downloads are disabled"}, 403); return
            if not access.get("allowed"): self._send_json({"error": "World save download cooldown is active", **access}, 429); return
            root = _profile_backups_dir(profile_id).resolve(); target = (root / name).resolve()
            if root not in target.parents or not target.is_file(): self._send_json({"error": "not found"}, 404); return
            data = target.read_bytes(); record_download(profile_id, self.client_address[0])
            self.send_response(200); self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        if path.startswith("/starter-characters/"):
            with STATE.lock: profile_id = STATE.active_profile_id
            character_id = unquote(path[len("/starter-characters/"):])
            if not profile_id or not character_id or "/" in character_id or "\\" in character_id:
                self._send_json({"error": "not found"}, 404); return
            with STATE.lock:
                offered = any(str(item.get("id") or "") == character_id for item in (STATE.manifest.get("starter_characters") or []))
            if not offered:
                self._send_json({"error": "character sharing is disabled or this character is not offered"}, 403); return
            try:
                target = starter_character_path(profile_id, character_id)
                data = target.read_bytes(); STATE.activity(self.client_address[0], f"downloaded starter character {character_id} ({len(data)} bytes)")
                self.send_response(200); self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
                self.send_header("Content-Length", str(len(data))); self.send_header("X-SHA256", sha256_of(target)); self.end_headers(); self.wfile.write(data); return
            except FileNotFoundError:
                self._send_json({"error": "not found"}, 404); return
        if path.startswith("/files/"):
            rel = unquote(path[len("/files/"):]); root = PUBLISH_DIR.resolve(); target = (root / rel).resolve()
            if root not in target.parents or not target.is_file(): self._send_json({"error": "not found"}, 404); return
            client_platform = normalize_client_platform(self.headers.get("X-DWS-Client-Platform"))
            with STATE.lock:
                entry = next((item for item in STATE.manifest.get("files", []) if item.get("path") == rel), None)
            if entry and not entry_allowed_for_platform(entry, client_platform):
                self._send_json({"error": "runtime is not compatible with the selected client platform"}, 409); return
            size = target.stat().st_size
            start, end, status = 0, max(0, size - 1), 200
            range_header = str(self.headers.get("Range") or "").strip()
            if range_header:
                match = re.fullmatch(r"bytes=(\d+)-(\d*)", range_header)
                if not match:
                    self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.end_headers(); return
                start = int(match.group(1)); end = int(match.group(2)) if match.group(2) else max(0, size - 1)
                if start >= size or end < start:
                    self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.end_headers(); return
                end = min(end, size - 1); status = 206
            length = max(0, end - start + 1) if size else 0
            expected = str((entry or {}).get("sha256") or "") or sha256_of(target)
            STATE.activity(self.client_address[0], f"downloading {rel} ({start}-{end} of {size} bytes)")
            self.send_response(status); self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Length", str(length)); self.send_header("X-SHA256", expected)
            if status == 206: self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with target.open("rb") as stream:
                stream.seek(start); remaining = length
                while remaining > 0:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk: break
                    self.wfile.write(chunk); remaining -= len(chunk)
            return
        self._send_json({"error": "not found"}, 404)

    def log_message(self, *_args):
        return


class Broadcaster:
    def __init__(self, get_info):
        self.get_info = get_info; self.stop_event = threading.Event(); self.thread: threading.Thread | None = None

    @property
    def running(self): return bool(self.thread and self.thread.is_alive())

    def start(self):
        if self.running: return
        self.stop_event.clear(); self.thread = threading.Thread(target=self._run, daemon=True); self.thread.start()

    def stop(self): self.stop_event.set()

    def _run(self):
        sock4 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sock4.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        query = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); query.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: query.bind(("", DISCOVERY_QUERY_PORT)); query.settimeout(0.2)
        except OSError: query.close(); query = None
        try: sock6 = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        except OSError: sock6 = None
        while not self.stop_event.is_set():
            full_info = self.get_info()
            wire_info = dict(full_info)
            wire_info["mod_count"] = len(full_info.get("mod_summary") or [])
            wire_info["mod_inventory_endpoint"] = "/identity"
            wire_info.pop("mod_summary", None)
            payload = json.dumps(wire_info).encode()
            try: sock4.sendto(payload, ("255.255.255.255", DISCOVERY_PORT))
            except OSError: pass
            if query:
                try:
                    request_data, request_addr = query.recvfrom(1024)
                    request_info = json.loads(request_data.decode("utf-8", "replace"))
                    if request_info.get("app") == DISCOVERY_MAGIC and request_info.get("discover") is True:
                        query.sendto(payload, request_addr)
                except (socket.timeout, OSError, ValueError, json.JSONDecodeError):
                    pass
            if sock6:
                try: sock6.sendto(payload, ("ff02::1", DISCOVERY_PORT, 0, 0))
                except OSError: pass
            self.stop_event.wait(2)
        sock4.close(); sock6 and sock6.close(); query and query.close()


def scan_for_servers(timeout: float = 3.0) -> list[dict]:
    found: dict[tuple[str, int], dict] = {}; sockets = []
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            s = socket.socket(family, socket.SOCK_DGRAM); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", DISCOVERY_PORT)); s.settimeout(0.25); sockets.append(s)
        except OSError: pass
    try:
        active = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        active.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        active.bind(("", 0)); active.settimeout(0.25)
        active.sendto(json.dumps({"app": DISCOVERY_MAGIC, "discover": True}).encode(), ("255.255.255.255", DISCOVERY_QUERY_PORT))
        sockets.append(active)
    except OSError:
        pass
    deadline = time.time() + max(0.1, min(timeout, 10.0))
    while time.time() < deadline:
        for s in sockets:
            try:
                data, addr = s.recvfrom(4096); info = json.loads(data.decode("utf-8", "replace"))
                if info.get("app") != DISCOVERY_MAGIC: continue
                ip = str(info.get("ip") or addr[0]); port = int(info.get("port") or SYNC_PORT_DEFAULT)
                found[(ip, port)] = {**info, "ip": ip, "port": port}
            except (socket.timeout, OSError, ValueError, json.JSONDecodeError): pass
    for s in sockets: s.close()
    results = list(found.values())
    for info in results:
        host = str(info.get("ip") or "").split("%", 1)[0]
        port = int(info.get("sync_port") or info.get("port") or SYNC_PORT_DEFAULT)
        address = f"[{host}]" if ":" in host else host
        try:
            from network_client import register_tls_pin, request as sync_request
            scheme = "https" if info.get("sync_tls") else "http"
            base_url = f"{scheme}://{address}:{port}"
            if scheme == "https":
                register_tls_pin(base_url, str(info.get("tls_cert_fingerprint") or ""))
            response = sync_request(f"{base_url}/identity?compact=1", timeout=2.5)
            identity = json.loads(response.read(4 * 1024 * 1024))
            world_sync = identity.get("world_sync") if isinstance(identity.get("world_sync"), dict) else {}
            advertised_fingerprint = str(info.get("fingerprint") or "")
            live_fingerprint = str(world_sync.get("fingerprint") or identity.get("launcher_fingerprint") or "")
            info["identity_verified"] = bool(
                advertised_fingerprint and live_fingerprint == advertised_fingerprint and
                str(world_sync.get("protocol") or "") == WORLD_SYNC_PROTOCOL)
            if not info["identity_verified"]:
                info["identity_error"] = "The live Sync fingerprint did not match this LAN broadcast."
                info["mod_inventory_complete"] = False
                continue
            for key in ("description", "classification", "audience", "platform_compatibility", "tags", "mod_badges",
                        "mod_summary", "icon_b64", "banner_b64", "placard_background", "community", "community_rules"):
                if key in identity:
                    info[key] = identity[key]
            info["mod_count"] = len(info.get("mod_summary") or [])
            info["mod_inventory_complete"] = True
        except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
            info["identity_verified"] = False
            info["identity_error"] = str(exc)
            info["mod_inventory_complete"] = False
    return results


def probe_server_address(address_value: str, timeout: float = 3.0) -> list[dict]:
    """Ask one host for every Sync World it is actively broadcasting."""
    from world_identity import normalize_endpoint
    endpoint = normalize_endpoint(address_value, default_port=SYNC_PORT_DEFAULT)
    if endpoint is None:
        raise ValueError("Enter a valid IP address or hostname.")
    family = socket.AF_INET6 if ":" in endpoint.host else socket.AF_INET
    target = (endpoint.host, DISCOVERY_QUERY_PORT, 0, 0) if family == socket.AF_INET6 else (endpoint.host, DISCOVERY_QUERY_PORT)
    sock = socket.socket(family, socket.SOCK_DGRAM)
    sock.settimeout(0.25)
    found: dict[tuple[str, int], dict] = {}
    try:
        sock.sendto(json.dumps({"app": DISCOVERY_MAGIC, "discover": True, "direct": True}).encode(), target)
        deadline = time.time() + max(0.25, min(float(timeout or 3.0), 10.0))
        while time.time() < deadline:
            try:
                data, source = sock.recvfrom(65535)
                info = json.loads(data.decode("utf-8", "replace"))
                if info.get("app") != DISCOVERY_MAGIC:
                    continue
                source_ip = str(source[0] or "").split("%", 1)[0]
                advertised_ip = str(info.get("ip") or source_ip).split("%", 1)[0]
                port = int(info.get("sync_port") or info.get("port") or SYNC_PORT_DEFAULT)
                found[(source_ip, port)] = {**info, "ip": source_ip, "queried_ip": endpoint.host,
                                            "advertised_ip": advertised_ip, "port": port, "source": "direct-query"}
            except socket.timeout:
                continue
            except (OSError, ValueError, json.JSONDecodeError):
                break
    finally:
        sock.close()
    # Reuse the same live identity and whole-fingerprint verification as LAN.
    original_scan = list(found.values())
    for info in original_scan:
        host = str(info.get("ip") or "").split("%", 1)[0]
        port = int(info.get("sync_port") or info.get("port") or SYNC_PORT_DEFAULT)
        rendered_host = f"[{host}]" if ":" in host else host
        try:
            from network_client import register_tls_pin, request as sync_request
            scheme = "https" if info.get("sync_tls") else "http"
            base_url = f"{scheme}://{rendered_host}:{port}"
            if scheme == "https":
                register_tls_pin(base_url, str(info.get("tls_cert_fingerprint") or ""))
            identity = json.loads(sync_request(f"{base_url}/identity?compact=1", timeout=2.5).read(4 * 1024 * 1024))
            world_sync = identity.get("world_sync") if isinstance(identity.get("world_sync"), dict) else {}
            actual = str(world_sync.get("fingerprint") or identity.get("launcher_fingerprint") or "")
            info["identity_verified"] = bool(str(info.get("fingerprint") or "") and actual == str(info.get("fingerprint") or "") and
                                               str(world_sync.get("protocol") or "") == WORLD_SYNC_PROTOCOL)
            if not info["identity_verified"]:
                info["identity_error"] = "The live Sync fingerprint did not match this direct announcement."
                continue
            for key in ("description", "classification", "audience", "platform_compatibility", "tags", "mod_badges", "mod_summary",
                        "icon_b64", "banner_b64", "placard_background", "community", "community_rules"):
                if key in identity:
                    info[key] = identity[key]
            info["mod_count"] = len(info.get("mod_summary") or [])
            info["mod_inventory_complete"] = True
        except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
            info["identity_verified"] = False
            info["identity_error"] = str(exc)
            info["mod_inventory_complete"] = False
    return original_scan


def _publish_baseline_client_runtimes(game_root: str, manifest_files: list[dict]) -> dict:
    """Publish the machine-level client runtime baseline for a World.

    Every connected client receives the UE4SS core and RuneSchema core through
    the ordinary verified Sync manifest so profile switching is deterministic.
    Dragonwilds dedicated-server ``version.dll`` is explicitly excluded because
    it is server-only runtime material. Per-World UE4SS/RuneSchema child mods are
    handled by the normal mod-unit publisher.
    """
    layout = resolve_server_layout(game_root)
    stats = {"ue4ss_files": 0, "runeschema_files": 0, "version_dll_excluded": True,
             "platforms": list(WIN64_RUNTIME_PLATFORMS), "native_linux_injection": False}

    def stage_file(source: Path, wire: str, generated: str) -> None:
        if not source.is_file():
            return
        pure = PurePosixPath(wire.replace("\\", "/"))
        if pure.name.casefold() == SERVER_LOADER_FILENAME.casefold():
            return
        dest = PUBLISH_DIR / Path(*pure.parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        manifest_files.append({
            "path": pure.as_posix(), "sha256": sha256_of(dest), "size": dest.stat().st_size,
            "category": "permanent", "kind": "file", "extract_to": "",
            "generated": generated, "baseline_runtime": True,
            "platforms": list(WIN64_RUNTIME_PLATFORMS), "game_abi": "windows-pe-x64",
        })

    def stage_ue4ss_bundle(bundle: Path) -> None:
        if not bundle.is_file():
            return
        with zipfile.ZipFile(bundle) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                parts = list(PurePosixPath(info.filename.replace("\\", "/")).parts)
                if len(parts) > 1 and parts[0].casefold().startswith(("ue4ss", "re-ue4ss")):
                    parts = parts[1:]
                lowered = [part.casefold() for part in parts]
                if not parts or ".." in parts or Path(parts[-1]).name.casefold() == SERVER_LOADER_FILENAME.casefold():
                    continue
                if "mods" in lowered:
                    continue
                wire = PurePosixPath("Binaries/Win64", *parts).as_posix()
                dest = PUBLISH_DIR / Path(*PurePosixPath(wire).parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, dest.open("wb") as out:
                    shutil.copyfileobj(src, out)
                manifest_files.append({
                    "path": wire, "sha256": sha256_of(dest), "size": dest.stat().st_size,
                    "category": "permanent", "kind": "file", "extract_to": "",
                    "generated": "ue4ss_bundled_baseline", "baseline_runtime": True,
                    "platforms": list(WIN64_RUNTIME_PLATFORMS), "game_abi": "windows-pe-x64",
                })
                stats["ue4ss_files"] += 1

    # Prefer the live, validated server runtime so clients receive the exact
    # baseline the server is running. Fall back to the launcher repair library.
    bootstrap = layout.ue4ss_bootstrap if layout.ue4ss_bootstrap.is_file() else UE4SS_RUNTIME_DIR / "dwmapi.dll"
    if bootstrap.is_file():
        stage_file(bootstrap, "Binaries/Win64/dwmapi.dll", "ue4ss_baseline")
        stats["ue4ss_files"] += 1
    live_core = layout.ue4ss_core_dir if layout.ue4ss_core_dir.is_dir() else UE4SS_RUNTIME_DIR / "ue4ss"
    if live_core.is_dir():
        for source in live_core.rglob("*"):
            if not source.is_file():
                continue
            rel = source.relative_to(live_core)
            if rel.parts and rel.parts[0].casefold() == "mods":
                continue
            if source.name.casefold() == SERVER_LOADER_FILENAME.casefold():
                continue
            stage_file(source, f"Binaries/Win64/ue4ss/{rel.as_posix()}", "ue4ss_baseline")
            stats["ue4ss_files"] += 1
    if not stats["ue4ss_files"]:
        stage_ue4ss_bundle(_bundled_app_resource(*BUNDLED_UE4SS_RESOURCE))

    rs_root = layout.runeschema_root if layout.runeschema_root.is_dir() else RUNESCHEMA_RUNTIME_DIR
    rs_bundle = None
    if rs_root.is_dir():
        wire = "_baseline/RuneSchema-core.zip"
        dest = PUBLISH_DIR / "_baseline" / "RuneSchema-core.zip"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            wrote_enabled = False
            for source in rs_root.rglob("*"):
                if not source.is_file():
                    continue
                rel = source.relative_to(rs_root)
                if rel.parts and rel.parts[0].casefold() == "mods":
                    continue
                if rel.as_posix().casefold() == "enabled.txt":
                    wrote_enabled = True
                zf.write(source, rel.as_posix())
                stats["runeschema_files"] += 1
            if not wrote_enabled:
                zf.writestr("enabled.txt", b"")
                stats["runeschema_files"] += 1
        manifest_files.append({
            "path": wire, "sha256": sha256_of(dest), "size": dest.stat().st_size,
            "category": "permanent", "kind": "zip_bundle",
            "extract_to": "Binaries/Win64/ue4ss/Mods/RuneSchema",
            "generated": "runeschema_baseline", "baseline_runtime": True,
            "platforms": list(WIN64_RUNTIME_PLATFORMS), "game_abi": "windows-pe-x64",
        })
    else:
        rs_bundle = RUNESCHEMA_CORE_CACHE_ZIP if RUNESCHEMA_CORE_CACHE_ZIP.is_file() else _bundled_app_resource("RuneSchema-core-latest.zip")
        if rs_bundle.is_file():
            wire = "_baseline/RuneSchema-core.zip"
            dest = PUBLISH_DIR / "_baseline" / "RuneSchema-core.zip"
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(rs_bundle) as source_zip, zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as target_zip:
                for info in source_zip.infolist():
                    if info.is_dir():
                        continue
                    parts = list(PurePosixPath(info.filename.replace("\\", "/")).parts)
                    if len(parts) > 1 and parts[0].casefold() == "runeschema":
                        parts = parts[1:]
                    if not parts or ".." in parts or parts[0].casefold() == "mods":
                        continue
                    target_zip.writestr(PurePosixPath(*parts).as_posix(), source_zip.read(info))
                    stats["runeschema_files"] += 1
            manifest_files.append({
                "path": wire, "sha256": sha256_of(dest), "size": dest.stat().st_size,
                "category": "permanent", "kind": "zip_bundle",
                "extract_to": "Binaries/Win64/ue4ss/Mods/RuneSchema",
                "generated": "runeschema_bundled_baseline", "baseline_runtime": True,
                "platforms": list(WIN64_RUNTIME_PLATFORMS), "game_abi": "windows-pe-x64",
            })
    return stats


class ShareServer:
    def __init__(self):
        self.httpd: ThreadingHTTPServer | None = None; self.thread: threading.Thread | None = None; self.port = None
        self.tls_enabled = False; self.tls_cert_fingerprint = ""
        self.listener_evidence: dict = {}
        self.broadcaster = Broadcaster(self.broadcast_payload); self.live_keys: set[str] = set()

    def _start_listener(self, port: int, tls_enabled: bool, cert_path: Path | None, key_path: Path | None, fingerprint: str) -> None:
        try:
            httpd = ThreadingHTTPServer(("0.0.0.0", int(port)), SyncHandler)
        except OSError as exc:
            raise RuntimeError(f"World Sync could not bind 0.0.0.0:{int(port)}. The port may already be in use or blocked ({exc}).") from exc
        if tls_enabled:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(str(cert_path), str(key_path)); httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        self.httpd = httpd; self.port = int(port); self.tls_enabled = bool(tls_enabled); self.tls_cert_fingerprint = str(fingerprint or "")
        self.thread = threading.Thread(target=httpd.serve_forever, daemon=True); self.thread.start()
        try:
            probe = socket.create_connection(("127.0.0.1", int(port)), timeout=2.0)
            if tls_enabled:
                context = ssl.create_default_context(); context.check_hostname = False; context.verify_mode = ssl.CERT_NONE
                probe = context.wrap_socket(probe, server_hostname="localhost")
            probe.close()
            self.listener_evidence = {"verified": True, "bind_host": "0.0.0.0", "probe_host": "127.0.0.1",
                                      "port": int(port), "transport": "https" if tls_enabled else "http", "checked_at": time.time()}
        except OSError as exc:
            self.stop()
            raise RuntimeError(f"World Sync bound port {int(port)} but its local listener probe failed ({exc}).") from exc

    def broadcast_payload(self):
        with STATE.lock:
            connection = STATE.manifest.get("connection") or {}
            world_sync = STATE.manifest.get("world_sync") or {}
            hardware = STATE.manifest.get("hw_stats") or {}
            return {"app": DISCOVERY_MAGIC, "name": STATE.manifest.get("profile_name") or "World",
                    "ip": local_ip_guess(), "port": self.port or SYNC_PORT_DEFAULT,
                    "sync_port": int(connection.get("sync_port") or self.port or SYNC_PORT_DEFAULT),
                    "game_port": int(connection.get("game_port") or 7777),
                    "external_ip": str(connection.get("external_ip") or ""),
                    "host_type": str(STATE.manifest.get("host_type") or "dedicated"),
                    "studio_compatible": bool(STATE.manifest.get("studio_compatible", True)),
                    "protocol": str(world_sync.get("protocol") or WORLD_SYNC_PROTOCOL),
                    "protocol_version": int(world_sync.get("version") or WORLD_SYNC_VERSION),
                    "fingerprint": str(world_sync.get("fingerprint") or STATE.manifest.get("launcher_fingerprint") or ""),
                    "sync_tls": bool(self.tls_enabled), "tls_cert_fingerprint": str(self.tls_cert_fingerprint or ""),
                    "tls_password_fallback": bool(STATE.allow_tls_password_fallback),
                    "lan_trust": bool(STATE.lan_trust_enabled),
                    "mod_badges": STATE.manifest.get("mod_badges") or ["VANILLA"],
                    "mod_summary": [{key: row.get(key) for key in ("key", "name", "kind", "loader", "classification", "client_required", "version", "author", "tags") if row.get(key) not in (None, "")}
                                    for row in (STATE.manifest.get("mod_summary") or []) if isinstance(row, dict)],
                    "tags": STATE.manifest.get("tags") or [],
                    "description": str(STATE.manifest.get("description") or "")[:300],
                    "classification": STATE.manifest.get("classification") or {},
                    "audience": STATE.manifest.get("audience") or "general",
                    "platform_compatibility": STATE.manifest.get("platform_compatibility") or {"pc": True},
                    "community": STATE.manifest.get("community") or {},
                    "community_rules": STATE.manifest.get("community_rules") or "",
                    **{key: hardware.get(key) for key in ("host_os", "host_os_label", "distro", "distro_name", "distro_version", "distro_codename", "distro_family", "distro_icon", "distro_known", "distro_id_like", "ubuntu", "ubuntu_supported") if hardware.get(key) not in (None, "")},
                    "operator_identity": signed_operator_world_identity(STATE.manifest),
                    "shared_character_count": len(STATE.manifest.get("starter_characters") or [])}

    def publish(self, profile_id: str, units: list[ModUnit], password: str, server_key: str, port: int,
                hw_stats: dict | None = None, game_port: int = 7777, broadcast: bool = True, public_ip: str = "", game_root: str = "",
                share_access_key: str = "", allow_shared_access: bool = True, profile_override: dict | None = None,
                persist_profile: bool = True) -> dict:
        if not 1 <= int(port) <= 65535: raise ValueError("Sync port must be 1-65535")
        profile = dict(profile_override or load_server_profile(profile_id) or {})
        if not profile: raise KeyError("World profile not found")
        dedicated = profile.get("dedicated_config") if isinstance(profile.get("dedicated_config"), dict) else {}
        # Hosted Worlds expose one player credential. Prefer the same password
        # Dragonwilds reads from DedicatedServer.ini even when an older profile
        # still carries a stale hidden Sync password. Private/co-op publishing
        # has no world_pass field and continues to use its explicit password.
        if "world_pass" in dedicated:
            password = str(dedicated.get("world_pass") or "").strip()
        else:
            password = str(password or "").strip()
        sync_options = profile.get("sync_config") if isinstance(profile.get("sync_config"), dict) else {}
        tls_enabled = bool(sync_options.get("tls_enabled"))
        allow_tls_password_fallback = bool(sync_options.get("allow_tls_password_fallback")) and tls_enabled
        cert_path = key_path = None
        tls_cert_fingerprint = ""
        if tls_enabled:
            cert_path, key_path, tls_cert_fingerprint = _sync_tls_material(
                profile_id, [local_ip_guess(), str(public_ip or profile.get("public_ip") or "")])
        required = [u for u in units if u.classification == "player_required"]
        security_reviews = []
        PUBLISH_DIR.mkdir(parents=True, exist_ok=True)
        # Wipe only app-owned published staging. It is regenerated atomically enough for current protocol.
        for child in list(PUBLISH_DIR.iterdir()):
            _remove_generated_path(child)
        manifest_files = []
        baseline_runtime = _publish_baseline_client_runtimes(game_root, manifest_files) if str(game_root or "").strip() else {"ue4ss_files": 0, "runeschema_files": 0, "version_dll_excluded": True}
        source_mods_txt = ""
        if game_root:
            try:
                live_mods_txt = resolve_server_layout(game_root).mods_txt
                if live_mods_txt.is_file():
                    source_mods_txt = live_mods_txt.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                source_mods_txt = ""
        for unit in [u for u in required if u.group not in ("runeschema", "runeschema_mod")]:
            unit_platforms = list(ALL_CLIENT_PLATFORMS if unit.group == "pak_mod" else WIN64_RUNTIME_PLATFORMS)
            for manifest_path, source in unit.iter_files():
                if PurePosixPath(manifest_path).name.lower() == "mods.txt":
                    continue
                dest = PUBLISH_DIR / Path(*PurePosixPath(manifest_path).parts); dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, dest)
                manifest_files.append({"path": manifest_path, "sha256": sha256_of(dest), "size": dest.stat().st_size,
                                       "category": unit.category, "kind": "file", "extract_to": "",
                                       "platforms": unit_platforms})
        # Selection is derived from the World. Whenever the resulting client set
        # contains UE4SS entries, publish its client-safe launcher-owned mods.txt
        # rather than asking each client to reconstruct it. An empty set is still
        # generated locally so a profile swap clears stale entries.
        client_ue4ss_mods = client_ue4ss_enablement(units, source_mods_txt, profile.get("mods_txt_mode") or "auto")
        mods_txt_writer = "server_push" if client_ue4ss_mods else "client_generate"
        if mods_txt_writer == "server_push":
            wire = "_client_control/mods.txt"
            dest = PUBLISH_DIR / "_client_control" / "mods.txt"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(_client_mods_txt_lines(client_ue4ss_mods, source_mods_txt), encoding="utf-8")
            manifest_files.append({"path": wire, "sha256": sha256_of(dest), "size": dest.stat().st_size,
                                   "category": "permanent", "kind": "file", "extract_to": "",
                                   "target_scope": "client_mods_txt", "target_path": "mods.txt",
                                   "generated": "server_client_mods_txt",
                                   "platforms": list(WIN64_RUNTIME_PLATFORMS)})

        # Safe server-authored compatibility config is mirrored into the player's
        # Windows config directory. DedicatedServer.ini and credential-like files
        # are explicitly excluded by world_maintenance.client_sync_server_configs.
        try:
            from world_maintenance import client_sync_server_configs
            server_root = str(game_root or "").strip()
            safe_configs = client_sync_server_configs(profile_id, server_root) if server_root else []
        except Exception:
            safe_configs = []
        for item in safe_configs:
            source = Path(item["source"])
            rel = str(item.get("target_path") or source.name).replace("\\", "/")
            wire = f"_client_config/{rel}"
            dest = PUBLISH_DIR / Path(*PurePosixPath(wire).parts)
            dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, dest)
            manifest_files.append({"path": wire, "sha256": sha256_of(dest), "size": dest.stat().st_size,
                                   "category": "permanent", "kind": "file", "extract_to": "",
                                   "target_scope": "client_config", "target_path": rel, "generated": "server_compat_config",
                                   "platforms": list(WIN64_RUNTIME_PLATFORMS)})

        for unit in [u for u in required if u.group == "runeschema_mod"]:
            base = GROUP_DEST_BASE[unit.group]; unit_root = f"{base}/{unit.name}" if unit.is_dir else base
            rel = f"{base}/{unit.name}.zip"; dest = PUBLISH_DIR / Path(*PurePosixPath(rel).parts); dest.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                for manifest_path, source in unit.iter_files():
                    arc = PurePosixPath(manifest_path).relative_to(PurePosixPath(unit_root)).as_posix(); zf.write(source, arc)
            manifest_files.append({"path": rel, "sha256": sha256_of(dest), "size": dest.stat().st_size,
                                   "category": unit.category, "kind": "zip_bundle", "extract_to": unit_root,
                                   "platforms": list(WIN64_RUNTIME_PLATFORMS)})
        # Client presentation intentionally omits runtime plumbing. Core UE4SS
        # loader files (including dwmapi.dll), mods.txt, and the RuneSchema core
        # are implied prerequisites rather than user-facing "mods". Server-only
        # mod metadata remains available so clients can opt to reveal it.
        visible_units = [u for u in units if u.group not in ("ue4ss_core", "runeschema")
                         and u.name.lower() not in {"mods.txt", "dwmapi.dll"}]
        summary = []
        for unit in visible_units:
            file_count, _, content_hash = unit.content_summary()
            summary.append({"name": unit.name, "section": UNIT_GROUP_SECTION.get(unit.group, ("other", ""))[0],
                            "subsection": UNIT_GROUP_SECTION.get(unit.group, ("other", ""))[1],
                            "classification": unit.classification,
                            "distribution": "client_required" if unit.classification == "player_required" else "server_retained",
                            "category": unit.category, "file_count": file_count, "content_hash": content_hash,
                            "source": normalize_mod_source(unit.source), "hotload_capable": bool(unit.hotload_capable),
                            "tags": list(unit.tags)})
        avg, count = profile_rating_summary(profile)
        full_health_config = normalize_health_config(profile.get("health_config"))
        hierarchy = profile.get("hierarchy") if isinstance(profile.get("hierarchy"), dict) else {}
        reports = profile.get("compatibility_reports") or []
        full_health_config["external_validation"] = {
            "provider": str(hierarchy.get("provider") or "shrug.games"),
            "hierarchy_confirmed": bool(hierarchy.get("confirmed")),
            "hierarchy_confirmed_at": hierarchy.get("confirmed_at"),
            "validated_client_reports": sum(1 for x in reports if isinstance(x, dict) and x.get("success") is True),
        }
        broadcast_health_config = public_health_config(full_health_config)
        consolidated_tags = []
        seen_tags = set()
        for tag in list(profile.get("tags") or []) + [t for u in visible_units if u.classification == "player_required" for t in (u.tags or [])]:
            value = str(tag).strip()[:40]
            if value and value.casefold() not in seen_tags:
                consolidated_tags.append(value); seen_tags.add(value.casefold())
            if len(consolidated_tags) >= 24: break
        runtime_stack = server_runtime_stack(load_state().get("application") or {}, profile, runeschema_runtime_dir=RUNESCHEMA_RUNTIME_DIR, remote=True)
        classification = normalize_world_classification(profile.get("classification"), tags=consolidated_tags,
                                                        mod_badges=compute_mod_badges(units), host_type="dedicated", visibility="public")
        character_sharing = profile.get("character_sharing") if isinstance(profile.get("character_sharing"), dict) else {}
        shared_characters = list_starter_characters(profile_id) if bool(character_sharing.get("enabled")) else []
        initial_health = score_server_health(hw_stats=hw_stats or {}, network_health=STATE.network_summary(None), health_config=full_health_config, uptime_seconds=None, online=STATE.server_online, runtime_stack=runtime_stack)
        # Do not leak operator-disabled reference URLs/notes through the nested health result.
        if isinstance(initial_health.get("hardware"), dict):
            initial_health["hardware"]["references"] = broadcast_health_config.get("hardware_reference") or {}
        with STATE.lock:
            version = max(int(profile.get("manifest_version") or 0), int(STATE.manifest.get("version") or 0)) + 1
            metadata_revision = max(int(profile.get("metadata_revision") or 0), int(STATE.metadata_revision or 0), int(STATE.manifest.get("metadata_revision") or 0)) + 1
            STATE.password = password; STATE.server_key = ""; STATE.share_access_key = ""
            STATE.allow_shared_access = True; STATE.active_profile_id = profile_id
            STATE.lan_trust_enabled = bool(broadcast)
            STATE.tokens.clear(); STATE.token_sources.clear(); STATE.metadata_revision = metadata_revision
            fingerprint = world_sync_fingerprint(profile_id)
            STATE.manifest = {"profile_id": profile_id, "profile_name": profile.get("name") or "World", "version": version, "metadata_revision": metadata_revision,
                              "launcher_fingerprint": fingerprint,
                              "world_sync": {"protocol": WORLD_SYNC_PROTOCOL, "version": WORLD_SYNC_VERSION, "fingerprint": fingerprint},
                              "runtime_negotiation": {"protocol": 1, "request_header": "X-DWS-Client-Platform",
                                                      "supported_platforms": list(ALL_CLIENT_PLATFORMS),
                                                      "default_platform": "windows"},
                              "runtime_variants": runtime_variant_catalog(),
                              "files": manifest_files, "description": profile.get("description") or "", "tags": consolidated_tags,
                              "classification": classification,
                              "audience": str(profile.get("audience") or "general"),
                              "platform_compatibility": {"pc": True, **{key: bool((profile.get("platform_compatibility") or {}).get(key, key in {"steam", "epic"})) for key in ("steam", "epic", "nintendo", "playstation", "xbox")}},
                              "console_policy": {"allow_connection_attempt": True, "client_required_writes": "skip_with_warning", "server_only_mods_supported": True},
                              "community": {"discord_invite": str((profile.get("community") or {}).get("discord_invite") or "")[:300],
                                            "discord_guild_id": str((profile.get("community") or {}).get("discord_guild_id") or "")[:24]},
                              "community_rules": str(profile.get("community_rules") or "")[:4000],
                              "mod_badges": compute_mod_badges(units), "icon_b64": profile.get("icon_b64") or "", "banner_b64": profile.get("banner_b64") or "",
                              "placard_background": str(profile.get("placard_background") or "1"),
                              "mod_summary": summary, "mods_txt_mode": str(profile.get("mods_txt_mode") or "auto").lower(),
                              "mods_txt_writer": mods_txt_writer,
                              "client_ue4ss_mods": client_ue4ss_mods,
                              "game_port": int(game_port or 7777), "rating_average": avg, "rating_count": count,
                              "hw_stats": hw_stats or {}, "network_health": STATE.network_summary(None),
                              "security_posture": {"package_validation": "hash-staging-rollback"},
                              "health_config": broadcast_health_config,
                              "runtime_stack": runtime_stack, "baseline_runtime": baseline_runtime,
                              "connection": {
                                  "internal_ip": local_ip_guess(), "external_ip": str(public_ip or profile.get("public_ip") or ""),
                                  "sync_port": int(port), "game_port": int(game_port or 7777),
                                  "sync_tls": tls_enabled, "tls_cert_fingerprint": tls_cert_fingerprint,
                                  "tls_password_fallback": allow_tls_password_fallback,
                              },
                              "share_profile": {"enabled": True, "scope": "world-password"},
                              "password_required": bool(password),
                              "authentication": {"mode": "world_password", "scope": "world-sync", "challenge": "hmac-sha256-nonce",
                                                 "transport": "pinned-tls" if tls_enabled else "http",
                                                 "tls_password_fallback": allow_tls_password_fallback},
                              "external_hierarchy": {
                                  "provider": "shrug.games",
                                  "label": "Public RuneScape Dragonwilds server hierarchy (unofficial)",
                                  "search_url": "https://shrug.games/games/runescape-dragonwilds/servers/?q=" + quote_plus(str(profile.get("name") or "World")),
                                  "confirmed": bool(hierarchy.get("confirmed")), "confirmed_at": hierarchy.get("confirmed_at"),
                              },
                              "service_notice": normalize_notice(profile.get("service_notice")),
                              "player_map": {"allow_remote_clients": bool((profile.get("player_map") or {}).get("allow_remote_clients", False))},
                              "world_save_download": profile.get("world_save_download") or {"enabled": False},
                              "character_sharing": {"enabled": bool(character_sharing.get("enabled")), "allow_submissions": bool(character_sharing.get("allow_submissions")), "request_backups": bool(character_sharing.get("request_backups")), "transport": "authenticated-direct-rsdwl", "website_storage": False},
                              "starter_characters": [{k: v for k, v in item.items() if k not in {"portrait_data"}} for item in shared_characters],
                              "server_health": initial_health}
            client_meta = build_client_meta(STATE.manifest)
            STATE.manifest["manifest_fingerprint"] = client_meta["manifest_fingerprint"]
            STATE.manifest["component_fingerprints"] = client_meta["components"]
            profile["manifest_version"] = version; profile["metadata_revision"] = metadata_revision; profile["last_published_at"] = time.time(); profile.pop("server_key", None)
            profile.setdefault("sync_config", {})["port"] = int(port); profile["sync_config"]["password"] = password
            profile["sync_config"]["tls_cert_fingerprint"] = tls_cert_fingerprint
            STATE.worldsave_source_dir = str(resolve_server_layout(game_root).savegames_dir) if game_root else ""
            STATE.tls_active = tls_enabled; STATE.tls_cert_fingerprint = tls_cert_fingerprint
            STATE.allow_tls_password_fallback = allow_tls_password_fallback
        if persist_profile:
            save_server_profile(profile_id, profile); persist_unit_overrides(profile_id, units)
        self.live_keys = {u.key for u in required}
        if self.httpd is None:
            self._start_listener(int(port), tls_enabled, cert_path, key_path, tls_cert_fingerprint)
        elif self.port != int(port) or self.tls_enabled != tls_enabled:
            self.stop(); self._start_listener(int(port), tls_enabled, cert_path, key_path, tls_cert_fingerprint)
        with STATE.lock:
            STATE.tls_active = tls_enabled; STATE.tls_cert_fingerprint = tls_cert_fingerprint
            STATE.allow_tls_password_fallback = allow_tls_password_fallback
        if broadcast: self.broadcaster.start()
        else: self.broadcaster.stop()
        return self.status()

    def stop(self):
        self.broadcaster.stop()
        if self.httpd:
            self.httpd.shutdown(); self.httpd.server_close()
        self.httpd = None; self.thread = None; self.port = None; self.tls_enabled = False; self.tls_cert_fingerprint = ""; self.listener_evidence = {}; self.live_keys.clear()
        with STATE.lock:
            STATE.tokens.clear()
            STATE.token_sources.clear()
            STATE.pending_nonces.clear()
            STATE.tls_active = False
            STATE.tls_cert_fingerprint = ""
            STATE.allow_tls_password_fallback = False

    def status(self):
        with STATE.lock:
            uptime = max(0, time.time() - STATE.server_start_ts) if STATE.server_online and STATE.server_start_ts else None
            return {"serving": self.httpd is not None, "port": self.port, "broadcasting": self.broadcaster.running,
                    "tls_enabled": bool(self.tls_enabled), "tls_cert_fingerprint": str(self.tls_cert_fingerprint or ""),
                    "tls_password_fallback": bool(STATE.allow_tls_password_fallback),
                    "listener": dict(self.listener_evidence),
                    "manifest_version": STATE.manifest.get("version", 0), "manifest_file_count": len(STATE.manifest.get("files", [])),
                    "manifest_fingerprint": STATE.manifest.get("manifest_fingerprint") or "",
                    "component_fingerprints": dict(STATE.manifest.get("component_fingerprints") or {}),
                    "live_unit_keys": sorted(self.live_keys), "client_reports": dict(STATE.client_reports),
                    "network_health": STATE.network_summary(uptime), "server_health": STATE.server_health_summary(uptime),
                    "runtime_stack": dict(STATE.manifest.get("runtime_stack") or {}),
                    "activities": list(STATE.activities[-150:])}


def refresh_live_profile_metadata(profile_id: str, profile: dict | None = None) -> dict:
    """Refresh the active share's non-file World metadata in place.

    The file list and manifest version are deliberately untouched. This lets a
    maintainer change presentation/status settings and have clients learn them
    through the metadata heartbeat without forcing a mod sync/publish.
    """
    profile_id = str(profile_id or "").strip()
    if not profile_id:
        return {"updated": False, "reason": "missing profile id"}
    profile = profile if isinstance(profile, dict) else load_server_profile(profile_id)
    if not profile:
        return {"updated": False, "reason": "profile not found"}
    with STATE.lock:
        if STATE.active_profile_id != profile_id or not STATE.manifest:
            return {"updated": False, "reason": "World is not the live published profile"}
        dedicated = profile.get("dedicated_config") if isinstance(profile.get("dedicated_config"), dict) else {}
        if "world_pass" in dedicated:
            next_password = str(dedicated.get("world_pass") or "").strip()
            if next_password != STATE.password:
                # A saved World Password is immediately authoritative for the
                # live endpoint. Old sessions must negotiate again.
                STATE.password = next_password
                STATE.tokens.clear()
                STATE.token_sources.clear()
                STATE.pending_nonces.clear()
        avg, count = profile_rating_summary(profile)
        health_cfg = public_health_config(normalize_health_config(profile.get("health_config")))
        hierarchy = profile.get("external_hierarchy") or {}
        current_external = str((STATE.manifest.get("connection") or {}).get("external_ip") or "")
        profile_external = str(profile.get("public_ip") or "").strip()
        refreshed_tags = normalize_tags(list(profile.get("tags") or []) + [tag for unit in (STATE.manifest.get("mod_summary") or []) if unit.get("classification") == "player_required" for tag in (unit.get("tags") or [])])
        character_sharing = profile.get("character_sharing") if isinstance(profile.get("character_sharing"), dict) else {}
        shared_characters = list_starter_characters(profile_id) if bool(character_sharing.get("enabled")) else []
        STATE.manifest.update({
            "profile_name": str(profile.get("name") or STATE.manifest.get("profile_name") or "World")[:80],
            "description": str(profile.get("description") or "")[:300],
            "tags": refreshed_tags,
            "classification": normalize_world_classification(profile.get("classification"), tags=refreshed_tags,
                                                                mod_badges=STATE.manifest.get("mod_badges") or [], host_type="dedicated", visibility="public"),
            "audience": str(profile.get("audience") or "general"),
            "platform_compatibility": {"pc": True, **{key: bool((profile.get("platform_compatibility") or {}).get(key, key in {"steam", "epic"})) for key in ("steam", "epic", "nintendo", "playstation", "xbox")}},
            "console_policy": {"allow_connection_attempt": True, "client_required_writes": "skip_with_warning", "server_only_mods_supported": True},
            "community": {"discord_invite": str((profile.get("community") or {}).get("discord_invite") or "")[:300],
                          "discord_guild_id": str((profile.get("community") or {}).get("discord_guild_id") or "")[:24]},
            "community_rules": str(profile.get("community_rules") or "")[:4000],
            "password_required": bool(str(dedicated.get("world_pass") or "").strip()),
            "authentication": {"mode": "world_password", "scope": "world-sync", "challenge": "hmac-sha256-nonce"},
            "icon_b64": str(profile.get("icon_b64") or ""),
            "banner_b64": str(profile.get("banner_b64") or ""),
            "rating_average": avg,
            "rating_count": count,
            "health_config": health_cfg,
            "service_notice": normalize_notice(profile.get("service_notice")),
            "world_save_download": profile.get("world_save_download") or {"enabled": False},
            "character_sharing": {"enabled": bool(character_sharing.get("enabled")), "allow_submissions": bool(character_sharing.get("allow_submissions")), "request_backups": bool(character_sharing.get("request_backups")), "transport": "authenticated-direct-rsdwl", "website_storage": False},
            "starter_characters": [{k: v for k, v in item.items() if k not in {"portrait_data"}} for item in shared_characters],
            "player_map": {"allow_remote_clients": bool((profile.get("player_map") or {}).get("allow_remote_clients", False))},
            "external_hierarchy": {
                "provider": "shrug.games",
                "label": "Public RuneScape Dragonwilds server hierarchy (unofficial)",
                "search_url": "https://shrug.games/games/runescape-dragonwilds/servers/?q=" + quote_plus(str(profile.get("name") or STATE.manifest.get("profile_name") or "World")),
                "confirmed": bool(hierarchy.get("confirmed")),
                "confirmed_at": hierarchy.get("confirmed_at"),
            },
        })
        if profile_external and profile_external != current_external:
            STATE.manifest.setdefault("connection", {})["external_ip"] = profile_external
        revision = STATE.touch_metadata()
        profile["metadata_revision"] = revision
    save_server_profile(profile_id, profile)
    return {"updated": True, "metadata_revision": revision}


SHARE = ShareServer()


def gather_server_hardware_stats() -> dict:
    stats = {"os": platform.platform(), **detect_server_host(), "cpu": platform.processor() or "Unknown", "gpu": "Unknown", "gpus": [],
             "primary_gpu": "Unknown", "cpu_cores": os.cpu_count(), "cpu_threads": os.cpu_count(), "ram_total_gb": None,
             "ram_available_gb": None, "ram_used_gb": None, "ram_used_percent": None, "ram_speed_mhz": None, "probed_at": time.time()}
    try:
        import psutil  # type: ignore
        vm = psutil.virtual_memory(); stats["ram_total_gb"] = round(vm.total / (1024 ** 3), 1)
        stats["ram_available_gb"] = round(vm.available / (1024 ** 3), 1)
        stats["ram_used_gb"] = round(vm.used / (1024 ** 3), 1)
        stats["ram_used_percent"] = round(float(vm.percent), 1)
        stats["cpu_cores"] = psutil.cpu_count(logical=False) or stats["cpu_cores"]
        stats["cpu_threads"] = psutil.cpu_count(logical=True) or stats["cpu_threads"]
    except Exception: pass
    if os.name == "nt":
        try:
            script = """$ErrorActionPreference='Stop';
$cpu=Get-CimInstance Win32_Processor | Select-Object -First 1;
$gpus=Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,PNPDeviceID,VideoProcessor;
$mem=Get-CimInstance Win32_PhysicalMemory;
[pscustomobject]@{
  cpu=$cpu.Name; cores=$cpu.NumberOfCores; threads=$cpu.NumberOfLogicalProcessors;
  ramSpeed=[math]::Round(($mem | Measure-Object -Property Speed -Average).Average);
  gpus=@($gpus | ForEach-Object {[pscustomobject]@{name=$_.Name; adapter_ram_bytes=$_.AdapterRAM; pnp_device_id=$_.PNPDeviceID; video_processor=$_.VideoProcessor}})
} | ConvertTo-Json -Compress -Depth 4"""
            raw = check_output_hidden(["powershell", "-NoProfile", "-Command", script], text=True, stderr=subprocess.DEVNULL, timeout=8).strip()
            data = json.loads(raw) if raw else {}
            stats["cpu"] = str(data.get("cpu") or stats["cpu"])
            if data.get("cores"): stats["cpu_cores"] = int(data["cores"])
            if data.get("threads"): stats["cpu_threads"] = int(data["threads"])
            if data.get("ramSpeed"): stats["ram_speed_mhz"] = int(float(data["ramSpeed"]))
            gpus = data.get("gpus") or []
            if isinstance(gpus, dict): gpus = [gpus]
            clean = []
            for item in gpus:
                if not isinstance(item, dict): continue
                name = str(item.get("name") or "").strip()
                if not name: continue
                ram = item.get("adapter_ram_bytes")
                try: ram_gb = round(int(ram) / (1024 ** 3), 1) if ram else None
                except Exception: ram_gb = None
                clean.append({"name": name, "adapter_ram_gb": ram_gb, "pnp_device_id": str(item.get("pnp_device_id") or ""), "video_processor": str(item.get("video_processor") or "")})
            def rank_gpu(g):
                n = g["name"].lower()
                virtual = any(x in n for x in ("microsoft basic", "remote", "virtual", "parsec", "citrix"))
                discrete = any(x in n for x in ("nvidia", "geforce", "radeon rx", "arc a", "arc b"))
                return (0 if virtual else 1, 1 if discrete else 0, float(g.get("adapter_ram_gb") or 0))
            clean.sort(key=rank_gpu, reverse=True)
            stats["gpus"] = clean
            if clean:
                stats["primary_gpu"] = clean[0]["name"]
                stats["gpu"] = clean[0]["name"]
        except Exception: pass
    return stats

def configure_shared_firewall(sync_port: int, game_port: int | None = None, *,
                              mode: str = "manual", instance_id: str = "server-1",
                              game_program: str = "", game_mode: str | None = None,
                              sync_mode: str | None = None) -> dict:
    sync_port = int(sync_port); game_port = int(game_port if game_port is not None else 7777)
    sync_spec = firewall_spec("world_sync", sync_port, program=backend_program(), mode=sync_mode or mode, instance_id=instance_id)
    discovery_spec = firewall_spec("sync_discovery", DISCOVERY_QUERY_PORT, program=backend_program(), mode=sync_mode or mode)
    game_spec = firewall_spec("dedicated_game", game_port, program=game_program, mode=game_mode or mode, instance_id=instance_id)
    sync_result = apply_firewall_spec(sync_spec)
    discovery_result = apply_firewall_spec(discovery_spec)
    game_result = apply_firewall_spec(game_spec)
    return {"ok": bool(sync_result.get("ok") and discovery_result.get("ok") and game_result.get("ok")), "sync_port": sync_port,
            "sync_discovery_port": DISCOVERY_QUERY_PORT, "game_port": game_port,
            "mode": mode, "rules": [sync_result, discovery_result, game_result]}


def configure_server_firewall_ports(sync_ports, game_ports, *, mode: str = "manual",
                                    game_program: str = "") -> dict:
    """Configure machine-wide rules for every hosted World's current ports.

    Rules are named per port so multiple Worlds with different sync/game ports can
    coexist without the last configured World replacing the previous rule.
    """
    sync = sorted({int(p) for p in (sync_ports or [27051]) if 1 <= int(p) <= 65535}) or [27051]
    game = sorted({int(p) for p in (game_ports or [7777]) if 1 <= int(p) <= 65535}) or [7777]
    results = []
    for index, port in enumerate(sync, 1):
        sync_spec = firewall_spec("world_sync", port, program=backend_program(), mode=mode, instance_id=f"server-{index}")
        results.append(apply_firewall_spec(sync_spec))
    results.append(apply_firewall_spec(firewall_spec("sync_discovery", DISCOVERY_QUERY_PORT,
                                                     program=backend_program(), mode=mode)))
    for index, port in enumerate(game, 1):
        results.append(apply_firewall_spec(firewall_spec("dedicated_game", port, program=game_program,
                                                        mode=mode, instance_id=f"server-{index}")))
    return {"ok": all(row.get("ok") for row in results), "sync_ports": sync,
            "sync_discovery_port": DISCOVERY_QUERY_PORT, "game_ports": game,
            "mode": mode, "rules": results}


def configure_firewall_services(services) -> dict:
    """Ensure one owned rule for every externally bound application service.

    Callers supply already-authorized listener descriptions. Duplicate
    service/port/program combinations are collapsed, preferring public scope
    when any profile publishes that listener beyond the LAN.
    """
    precedence = {"none": 0, "tunnel": 0, "local": 1, "manual": 2, "upnp": 3}
    selected = {}
    for raw in services or []:
        service = str((raw or {}).get("service") or "").strip().casefold()
        if service not in {"pc_game", "dedicated_game", "world_sync", "sync_discovery", "webhost"}:
            raise ValueError(f"Unsupported host firewall service: {service or 'blank'}")
        port = int((raw or {}).get("port") or (DISCOVERY_QUERY_PORT if service == "sync_discovery" else 0))
        if not 1 <= port <= 65535:
            raise ValueError(f"Invalid {service} firewall port: {port}")
        program = str((raw or {}).get("program") or "")
        mode = str((raw or {}).get("mode") or "local").strip().casefold()
        instance_id = str((raw or {}).get("instance_id") or "")
        key = (service, port, program.casefold())
        current = selected.get(key)
        if current is None or precedence.get(mode, -1) > precedence.get(str(current.get("mode") or ""), -1):
            selected[key] = {"service": service, "port": port, "program": program,
                             "mode": mode, "instance_id": instance_id}
    results = []
    for row in sorted(selected.values(), key=lambda item: (item["service"], item["port"], item["program"].casefold())):
        results.append(apply_firewall_spec(firewall_spec(
            row["service"], row["port"], program=row["program"], mode=row["mode"],
            instance_id=row["instance_id"],
        )))
    return {"ok": bool(results) and all(row.get("ok") for row in results),
            "rule_count": len(results), "rules": results,
            "ports": [{"service": row.get("service"), "protocol": row.get("protocol"),
                       "port": row.get("port"), "mode": row.get("mode")} for row in results]}



def download_steamcmd(steamcmd_dir: str, progress=None) -> dict:
    root = Path(steamcmd_dir); root.mkdir(parents=True, exist_ok=True)
    def report(blocks, block_size, total):
        downloaded = min(max(0, int(blocks) * int(block_size)), max(0, int(total))) if int(total) > 0 else max(0, int(blocks) * int(block_size))
        if progress:
            progress({"phase": "steamcmd-download", "message": "Downloading SteamCMD", "downloaded_bytes": downloaded, "total_bytes": max(0, int(total)), "percent": round(downloaded * 100 / total, 1) if int(total) > 0 else None})
    if sys.platform.startswith("linux"):
        archive = root / "steamcmd_linux.tar.gz"
        urllib.request.urlretrieve(DEDICATED_STEAMCMD_LINUX_URL, archive, reporthook=report)
        with tarfile.open(archive, "r:gz") as tf:
            destination = root.resolve()
            for member in tf.getmembers():
                target = (destination / member.name).resolve()
                if destination != target and destination not in target.parents:
                    raise tarfile.ReadError(f"Unsafe SteamCMD archive path: {member.name}")
                if member.issym() or member.islnk():
                    raise tarfile.ReadError(f"SteamCMD archive link is not accepted: {member.name}")
            # Traversal and link members were rejected above. Avoid the newer
            # filter= API here so Debian 12's Python 3.11 remains supported.
            tf.extractall(root)
        archive.unlink(missing_ok=True)
        steam = root / "steamcmd.sh"
        steam.chmod(steam.stat().st_mode | stat.S_IXUSR)
        return {"ok": True, "steamcmd_exe": str(steam), "platform": "linux"}
    zip_path = root / "steamcmd.zip"
    urllib.request.urlretrieve(DEDICATED_STEAMCMD_URL, zip_path, reporthook=report)
    with zipfile.ZipFile(zip_path) as zf: safe_extract_zip(zf, root)
    zip_path.unlink(missing_ok=True); return {"ok": True, "steamcmd_exe": str(root / "steamcmd.exe"), "platform": "windows"}


def install_dedicated_server(install_dir: str, steamcmd_dir: str, progress=None) -> dict:
    install = Path(install_dir)
    steam_name = "steamcmd.sh" if sys.platform.startswith("linux") else "steamcmd.exe"
    steam = Path(steamcmd_dir) / steam_name
    if not steam.exists(): raise FileNotFoundError(f"{steam_name} not found")
    install.mkdir(parents=True, exist_ok=True)
    cmd = [str(steam), "+force_install_dir", str(install), "+login", "anonymous", "+app_update", DEDICATED_STEAM_APP_ID, "validate", "+quit"]
    def execute():
        process = popen_hidden(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
        output = []
        for raw in iter(process.stdout.readline, ""):
            line = raw.strip()
            if not line: continue
            output.append(line); output = output[-300:]
            phase = "steamcmd"
            lowered = line.lower()
            for candidate in ("preallocating", "downloading", "verifying", "committing"):
                if candidate in lowered: phase = candidate; break
            match = re.search(r"progress:\s*([0-9]+(?:\.[0-9]+)?)\s*\(([0-9]+)\s*/\s*([0-9]+)\)", line, re.I)
            update = {"phase": phase, "message": line[-500:]}
            if match:
                update.update({"percent": float(match.group(1)), "downloaded_bytes": int(match.group(2)), "total_bytes": int(match.group(3))})
            if progress: progress(update)
        process.wait()
        return process.returncode, "\n".join(output)
    if progress:
        returncode, output = execute()
        if returncode == 7: returncode, output = execute()
    else:
        # Compatibility path for synchronous callers and deterministic unit
        # tests. Interactive update jobs always provide progress and stream.
        result = run_hidden(cmd, capture_output=True, text=True)
        if result.returncode == 7: result = run_hidden(cmd, capture_output=True, text=True)
        returncode = result.returncode
        output = (result.stderr or result.stdout or "") if returncode else (result.stdout or "")
    if returncode != 0: raise RuntimeError(f"SteamCMD exited with {returncode}: {output[-1500:]}")
    exe = next((candidate for name in DEDICATED_SERVER_EXE_ALIASES for candidate in install.rglob(name)), None)
    if exe and sys.platform.startswith("linux"):
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return {"ok": True, "server_exe": str(exe) if exe else "", "output": output[-4000:], "platform": "linux" if sys.platform.startswith("linux") else "windows"}


def delete_dedicated_server_files(install_dir: str) -> dict:
    target = Path(install_dir).resolve()
    if not target.exists(): return {"ok": True, "deleted": False}
    if not target.is_dir() or target == Path(target.anchor) or len(target.parts) < 2: raise ValueError(f"Refusing to delete unsafe path: {target}")
    shutil.rmtree(target); return {"ok": True, "deleted": True}


def backup_install_for_reset(install_dir: str, *, label: str) -> dict:
    """Capture user-owned saves/configuration/mods before a destructive repair.

    The backup lives outside the game tree under LocalAppData.  Runtime binaries
    and Steam-owned content are intentionally excluded because Steam/SteamCMD
    will reconstruct them.  Symlinks are copied as links and never followed.
    """
    source = Path(install_dir).resolve()
    if not source.is_dir() or source == Path(source.anchor) or len(source.parts) < 3:
        raise ValueError(f"Refusing to back up unsafe install path: {source}")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_root = APP_DATA_DIR / "reset_backups" / f"{label}-{stamp}"
    backup_root.mkdir(parents=True, exist_ok=False)
    candidates = (
        "Saved",
        "RSDragonwilds/Saved",
        "Binaries/Win64/ue4ss/Mods",
        "RSDragonwilds/Binaries/Win64/ue4ss/Mods",
        "Content/Paks/~mods",
        "RSDragonwilds/Content/Paks/~mods",
    )
    copied = []
    for relative in candidates:
        candidate = source / Path(relative)
        if not candidate.exists():
            continue
        destination = backup_root / "install" / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if candidate.is_dir():
            shutil.copytree(candidate, destination, symlinks=True, dirs_exist_ok=True)
        else:
            shutil.copy2(candidate, destination, follow_symlinks=False)
        copied.append(relative.replace("\\", "/"))
    local_saved = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "RSDragonwilds" / "Saved"
    if local_saved.is_dir():
        # EOS keeps this coordination marker exclusively locked while the game
        # or Epic services are alive. It contains no identity/catalog payload;
        # skipping only the marker allows the persistent EOS cache itself to be
        # copied without turning a safe mod reset into a false failure.
        shutil.copytree(local_saved, backup_root / "LocalAppData-RSDragonwilds-Saved", symlinks=True,
                        dirs_exist_ok=True, ignore=shutil.ignore_patterns("__cache_registry_lock"))
        copied.append("%LOCALAPPDATA%/RSDragonwilds/Saved")
    manifest = {
        "schema": "DragonwildsSync.ResetBackup.v1",
        "created_at": time.time(),
        "label": label,
        "install_dir": str(source),
        "copied": copied,
        "preserved_in_place": ["Steam-owned game files", "EOS account/identity data", "%LOCALAPPDATA%/RSDragonwilds/Saved"],
        "reset_scope": "managed_mods_only",
    }
    (backup_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(backup_root), "copied": copied}


def wipe_install_after_backup(install_dir: str) -> dict:
    """Reset launcher-managed mod surfaces without deleting the game install.

    Steam/EOS-owned binaries, saves, account data, and configuration remain in
    place. ``backup_install_for_reset`` must run first; this function then
    removes only the reconstructable UE4SS child tree and PAK-mod locations.
    The colocated machine-level loaders (client ``dwmapi.dll`` and dedicated
    server ``version.dll``) are protected in place. The historical function
    name is retained for RPC/backward compatibility, but a reset is no longer
    a recursive install wipe.
    """
    target = Path(install_dir).resolve()
    if not target.is_dir() or target == Path(target.anchor) or len(target.parts) < 3:
        raise ValueError(f"Refusing to reset unsafe install path: {target}")
    # A Dragonwilds-shaped marker is mandatory.  This prevents an arbitrary
    # directory entered into Settings from becoming a recursive-delete target.
    markers = [*target.rglob("RSDragonwilds.exe"), *target.rglob("RSDragonwildsServer.exe"),
               *target.rglob("RSDragonwilds-Win64-Shipping.exe")]
    if not markers and not (target / "RSDragonwilds").is_dir():
        raise ValueError("The selected folder does not look like a Dragonwilds installation.")
    candidates = (
        "Binaries/Win64/ue4ss",
        "RSDragonwilds/Binaries/Win64/ue4ss",
        "Content/Paks/~mods",
        "Content/Paks/~Mods",
        "RSDragonwilds/Content/Paks/~mods",
        "RSDragonwilds/Content/Paks/~Mods",
    )
    removed = []
    resolved_target = target.resolve()
    for relative in candidates:
        candidate = (target / Path(relative)).resolve(strict=False)
        if candidate == resolved_target or resolved_target not in candidate.parents or not candidate.exists():
            continue
        _set_runtime_tree_writable(candidate, True)
        if candidate.is_dir():
            shutil.rmtree(candidate)
        else:
            candidate.unlink()
        removed.append(relative)
    protected = [str(path) for path in (
        target / "Binaries/Win64/dwmapi.dll", target / "Binaries/Win64/version.dll",
        target / "RSDragonwilds/Binaries/Win64/dwmapi.dll", target / "RSDragonwilds/Binaries/Win64/version.dll",
    ) if path.is_file()]
    return {"ok": True, "deleted": False, "path": str(target), "removed": removed,
            "protected_runtime_loaders": protected, "scope": "managed_mods_only",
            "steam_files_preserved": True, "eos_data_preserved": True}


def _find_public_branch_info(obj):
    if isinstance(obj, dict):
        branches = obj.get("branches")
        if isinstance(branches, dict) and isinstance(branches.get("public"), dict) and "buildid" in branches["public"]: return branches["public"]
        for value in obj.values():
            found = _find_public_branch_info(value)
            if found: return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_public_branch_info(value)
            if found: return found
    return None


def check_steam_build(timeout: float = 8.0) -> dict | None:
    try:
        req = urllib.request.Request(STEAMCMD_INFO_URL.format(appid=DEDICATED_STEAM_APP_ID), headers={"User-Agent": "DragonwildsSync/2"})
        with urllib.request.urlopen(req, timeout=timeout) as response: data = json.loads(response.read().decode("utf-8", "replace"))
        branch = _find_public_branch_info(data)
        return {"buildid": str(branch.get("buildid")), "timeupdated": str(branch.get("timeupdated", ""))} if branch else None
    except Exception: return None


def check_ue4ss_update(releases_url: str = DEFAULT_UE4SS_RELEASES_URL, timeout: float = 8.0) -> dict | None:
    return resolve_runtime_zip_source(releases_url, prefer_contains=("ue4ss",), timeout=timeout)


def _github_release_zip(api_url: str, source: str, prefer_contains: tuple[str, ...], timeout: float) -> dict | None:
    req = urllib.request.Request(api_url, headers={"User-Agent": "DragonwildsSync/2", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    releases = payload if isinstance(payload, list) else [payload]
    releases = [release for release in releases if isinstance(release, dict) and not release.get("draft")]
    payload = next((release for release in releases if any(
        str(asset.get("name") or "").casefold().endswith(".zip")
        for asset in (release.get("assets") or []) if isinstance(asset, dict)
    )), {})
    assets = [asset for asset in (payload.get("assets") or []) if str(asset.get("name") or "").casefold().endswith(".zip")]
    if prefer_contains:
        preferred = [asset for asset in assets if any(token.casefold() in str(asset.get("name") or "").casefold() for token in prefer_contains)]
        if preferred:
            assets = preferred
    non_developer = [asset for asset in assets if not str(asset.get("name") or "").casefold().startswith(("zdev-", "dev-"))]
    if non_developer:
        assets = non_developer
    if not assets:
        return None
    asset = assets[0]
    download_url = str(asset.get("browser_download_url") or "")
    if not download_url:
        return None
    return {"filename": str(asset.get("name") or "runtime.zip"), "download_url": download_url,
            "source": source, "release_tag": str(payload.get("tag_name") or ""),
            "published_at": str(payload.get("published_at") or payload.get("created_at") or ""),
            "resolver": "github-api"}


def resolve_runtime_zip_source(source_url: str, *, prefer_contains: tuple[str, ...] = (), timeout: float = 10.0) -> dict | None:
    """Resolve an editable runtime source into a downloadable ZIP.

    Accepts a direct ZIP URL, a GitHub repository URL, /releases/latest, or a
    concrete /releases/tag/<tag> URL, or a repository /tags page. GitHub release assets are preferred over
    source-code archives because UE4SS/RuneSchema are installed runtimes.
    """
    source = str(source_url or "").strip()
    if not source:
        return None
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.path.lower().endswith(".zip"):
        return {"filename": Path(parsed.path).name or "runtime.zip", "download_url": source, "source": source}

    owner = repo = tag = None
    match = _GITHUB_RELEASE_TAG_RE.match(source)
    if match:
        owner, repo, tag = match.groups()
        try:
            resolved = _github_release_zip(
                f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{quote(tag, safe='')}",
                source, prefer_contains, timeout)
            if resolved:
                return resolved
        except Exception:
            pass
    else:
        tags_match = _GITHUB_TAGS_RE.match(source)
        if tags_match:
            owner, repo = tags_match.groups()
            try:
                req = urllib.request.Request(
                    f"https://api.github.com/repos/{owner}/{repo}/tags?per_page=1",
                    headers={"User-Agent": "DragonwildsSync/2", "Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    tag_rows = json.loads(response.read().decode("utf-8", "replace"))
                tag = str(tag_rows[0].get("name") or "").strip() if isinstance(tag_rows, list) and tag_rows else ""
                if tag:
                    resolved = _github_release_zip(
                        f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{quote(tag, safe='')}",
                        source, prefer_contains, timeout)
                    if resolved:
                        resolved["resolver"] = "github-latest-tag-release"
                        return resolved
            except Exception:
                return None
            return None
        match = _GITHUB_RELEASES_LATEST_RE.match(source) or _GITHUB_RELEASES_RE.match(source) or _GITHUB_REPO_RE.match(source)
        if match:
            owner, repo = match.groups()
            api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
            try:
                resolved = _github_release_zip(api_url, source, prefer_contains, timeout)
                if resolved:
                    return resolved
            except Exception:
                # GitHub's /releases/latest endpoint excludes prereleases. Runtime
                # testing channels commonly publish prerelease-only builds, so
                # fall back to the ordered releases collection before reporting
                # the source as unresolved.
                try:
                    resolved = _github_release_zip(
                        f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=20",
                        source, prefer_contains, timeout)
                    if resolved:
                        return resolved
                except Exception:
                    return None
    if not (owner and repo and tag):
        return None
    expanded = f"https://github.com/{owner}/{repo}/releases/expanded_assets/{tag}"
    try:
        req = urllib.request.Request(expanded, headers={"User-Agent": "Mozilla/5.0 (DragonwildsSync)"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            html = response.read().decode(errors="replace")
    except Exception:
        return None
    assets = []
    for href in _GITHUB_ASSET_HREF_RE.findall(html):
        filename = href.rsplit("/", 1)[-1]
        assets.append((filename, "https://github.com" + href))
    if prefer_contains:
        preferred = [item for item in assets if any(token.casefold() in item[0].casefold() for token in prefer_contains)]
        if preferred:
            assets = preferred
    if not assets:
        return None
    filename, download_url = assets[0]
    return {"filename": filename, "download_url": download_url, "source": source}


def download_runtime_zip(source_url: str, *, prefer_contains: tuple[str, ...] = (), timeout: float = 90.0) -> tuple[Path, dict, tempfile.TemporaryDirectory]:
    resolved = resolve_runtime_zip_source(source_url, prefer_contains=prefer_contains, timeout=min(timeout, 15.0))
    if not resolved or not resolved.get("download_url"):
        raise ValueError("No downloadable ZIP release asset could be resolved from the configured source URL.")
    temp = tempfile.TemporaryDirectory(prefix="dwsync_runtime_")
    target = Path(temp.name) / str(resolved.get("filename") or "runtime.zip")
    req = urllib.request.Request(str(resolved["download_url"]), headers={"User-Agent": "DragonwildsSync/2"})
    with urllib.request.urlopen(req, timeout=timeout) as response, target.open("wb") as out:
        shutil.copyfileobj(response, out)
    return target, resolved, temp


def install_authoritative_runeschema_update(source_url: str, game_root: str, timeout: float = 90.0, *, role: str = "server") -> dict:
    zip_path, resolved, temp = download_runtime_zip(source_url, prefer_contains=("runeschema",), timeout=timeout)
    try:
        result = install_runeschema_zip(str(zip_path), game_root, role=role)
        if str(result.get("kind") or "").casefold() != "core":
            raise ValueError("The resolved RuneSchema ZIP is not a core package; expected a package containing RuneSchema's mods/ directory.")
        return {**result, "filename": resolved.get("filename"), "source": resolved.get("source"), "download_url": resolved.get("download_url")}
    finally:
        temp.cleanup()


def install_ue4ss_update(download_url: str, binaries_dir: str, timeout: float = 90.0) -> dict:
    root = Path(binaries_dir); root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dwsync_ue4ss_") as temp:
        zp = Path(temp) / "ue4ss.zip"
        req = urllib.request.Request(download_url, headers={"User-Agent": "DragonwildsSync/2"})
        with urllib.request.urlopen(req, timeout=timeout) as response, zp.open("wb") as out: shutil.copyfileobj(response, out)
        return install_ue4ss_zip(str(zp), str(root))


def _ue4ss_archive_wrapper(zf: zipfile.ZipFile) -> str:
    """Identify a single release wrapper without stripping UE4SS's new payload folder."""
    first_parts = set()
    for info in zf.infolist():
        if info.is_dir():
            continue
        parts = PurePosixPath(info.filename.replace("\\", "/")).parts
        if parts:
            first_parts.add(parts[0])
    if len(first_parts) != 1:
        return ""
    first = next(iter(first_parts))
    lowered = first.casefold()
    return first if lowered == "ue4ss" or lowered.startswith(("ue4ss_", "ue4ss-", "re-ue4ss")) else ""


def install_client_ue4ss_update(download_url: str, game_root: str, timeout: float = 90.0) -> dict:
    """Download an upstream UE4SS ZIP through the client-only installer."""
    layout = resolve_client_layout(game_root)
    with tempfile.TemporaryDirectory(prefix="dwsync_client_ue4ss_") as temp:
        archive = Path(temp) / "ue4ss.zip"
        req = urllib.request.Request(download_url, headers={"User-Agent": "DragonwildsSync/2"})
        with urllib.request.urlopen(req, timeout=timeout) as response, archive.open("wb") as out:
            shutil.copyfileobj(response, out)
        result = install_client_ue4ss_zip(str(archive), str(layout.game_root))
    return {**result, "download_url": download_url, "role": "client", "server_loader_excluded": True}


def install_client_ue4ss_zip(zip_path: str, game_root: str) -> dict:
    """Install the distributable UE4SS baseline into a retail client.

    The launcher-bundled Dragonwilds server runtime may also contain
    ``version.dll``. That loader is dedicated-server-only and is *never*
    copied to a player installation.
    """
    if not _is_launcher_bundled_ue4ss(zip_path):
        review_with_defender(zip_path, "UE4SS client runtime")
    layout = resolve_client_layout(game_root)
    target_root = layout.win64_dir
    target_root.mkdir(parents=True, exist_ok=True)
    written = []
    with zipfile.ZipFile(zip_path) as zf:
        wrapper = _ue4ss_archive_wrapper(zf)
        for info in zf.infolist():
            if info.is_dir():
                continue
            relative = PurePosixPath(info.filename.replace("\\", "/"))
            parts = list(relative.parts)
            if wrapper and len(parts) > 1 and parts[0] == wrapper:
                parts = parts[1:]
            if not parts or ".." in parts:
                raise zipfile.BadZipFile(f"Unsafe UE4SS archive path: {info.filename}")
            if Path(parts[-1]).name.casefold() == SERVER_LOADER_FILENAME.casefold():
                continue
            lower = [part.casefold() for part in parts]
            # The launcher baseline intentionally includes UE4SS's standard
            # modules plus RuneSchema core and RSDWTools. RuneSchema child
            # mods are World-profile material and must never be seeded by the
            # machine baseline.
            if "runeschema" in lower and "mods" in lower[lower.index("runeschema") + 1:]:
                continue
            dest = (target_root / Path(*parts)).resolve()
            root = target_root.resolve()
            if dest != root and root not in dest.parents:
                raise zipfile.BadZipFile(f"UE4SS archive path escapes destination: {info.filename}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out)
            written.append(PurePosixPath(*parts).as_posix())
    normalized = _normalize_bundled_integration_contract(target_root)
    return {"ok": True, "files_written": len(written), "files": written,
            "server_loader_excluded": True, "integrations": normalized}


def client_runtime_status(game_root: str) -> dict:
    layout = resolve_client_layout(game_root)
    core = layout.win64_dir / "ue4ss"
    ue_checks = {
        "bootstrap": (layout.win64_dir / "dwmapi.dll").is_file(),
        "core_dll": (core / "UE4SS.dll").is_file(),
        "settings": (core / "UE4SS-settings.ini").is_file(),
        "imgui": (core / "imgui.ini").is_file(),
    }
    rs = layout.runeschema_root
    rs_checks = {
        "root": rs.is_dir(),
        "enabled": (rs / "enabled.txt").is_file(),
        "config": (rs / "config").is_dir(),
        "dlls": (rs / "dlls").is_dir(),
    }
    return {
        "ok": all(ue_checks.values()) and all(rs_checks.values()),
        "ue4ss": {"installed": all(ue_checks.values()), "checks": ue_checks},
        "runeschema": {"installed": all(rs_checks.values()), "checks": rs_checks},
        "server_loader_present": (layout.win64_dir / SERVER_LOADER_FILENAME).is_file(),
        "server_loader_required": False,
    }


def ensure_client_base_runtimes(game_root: str) -> dict:
    """Install/repair UE4SS + RuneSchema during Player Setup.

    These are machine-level client prerequisites shared by every Private/linked
    World. World-specific mods remain profile-managed. ``version.dll`` is not a
    player prerequisite and is never installed by this path.
    """
    layout = resolve_client_layout(game_root)
    if not layout.game_root.exists():
        raise ValueError("The Dragonwilds client game root does not exist.")
    before = client_runtime_status(game_root)
    repaired = []
    errors = []
    imgui_settings = layout.win64_dir / "ue4ss" / "imgui.ini"
    if not imgui_settings.is_file() and (layout.win64_dir / "ue4ss" / "UE4SS.dll").is_file():
        imgui_settings.parent.mkdir(parents=True, exist_ok=True)
        imgui_settings.write_text("", encoding="utf-8")
        repaired.append("UE4SS imgui.ini baseline restored")
        before = client_runtime_status(game_root)
    if not before["ue4ss"]["installed"]:
        bundle = CLIENT_UE4SS_OVERRIDE_ZIP if CLIENT_UE4SS_OVERRIDE_ZIP.is_file() else _bundled_app_resource(*BUNDLED_UE4SS_RESOURCE)
        if bundle.is_file():
            install_client_ue4ss_zip(str(bundle), str(layout.game_root))
            repaired.append("UE4SS client baseline installed/repaired")
        else:
            errors.append("Bundled UE4SS baseline is unavailable.")
    if not imgui_settings.is_file() and (layout.win64_dir / "ue4ss" / "UE4SS.dll").is_file():
        imgui_settings.parent.mkdir(parents=True, exist_ok=True)
        imgui_settings.write_text("", encoding="utf-8")
        repaired.append("UE4SS imgui.ini baseline restored")
    mid = client_runtime_status(game_root)
    if not mid["runeschema"]["installed"]:
        rs_bundle = CLIENT_RUNESCHEMA_CORE_CACHE_ZIP if CLIENT_RUNESCHEMA_CORE_CACHE_ZIP.is_file() else _bundled_app_resource("RuneSchema-core-latest.zip")
        try:
            if rs_bundle.is_file():
                install_runeschema_zip(str(rs_bundle), str(layout.game_root), role="client")
                repaired.append("RuneSchema client baseline installed/repaired")
            else:
                errors.append("Bundled RuneSchema baseline is unavailable.")
        except Exception as exc:
            errors.append(f"RuneSchema client baseline repair failed: {exc}")
    try:
        from persistent_direct_connect import ensure_installed as ensure_persistent_direct_connect
        functional = ensure_persistent_direct_connect(layout.game_root)
        if functional.get("changed"):
            repaired.append("Persistent Direct Connect functional baseline installed")
    except Exception as exc:
        errors.append(f"Persistent Direct Connect baseline repair failed: {exc}")
    try:
        rsdwtools = ensure_rsdwtools_baseline(layout.ue4ss_mods_dir)
        if rsdwtools.get("changed"):
            repaired.append("RSDWTools bridge baseline installed/updated (DEBUG_BRIDGE=false)")
        if not rsdwtools.get("ok"):
            errors.append(str(rsdwtools.get("error") or "RSDWTools baseline repair failed."))
    except Exception as exc:
        errors.append(f"RSDWTools client baseline repair failed: {exc}")
    writable = _set_runtime_configs_writable(layout.win64_dir / "ue4ss", layout.runeschema_root)
    after = client_runtime_status(game_root)
    # Defensive cleanup: Player Setup never owns the dedicated-server loader.
    # If a user already has a file named version.dll we do not delete it here;
    # we only guarantee our package never creates or syncs one.
    return {"ok": after["ok"], "before": before, "after": after, "repaired": repaired, "errors": errors,
            "editable_configs_repaired": writable}


def install_ue4ss_zip(zip_path: str, binaries_dir: str) -> dict:
    if not _is_launcher_bundled_ue4ss(zip_path):
        review_with_defender(zip_path, "mod package")
    root = Path(binaries_dir); root.mkdir(parents=True, exist_ok=True)
    updated = []
    with zipfile.ZipFile(zip_path) as zf:
        wrapper = _ue4ss_archive_wrapper(zf)
        for info in zf.infolist():
            if info.is_dir(): continue
            relative = PurePosixPath(info.filename.replace("\\", "/"))
            parts = list(relative.parts)
            if wrapper and len(parts) > 1 and parts[0] == wrapper:
                parts = parts[1:]
            if not parts or ".." in parts: raise zipfile.BadZipFile(f"Unsafe UE4SS archive path: {info.filename}")
            if Path(parts[-1]).name.casefold() == SERVER_LOADER_FILENAME.casefold():
                continue
            lower = [part.casefold() for part in parts]
            if "runeschema" in lower and "mods" in lower[lower.index("runeschema") + 1:]:
                continue
            target = (root / Path(*parts)).resolve(); resolved_root = root.resolve()
            if target != resolved_root and resolved_root not in target.parents: raise zipfile.BadZipFile(f"UE4SS archive path escapes destination: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst: shutil.copyfileobj(src, dst)
            updated.append(PurePosixPath(*parts).as_posix())
    normalized = _normalize_bundled_integration_contract(root)
    return {"ok": True, "files_written": len(updated), "files": updated,
            "server_loader_excluded": True, "integrations": normalized}


def _normalize_bundled_integration_contract(target_root: Path) -> dict:
    """Normalize self-enabled baseline modules after any UE4SS extraction."""
    mods = Path(target_root) / "ue4ss" / "Mods"
    runeschema = mods / "RuneSchema"
    rsdwtools = mods / "RSDWTools"
    result = {"runeschema": runeschema.is_dir(), "rsdwtools": rsdwtools.is_dir()}
    if runeschema.is_dir():
        for name in ("config", "dlls", "mods"):
            (runeschema / name).mkdir(parents=True, exist_ok=True)
        if not (runeschema / "enabled.txt").exists():
            (runeschema / "enabled.txt").write_text("", encoding="utf-8")
    if rsdwtools.is_dir():
        if not (rsdwtools / "enabled.txt").exists():
            (rsdwtools / "enabled.txt").write_text("", encoding="utf-8")
    return result


def ensure_rsdwtools_baseline(mods_dir: Path, *, allow_update: bool = True) -> dict:
    """Install or optionally update the self-enabled RSDWTools base mod."""
    target = Path(mods_dir) / "RSDWTools"
    bundle = _bundled_app_resource(*BUNDLED_RSDWTOOLS_RESOURCE)
    live_main = target / "scripts" / "main.lua"
    live_dll = target / "dlls" / "main.dll"
    if target.is_dir() and live_main.is_file() and live_dll.is_file() and not allow_update:
        if not (target / "enabled.txt").exists():
            _write_launcher_control_file(target / "enabled.txt")
        return {"ok": True, "installed": True, "changed": False, "update_skipped": True,
                "path": str(target), "debug_bridge": False, "activation": "enabled.txt", "mods_txt_managed": False}
    if not bundle.is_file():
        return {"ok": target.is_dir(), "installed": target.is_dir(), "changed": False,
                "path": str(target), "error": "Bundled RSDWTools baseline is unavailable."}
    marker = target / ".dragonwilds-sync-baseline.json"
    signature = {"bundle_bytes": int(bundle.stat().st_size), "bundle_mtime_ns": int(bundle.stat().st_mtime_ns)}
    try:
        current = json.loads(marker.read_text(encoding="utf-8"))
    except Exception:
        current = {}
    if current == signature and live_main.is_file() and (target / "dlls" / "main.dll").is_file() and (target / "enabled.txt").is_file():
        text = live_main.read_text(encoding="utf-8-sig", errors="replace")
        if re.search(r"(?m)^\s*DEBUG_BRIDGE\s*=\s*false\s*$", text):
            return {"ok": True, "installed": True, "changed": False, "path": str(target),
                    "debug_bridge": False, "activation": "enabled.txt", "mods_txt_managed": False}
    with tempfile.TemporaryDirectory(prefix="dws-rsdwtools-") as temp_name:
        staged = Path(temp_name) / "payload"
        with zipfile.ZipFile(bundle) as archive:
            safe_extract_zip(archive, staged)
        main_lua = staged / "scripts" / "main.lua"
        if not main_lua.is_file() or not (staged / "dlls" / "main.dll").is_file():
            raise RuntimeError("Bundled RSDWTools baseline failed validation.")
        text = main_lua.read_text(encoding="utf-8-sig", errors="replace")
        if re.search(r"(?m)^\s*DEBUG_BRIDGE\s*=", text):
            text = re.sub(r"(?m)^\s*DEBUG_BRIDGE\s*=\s*(?:true|false)\s*$", "DEBUG_BRIDGE = false", text)
        else:
            text = "-- Disable all bridge_shm console output when set to false.\nDEBUG_BRIDGE = false\n" + text
        main_lua.write_text(text, encoding="utf-8")
        (staged / "enabled.txt").write_text("", encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staged, target, dirs_exist_ok=True)
    (target / "enabled.txt").write_text("", encoding="utf-8")
    marker.write_text(json.dumps(signature, indent=2), encoding="utf-8")
    return {"ok": True, "installed": True, "changed": True, "path": str(target),
            "debug_bridge": False, "activation": "enabled.txt", "mods_txt_managed": False}


def _ue4ss_settings_present(core_dir: Path) -> bool:
    direct = core_dir / "UE4SS-Settings"
    if direct.exists():
        return True
    try:
        # Keep this case-insensitive so packaged-runtime verification behaves
        # the same on Windows and Linux CI/source-validation hosts.
        return any(p.exists() and p.name.casefold().startswith("ue4ss-settings") for p in core_dir.iterdir())
    except OSError:
        return False


def _bundled_app_resource(*parts: str) -> Path:
    """Resolve launcher-owned resources in source and frozen service layouts."""
    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).resolve().parent.parent / "resources"
        for part in parts:
            candidate = candidate / part
        if candidate.exists():
            return candidate
    candidate = Path(__file__).resolve().parent.parent / "resources"
    for part in parts:
        candidate = candidate / part
    return candidate


def bundled_server_loader_path() -> Path | None:
    """Return a launcher-bundled Dragonwilds dedicated-server version.dll, if supplied.

    version.dll is intentionally treated as Dragonwilds server-only runtime
    material, not as part of upstream UE4SS.  Builds may carry it under
    resources/DragonwildsServerRuntime/version.dll.  It is never published to
    clients.
    """
    for parts in (("DragonwildsServerRuntime", SERVER_LOADER_FILENAME), (SERVER_LOADER_FILENAME,)):
        candidate = _bundled_app_resource(*parts)
        if candidate.is_file():
            return candidate
    return None


def _ensure_server_loader_library_from_bundle() -> dict:
    """Seed the authoritative runtime library with the bundled server loader.

    Existing cached/live copies always win. This makes first-time linked server
    repair deterministic when the release package includes the Dragonwilds
    loader, while preserving operator-proven DLLs across subsequent UE4SS
    updates.
    """
    target = UE4SS_RUNTIME_DIR / SERVER_LOADER_FILENAME
    if target.is_file():
        return {"ok": True, "installed": True, "source": str(target), "copied": False}
    source = bundled_server_loader_path()
    if source is None:
        return {"ok": False, "installed": False, "source": "", "copied": False}
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {"ok": True, "installed": True, "source": str(source), "copied": True}


def _set_runtime_tree_writable(root: Path, writable: bool) -> None:
    """Toggle owner write permission for launcher-owned runtime files.

    Windows maps this to the file read-only attribute. This lets the launcher
    self-heal infrastructure that an earlier release may already have locked.
    """
    if not root.exists():
        return
    for path in [root, *root.rglob("*")]:
        try:
            mode = path.stat().st_mode
            path.chmod(mode | stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        except OSError:
            continue


def _set_runtime_configs_writable(*roots: Path) -> int:
    """Clear stale read-only attributes from operator-editable core configs.

    Runtime DLLs and launcher-owned control files may remain protected, but
    UE4SS settings and RuneSchema's config tree are user configuration. Copies
    made with ``copy2`` can inherit a read-only source bit, so this runs after
    every materialization boundary as well as before editing.
    """
    changed = 0
    for root in roots:
        if not root:
            continue
        candidates: list[Path] = []
        if root.name.casefold() == "ue4ss":
            candidates.extend(root / name for name in ("UE4SS-settings.ini", "UE4SS-Settings.ini", "ue4ss-settings.ini", "imgui.ini"))
        else:
            config = root / "config"
            if root.is_dir():
                try:
                    config = next((child for child in root.iterdir() if child.name.casefold() == "config"), config)
                except OSError:
                    pass
            if config.exists():
                candidates.extend([config, *config.rglob("*")])
        for path in candidates:
            if not path.exists():
                continue
            try:
                before = path.stat().st_mode
                path.chmod(before | stat.S_IWUSR)
                changed += int(path.stat().st_mode != before)
            except OSError:
                continue
    return changed


def runtime_prerequisite_status(game_root: str) -> dict:
    """Report whether the dedicated-server runtime contract is present.

    UE4SS itself is the ordinary upstream runtime (``dwmapi.dll`` + ``ue4ss``).
    Dragonwilds dedicated hosting additionally requires the server-only
    ``version.dll`` loader beside the game binary.  That DLL is *not* part of
    upstream UE4SS and is preserved independently across UE4SS upgrades.
    RuneSchema is launcher-managed infrastructure under
    ``ue4ss/Mods/RuneSchema`` and self-enables via a blank ``enabled.txt``.
    """
    layout = resolve_server_layout(game_root)
    if sys.platform.startswith("linux") and layout.server_exe.suffix.casefold() != ".exe":
        # UE4SS/RuneSchema integration in this release targets the Win64
        # Dragonwilds runtime.  The native Linux server remains fully usable
        # for install/config/save/process and Sync fingerprint operations.
        skipped = {"installed": False, "checks": {}, "library_ready": False, "library_checks": {}, "platform_supported": False}
        return {
            "ok": True,
            "game_root": str(layout.game_root),
            "native_linux_server": True,
            "platform_note": "Native Linux server detected; Win64 UE4SS, RuneSchema, and PlayerTracker injection is intentionally not applied.",
            "ue4ss": dict(skipped),
            "server_loader": {**skipped, "server_only": True, "client_distributed": False, "filename": SERVER_LOADER_FILENAME},
            "runeschema": dict(skipped),
            "bundled_ue4ss_zip": "",
        }
    ue_checks = {
        "bootstrap": layout.ue4ss_bootstrap.is_file(),
        "core_dll": (layout.ue4ss_core_dir / "UE4SS.dll").is_file(),
        "settings": _ue4ss_settings_present(layout.ue4ss_core_dir),
    }
    server_loader_checks = {
        "version_dll": layout.server_loader.is_file(),
        "colocated_with_dwmapi": layout.server_loader.parent == layout.ue4ss_bootstrap.parent,
    }
    rs_checks = {
        "root": layout.runeschema_root.is_dir(),
        "enabled": layout.runeschema_enabled_file.is_file(),
        "config": layout.runeschema_config_dir.is_dir(),
        "dlls": layout.runeschema_dlls_dir.is_dir(),
    }
    lib_ue_checks = {
        "bootstrap": (UE4SS_RUNTIME_DIR / "dwmapi.dll").is_file(),
        "core_dll": (UE4SS_RUNTIME_DIR / "ue4ss" / "UE4SS.dll").is_file(),
        "settings": _ue4ss_settings_present(UE4SS_RUNTIME_DIR / "ue4ss"),
    }
    lib_server_loader_checks = {
        "version_dll": (UE4SS_RUNTIME_DIR / SERVER_LOADER_FILENAME).is_file(),
    }
    lib_rs_checks = {
        "enabled": (RUNESCHEMA_RUNTIME_DIR / "enabled.txt").is_file(),
        "config": (RUNESCHEMA_RUNTIME_DIR / "config").is_dir(),
        "dlls": (RUNESCHEMA_RUNTIME_DIR / "dlls").is_dir(),
    }
    ue_ok = all(ue_checks.values())
    server_loader_ok = all(server_loader_checks.values())
    rs_ok = all(rs_checks.values())
    return {
        "ok": ue_ok and server_loader_ok and rs_ok,
        "game_root": str(layout.game_root),
        "ue4ss": {"installed": ue_ok, "checks": ue_checks, "library_ready": all(lib_ue_checks.values()), "library_checks": lib_ue_checks},
        "server_loader": {
            "installed": server_loader_ok,
            "checks": server_loader_checks,
            "library_ready": all(lib_server_loader_checks.values()),
            "library_checks": lib_server_loader_checks,
            "server_only": True,
            "client_distributed": False,
            "filename": SERVER_LOADER_FILENAME,
        },
        "runeschema": {
            "installed": rs_ok, "checks": rs_checks, "library_ready": all(lib_rs_checks.values()), "library_checks": lib_rs_checks,
            "cached_core_zip": str(RUNESCHEMA_CORE_CACHE_ZIP) if RUNESCHEMA_CORE_CACHE_ZIP.is_file() else "",
            "bundled_core_zip": str(_bundled_app_resource("RuneSchema-core-latest.zip")) if _bundled_app_resource("RuneSchema-core-latest.zip").is_file() else "",
        },
        "bundled_ue4ss_zip": str(_bundled_app_resource(*BUNDLED_UE4SS_RESOURCE)) if _bundled_app_resource(*BUNDLED_UE4SS_RESOURCE).is_file() else "",
    }


def capture_authoritative_runtimes(game_root: str) -> dict:
    """Seed the app-owned repair library from an already-good live install.

    This lets Dragonwilds Sync adopt an existing manually-installed UE4SS /
    RuneSchema base once, then repair future World swaps or accidental deletes
    without asking the maintainer to find the files again. Per-World mods are
    deliberately excluded.
    """
    layout = resolve_server_layout(game_root)
    status = runtime_prerequisite_status(game_root)
    captured = {"ue4ss_files": 0, "server_loader_files": 0, "runeschema_files": 0}
    # Capture UE4SS first. The Dragonwilds dedicated-server version.dll is not
    # an upstream UE4SS file and is captured *after* any UE4SS library rebuild
    # so a clean-cache adoption can never erase it.
    if status["ue4ss"]["installed"] and not status["ue4ss"]["library_ready"]:
        shutil.rmtree(UE4SS_RUNTIME_DIR, ignore_errors=True)
        UE4SS_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        if layout.ue4ss_bootstrap.is_file():
            shutil.copy2(layout.ue4ss_bootstrap, UE4SS_RUNTIME_DIR / "dwmapi.dll")
            captured["ue4ss_files"] += 1
        if layout.ue4ss_core_dir.exists():
            target_core = UE4SS_RUNTIME_DIR / "ue4ss"
            for src in layout.ue4ss_core_dir.rglob("*"):
                if not src.is_file():
                    continue
                rel = src.relative_to(layout.ue4ss_core_dir)
                if rel.parts and rel.parts[0].casefold() == "mods":
                    continue
                dest = target_core / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                captured["ue4ss_files"] += 1
    # Capture the dedicated-server loader independently after UE4SS cache
    # rebuild. Existing cached loader wins; otherwise adopt the live one.
    if layout.server_loader.is_file() and not (UE4SS_RUNTIME_DIR / SERVER_LOADER_FILENAME).is_file():
        UE4SS_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(layout.server_loader, UE4SS_RUNTIME_DIR / SERVER_LOADER_FILENAME)
        captured["server_loader_files"] += 1
    if status["runeschema"]["installed"] and not status["runeschema"]["library_ready"]:
        shutil.rmtree(RUNESCHEMA_RUNTIME_DIR, ignore_errors=True)
        RUNESCHEMA_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        for src in layout.runeschema_root.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(layout.runeschema_root)
            if rel.parts and rel.parts[0].casefold() == "mods":
                continue
            dest = RUNESCHEMA_RUNTIME_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            captured["runeschema_files"] += 1
        # Preserve the required directory contract even when a source package
        # happens to contain empty config/dlls directories.
        (RUNESCHEMA_RUNTIME_DIR / "config").mkdir(parents=True, exist_ok=True)
        (RUNESCHEMA_RUNTIME_DIR / "dlls").mkdir(parents=True, exist_ok=True)
        (RUNESCHEMA_RUNTIME_DIR / "mods").mkdir(parents=True, exist_ok=True)
        (RUNESCHEMA_RUNTIME_DIR / "enabled.txt").write_text("", encoding="utf-8")
        layout.runeschema_enabled_file.write_text("", encoding="utf-8")
    _set_runtime_configs_writable(
        layout.ue4ss_core_dir, layout.runeschema_root,
        UE4SS_RUNTIME_DIR / "ue4ss", RUNESCHEMA_RUNTIME_DIR,
    )
    return {**captured, "status": runtime_prerequisite_status(game_root)}


def ensure_base_runtimes(game_root: str, *, allow_ue4ss_download: bool = True, ue4ss_source_url: str = "", runeschema_source_url: str = "", auto_rsdwtools: bool = True) -> dict:
    """Serialize runtime repair with startup/manual update operations."""
    with RUNTIME_MUTATION_LOCK:
        return _ensure_base_runtimes_unlocked(
            game_root,
            allow_ue4ss_download=allow_ue4ss_download,
            ue4ss_source_url=ue4ss_source_url,
            runeschema_source_url=runeschema_source_url,
            auto_rsdwtools=auto_rsdwtools,
        )


def _ensure_base_runtimes_unlocked(game_root: str, *, allow_ue4ss_download: bool = True, ue4ss_source_url: str = "", runeschema_source_url: str = "", auto_rsdwtools: bool = True) -> dict:
    """Self-heal UE4SS and RuneSchema before a hosted World is used.

    Server Setup owns these machine-wide prerequisites. UE4SS can bootstrap
    from its configured GitHub/release ZIP source. RuneSchema repairs from the
    app-owned runtime library, the last imported core ZIP, an optional launcher-
    bundled core ZIP, or its configured GitHub/release ZIP source.
    """
    if not str(game_root or "").strip():
        raise ValueError("A dedicated server root is required for runtime validation.")
    layout = resolve_server_layout(game_root)
    if not layout.game_root.exists():
        raise ValueError("The dedicated server game root does not exist yet. Run Settings → Server → Full Setup first.")
    # Repair every path an older launcher release may have marked read-only
    # before validation, profile restore, mods.txt generation, or process start.
    for managed_root in (
        layout.ue4ss_core_dir, layout.paks_mods_dir, layout.config_dir,
        UE4SS_RUNTIME_DIR, RUNESCHEMA_RUNTIME_DIR, CLIENT_RUNTIME_OVERRIDE_DIR,
    ):
        _set_runtime_tree_writable(managed_root, True)
    if sys.platform.startswith("linux") and layout.server_exe.suffix.casefold() != ".exe":
        status = runtime_prerequisite_status(game_root)
        return {
            "ok": True, "before": status, "after": status, "repaired": [], "errors": [],
            "warnings": [status["platform_note"]],
            "action_required": False, "native_linux_server": True,
        }

    before = runtime_prerequisite_status(game_root)
    # Adopt a manually-prepared good runtime as our repair source before doing
    # anything destructive. If the launcher release includes the Dragonwilds
    # server-only loader, seed it only when neither the live server nor the
    # authoritative runtime library already has one.
    capture_authoritative_runtimes(game_root)
    _ensure_server_loader_library_from_bundle()
    status = runtime_prerequisite_status(game_root)
    repaired: list[str] = []
    errors: list[str] = []

    if not status["ue4ss"]["installed"]:
        bundled_ue4ss = _bundled_app_resource(*BUNDLED_UE4SS_RESOURCE)
        if status["ue4ss"]["library_ready"]:
            deploy_authoritative_runtimes(game_root, include_ue4ss=True, include_runeschema=False)
            repaired.append("UE4SS restored from cached base runtime")
        elif bundled_ue4ss.is_file():
            install_authoritative_ue4ss_zip(str(bundled_ue4ss), str(layout.game_root))
            repaired.append("UE4SS installed from launcher-bundled Dragonwilds runtime package")
        elif allow_ue4ss_download:
            source = str(ue4ss_source_url or DEFAULT_UE4SS_RELEASES_URL).strip()
            update = check_ue4ss_update(source) or resolve_runtime_zip_source(source, prefer_contains=("ue4ss",)) or {}
            if update.get("download_url"):
                install_authoritative_ue4ss_update(str(update["download_url"]), str(layout.game_root))
                repaired.append(f"UE4SS installed from {update.get('filename') or source}")
            else:
                errors.append("UE4SS is missing and the configured release source could not be resolved.")
        else:
            errors.append("UE4SS is missing and no cached/bundled base runtime is available.")

    status = runtime_prerequisite_status(game_root)
    if not status.get("server_loader", {}).get("installed"):
        if status.get("server_loader", {}).get("library_ready"):
            deploy_authoritative_runtimes(game_root, include_ue4ss=True, include_runeschema=False)
            repaired.append("Dragonwilds server version.dll restored from cached server runtime")
        else:
            errors.append("Dragonwilds dedicated-server version.dll is missing and no cached/bundled server loader is available. Load the Dragonwilds server runtime ZIP once; future UE4SS updates will preserve this server-only DLL.")

    status = runtime_prerequisite_status(game_root)
    if not status["runeschema"]["installed"]:
        if status["runeschema"]["library_ready"]:
            deploy_authoritative_runtimes(game_root, include_ue4ss=False, include_runeschema=True)
            repaired.append("RuneSchema restored from cached base runtime")
        elif RUNESCHEMA_CORE_CACHE_ZIP.is_file():
            install_runeschema_zip(str(RUNESCHEMA_CORE_CACHE_ZIP), str(layout.game_root))
            repaired.append("RuneSchema restored from cached core package")
        elif _bundled_app_resource("RuneSchema-core-latest.zip").is_file():
            install_runeschema_zip(str(_bundled_app_resource("RuneSchema-core-latest.zip")), str(layout.game_root))
            repaired.append("RuneSchema installed from launcher-bundled core package")
        elif str(runeschema_source_url or "").strip():
            try:
                result = install_authoritative_runeschema_update(str(runeschema_source_url).strip(), str(layout.game_root))
                repaired.append(f"RuneSchema installed from {result.get('filename') or runeschema_source_url}")
            except Exception as exc:
                errors.append(f"RuneSchema is missing and the configured release source failed: {exc}")
        else:
            errors.append("RuneSchema is missing. Load a core ZIP, configure a GitHub/release ZIP source, or use a launcher build containing the bundled RuneSchema core.")

    try:
        from persistent_direct_connect import ensure_installed as ensure_dragonconnect
        dragonconnect = ensure_dragonconnect(layout.game_root)
        if dragonconnect.get("changed"):
            repaired.append("DragonConnect host baseline installed/repaired")
    except Exception as exc:
        errors.append(f"DragonConnect host baseline repair failed: {exc}")

    try:
        rsdwtools = ensure_rsdwtools_baseline(layout.ue4ss_mods_dir, allow_update=auto_rsdwtools)
        if rsdwtools.get("changed"):
            repaired.append("RSDWTools bridge baseline installed/updated (DEBUG_BRIDGE=false)")
        if not rsdwtools.get("ok"):
            errors.append(str(rsdwtools.get("error") or "RSDWTools baseline repair failed."))
    except Exception as exc:
        errors.append(f"RSDWTools server baseline repair failed: {exc}")

    after = runtime_prerequisite_status(game_root)
    base_ok = bool(after.get("ok"))
    return {
        "ok": base_ok, "before": before, "after": after,
        "repaired": repaired, "errors": errors, "warnings": [],
        "action_required": not base_ok,
    }


def deploy_authoritative_runtimes(game_root: str, include_ue4ss: bool = True, include_runeschema: bool = True) -> dict:
    """Overlay app-owned runtime cores onto one dedicated-server install.

    Runtime libraries are machine-wide and intentionally separate from per-World
    mod snapshots. RuneSchema's ``mods`` children remain profile-owned.
    """
    layout = resolve_server_layout(game_root)
    root = layout.game_root
    if not game_root or not root.exists():
        raise ValueError("A valid dedicated server root is required to deploy runtimes.")
    win64 = layout.win64_dir
    win64.mkdir(parents=True, exist_ok=True)
    copied_ue4ss = 0
    copied_runeschema = 0
    if include_ue4ss and UE4SS_RUNTIME_DIR.exists():
        for src in UE4SS_RUNTIME_DIR.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(UE4SS_RUNTIME_DIR)
            if src.name.casefold() == SERVER_LOADER_FILENAME.casefold() and rel != Path(SERVER_LOADER_FILENAME):
                continue
            dest = win64 / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied_ue4ss += 1
    if include_runeschema and RUNESCHEMA_RUNTIME_DIR.exists():
        target = layout.runeschema_root
        target.mkdir(parents=True, exist_ok=True)
        for src in RUNESCHEMA_RUNTIME_DIR.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(RUNESCHEMA_RUNTIME_DIR)
            if rel.parts and rel.parts[0].lower() == "mods":
                continue
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied_runeschema += 1
        # Self-enabled RuneSchema infrastructure is intentionally omitted from
        # generated mods.txt; presence of a blank enabled.txt is authoritative.
        (target / "enabled.txt").write_text("", encoding="utf-8")
        (RUNESCHEMA_RUNTIME_DIR / "enabled.txt").write_text("", encoding="utf-8")
        (target / "mods").mkdir(parents=True, exist_ok=True)
        (RUNESCHEMA_RUNTIME_DIR / "mods").mkdir(parents=True, exist_ok=True)
    writable = _set_runtime_configs_writable(
        layout.ue4ss_core_dir, layout.runeschema_root,
        UE4SS_RUNTIME_DIR / "ue4ss", RUNESCHEMA_RUNTIME_DIR,
    )
    return {"ok": True, "ue4ss_files": copied_ue4ss, "runeschema_files": copied_runeschema,
            "editable_configs_repaired": writable}


def _preserved_server_loader_bytes(game_root: str) -> tuple[bytes | None, str]:
    """Read the Dragonwilds server-only version.dll before replacing UE4SS.

    Prefer the live dedicated-server copy because that is the operator-proven
    runtime. Fall back to the app-owned runtime library.
    """
    layout = resolve_server_layout(game_root)
    for candidate in (layout.server_loader, UE4SS_RUNTIME_DIR / SERVER_LOADER_FILENAME):
        try:
            if candidate.is_file():
                return candidate.read_bytes(), str(candidate)
        except OSError:
            continue
    return None, ""


def _restore_server_loader_to_runtime(payload: bytes | None) -> bool:
    if not payload:
        return False
    target = UE4SS_RUNTIME_DIR / SERVER_LOADER_FILENAME
    if target.is_file():
        # A deliberately supplied Dragonwilds server runtime ZIP may carry a
        # newer version.dll. Never overwrite that with the preserved copy.
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return True


def _copy_baseline_integration(source: Path, destination: Path, *, exclude_mods: bool = False) -> int:
    """Copy one launcher baseline integration without profile-owned content."""
    if not source.is_dir():
        return 0
    copied = 0
    for item in source.rglob("*"):
        if not item.is_file():
            continue
        relative = item.relative_to(source)
        if exclude_mods and relative.parts and relative.parts[0].casefold() == "mods":
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied += 1
    return copied


def _preserve_live_baseline_integrations(game_root: str, destination: Path) -> dict:
    """Stage RuneSchema core and RSDWTools while UE4SS itself is replaced."""
    layout = resolve_server_layout(game_root)
    mods = destination / "ue4ss" / "Mods"
    return {
        "runeschema_files": _copy_baseline_integration(layout.runeschema_root, mods / "RuneSchema", exclude_mods=True),
        "rsdwtools_files": _copy_baseline_integration(layout.ue4ss_mods_dir / "RSDWTools", mods / "RSDWTools"),
    }


def _restore_missing_baseline_integrations(staged: Path) -> dict:
    """Restore integrations absent from an ordinary upstream UE4SS archive."""
    runtime_mods = UE4SS_RUNTIME_DIR / "ue4ss" / "Mods"
    staged_mods = staged / "ue4ss" / "Mods"
    restored = {"runeschema_files": 0, "rsdwtools_files": 0}
    for name, key, exclude in (("RuneSchema", "runeschema_files", True), ("RSDWTools", "rsdwtools_files", False)):
        target = runtime_mods / name
        source = staged_mods / name
        if not target.exists() and source.is_dir():
            restored[key] = _copy_baseline_integration(source, target, exclude_mods=exclude)
    return restored


def _adopt_runtime_runeschema_core() -> int:
    """Mirror the UE4SS-bundled RuneSchema core into its repair library."""
    source = UE4SS_RUNTIME_DIR / "ue4ss" / "Mods" / "RuneSchema"
    if not source.is_dir():
        return 0
    shutil.rmtree(RUNESCHEMA_RUNTIME_DIR, ignore_errors=True)
    RUNESCHEMA_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    copied = _copy_baseline_integration(source, RUNESCHEMA_RUNTIME_DIR, exclude_mods=True)
    (RUNESCHEMA_RUNTIME_DIR / "config").mkdir(parents=True, exist_ok=True)
    (RUNESCHEMA_RUNTIME_DIR / "dlls").mkdir(parents=True, exist_ok=True)
    (RUNESCHEMA_RUNTIME_DIR / "mods").mkdir(parents=True, exist_ok=True)
    (RUNESCHEMA_RUNTIME_DIR / "enabled.txt").write_text("", encoding="utf-8")
    return copied


def install_authoritative_ue4ss_zip(zip_path: str, game_root: str) -> dict:
    with RUNTIME_MUTATION_LOCK:
        if not _is_launcher_bundled_ue4ss(zip_path):
            review_with_defender(zip_path, "mod package")
        preserved_loader, preserved_from = _preserved_server_loader_bytes(game_root)
        with tempfile.TemporaryDirectory(prefix="dwsync-integrations-") as temp:
            staged = Path(temp)
            preserved = _preserve_live_baseline_integrations(game_root, staged)
            shutil.rmtree(UE4SS_RUNTIME_DIR, ignore_errors=True)
            UE4SS_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
            result = install_ue4ss_zip(zip_path, str(UE4SS_RUNTIME_DIR))
            restored = _restore_missing_baseline_integrations(staged)
        restored_loader = _restore_server_loader_to_runtime(preserved_loader)
        adopted_runeschema = _adopt_runtime_runeschema_core()
        deployed = deploy_authoritative_runtimes(game_root, include_ue4ss=True, include_runeschema=True)
        return {**result, "runtime_library": str(UE4SS_RUNTIME_DIR), "deployed": deployed,
                "server_loader_preserved": bool(preserved_loader), "server_loader_restored": restored_loader,
                "server_loader_source": preserved_from, "integrations_preserved": preserved,
                "integrations_restored": restored, "runeschema_core_adopted": adopted_runeschema}


def install_authoritative_ue4ss_update(download_url: str, game_root: str, timeout: float = 90.0) -> dict:
    with RUNTIME_MUTATION_LOCK:
        preserved_loader, preserved_from = _preserved_server_loader_bytes(game_root)
        with tempfile.TemporaryDirectory(prefix="dwsync-integrations-") as temp:
            staged = Path(temp)
            preserved = _preserve_live_baseline_integrations(game_root, staged)
            shutil.rmtree(UE4SS_RUNTIME_DIR, ignore_errors=True)
            UE4SS_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
            result = install_ue4ss_update(download_url, str(UE4SS_RUNTIME_DIR), timeout=timeout)
            restored = _restore_missing_baseline_integrations(staged)
        restored_loader = _restore_server_loader_to_runtime(preserved_loader)
        adopted_runeschema = _adopt_runtime_runeschema_core()
        deployed = deploy_authoritative_runtimes(game_root, include_ue4ss=True, include_runeschema=True)
        return {**result, "runtime_library": str(UE4SS_RUNTIME_DIR), "deployed": deployed,
                "server_loader_preserved": bool(preserved_loader), "server_loader_restored": restored_loader,
                "server_loader_source": preserved_from, "integrations_preserved": preserved,
                "integrations_restored": restored, "runeschema_core_adopted": adopted_runeschema}



_PAK_LOAD_PREFIX = re.compile(r"^(\d{2,3})_(.+)$")
_PAK_PACKAGE_EXTENSIONS = {".pak", ".utoc", ".ucas"}


def _strip_pak_load_prefix(name: str) -> tuple[int | None, str]:
    match = _PAK_LOAD_PREFIX.match(str(name or ""))
    return (int(match.group(1)), match.group(2)) if match else (None, str(name or ""))


def _pak_physical_groups(root: Path) -> list[dict]:
    groups: dict[str, dict] = {}
    if not root.exists():
        return []
    for path in root.iterdir():
        if path.name.startswith("."):
            continue
        if path.is_dir():
            order, clean = _strip_pak_load_prefix(path.name)
            groups[clean.casefold()] = {"name": clean, "order": order, "paths": [path]}
        elif path.suffix.casefold() in _PAK_PACKAGE_EXTENSIONS:
            order, clean = _strip_pak_load_prefix(path.stem)
            item = groups.setdefault(clean.casefold(), {"name": clean, "order": order, "paths": []})
            item["paths"].append(path)
            if item.get("order") is None and order is not None:
                item["order"] = order
    result = list(groups.values())
    result.sort(key=lambda item: (item.get("order") if item.get("order") is not None else 9999, item["name"].casefold()))
    return result


def _materialize_pak_order(root: Path, ordered_names: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    groups = {item["name"].casefold(): item for item in _pak_physical_groups(root)}
    ordered, seen = [], set()
    for raw in ordered_names:
        key = str(raw or "").casefold()
        if key in groups and key not in seen:
            ordered.append(groups[key]); seen.add(key)
    for item in _pak_physical_groups(root):
        key = item["name"].casefold()
        if key not in seen:
            ordered.append(item); seen.add(key)
    staged = []
    for idx, item in enumerate(ordered, 1):
        prefix = f"{idx:02d}_"
        for src in item["paths"]:
            final = src.with_name(prefix + item["name"] + (src.suffix if src.is_file() else ""))
            temp = src.with_name(f".dwsync-order-{idx:03d}-{len(staged):03d}-{src.name}")
            src.rename(temp); staged.append((temp, final))
    for temp, final in staged:
        if final.exists():
            if final.is_dir(): shutil.rmtree(final)
            else: final.unlink()
        temp.rename(final)


def _peel_mod_wrapper(root: Path) -> tuple[Path, str | None]:
    entries = [p for p in root.iterdir() if not p.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0], entries[0].name
    return root, None


def _copy_mod_contents(source: Path, destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    written = 0
    for src in source.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(source); dest = destination / rel
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dest); written += 1
    return written


def _snapshot_world_mod_rollback(profile_id: str, paths: list[Path], label: str) -> str:
    existing = [Path(p) for p in paths if Path(p).exists()]
    if not existing:
        return ""
    rollback_dir = SERVER_PROFILES_DIR / profile_id / "mod_rollbacks"
    rollback_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_. -]+", "_", str(label or "mod")).strip(" .") or "mod"
    target = rollback_dir / f"{int(time.time())}-{safe}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in existing:
            if item.is_dir():
                for child in item.rglob("*"):
                    if child.is_file():
                        zf.write(child, (Path(item.name) / child.relative_to(item)).as_posix())
            elif item.is_file():
                zf.write(item, item.name)
    siblings = sorted(rollback_dir.glob(f"*-{safe}.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
    for stale in siblings[3:]:
        stale.unlink(missing_ok=True)
    return str(target)


def inspect_world_mod_zip(zip_path: str) -> dict:
    archive = Path(zip_path)
    detected = detect_mod_zip_kind(zip_path)
    with tempfile.TemporaryDirectory(prefix="dwsync_mod_inspect_") as temp:
        scratch = Path(temp)
        with zipfile.ZipFile(archive) as zf:
            safe_extract_zip(zf, scratch)
        payloads = inspect_mod_payloads(scratch)
        if not payloads and detected:
            located = locate_mod_payload(scratch, detected, archive.stem)
            content = Path(located["content"])
            payloads = [{"id": f"{detected}:{content.relative_to(scratch).as_posix()}", "kind": detected,
                         "name": str(located.get("name") or archive.stem),
                         "payload_root": content.relative_to(scratch).as_posix(), "payload_name": "", "selected": True}]
    kinds = {str(item.get("kind") or "") for item in payloads}
    return {"kind": next(iter(kinds)) if len(payloads) == 1 and len(kinds) == 1 else "",
            "detected_kind": detected or "", "payloads": payloads, "count": len(payloads)}


def install_world_mod_zip(profile_id: str, game_root: str, zip_path: str, *, active: bool = True,
                          preferred_kind: str | None = None, payload_root: str = "", payload_name: str = "") -> dict:
    """Install a normal World mod ZIP into its authoritative live/snapshot slot.

    UE4SS imports deliberately lose embedded enabled.txt so Dragonwilds Sync owns
    enablement/order through mods.txt. Normal PAKs receive numeric load prefixes.
    RuneSchema mods remain untouched beneath RuneSchema/mods and have no order.
    """
    archive = Path(zip_path)
    if not archive.is_file():
        raise FileNotFoundError("Mod ZIP was not found.")
    review_with_defender(zip_path, "mod package")
    kind = str(preferred_kind or detect_mod_zip_kind(zip_path) or "").casefold()
    if kind not in {"ue4ss", "paks", "runeschema"}:
        raise ValueError("Could not identify this ZIP as a UE4SS, PAK, or RuneSchema mod.")
    if active:
        layout = resolve_server_layout(game_root)
        ue4ss_root, paks_root, rs_mods_root = layout.ue4ss_mods_dir, layout.paks_mods_dir, layout.runeschema_mods_dir
    else:
        stored = SERVER_PROFILES_DIR / profile_id / "mods"
        ue4ss_root, paks_root = stored / "ue4ss_mods", stored / "pak_mods"
        rs_mods_root = ue4ss_root / "RuneSchema" / "mods"
    for managed_root in (ue4ss_root, paks_root, rs_mods_root):
        _set_runtime_tree_writable(managed_root, True)
    with tempfile.TemporaryDirectory(prefix="dwsync_world_mod_") as temp:
        scratch = Path(temp)
        with zipfile.ZipFile(archive) as zf:
            safe_extract_zip(zf, scratch)
        located = locate_mod_payload(scratch, kind, archive.stem, payload_root=payload_root, payload_name=payload_name)
        content = Path(located["content"])
        payload_root = content.relative_to(scratch).as_posix() or "."
        metadata_root = content
        archive_metadata = {"tags": [], "hotload_capable": False, "tag_files": [], "hotload_files": []}
        mod_name = re.sub(r"[^A-Za-z0-9_. -]+", "_", str(located.get("name") or archive.stem)).strip(" .") or "ImportedMod"
        if kind == "ue4ss":
            if mod_name.casefold() == "runeschema":
                raise ValueError(f"{mod_name} is launcher-managed infrastructure and cannot be imported as a normal UE4SS mod.")
            if mod_name.casefold() == "runeschema":
                raise ValueError(f"{mod_name} is launcher-managed infrastructure and cannot be imported as a normal UE4SS mod.")
            archive_metadata = discover_packaged_metadata(metadata_root, effective_root=content, recursive_fallback=False)
            dest = ue4ss_root / mod_name
            rollback_archive = _snapshot_world_mod_rollback(profile_id, [dest], f"ue4ss-{mod_name}")
            shutil.rmtree(dest, ignore_errors=True)
            written = _copy_mod_contents(content, dest)
            removed = 0
            for marker in list(dest.rglob("enabled.txt")):
                marker.unlink(missing_ok=True); removed += 1
            if archive_metadata.get("hotload_capable"): set_hotload_marker(dest, True)
            result = {"ok": True, "kind": kind, "name": mod_name, "destination": str(dest), "files_written": written, "enabled_markers_removed": removed, "rollback_archive": rollback_archive}
        elif kind == "runeschema":
            archive_metadata = discover_packaged_metadata(metadata_root, effective_root=content)
            dest = rs_mods_root / mod_name
            rollback_archive = _snapshot_world_mod_rollback(profile_id, [dest], f"runeschema-{mod_name}")
            shutil.rmtree(dest, ignore_errors=True)
            written = _copy_mod_contents(content, dest)
            if archive_metadata.get("hotload_capable"): set_hotload_marker(dest, True)
            if archive_metadata.get("tags"): set_tags_file(dest, archive_metadata.get("tags"))
            result = {"ok": True, "kind": kind, "name": mod_name, "destination": str(dest), "files_written": written, "enabled_markers_removed": 0, "rollback_archive": rollback_archive}
        else:
            paks_root.mkdir(parents=True, exist_ok=True)
            package_files = list(located.get("files") or [])
            if not package_files:
                raise ValueError("No .pak/.utoc/.ucas files were found in this archive.")
            archive_metadata = discover_packaged_metadata(metadata_root, effective_root=content, payload_files=package_files)
            incoming_name = _strip_pak_load_prefix(package_files[0].stem)[1]
            existing_group = [p for p in paks_root.iterdir() if p.is_file() and p.suffix.casefold() in _PAK_PACKAGE_EXTENSIONS and _strip_pak_load_prefix(p.stem)[1].casefold() == incoming_name.casefold()]
            rollback_archive = _snapshot_world_mod_rollback(profile_id, existing_group, f"paks-{incoming_name}")
            for src in package_files:
                _, clean = _strip_pak_load_prefix(src.stem)
                shutil.copy2(src, paks_root / f"{clean}{src.suffix}")
            order = [item["name"] for item in _pak_physical_groups(paks_root)]
            _materialize_pak_order(paks_root, order)
            result = {"ok": True, "kind": kind, "name": _strip_pak_load_prefix(package_files[0].stem)[1], "destination": str(paks_root), "files_written": len(package_files), "enabled_markers_removed": 0, "rollback_archive": rollback_archive}
        source_manifest = Path(str(located.get("manifest") or "")) if located.get("manifest") else None
        installed_manifest = ""
        if source_manifest and source_manifest.is_file():
            if kind in {"ue4ss", "runeschema"}:
                installed = dest / source_manifest.relative_to(content)
            else:
                installed = paks_root / f"{result['name']}.{source_manifest.name}"
                shutil.copy2(source_manifest, installed)
            installed_manifest = str(installed)
    units = scan_mod_units(profile_id, game_root) if active else scan_profile_snapshot_units(profile_id)
    persist_unit_overrides(profile_id, units)
    archive_tags = normalize_tags(archive_metadata.get("tags"))
    archive_hotload = bool(kind in {"ue4ss", "runeschema"} and archive_metadata.get("hotload_capable"))
    if archive_tags or archive_hotload:
        profile = load_server_profile(profile_id); overrides = profile.setdefault("unit_overrides", {})
        group = {"ue4ss": "ue4ss_mod", "paks": "pak_mod", "runeschema": "runeschema_mod"}[kind]
        key = f"{group}::{result['name']}"; current = dict(overrides.get(key) or {})
        if archive_tags: current["tags"] = archive_tags
        if archive_hotload: current["hotload_capable"] = True
        overrides[key] = current; save_server_profile(profile_id, profile)
    result["tags"] = archive_tags
    result["hotload_capable"] = archive_hotload
    result["metadata_detected"] = {"tag_files": list(archive_metadata.get("tag_files") or []), "hotload_files": list(archive_metadata.get("hotload_files") or [])}
    result["payload_root"] = payload_root
    result["main_manifest"] = installed_manifest
    if active:
        generate_server_mods_txt(profile_id, game_root)
    return result

def detect_mod_zip_kind(path: str) -> str | None:
    p = Path(path)
    try:
        with zipfile.ZipFile(p) as zf:
            names = [n.lower().replace("\\", "/").strip("/") for n in zf.namelist() if n and not n.endswith("/")]
    except Exception:
        return None
    wrapped = [f"/{n}" for n in names]
    # tags.json, <pak>.tags.json, and hotload.json are launcher metadata,
    # not evidence that the archive itself is a RuneSchema mod.
    def is_content_json(name: str) -> bool:
        leaf = name.rsplit("/", 1)[-1]
        return name.endswith(".json") and leaf not in {"tags.json", "hotload.json"} and not leaf.endswith(".tags.json")

    has_json = any(is_content_json(n) for n in names)
    has_pak = any(n.endswith((".pak", ".utoc", ".ucas")) for n in names)
    has_main_lua = any(n.endswith("scripts/main.lua") for n in names)
    if any("/ue4ss/mods/" in n for n in wrapped):
        return "ue4ss"
    if "runeschema" in p.name.lower() or any("/runeschema/" in n for n in wrapped):
        return "runeschema"
    if any(n.startswith("raw/") or "/raw/" in n for n in names) and has_json:
        return "runeschema"
    # A RuneSchema child mod can legitimately contain JSON, scripts/main.lua,
    # and an embedded PAK. Keep the archive intact beneath RuneSchema/mods.
    if has_json and (has_main_lua or has_pak):
        return "runeschema"
    if has_main_lua:
        return "ue4ss"
    if any(n.endswith(".lua") for n in names) and not has_pak:
        return "ue4ss"
    if has_pak:
        return "paks"
    if has_json:
        return "runeschema"
    return None


def install_runeschema_zip(zip_path: str, game_root: str, *, role: str = "server") -> dict:
    review_with_defender(zip_path, "mod package")
    """Install either a full RuneSchema package or one RuneSchema mod.

    Full/core packages are recognized by a top-level ``mods`` directory after
    peeling one release wrapper folder. Core files are retained in the app-owned
    runtime library and merged into the live RuneSchema folder. Its ``mods``
    directory is profile-owned, so child mods bundled in a core archive are
    intentionally ignored. A non-core archive becomes one mod under
    Runeschema/mods/<archive-or-wrapper-name>.
    """
    normalized_role = str(role or "server").strip().casefold()
    if normalized_role not in {"server", "client"}:
        raise ValueError("RuneSchema runtime role must be server or client.")
    live_rs = (resolve_client_layout(game_root).runeschema_root if normalized_role == "client"
               else resolve_server_layout(game_root).runeschema_root)
    live_rs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dwsync_rs_") as temp:
        scratch = Path(temp)
        with zipfile.ZipFile(zip_path) as zf: safe_extract_zip(zf, scratch)
        entries = [p for p in scratch.iterdir() if not p.name.startswith(".")]
        wrapper_name = entries[0].name if len(entries) == 1 and entries[0].is_dir() else None

        def core_contract(path: Path) -> bool:
            children = {child.name.casefold(): child for child in path.iterdir()} if path.is_dir() else {}
            return ("enabled.txt" in children and children["enabled.txt"].is_file()
                    and "dlls" in children and children["dlls"].is_dir()
                    and ("config" in children or "mods" in children))

        # Release archives and manually packed builds commonly add repository
        # and product wrappers (for example runeschema/RuneSchema/...). Locate
        # the one actual runtime root instead of treating it as a child mod.
        candidates = [path for path in [scratch, *scratch.rglob("*")] if path.is_dir() and core_contract(path)]
        candidates.sort(key=lambda path: len(path.relative_to(scratch).parts))
        content_root = candidates[0] if candidates else (entries[0] if len(entries) == 1 and entries[0].is_dir() else scratch)
        # Core releases normally contain ``mods/``, but empty directories are
        # not always preserved by ZIP tooling. Recognize the authoritative
        # RuneSchema runtime contract as config + dlls + enabled.txt too.
        children = {child.name.casefold(): child for child in content_root.iterdir()} if content_root.is_dir() else {}
        mods_dir = children.get("mods", content_root / "mods")
        is_core = mods_dir.is_dir() or (
            bool(children.get("config") and children["config"].is_dir())
            and bool(children.get("dlls") and children["dlls"].is_dir())
            and bool(children.get("enabled.txt") and children["enabled.txt"].is_file())
        )
        written = 0
        if is_core:
            runtime_dir = CLIENT_RUNESCHEMA_RUNTIME_DIR if normalized_role == "client" else RUNESCHEMA_RUNTIME_DIR
            cache_target = CLIENT_RUNESCHEMA_CORE_CACHE_ZIP if normalized_role == "client" else RUNESCHEMA_CORE_CACHE_ZIP
            # A loaded native RuneSchema DLL cannot be replaced on Windows. Test
            # every live DLL before removing or copying anything so a stray or
            # still-shutting-down server process can never leave a half-written
            # runtime behind.
            live_dlls = live_rs / "dlls"
            if live_dlls.is_dir():
                for live_dll in live_dlls.rglob("*"):
                    if not live_dll.is_file():
                        continue
                    try:
                        with live_dll.open("r+b"):
                            pass
                    except PermissionError as exc:
                        raise PermissionError(
                            f"RuneSchema is still in use by a Dragonwilds process: {live_dll}. "
                            "Stop the dedicated server and wait for it to exit before applying the flavor. "
                            "No live RuneSchema files were changed."
                        ) from exc
            # A core update is a complete upstream replacement. Preserve only
            # profile-owned child mods; never mix one release's DLL with
            # another release's config/support files.
            live_mods = live_rs / "mods"
            for child in list(live_rs.iterdir()):
                if child != live_mods:
                    _remove_generated_path(child)
            cache_target.parent.mkdir(parents=True, exist_ok=True)
            src_zip = Path(zip_path).resolve()
            cache_zip = cache_target.resolve()
            cache_zip.parent.mkdir(parents=True, exist_ok=True)
            if src_zip != cache_zip:
                shutil.copy2(src_zip, cache_zip)
            shutil.rmtree(runtime_dir, ignore_errors=True); runtime_dir.mkdir(parents=True, exist_ok=True)
            for root, dirs, files in os.walk(content_root):
                if Path(root) == content_root: dirs[:] = [d for d in dirs if d.lower() != "mods"]
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                rel_root = Path(root).relative_to(content_root)
                for filename in files:
                    if filename.startswith("."): continue
                    src = Path(root) / filename
                    rel_parts = list(rel_root.parts)
                    if rel_parts and rel_parts[0].casefold() in {"config", "dlls"}:
                        rel_parts[0] = rel_parts[0].casefold()
                    rel = Path(*rel_parts) / filename
                    for base in (runtime_dir, live_rs):
                        dest = base / rel; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dest)
                    written += 1
            (runtime_dir / "config").mkdir(parents=True, exist_ok=True)
            (runtime_dir / "dlls").mkdir(parents=True, exist_ok=True)
            # RuneSchema is launcher infrastructure and self-enables by the
            # presence of a blank enabled.txt. Normalize both authoritative
            # library and live install so it never needs an entry in mods.txt.
            for base in (runtime_dir, live_rs):
                if not (base / "enabled.txt").exists():
                    (base / "enabled.txt").write_text("", encoding="utf-8")
                (base / "mods").mkdir(parents=True, exist_ok=True)
            writable = _set_runtime_configs_writable(runtime_dir, live_rs)
            ignored_mod_files = sum(1 for child in mods_dir.rglob("*") if child.is_file()) if mods_dir.is_dir() else 0
            return {"ok": True, "kind": "core", "role": normalized_role, "files_written": written,
                    "bundled_mod_files_ignored": ignored_mod_files,
                    "mods_profile_owned": True, "destination": str(live_rs),
                    "editable_configs_repaired": writable}
        name = wrapper_name or Path(zip_path).stem
        dest_root = live_rs / "mods" / name; dest_root.mkdir(parents=True, exist_ok=True)
        for src in content_root.rglob("*"):
            if not src.is_file(): continue
            rel = src.relative_to(content_root); dest = dest_root / rel; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dest); written += 1
        return {"ok": True, "kind": "mod", "role": normalized_role, "name": name, "files_written": written, "destination": str(dest_root)}



class PlayerLogMonitor:
    """Headless dedicated-server monitor with join/leave parsing. No GUI dependencies."""
    def __init__(self):
        self.pid: int | None = None; self.exe_path = ""; self.start_ts: float | None = None
        self.players: set[str] = set(); self.log_path: Path | None = None; self.log_offset = 0; self.reported_cl = ""

    def poll(self, known_pid: int | None = None, known_exe: str = "") -> dict:
        pid = known_pid; exe = known_exe
        if pid is None:
            try:
                import psutil  # type: ignore
                for proc in psutil.process_iter(["pid", "name", "exe", "create_time"]):
                    if any(name.lower() in str(proc.info.get("name") or "").lower() for name in DEDICATED_SERVER_EXE_ALIASES):
                        pid = int(proc.info["pid"]); exe = str(proc.info.get("exe") or ""); self.start_ts = float(proc.info.get("create_time") or time.time()); break
            except Exception: pass
        if pid is None:
            self.pid = None; self.exe_path = ""; self.start_ts = None; self.players.clear(); self.log_path = None; self.log_offset = 0; self.reported_cl = ""
            with STATE.lock: STATE.server_online = False; STATE.player_count = 0; STATE.server_start_ts = None
            return {"online": False, "pid": None, "players": [], "player_count": 0, "uptime_seconds": None}
        if self.pid != pid:
            self.players.clear(); self.log_path = None; self.log_offset = 0; self.reported_cl = ""
        self.pid = pid; self.exe_path = exe or self.exe_path; self.start_ts = self.start_ts or time.time()
        if self.exe_path and not self.log_path:
            try:
                from server_layout import resolve_server_layout_from_exe
                logs = resolve_server_layout_from_exe(self.exe_path).logs_dir
                candidates = [logs / "RSDragonwilds.log", *sorted(logs.glob("*.log"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)]
            except Exception:
                base = Path(self.exe_path).parent
                candidates = [base / "RSDragonwilds" / "Saved" / "Logs" / "RSDragonwilds.log", base / "Saved" / "Logs" / "RSDragonwilds.log"]
            for candidate in candidates:
                if candidate.exists(): self.log_path = candidate; break
        if self.log_path and self.log_path.exists():
            try:
                size = self.log_path.stat().st_size
                if size < self.log_offset: self.log_offset = 0; self.players.clear()
                with self.log_path.open("r", encoding="utf-8", errors="ignore") as fh:
                    fh.seek(self.log_offset)
                    for line in fh:
                        reported_cl = normalize_cl_version(line)
                        if reported_cl:
                            self.reported_cl = reported_cl
                        m = _DEDICATED_JOIN_RE.search(line)
                        if m: self.players.add(m.group(1).strip()); continue
                        m = _DEDICATED_LEAVE_RE.search(line)
                        if m: self.players.discard(m.group(1).strip())
                    self.log_offset = fh.tell()
            except OSError: pass
        uptime = max(0, int(time.time() - self.start_ts)) if self.start_ts else None
        with STATE.lock: STATE.server_online = True; STATE.player_count = len(self.players); STATE.server_start_ts = self.start_ts
        return {"online": True, "pid": pid, "players": sorted(self.players), "player_count": len(self.players),
                "uptime_seconds": uptime, "reported_cl": self.reported_cl}


def clear_server_mods(game_root: str) -> dict:
    """Clear profile mods while retaining RuneSchema, RSDWTools, UE4SS core and mods.txt."""
    layout = resolve_server_layout(game_root)
    mods_root = layout.ue4ss_mods_dir
    paks_root = layout.paks_mods_dir
    removed = 0
    if paks_root.exists():
        for child in list(paks_root.iterdir()):
            if child.is_dir(): shutil.rmtree(child)
            else: child.unlink(missing_ok=True)
            removed += 1
    if mods_root.exists():
        for child in list(mods_root.iterdir()):
            lower = child.name.lower()
            if lower == "runeschema" and child.is_dir():
                rs_mods = child / "mods"
                if rs_mods.exists():
                    for mod in list(rs_mods.iterdir()):
                        if mod.is_dir(): shutil.rmtree(mod)
                        else: mod.unlink(missing_ok=True)
                        removed += 1
                continue
            if lower in {"mods.txt", "rsdwtools"}:
                continue
            if child.is_dir(): shutil.rmtree(child)
            else: child.unlink(missing_ok=True)
            removed += 1
    return {"ok": True, "removed_units": removed}


def backup_dedicated_savegames(destination_root: str, exe_path: str) -> dict:
    destination = Path(destination_root); destination.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S"); backup_root = destination / f"DragonwildsBackup-{stamp}"; backup_root.mkdir(parents=True, exist_ok=True)
    base = Path(exe_path).parent if exe_path else None
    candidates = []
    local = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "RSDragonwilds" / "Saved" / "SaveGames"
    if local.exists(): candidates.append(("LocalSaveGames", local))
    if base:
        for idx, path in enumerate((base / "RSDragonwilds" / "Saved" / "SaveGames", base / "Saved" / "SaveGames")):
            if path.exists(): candidates.append((f"DedicatedSaveGames-{idx+1}", path))
    if not candidates:
        shutil.rmtree(backup_root, ignore_errors=True); return {"ok": False, "reason": "No SaveGames folders found"}
    for label, src in candidates: shutil.copytree(src, backup_root / label, dirs_exist_ok=True)
    return {"ok": True, "path": str(backup_root), "sources": len(candidates)}
