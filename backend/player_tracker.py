from __future__ import annotations

import json
import math
import os
import struct
import threading
import time
from contextlib import contextmanager

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

MAX_SHM_BYTES = 1024 * 1024
DEFAULT_WORLD_CALIBRATION = {"world_min_x": -11075.0, "world_max_x": 408925.0,
                             "world_min_y": -117685.0, "world_max_y": 302315.0,
                             "invert_y": False}


def _finite(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def normalize_snapshot(payload: dict) -> dict:
    if not isinstance(payload, dict) or payload.get("type") != "players":
        raise ValueError("player tracker snapshot must have type=players")
    players = []
    for item in payload.get("players") or []:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or "").strip()[:128]
        name = str(item.get("name") or "").strip()[:96]
        x, y, z, yaw = (_finite(item.get(k)) for k in ("x", "y", "z", "yaw"))
        if not name:
            continue
        # RSDWTools can report a connected controller before its pawn exists.
        # Presence/identity is still valid in that state; only map positioning
        # requires X/Y coordinates.  Previously these players vanished from the
        # desktop and WebGUI until a pawn and location were both available.
        has_position = x is not None and y is not None
        position_2d = has_position and z is None
        row = {"id": pid or name.casefold(), "name": name, "yaw": yaw,
               "position_2d": bool(position_2d), "has_position": bool(has_position)}
        if has_position:
            row.update({"x": x, "y": y, "z": 0.0 if position_2d else z})
        # The tracker payload is intentionally forward-compatible.  Console support
        # is expected to expand the identifiers we may see, so retain only known,
        # bounded optional fields when the upstream bridge provides them.
        for source_key, target_key in (
            ("level", "level"), ("combat_level", "level"), ("total_level", "total_level"),
            ("steam_id", "steam_id"), ("steamid", "steam_id"),
            ("epic_id", "epic_id"), ("epicid", "epic_id"),
            ("xbox_id", "xbox_id"), ("xuid", "xbox_id"),
            ("playstation_id", "playstation_id"), ("psn_id", "playstation_id"),
            ("nintendo_id", "nintendo_id"), ("switch_id", "nintendo_id"),
            ("platform", "platform"),
            ("is_local", "is_local"), ("has_authority", "has_authority"),
            ("alive", "alive"), ("pawn_class", "pawn_class"), ("netmode", "netmode"),
        ):
            value = item.get(source_key)
            if value in (None, "") or target_key in row:
                continue
            if target_key in {"level", "total_level"}:
                try: row[target_key] = max(0, int(value))
                except (TypeError, ValueError): pass
            elif target_key in {"is_local", "has_authority", "alive"}:
                row[target_key] = bool(value)
            else:
                row[target_key] = str(value).strip()[:160]
        players.append(row)
    try: ts = int(payload.get("timestamp") or int(time.time() * 1000))
    except (TypeError, ValueError): ts = int(time.time() * 1000)
    return {"type": "players", "timestamp": ts, "players": players}


