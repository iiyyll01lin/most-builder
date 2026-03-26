"""AI-powered SOP Conflict Resolution Copilot.

The review pipeline:
1.  Receive the ordered action sequence (flat list, station-by-station).
2.  Build a specialised system prompt that gives the LLM a Physical World State
    Model (PWSM) framework: each step must be evaluated against the cumulative
    physical state established by all prior steps.
3.  Call the LLM (or the deterministic mock when no API key is configured).
4.  Parse the JSON Conflict[] array and return a validated SopReviewResponse.

Sequence ordering strategy
--------------------------
Actions are ordered by their natural list position inside the SOP version.  The
caller (the API route) is responsible for sorting them by
``(station_index, action_index_within_sop)`` when a line-balance assignment is
available, or simply by their SOP list order for unbalanced drafts.

Physical World State Model (PWSM) used in the prompt
------------------------------------------------------
Rather than asking the LLM to "look for bugs", the prompt frames the task as a
stateful simulation audit:

    At each step i the LLM must answer:
      "What physical state does this action require the world to be in?
       Has that state been established by steps 1 … i-1?"

Examples encoded in the prompt:
  • A "Fasten Screw" step requires the mating component to already be placed.
  • A "Close Chassis" step makes all subsequent internal-component steps invalid.
  • A "Test Power" step requires the power source (battery / PSU) to be installed.
  • A "Scan Label" step requires the label to have already been applied.
  • A "Torque" step requires the part to be seated (placed) first.

Dependency-inversion detection is handled by asking the LLM to trace the
sequence top-to-bottom and flag any step whose prerequisite state has not yet
been established.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any

from ddm_v2.ai_schemas import Conflict, SopReviewResponse

# ─── PWSM prompt template ─────────────────────────────────────────────────────

_REVIEW_SYSTEM_PROMPT_TEMPLATE = """\
You are a Senior Manufacturing Process Auditor specialising in server-assembly \
factories and MOST (Maynard Operation Sequence Technique) work measurement.

## Your Mission
You will receive a numbered, ordered list of SOP (Standard Operating Procedure) \
actions for a manufacturing line.  Your task is to audit the sequence for \
manufacturing logic defects using a Physical World State Model (PWSM) approach.

## Physical World State Model (PWSM) Framework
Simulate the physical world state step-by-step.  Before accepting each step as \
valid, ask:
  1. PREREQUISITE STATE: What physical condition must exist for this action to be
     physically possible?
  2. STATE CHECK: Has that condition been established by any prior step in the
     sequence?
  3. CONFLICT: If not, this is a conflict.

## Known Manufacturing State Dependencies (Server-Assembly Domain)
Apply these rules strictly:

PLACEMENT BEFORE FASTENING
  • Any "Fasten", "Torque", "Tighten", or "Screw" action on component X requires
    a prior "Place" or "Install" action for the same component X.

INTERNAL ACCESS WINDOW
  • Any action that installs, seats, or connects a component INSIDE the chassis
    (RAM, CPU, SSD, cable, PCIe card, etc.) is only valid while the chassis is
    OPEN.  If a "Close Chassis", "Install Cover", or "Place Lid" step has already
    occurred, all subsequent internal-installation steps are physically impossible.

POWER / ELECTRICAL PREREQUISITE
  • "Test Power", "Power On", "BIOS Check", "Functional Test" actions require
    that the power source (battery, PSU, power cable) has already been installed.
  • "Connect Power Cable" requires a PSU to already be mounted.

LABEL / SCAN ORDERING
  • "Scan" or "Verify" actions on a label require that the "Apply Label" or
    "Attach Label" step has already occurred for the same component.

CABLE ROUTING
  • "Secure Cable" or "Route Cable" requires "Connect Cable" to have occurred first.

THERMAL MANAGEMENT
  • "Mount Heatsink" or "Apply Thermal Paste" must occur BEFORE "Install CPU Cover"
    or closing the system.
  • If "Mount Heatsink" appears AFTER any cover-closing step, it is a conflict.

CTQ (Critical to Quality) INSPECTION SEQUENCING
  • CTQ inspection steps should occur AFTER installation of the inspected component,
    not before.

## Sequence to Audit
{sequence_block}

## Required Output Format
Return ONLY a valid JSON array — no markdown, no explanation, no code fences.
Each element must be a JSON object with these exact fields:

  "severity"           : "High" | "Medium" | "Low"
  "description"        : string — precise explanation of what is wrong
  "related_action_ids" : array of string — IDs of the conflicting actions
                         (use the "id" field from the sequence; empty list if
                          the action has no id)
  "suggestion"         : string — concrete fix: which steps to reorder or add

