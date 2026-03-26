from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any

# ─── MOST TMU constants ────────────────────────────────────────────────────────
# 1 TMU = 0.036 seconds (matches settings.py DDM_TMU_FACTOR default)
_TMU_FACTOR = 0.036

# MOST action → (typical_tmu_per_unit, seq_type)
_ACTION_TMU: dict[str, tuple[int, str]] = {
    "Grab": (40, "GENERAL"),
    "Place": (50, "GENERAL"),
    "Fasten": (18, "CONTROLLED"),
    "Inspect": (24, "GENERAL"),
    "Scan": (10, "GENERAL"),
}

# Instruction verb → list of MOST motion verbs to emit
_VERB_MAP: dict[str, list[str]] = {
    "assemble": ["Grab", "Place", "Fasten"],
    "install": ["Grab", "Place"],
    "mount": ["Grab", "Place"],
    "seat": ["Grab", "Place"],
    "connect": ["Grab", "Place"],
    "insert": ["Grab", "Place"],
    "fasten": ["Fasten"],
    "tighten": ["Fasten"],
    "screw": ["Fasten"],
    "torque": ["Fasten"],
    "inspect": ["Inspect"],
    "verify": ["Inspect"],
    "check": ["Inspect"],
    "scan": ["Scan"],
    "barcode": ["Scan"],
    "pick": ["Grab"],
    "grab": ["Grab"],
    "place": ["Place"],
    "remove": ["Grab"],
}

# Component / action keyword → preferred tool name
_TOOL_KEYWORD_MAP: dict[str, str] = {
    "screw": "Torque Driver",
    "fasten": "Torque Driver",
    "tighten": "Torque Driver",
    "torque": "Torque Driver",
    "scan": "Barcode Scanner",
    "barcode": "Barcode Scanner",
    "label": "Barcode Scanner",
}


# ─── Prompt builder ───────────────────────────────────────────────────────────

def build_system_prompt(
    object_library: list[dict[str, Any]],
    tool_library: list[dict[str, Any]],
    precaution_rules: list[dict[str, Any]],
) -> str:
    """Construct the LLM system prompt by injecting master data as structured context.

    Injection strategy:
    - Object library: serialized as a compact JSON array with the fields the LLM
      needs to populate SOPAction (name, category, glove_type, is_ctq, required_skill).
    - Tool library: compact JSON array with name + spec.
    - Precaution rule triggers: inlined as a summary string so the LLM knows which
      component/tool keywords carry mandatory safety text (the backend will enforce
      them anyway, but this improves LLM recall).
    - SOPAction output schema: explicit field-by-field spec with types and constraints.
    - MOST TMU reference: typical TMU values for each action type so the LLM
      produces numerically correct outputs.
    """
    objects_json = json.dumps(
        [
            {
                "name": o.get("name", ""),
                "category": o.get("category", ""),
                "glove_type": o.get("glove_type", "General Glove"),
                "is_ctq": bool(o.get("ctq", False)),
                "required_skill": o.get("required_skill"),
            }
            for o in object_library
        ],
        ensure_ascii=False,
        indent=2,
    )
    tools_json = json.dumps(
        [{"name": t.get("name", ""), "spec": t.get("spec", "")} for t in tool_library],
        ensure_ascii=False,
        indent=2,
    )
    precaution_summary = "; ".join(
        f"{r.get('trigger_type')}={r.get('trigger_value')!r} → {r.get('text', '')!r}"
        for r in precaution_rules
    ) or "(none)"

    return f"""You are an expert Industrial Engineering (IE) assistant specializing in MOST \
(Maynard Operation Sequence Technique) work measurement for server-assembly factories.

## Your Task
Convert a natural language manufacturing operation description into a JSON array of SOPAction objects.
Each object represents one atomic MOST motion step.

## Domain Master Data

### Object Library — use EXACT names from this list
{objects_json}

### Tool Library — use EXACT names from this list
{tools_json}

### Auto-Binding Precaution Rule Triggers (backend enforces these; include relevant ones)
{precaution_summary}

## MOST TMU Reference
- 1 TMU = 0.036 seconds
- Grab   (GENERAL):    ~40 TMU  →  1.44 s
- Place  (GENERAL):    ~50 TMU  →  1.80 s
- Fasten (CONTROLLED): ~18 TMU  →  0.65 s  (per fastener; multiply by frequency)
- Inspect(GENERAL):    ~24 TMU  →  0.86 s
- Scan   (GENERAL):    ~10 TMU  →  0.36 s

## Required Output Schema
Return ONLY a valid JSON array — no markdown, no explanation, no code fences.
Each element must be a JSON object with ALL of the following fields:

  "seq_type"       : "GENERAL" | "CONTROLLED"
  "description"    : string   — concise English action sentence
  "tmu"            : integer  — total TMU = base_tmu_per_unit × frequency
  "seconds"        : float    — tmu × 0.036, rounded to 2 decimal places
  "params"         : {{}}      — empty dict (MOST index params not required here)
  "component"      : string | null  — object name from Object Library, or null
  "tool"           : string | null  — tool name from Tool Library, or null
  "is_ctq"         : boolean  — true if component is CTQ per Object Library
  "object_category": string | null  — category from Object Library, or null
  "glove_type"     : string   — from Object Library, default "General Glove"
  "frequency"      : integer ≥ 1  — honour quantity words ("4 screws" → 4)
  "required_skill" : string | null — from Object Library, null if not listed
  "is_simo"        : false
  "precautions"    : []

## Rules
1. Emit one object per MOST motion type (Grab, Place, Fasten, Inspect, Scan).
2. Quantity words ("4 screws") must set "frequency" to that integer.
3. Fastening steps must use "Torque Driver" as tool when applicable.
4. Do NOT invent component names; use only the Object Library.
"""