class ServerPlayerService:
    def __init__(self):
        self.lock = threading.RLock()
        self.records: dict[str, dict] = {}
        self.last_tracker_update = 0.0
        self.tracker_connected = False

    def update_log_players(self, names: list[str]) -> None:
        now = time.time(); current = {str(n).strip() for n in names if str(n).strip()}
        with self.lock:
            for key, rec in list(self.records.items()):
                if rec.get("log_available") and rec.get("name") not in current:
                    rec["log_available"] = False
                    if not rec.get("tracker_available"):
                        rec["connected"] = False; rec["disconnected_at"] = now
            for name in current:
                key = next((k for k, r in self.records.items() if str(r.get("name") or "").casefold() == name.casefold()
                            or name.casefold() in {str(alias).casefold() for alias in (r.get("aliases") or [])}), f"name:{name.casefold()}")
                rec = self.records.setdefault(key, {"id": key, "name": name, "connected": True, "connected_at": now})
                if not rec.get("connected"):
                    rec["connected_at"] = now
                rec["connected"] = True; rec["log_available"] = True; rec["last_log_seen"] = now
                # A coordinate-bearing tracker identity is the in-game character.
                # Keep the log/Steam identity as an alias instead of replacing it.
                if rec.get("tracker_available") and rec.get("has_position"):
                    aliases = {str(value) for value in (rec.get("aliases") or []) if str(value)}
                    aliases.add(name); rec["aliases"] = sorted(aliases, key=str.casefold)
                    rec["account_name"] = name
                else:
                    rec["name"] = name
                rec.pop("disconnected_at", None)
            # Bound stale disconnected records.
            cutoff = now - 86400
            self.records = {k: r for k, r in self.records.items() if r.get("connected") or float(r.get("disconnected_at") or now) >= cutoff}

    def ingest(self, payload: dict) -> dict:
        snap = normalize_snapshot(payload); now = time.time()
        with self.lock:
            self.last_tracker_update = now; self.tracker_connected = True
            seen = set()
            positioned = [item for item in snap["players"] if item.get("has_position")]
            unmatched_logs = [(key, rec) for key, rec in self.records.items()
                              if rec.get("log_available") and not rec.get("tracker_available")]
            for item in snap["players"]:
                key = next((k for k, r in self.records.items() if (item["id"] and str(r.get("tracker_id") or "") == item["id"])
                            or str(r.get("name") or "").casefold() == item["name"].casefold()
                            or item["name"].casefold() in {str(alias).casefold() for alias in (r.get("aliases") or [])}), "")
                # RSDW emits the character/pawn name while the game log commonly
                # emits the Steam account name. With a one-to-one live set, merge
                # those two observations into the coordinate-bearing character.
                if not key and item.get("has_position") and len(positioned) == len(unmatched_logs) == 1:
                    key, account = unmatched_logs[0]
                    aliases = {str(value) for value in (account.get("aliases") or []) if str(value)}
                    aliases.add(str(account.get("name") or ""))
                    account["aliases"] = sorted((value for value in aliases if value), key=str.casefold)
                    account["account_name"] = str(account.get("name") or "")
                if not key:
                    key = f"tracker:{item['id']}"
                rec = self.records.setdefault(key, {"id": item["id"], "name": item["name"], "connected": True, "connected_at": now})
                was_connected = bool(rec.get("connected"))
                update = {"tracker_id": item["id"], "name": item["name"], "has_position": bool(item.get("has_position")),
                            "yaw": item.get("yaw"), "tracker_available": True,
                            "position_2d": bool(item.get("position_2d")), "connected": True, "last_seen": now}
                if item.get("has_position"):
                    update["position"] = {"x": item.get("x"), "y": item.get("y"), "z": item.get("z")}
                    update["last_position_update"] = now
                rec.update(update)
                if not rec.get("first_seen"):
                    rec["first_seen"] = now
                if not was_connected:
                    rec["connected_at"] = now
                    rec["visit_count"] = int(rec.get("visit_count") or 0) + 1
                elif not rec.get("visit_count"):
                    rec["visit_count"] = 1
                for optional in ("level","total_level","steam_id","epic_id","xbox_id","playstation_id","nintendo_id","platform",
                                 "is_local","has_authority","alive","pawn_class","netmode"):
                    if item.get(optional) not in (None, ""):
                        rec[optional] = item.get(optional)
                seen.add(key)
            for key, rec in self.records.items():
                if key not in seen and now - float(rec.get("last_position_update") or 0) > 2.0:
                    rec["tracker_available"] = False
                    # A live tracker snapshot is authoritative for presence.  Keep
                    # the record for Recent/Common Players instead of deleting it.
                    if rec.get("connected") and not rec.get("log_available"):
                        rec["connected"] = False
                        rec["disconnected_at"] = now
                        rec["last_seen"] = max(float(rec.get("last_seen") or 0), now)
        return self.status()

    def mark_timeout(self):
        now = time.time()
        with self.lock:
            if self.last_tracker_update and now - self.last_tracker_update > 12.0:
                self.tracker_connected = False
                for rec in self.records.values(): rec["tracker_available"] = False

    def status(self) -> dict:
        self.mark_timeout(); now = time.time()
        with self.lock:
            players=[]; recent=[]
            for rec in self.records.values():
                item=dict(rec)
                if rec.get("connected"):
                    item["connected_seconds"] = max(0, int(now - float(rec.get("connected_at") or now)))
                    players.append(item)
                else:
                    item["last_seen"] = float(item.get("last_seen") or item.get("disconnected_at") or 0) or None
                    recent.append(item)
            players.sort(key=lambda x: str(x.get("name") or "").casefold())
            recent.sort(key=lambda x: (float(x.get("last_seen") or 0), int(x.get("visit_count") or 0)), reverse=True)
            return {"tracker_connected": self.tracker_connected, "last_tracker_update": self.last_tracker_update or None,
                    "players": players, "player_count": len(players), "recent_players": recent[:250]}