Severity guide:
  High   — physically impossible (would cause assembly failure or damage)
  Medium — likely incorrect (would cause quality defect or rework)
  Low    — advisory (best-practice deviation, no immediate failure risk)

If you detect zero conflicts, return an empty array: []
"""


def build_review_system_prompt(ordered_actions: list[dict[str, Any]]) -> tuple[str, str]:
    """Return (system_prompt, user_message) for the SOP review task.

    The system prompt embeds the PWSM framework.
    The user message contains the numbered action sequence.
    """
    lines: list[str] = []
    for idx, action in enumerate(ordered_actions, start=1):
        action_id = action.get("id", "")
        description = action.get("description", "(no description)")
        component = action.get("component") or ""
        tool = action.get("tool") or ""
        station_id = action.get("station_id") or ""
        is_ctq = action.get("is_ctq", False)

        parts = [f"Step {idx:>3d}  [{action_id}]  {description}"]
        if component:
            parts.append(f"component={component!r}")
        if tool:
            parts.append(f"tool={tool!r}")
        if station_id:
            parts.append(f"station={station_id!r}")
        if is_ctq:
            parts.append("CTQ=true")
        lines.append("  " + "  ".join(parts))

    sequence_block = "\n".join(lines) or "  (empty sequence — nothing to audit)"

    system_prompt = _REVIEW_SYSTEM_PROMPT_TEMPLATE.format(
        sequence_block=sequence_block
    )
    user_message = (
        f"Please audit the {len(ordered_actions)}-step SOP sequence above "
        "and return a JSON array of Conflict objects as specified."
    )
    return system_prompt, user_message


# ─── Mock LLM reviewer (deterministic, for testing & offline mode) ────────────

def _mock_llm_review(ordered_actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a realistic hardcoded conflict list derived from the action sequence.

    Scans the ordered sequence for the most common server-assembly conflict
    patterns (fastening before placement, internal access after close, power
    testing before PSU install) and emits deterministic Conflict dicts.

    This generator is used:
      • When OPENAI_API_KEY is not set (offline / CI mode).
      • Directly in unit tests to verify parsing logic.
    """
    conflicts: list[dict[str, Any]] = []

    # Index actions by their description tokens for pattern matching
    placed: set[str] = set()       # components that have been placed/installed
    chassis_closed = False
    power_source_installed = False
    label_applied: set[str] = set()

    # Keywords that indicate chassis closure
    _CLOSE_CHASSIS_KEYWORDS = {
        "close chassis", "install cover", "place lid", "close cover",
        "attach cover", "mount cover", "close panel", "install top cover",
    }
    # Keywords that indicate internal component work
    _INTERNAL_KEYWORDS = {
        "install", "seat", "insert", "connect", "mount",
        "place dimm", "place ram", "place ssd", "place cpu",
    }
    _POWER_SOURCE_KEYWORDS = {"battery", "psu", "power supply", "power cable"}
    _POWER_TEST_KEYWORDS = {"test power", "power on", "bios check", "functional test", "power test"}
    _LABEL_APPLY_KEYWORDS = {"apply label", "attach label", "place label", "stick label"}
    _LABEL_SCAN_KEYWORDS = {"scan label", "verify label", "scan barcode", "read label"}
    _FASTEN_KEYWORDS = {"fasten", "torque", "tighten", "screw"}
    _THERMAL_PASTE_KEYWORDS = {"thermal paste", "heatsink", "mount heatsink"}
    # Fasteners don't need to be "placed" themselves — they secure other components.
    # A fasten step on a fastener is only a conflict if nothing has been placed yet
    # (nothing to fasten to), whereas a fasten step on a non-fastener component
    # (e.g., torquing a heatsink retention bracket) requires that component to be placed.
    _FASTENER_NAMES = {"screw", "bolt", "nut", "rivet", "clip", "pin", "standoff", "stud"}

    for idx, action in enumerate(ordered_actions):
        desc_lower = (action.get("description") or "").lower()
        component = (action.get("component") or "").lower()
        action_id = action.get("id", "")
        ids = [action_id] if action_id else []

        # ── Track state ────────────────────────────────────────────────────────
        # Track placement
        if any(kw in desc_lower for kw in ("place ", "install ", "seat ", "mount ")):
            if component:
                placed.add(component)

        # Track chassis closure
        if any(kw in desc_lower for kw in _CLOSE_CHASSIS_KEYWORDS):
            chassis_closed = True

        # Track power source installation
        if any(kw in desc_lower for kw in _POWER_SOURCE_KEYWORDS) and any(
            kw in desc_lower for kw in ("install", "mount", "connect", "place")
        ):
            power_source_installed = True

        # Track label application
        if any(kw in desc_lower for kw in _LABEL_APPLY_KEYWORDS):
            if component:
                label_applied.add(component)

        # ── Detect conflicts ───────────────────────────────────────────────────

        # 1. Fasten before place
        if any(kw in desc_lower for kw in _FASTEN_KEYWORDS):
            if component:
                is_fastener = any(fn in component.lower() for fn in _FASTENER_NAMES)
                if is_fastener:
                    # Screw/bolt: allowed once at least one non-fastener part has been placed
                    # (something to fasten to).  If nothing at all is placed yet, flag it.
                    if not placed:
                        future_ids = [
                            a.get("id", "")
                            for a in ordered_actions[idx + 1:]
                            if any(kw in (a.get("description") or "").lower()
                                   for kw in ("place", "install", "seat"))
                        ]
                        related = [*ids, *[fid for fid in future_ids[:1] if fid]]
                        conflicts.append({
                            "severity": "High",
                            "description": (
                                f"Step {idx + 1} fastens '{component}' but no component "
                                "has been placed or installed yet — there is nothing to "
                                "fasten to. Place the mating component first."
                            ),
                            "related_action_ids": related,
                            "suggestion": (
                                f"Add a 'Place / Install <component>' step before "
                                f"Step {idx + 1} ('{action.get('description')}')."
                            ),
                        })
                elif component not in placed:
                    # Non-fastener component being torqued/fastened without prior placement
                    future_ids = [
                        a.get("id", "")
                        for a in ordered_actions[idx + 1:]
                        if component in (a.get("component") or "").lower()
                        and any(kw in (a.get("description") or "").lower()
                                for kw in ("place", "install", "seat"))
                    ]
                    related = [*ids, *[fid for fid in future_ids[:1] if fid]]
                    conflicts.append({
                        "severity": "High",
                        "description": (
                            f"Step {idx + 1} fastens '{component}' before it has been placed. "
                            "Fastening requires the component to already be seated in its socket."
                        ),
                        "related_action_ids": related,
                        "suggestion": (
                            f"Move the 'Place / Install {component}' step to before "
                            f"Step {idx + 1} ('{action.get('description')}')."
                        ),
                    })

        # 2. Internal component work after chassis is closed
        if chassis_closed and any(kw in desc_lower for kw in _INTERNAL_KEYWORDS):
            if component in (
                "ram", "dimm", "ssd", "cpu", "cable", "pcie", "gpu", "m.2", "nvme"
            ):
                conflicts.append({
                    "severity": "High",
                    "description": (
                        f"Step {idx + 1} attempts to install internal component "
                        f"'{component}' after the chassis has already been closed. "
                        "This is physically impossible."
                    ),
                    "related_action_ids": ids,
                    "suggestion": (
                        f"Move Step {idx + 1} ('{action.get('description')}') "
                        "to before the 'Close / Install Cover' step."
                    ),
                })

        # 3. Power test before power source installed
        if any(kw in desc_lower for kw in _POWER_TEST_KEYWORDS) and not power_source_installed:
            conflicts.append({
                "severity": "High",
                "description": (
                    f"Step {idx + 1} attempts '{action.get('description')}' "
                    "before a power source (PSU / battery / power cable) has been installed. "
                    "Powering on without a PSU will damage the board."
                ),
                "related_action_ids": ids,
                "suggestion": (
                    "Ensure 'Install PSU' or 'Connect Power Cable' appears before "
                    f"Step {idx + 1}."
                ),
            })

        # 4. Scan label before label applied
        if any(kw in desc_lower for kw in _LABEL_SCAN_KEYWORDS):
            if component and component not in label_applied:
                conflicts.append({
                    "severity": "Medium",
                    "description": (
                        f"Step {idx + 1} scans a label on '{component}' but no prior "
                        "'Apply Label' step was found. Scanning a non-existent label "
                        "will fail at the scan station."
                    ),
                    "related_action_ids": ids,
                    "suggestion": (
                        f"Add an 'Apply Label' step for '{component}' before Step {idx + 1}."
                    ),
                })

        # 5. Thermal paste / heatsink after cover
        if chassis_closed and any(kw in desc_lower for kw in _THERMAL_PASTE_KEYWORDS):
            conflicts.append({
                "severity": "Medium",
                "description": (
                    f"Step {idx + 1} performs thermal management ('{action.get('description')}') "
                    "after the chassis cover has already been installed. "
                    "Heatsink cannot be accessed once the cover is on."
                ),
                "related_action_ids": ids,
                "suggestion": (
                    f"Move Step {idx + 1} to before the 'Close Cover' step."
                ),
            })

    # If we found no real conflicts, emit a single realistic example conflict
    # so that the mock always demonstrates the data contract.
    if not conflicts:
        first_id = ordered_actions[0].get("id", "") if ordered_actions else ""
        last_id = ordered_actions[-1].get("id", "") if ordered_actions else ""
        conflicts.append({
            "severity": "Low",
            "description": (
                "Advisory: No hard dependency inversions detected in this sequence. "
                "Verify that all CTQ inspection steps occur after the inspected components "
                "are fully installed and torqued to spec."
            ),
            "related_action_ids": [x for x in [first_id, last_id] if x],
            "suggestion": (
                "Cross-check that every CTQ-flagged action (is_ctq=true) has a "
                "corresponding 'Inspect' step immediately after it."
            ),
        })

    return conflicts


