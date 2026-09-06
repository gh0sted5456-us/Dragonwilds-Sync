"""Approval-only runtime notices using the application's dismissible inbox."""
import time


def record_notice(state, component, version, world_id=""):
    application = state.setdefault("application", {})
    key = f"update:{'core_mod' if component == 'UE4SS' else 'runeschema'}:{version}"
    now = time.time()
    if float((application.get("dismissed_notifications") or {}).get(key) or 0) > now:
        return False
    notices = application.setdefault("notifications", [])
    if any(row.get("key") == key for row in notices):
        return False
    notices.append({"id": key, "key": key, "title": f"{component} update available",
                    "body": f"{version}. Review and install in Settings. No loader was downloaded or changed.",
                    "kind": "info", "world_id": world_id, "created_at": now, "last_seen_at": now,
                    "repeat_count": 1, "read": False, "details": {"approval_required": True}})
    return True