class RSDWSharedLineClient:
    """Exact client for RSDWTools' public ``BridgeLine`` shared-memory ABI.

    RSDWTools owns the mapping and synchronization objects.  Dragonwilds Sync
    only opens them and exchanges bounded UTF-8 command/acknowledgement lines.
    This keeps the upstream UE4SS module replaceable without coupling the
    launcher release to a particular DLL build.
    """

    MAPPING = r"Local\RSDWTools_SharedLine_v1"
    MUTEX = r"Local\RSDWTools_SharedLine_v1_Mutex"
    REQUEST_EVENT = r"Local\RSDWTools_SharedLine_v1_EvtReq"
    ACK_EVENT = r"Local\RSDWTools_SharedLine_v1_EvtAck"
    SIZE = 0x830
    REQUEST_SEQ, REQUEST_LEN, REQUEST_BUFFER = 0x10, 0x18, 0x20
    ACK_SEQ, ACK_LEN, ACK_BUFFER = 0x420, 0x428, 0x430
    BUFFER_SIZE = 0x400

    FILE_MAP_ALL_ACCESS = 0xF001F
    SYNCHRONIZE = 0x00100000
    MUTEX_MODIFY_STATE = 0x0001
    EVENT_MODIFY_STATE = 0x0002
    WAIT_OBJECT_0 = 0

    def __init__(self):
        self.lock = threading.RLock()
        self.last_error = ""
        self.last_ack = ""
        self.last_success = 0.0

    @staticmethod
    def _kernel32():
        if os.name != "nt":
            raise OSError("RSDWTools shared memory is available on Windows only")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.OpenFileMappingW.restype = wintypes.HANDLE
        kernel32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
        kernel32.MapViewOfFile.restype = ctypes.c_void_p
        kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        kernel32.UnmapViewOfFile.restype = wintypes.BOOL
        kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.OpenMutexW.restype = wintypes.HANDLE
        kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.OpenEventW.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
        kernel32.ReleaseMutex.restype = wintypes.BOOL
        kernel32.SetEvent.argtypes = [wintypes.HANDLE]
        kernel32.SetEvent.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        return kernel32

    @contextmanager
    def _objects(self):
        k32 = self._kernel32()
        mapping = k32.OpenFileMappingW(self.FILE_MAP_ALL_ACCESS, False, self.MAPPING)
        if not mapping:
            raise FileNotFoundError("RSDWTools bridge is not running")
        view = mutex = request_event = ack_event = None
        try:
            view = k32.MapViewOfFile(mapping, self.FILE_MAP_ALL_ACCESS, 0, 0, self.SIZE)
            mutex = k32.OpenMutexW(self.SYNCHRONIZE | self.MUTEX_MODIFY_STATE, False, self.MUTEX)
            request_event = k32.OpenEventW(self.SYNCHRONIZE | self.EVENT_MODIFY_STATE, False, self.REQUEST_EVENT)
            ack_event = k32.OpenEventW(self.SYNCHRONIZE, False, self.ACK_EVENT)
            if not view or not mutex or not request_event or not ack_event:
                raise FileNotFoundError("RSDWTools bridge synchronization objects are unavailable")
            yield k32, int(view), mutex, request_event, ack_event
        finally:
            if view: k32.UnmapViewOfFile(view)
            for handle in (ack_event, request_event, mutex, mapping):
                if handle: k32.CloseHandle(handle)

    @contextmanager
    def _acquire(self, k32, mutex, timeout_ms: int):
        if k32.WaitForSingleObject(mutex, max(1, int(timeout_ms))) != self.WAIT_OBJECT_0:
            raise TimeoutError("Timed out waiting for the RSDWTools bridge mutex")
        try:
            yield
        finally:
            k32.ReleaseMutex(mutex)

    @staticmethod
    def _u64(address: int) -> int:
        return int(ctypes.c_uint64.from_address(address).value)

    @staticmethod
    def _u32(address: int) -> int:
        return int(ctypes.c_uint32.from_address(address).value)

    def available(self) -> bool:
        try:
            with self._objects():
                return True
        except (OSError, FileNotFoundError):
            return False

    def status(self) -> dict:
        return {"available": self.available(), "protocol": "RSDWTools_SharedLine_v1",
                "last_success": self.last_success or None, "last_error": self.last_error,
                "last_ack": self.last_ack[:240]}

    def command(self, line: str, timeout: float = 2.5) -> str:
        raw = str(line or "").strip().encode("utf-8")
        if not raw:
            raise ValueError("RSDWTools command is empty")
        if len(raw) >= self.BUFFER_SIZE:
            raise ValueError("RSDWTools command exceeds the 1023-byte bridge limit")
        timeout_ms = max(100, min(int(float(timeout) * 1000), 30000))
        started = time.monotonic()
        with self.lock:
            try:
                with self._objects() as (k32, view, mutex, request_event, ack_event):
                    with self._acquire(k32, mutex, timeout_ms):
                        prior_ack = self._u64(view + self.ACK_SEQ)
                        request_seq = (self._u64(view + self.REQUEST_SEQ) + 1) & 0xFFFFFFFFFFFFFFFF
                        ctypes.memset(view + self.REQUEST_BUFFER, 0, self.BUFFER_SIZE)
                        ctypes.memmove(view + self.REQUEST_BUFFER, raw, len(raw))
                        ctypes.c_uint32.from_address(view + self.REQUEST_LEN).value = len(raw)
                        # Sequence is written last so the native poller never sees a
                        # new request with a partially copied command buffer.
                        ctypes.c_uint64.from_address(view + self.REQUEST_SEQ).value = request_seq
                    if not k32.SetEvent(request_event):
                        raise OSError("Could not signal the RSDWTools request event")
                    while True:
                        remaining = timeout_ms - int((time.monotonic() - started) * 1000)
                        if remaining <= 0:
                            raise TimeoutError("RSDWTools did not acknowledge the command")
                        k32.WaitForSingleObject(ack_event, max(1, remaining))
                        with self._acquire(k32, mutex, min(remaining, 1000)):
                            ack_seq = self._u64(view + self.ACK_SEQ)
                            if ack_seq == prior_ack:
                                continue
                            length = min(self._u32(view + self.ACK_LEN), self.BUFFER_SIZE - 1)
                            ack = ctypes.string_at(view + self.ACK_BUFFER, length).decode("utf-8", "replace").strip()
                        self.last_error = ""
                        self.last_ack = ack
                        self.last_success = time.time()
                        return ack
            except Exception as exc:
                self.last_error = str(exc)
                raise


