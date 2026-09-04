from __future__ import annotations

"""World-declared loader/runtime architecture requirements.

RuneSchema currently depends on UE4SS. It may eventually replace UE4SS
functionality outright, at which point running RuneSchema standalone
*alongside* a legacy UE4SS install could crash a World rather than merely
being redundant. Today's architecture must not hard-code "RuneSchema always
requires UE4SS forever" — a World needs to be able to declare which loader
components it requires, forbids, or treats as optional, independently of
today's UE4SS+RuneSchema default, so a client can reconcile its local
runtime against what the World actually needs.

This module is intentionally narrow: it is the declaration model plus a
read-only reconciliation report. It does not install, remove, or migrate
anything on its own — that stays a deliberate, separately-reviewed follow-up
once a real standalone-RuneSchema build exists (see the module docstring in
managed_runtime_mods.py for the equivalent pattern already used for the
retired DragonLink native runtime).
"""

COMPONENTS = ("ue4ss", "runeschema")

# "required"   — the World expects this loader to be present.
# "optional"   — the World tolerates either presence or absence.
# "forbidden"  — the World must not run with this loader present (e.g. a
#                future standalone RuneSchema build that cannot coexist with
#                UE4SS).
# "standalone" — meaningful for runeschema only: RuneSchema runs without a
#                UE4SS host at all. Reconciliation treats it like "required"
#                for runeschema and implies UE4SS is not needed for that
#                requirement (a World can still separately mark UE4SS
#                "optional"/"forbidden"/"required" for its own gameplay mods).
POLICIES = frozenset({"required", "optional", "forbidden", "standalone"})

# Matches the only configuration every current build actually supports.
# Existing Worlds that never declared an architecture reconcile exactly as
# they always have: both components required.
DEFAULT_ARCHITECTURE = {"ue4ss": "required", "runeschema": "required"}


def normalize_runtime_architecture(value: object) -> dict[str, str]:
    """Coerce an incoming declaration to a complete, valid architecture dict.

    Unknown components are dropped; missing or invalid policies fall back to
    the default (safe) policy for that component rather than raising, since
    this is read on every manifest build and must never be able to break an
    otherwise-valid World.
    """
    incoming = value if isinstance(value, dict) else {}
    result: dict[str, str] = {}
    for component in COMPONENTS:
        policy = str(incoming.get(component) or "").strip().casefold()
        if component == "ue4ss" and policy == "standalone":
            # "standalone" only has meaning for runeschema (running without a
            # UE4SS host). Treat a mistaken ue4ss:"standalone" declaration as
            # the safe default rather than silently accepting a policy word
            # that has no defined behavior for this component.
            policy = ""
        result[component] = policy if policy in POLICIES else DEFAULT_ARCHITECTURE[component]
    return result


def is_default(architecture: dict[str, str]) -> bool:
    return normalize_runtime_architecture(architecture) == DEFAULT_ARCHITECTURE


def reconcile_local_runtime(advertised: object, *, ue4ss_present: bool, runeschema_present: bool) -> dict:
    """Read-only comparison of a World's declared architecture against what
    is actually installed locally. Returns a report a client can act on
    later; this function itself never touches disk.
    """
    architecture = normalize_runtime_architecture(advertised)
    runeschema_policy = architecture["runeschema"]
    # A standalone RuneSchema requirement does not, by itself, forbid UE4SS
    # being present for other reasons (ordinary gameplay mods); it only means
    # UE4SS is not required for RuneSchema's own sake. Only an explicit
    # "forbidden" on ue4ss is ever surfaced as a removal recommendation.
    ue4ss_policy = architecture["ue4ss"]

    def _component_report(component: str, policy: str, present: bool) -> dict:
        if policy == "required" or (component == "runeschema" and policy == "standalone"):
            action = "none" if present else "install_recommended"
        elif policy == "forbidden":
            action = "removal_recommended" if present else "none"
        else:  # optional
            action = "none"
        return {"component": component, "policy": policy, "locally_present": bool(present), "action": action}

    components = [
        _component_report("ue4ss", ue4ss_policy, ue4ss_present),
        _component_report("runeschema", runeschema_policy, runeschema_present),
    ]
    return {
        "architecture": architecture,
        "is_default": architecture == DEFAULT_ARCHITECTURE,
        "components": components,
        "action_needed": any(row["action"] != "none" for row in components),
    }