# ─── Optional OpenAI call ──────────────────────────────────────────────────────

def _validated_https_url(url: str) -> str:
    """Reject non-HTTPS URLs to prevent SSRF from a misconfigured env var."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(
            f"OPENAI_BASE_URL must use https://; got scheme={parsed.scheme!r}. "
            "Set DDM_OPENAI_BASE_URL to a valid https endpoint."
        )
    return url


def _call_openai_review(
    ordered_actions: list[dict[str, Any]],
    api_key: str,
    base_url: str,
    model: str,
) -> list[dict[str, Any]]:
    """Call an OpenAI-compatible endpoint and return a parsed Conflict list."""
    endpoint = _validated_https_url(base_url.rstrip("/")) + "/chat/completions"
    system_prompt, user_message = build_review_system_prompt(ordered_actions)

    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.1,
            "max_tokens": 3000,
        }
    ).encode("utf-8")

    req = urllib.request.Request(  # noqa: S310
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        response_body = json.loads(resp.read().decode("utf-8"))

    raw_content: str = response_body["choices"][0]["message"]["content"].strip()

    # Strip any accidental markdown fences the model may have added
    raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content)
    raw_content = re.sub(r"\s*```$", "", raw_content)

    return json.loads(raw_content)


# ─── Public entry point ───────────────────────────────────────────────────────

def review_sop_sequence(ordered_actions: list[dict[str, Any]]) -> SopReviewResponse:
    """Audit an ordered SOP action sequence and return structured conflict findings.

    Falls back to the deterministic mock generator when OPENAI_API_KEY is unset,
    exactly mirroring the pattern in ``ai_service.generate_sop_actions``.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get(
        "DDM_OPENAI_BASE_URL", "https://api.openai.com/v1"
    ).strip()
    model = os.environ.get("DDM_OPENAI_MODEL", "gpt-4o-mini").strip()

    if api_key:
        raw_conflicts = _call_openai_review(
            ordered_actions, api_key, base_url, model
        )
    else:
        raw_conflicts = _mock_llm_review(ordered_actions)

    # Validate and coerce each conflict into the Pydantic schema
    validated: list[Conflict] = []
    for item in raw_conflicts:
        if not isinstance(item, dict):
            continue
        try:
            validated.append(Conflict.model_validate(item))
        except Exception:  # noqa: BLE001 — skip malformed items gracefully
            continue

    n = len(ordered_actions)
    if validated:
        high = sum(1 for c in validated if c.severity == "High")
        med = sum(1 for c in validated if c.severity == "Medium")
        low = sum(1 for c in validated if c.severity == "Low")
        parts: list[str] = []
        if high:
            parts.append(f"{high} High")
        if med:
            parts.append(f"{med} Medium")
        if low:
            parts.append(f"{low} Low")
        summary = f"{len(validated)} conflict(s) detected ({', '.join(parts)}) across {n} actions."
    else:
        summary = f"No conflicts detected across {n} actions. Sequence looks valid."

    return SopReviewResponse(
        conflicts=validated,
        reviewed_action_count=n,
        summary=summary,
    )