class PlayerTrackerBridge:
    """Poll the replaceable RSDWTools module and normalize its live roster."""

    def __init__(self, service: ServerPlayerService, client: RSDWSharedLineClient | None = None):
        self.service = service
        self.client = client or RSDWSharedLineClient()
        self.thread = None
        self.stop_event = threading.Event()
        self.active_until = 0.0
        # Roster is presence telemetry, not animation telemetry. RSDWTools logs
        # each shared-line command it receives, so a five-second loop flooded
        # UE4SS.log while adding no useful fidelity to the launcher. Keep one
        # demand-driven poller and retain a short cache between UI refreshes.
        self.poll_interval = 15.0
        self._last_roster_poll = 0.0
        self._minimum_roster_age = 12.0

    def demand(self, ttl: float = 20.0):
        """Keep the installed RSDWTools bridge active only while a view needs it."""
        self.active_until = max(self.active_until, time.time() + max(5.0, float(ttl or 20.0)))
        self.start()

    def start(self):
        if self.active_until <= time.time():
            self.active_until = time.time() + 20.0
        if self.thread and self.thread.is_alive(): return
        self.stop_event.clear(); self.thread=threading.Thread(target=self._loop, name="PlayerTrackerBridge", daemon=True); self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive(): self.thread.join(timeout=1.0)
        self.thread=None

    def command(self, line: str, timeout: float = 2.5) -> str:
        return self.client.command(line, timeout)

    def status(self) -> dict:
        return self.client.status()

    @staticmethod
    def _roster_snapshot(text: str) -> dict:
        payload = json.loads(str(text or "").strip())
        if isinstance(payload, dict) and payload.get("type") == "players":
            return payload
        if not isinstance(payload, list):
            raise ValueError("RSDWTools world.net.roster did not return a JSON array")
        players = []
        for index, row in enumerate(payload):
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            players.append({
                "id": str(row.get("id") or row.get("steam_id") or name.casefold()),
                "name": name, "x": row.get("x"), "y": row.get("y"), "z": row.get("z"),
                "yaw": row.get("yaw"), "is_local": bool(row.get("is_local")),
                "has_authority": bool(row.get("has_authority")), "alive": row.get("alive"),
                "pawn_class": str(row.get("pawn_class") or "")[:240], "netmode": str(row.get("netmode") or "")[:80],
            })
        return {"type": "players", "timestamp": int(time.time() * 1000), "players": players}

    def _loop(self):
        while not self.stop_event.is_set() and time.time() <= self.active_until:
            try:
                now = time.monotonic()
                if now - self._last_roster_poll >= self._minimum_roster_age:
                    text = self.command("world.net.roster", timeout=1.8)
                    self.service.ingest(self._roster_snapshot(text))
                    self._last_roster_poll = now
            except (FileNotFoundError, json.JSONDecodeError, ValueError, TimeoutError, OSError):
                self.service.mark_timeout()
            except Exception:
                self.service.mark_timeout()
            if self.stop_event.wait(self.poll_interval):
                break


def world_to_map(x: float, y: float, calibration: dict | None) -> dict | None:
    c={**DEFAULT_WORLD_CALIBRATION, **(calibration if isinstance(calibration,dict) else {})}
    try:
        xmin=float(c["world_min_x"]); xmax=float(c["world_max_x"]); ymin=float(c["world_min_y"]); ymax=float(c["world_max_y"])
    except (KeyError,TypeError,ValueError): return None
    if xmax==xmin or ymax==ymin: return None
    px=(float(x)-xmin)/(xmax-xmin); py=(float(y)-ymin)/(ymax-ymin)
    if c.get("invert_y", True): py=1-py
    return {"x": max(0.0,min(1.0,px)), "y": max(0.0,min(1.0,py))}


PLAYER_SERVICE = ServerPlayerService()
PLAYER_BRIDGE = PlayerTrackerBridge(PLAYER_SERVICE)