# ─── Mock deterministic generator ─────────────────────────────────────────────

def _extract_quantity(instruction: str, obj_name: str) -> int:
    """Extract a numeric quantity near the object name in the instruction."""
    lower = instruction.lower()
    obj_lower = obj_name.lower()
    patterns = [
        rf"\b(\d+)\s+{re.escape(obj_lower)}s?\b",
        rf"{re.escape(obj_lower)}s?\s+[×x]\s*(\d+)",
        rf"{re.escape(obj_lower)}s?\s+(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, lower)
        if m:
            return max(1, int(m.group(1)))
    # Standalone number anywhere in the instruction (last resort)
    nums = re.findall(r"\b(\d+)\b", lower)
    if nums:
        return max(1, int(nums[0]))
    return 1


def _match_objects(instruction: str, library: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return library objects whose name appears in the instruction, sorted by first occurrence.

    Sorting by position ensures that the primary subject of the instruction (e.g. "CPU" in
    "Install CPU on motherboard") becomes `primary` rather than whatever happens to appear
    first in the library definition order.
    """
    lower = instruction.lower()
    hits: list[tuple[int, dict[str, Any]]] = []
    for obj in library:
        name = (obj.get("name") or "").lower()
        if name and name in lower:
            hits.append((lower.index(name), obj))
    hits.sort(key=lambda x: x[0])
    return [obj for _, obj in hits]


def _detect_verbs(instruction: str) -> list[str]:
    """Return deduplicated MOST motion verbs implied by the instruction keywords."""
    lower = instruction.lower()
    seen: set[str] = set()
    motions: list[str] = []
    for keyword, candidates in _VERB_MAP.items():
        if keyword in lower:
            for m in candidates:
                if m not in seen:
                    seen.add(m)
                    motions.append(m)
    return motions or ["Grab", "Place"]


def _resolve_tool(action_name: str, component_name: str | None, tool_library: list[dict[str, Any]]) -> str | None:
    """Infer the best tool for an action based on action name and component name."""
    target_name: str | None = None
    for keyword, tool in _TOOL_KEYWORD_MAP.items():
        if component_name and keyword in component_name.lower():
            target_name = tool
            break
    if not target_name:
        for keyword, tool in _TOOL_KEYWORD_MAP.items():
            if keyword in action_name.lower():
                target_name = tool
                break
    if not target_name:
        return None
    for t in tool_library:
        if (t.get("name") or "").lower() == target_name.lower():
            return t["name"]
    return tool_library[0]["name"] if tool_library else None


def _build_action(
    motion: str,
    obj: dict[str, Any] | None,
    tool_library: list[dict[str, Any]],
    frequency: int = 1,
) -> dict[str, Any]:
    """Build a single SOPAction dict for the given motion and object."""
    base_tmu, seq_type = _ACTION_TMU.get(motion, (30, "GENERAL"))
    total_tmu = base_tmu * frequency
    component = obj.get("name") if obj else None
    tool = _resolve_tool(motion, component, tool_library)
    suffix = f" ×{frequency}" if frequency > 1 else ""
    return {
        "seq_type": seq_type,
        "description": f"{motion} {component or 'part'}{suffix}",
        "tmu": total_tmu,
        "seconds": round(total_tmu * _TMU_FACTOR, 2),
        "params": {},
        "component": component,
        "tool": tool,
        "is_ctq": bool(obj.get("ctq", False)) if obj else False,
        "object_category": obj.get("category") if obj else None,
        "glove_type": obj.get("glove_type", "General Glove") if obj else "General Glove",
        "frequency": frequency,
        "required_skill": obj.get("required_skill") if obj else None,
        "is_simo": False,
        "precautions": [],
    }


def _mock_llm_generate(
    instruction: str,
    object_library: list[dict[str, Any]],
    tool_library: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deterministically parse the natural language instruction into SOPAction dicts.

    Algorithm:
    1. Detect MOST motion verbs from keyword matching.
    2. Find all objects mentioned in the instruction by substring match.
    3. For each motion, select the most appropriate object:
       - Fasten → prefer Fastener-category objects.
       - Grab/Place/Inspect/Scan → prefer the primary (non-Fastener) component.
    4. Extract frequency from quantity words ("4 screws" → frequency=4 for Fasten).
    5. Deduplicate on (description) to avoid emitting identical steps twice.
    """
    motions = _detect_verbs(instruction)
    matched = _match_objects(instruction, object_library)

    non_fasteners = [o for o in matched if o.get("category") != "Fastener"]
    fasteners = [o for o in matched if o.get("category") == "Fastener"]
    primary = non_fasteners[0] if non_fasteners else (matched[0] if matched else None)
    fastener = fasteners[0] if fasteners else None

    actions: list[dict[str, Any]] = []
    seen: set[str] = set()

    for motion in motions:
        if motion == "Fasten":
            target = fastener or primary
            freq = _extract_quantity(instruction, target["name"]) if target else 1
            action = _build_action(motion, target, tool_library, frequency=freq)
        else:
            action = _build_action(motion, primary, tool_library)

        key = action["description"]
        if key not in seen:
            seen.add(key)
            actions.append(action)

    # Fallback: guarantee at least one action even if nothing was matched
    if not actions:
        actions.append(_build_action("Grab", primary, tool_library))

    return actions


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


def _call_openai_api(
    instruction: str,
    api_key: str,
    base_url: str,
    model: str,
    object_library: list[dict[str, Any]],
    tool_library: list[dict[str, Any]],
    precaution_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Call an OpenAI-compatible /chat/completions endpoint and parse the JSON array response.

    Uses only stdlib (urllib.request + json) to avoid adding an extra dependency.
    The base_url is validated to be https:// only.
    """
    endpoint = _validated_https_url(base_url.rstrip("/")) + "/chat/completions"
    system_prompt = build_system_prompt(object_library, tool_library, precaution_rules)
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": instruction},
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
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
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        raw = json.loads(resp.read().decode("utf-8"))

    content: str = raw["choices"][0]["message"]["content"]
    # Strip potential markdown code fences defensively
    content = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.IGNORECASE)
    content = re.sub(r"\s*```$", "", content, flags=re.IGNORECASE)
    result = json.loads(content)
    if not isinstance(result, list):
        raise ValueError("LLM response must be a JSON array")
    return result


# ─── Public entry point ────────────────────────────────────────────────────────

def generate_sop_actions(
    instruction: str,
    object_library: list[dict[str, Any]],
    tool_library: list[dict[str, Any]],
    precaution_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate SOPAction dicts from a natural language instruction.

    Strategy:
    - If ``OPENAI_API_KEY`` env var is set, attempt a real call to the
      OpenAI-compatible API pointed to by ``OPENAI_BASE_URL``
      (default: https://api.openai.com/v1) using model ``OPENAI_MODEL``
      (default: gpt-4o-mini).
    - On any API failure (network error, parse error, invalid response shape),
      gracefully fall back to the deterministic mock generator so the UI never
      blocks on an external service outage.
    - When no API key is present, skip the network call entirely and use the mock.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        try:
            return _call_openai_api(
                instruction=instruction,
                api_key=api_key,
                base_url=base_url,
                model=model,
                object_library=object_library,
                tool_library=tool_library,
                precaution_rules=precaution_rules,
            )
        except Exception:  # noqa: BLE001 — intentional: any failure falls back to mock
            pass

    return _mock_llm_generate(instruction, object_library, tool_library)
