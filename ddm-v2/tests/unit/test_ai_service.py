from __future__ import annotations

import pytest

from ddm_v2.services.ai_service import (
    _mock_llm_generate,
    build_system_prompt,
    generate_sop_actions,
)
from ddm_v2.services.most_workspace_service import _apply_precaution_rules

# ─── Fixtures ──────────────────────────────────────────────────────────────────

OBJECT_LIBRARY = [
    {"id": "obj-screw", "name": "Screw", "category": "Fastener", "sub_category": "M3", "glove_type": "Finger Cot", "ctq": True},
    {"id": "obj-board", "name": "Motherboard", "category": "PCB", "sub_category": "Main", "glove_type": "兩只半指手套", "ctq": True},
    {"id": "obj-mlb", "name": "MLB", "category": "主板/MLB", "sub_category": "MLB", "glove_type": "兩只半指手套", "ctq": True},
    {"id": "obj-dimm", "name": "DIMM", "category": "記憶體", "sub_category": "DIMM", "glove_type": "兩只半指手套", "ctq": True},
    {"id": "obj-cpu", "name": "CPU", "category": "處理器", "sub_category": "CPU", "glove_type": "兩只半指手套", "ctq": True, "required_skill": "FATP07"},
    {"id": "obj-ssd", "name": "SSD", "category": "儲存裝置", "sub_category": "SSD", "glove_type": "兩只半指手套", "ctq": True},
    {"id": "obj-cable", "name": "Cable", "category": "線材", "sub_category": "Cable", "glove_type": "左手半指+右手指套", "ctq": False},
    {"id": "obj-label", "name": "Label", "category": "Label", "sub_category": "RFID", "glove_type": "General Glove", "ctq": False},
]

TOOL_LIBRARY = [
    {"id": "tool-driver", "name": "Torque Driver", "spec": "0.6 Nm", "bit": "PH1"},
    {"id": "tool-scanner", "name": "Barcode Scanner", "spec": "USB", "bit": None},
]

PRECAUTION_RULES: list[dict] = [
    {
        "id": "prule-lcd-1",
        "trigger_type": "component",
        "trigger_value": "LCD",
        "text": "擦拭LCD时需用手扶着LCD",
        "category": "Handling",
    },
    {
        "id": "prule-driver-1",
        "trigger_type": "tool",
        "trigger_value": "电动起子",
        "text": "电动起子高度需距离机台 22~35cm",
        "category": "Tooling",
    },
]


# ─── Unit: core mock generator ─────────────────────────────────────────────────

@pytest.mark.unit
def test_ai_service_generates_compliant_actions():
    """Mock generator converts 'Assemble motherboard with 4 screws' into valid SOPAction dicts
    that survive precaution rule validation and satisfy the full domain schema contract."""
    actions = generate_sop_actions(
        instruction="Assemble motherboard with 4 screws",
        object_library=OBJECT_LIBRARY,
        tool_library=TOOL_LIBRARY,
        precaution_rules=PRECAUTION_RULES,
    )

    assert len(actions) >= 1, "Must generate at least one action"

    for action in actions:
        assert action["seq_type"] in ("GENERAL", "CONTROLLED"), (
            f"Invalid seq_type: {action['seq_type']!r}"
        )
        assert isinstance(action["description"], str) and action["description"], (
            "description must be a non-empty string"
        )
        assert isinstance(action["tmu"], int) and action["tmu"] > 0, (
            "tmu must be a positive integer"
        )
        assert isinstance(action["seconds"], float) and action["seconds"] > 0, (
            "seconds must be a positive float"
        )
        assert isinstance(action["frequency"], int) and action["frequency"] >= 1, (
            "frequency must be an integer ≥ 1"
        )
        assert isinstance(action["is_ctq"], bool), "is_ctq must be boolean"
        assert isinstance(action["precautions"], list), "precautions must be a list"
        assert isinstance(action["is_simo"], bool), "is_simo must be boolean"
        assert action["params"] == {}, "params must be an empty dict"
        # seconds must be consistent with tmu × 0.036 within floating-point rounding
        assert abs(action["seconds"] - round(action["tmu"] * 0.036, 2)) < 0.02, (
            f"seconds={action['seconds']} inconsistent with tmu={action['tmu']}"
        )

    # CTQ check: Motherboard is ctq=True → at least one action should carry is_ctq=True
    assert any(a["is_ctq"] for a in actions), (
        "Expected at least one CTQ action for Motherboard"
    )

    # Fasten step: frequency must honour "4 screws" → 4
    fasten_actions = [a for a in actions if "Fasten" in a.get("description", "")]
    if fasten_actions:
        assert fasten_actions[0]["frequency"] == 4, (
            f"Expected frequency=4 for '4 screws', got {fasten_actions[0]['frequency']}"
        )

    # Precaution rules: every action must survive _apply_precaution_rules without exception
    for action in actions:
        result = _apply_precaution_rules(action, PRECAUTION_RULES)
        assert isinstance(result, list), "_apply_precaution_rules must return a list"


@pytest.mark.unit
def test_ai_service_generates_cpu_with_required_skill():
    """CPU action must carry required_skill='FATP07' from the object library."""
    actions = generate_sop_actions(
        instruction="Install CPU on motherboard",
        object_library=OBJECT_LIBRARY,
        tool_library=TOOL_LIBRARY,
        precaution_rules=PRECAUTION_RULES,
    )
    cpu_actions = [a for a in actions if a.get("component") == "CPU"]
    assert cpu_actions, "Expected at least one action with component='CPU'"
    for action in cpu_actions:
        assert action["required_skill"] == "FATP07", (
            f"CPU action must carry required_skill='FATP07', got {action.get('required_skill')!r}"
        )


@pytest.mark.unit
def test_ai_service_handles_unknown_objects_gracefully():
    """Unknown objects produce fallback actions without raising."""
    actions = generate_sop_actions(
        instruction="Apply thermal paste and seat the heatsink",
        object_library=OBJECT_LIBRARY,
        tool_library=TOOL_LIBRARY,
        precaution_rules=PRECAUTION_RULES,
    )
    assert isinstance(actions, list), "Must return a list even for unrecognised objects"
    assert len(actions) >= 1, "Must produce at least one fallback action"
    for action in actions:
        assert action["tmu"] > 0
        assert action["seconds"] > 0


@pytest.mark.unit
def test_ai_service_scan_instruction_uses_barcode_scanner():
    """Scan / barcode instructions should reference the Barcode Scanner tool."""
    actions = _mock_llm_generate(
        instruction="Scan the label barcode",
        object_library=OBJECT_LIBRARY,
        tool_library=TOOL_LIBRARY,
    )
    assert actions, "Must generate at least one action for scan instruction"
    # Scan steps use "Scan" motion which checks tool from _TOOL_KEYWORD_MAP via action name
    scan_actions = [a for a in actions if "Scan" in a.get("description", "")]
    assert scan_actions, "Expected at least one Scan action"
    # Scan motion resolves "scan" keyword → Barcode Scanner
    assert any(a.get("tool") == "Barcode Scanner" for a in scan_actions), (
        "Scan action should use Barcode Scanner"
    )


@pytest.mark.unit
def test_build_system_prompt_contains_master_data():
    """System prompt must embed object names, tool names, and schema field names."""
    prompt = build_system_prompt(OBJECT_LIBRARY, TOOL_LIBRARY, PRECAUTION_RULES)
    assert "Motherboard" in prompt, "Object library must be injected into prompt"
    assert "Torque Driver" in prompt, "Tool library must be injected into prompt"
    assert "is_ctq" in prompt, "SOPAction schema field must appear in prompt"
    assert "required_skill" in prompt, "SOPAction schema field must appear in prompt"
    assert "GENERAL" in prompt, "MOST seq_type values must appear in prompt"
    assert "https://" not in prompt or "api.openai.com" not in prompt, (
        "Prompt must not embed live API credentials"
    )


@pytest.mark.unit
def test_fasten_only_instruction_generates_controlled_step():
    """A pure 'fasten 2 screws' instruction must produce a CONTROLLED step with frequency=2."""
    actions = _mock_llm_generate(
        instruction="Fasten 2 screws",
        object_library=OBJECT_LIBRARY,
        tool_library=TOOL_LIBRARY,
    )
    fasten = [a for a in actions if a["seq_type"] == "CONTROLLED"]
    assert fasten, "Expected at least one CONTROLLED action for fasten instruction"
    assert fasten[0]["frequency"] == 2, (
        f"Expected frequency=2 for '2 screws', got {fasten[0]['frequency']}"
    )
    assert fasten[0]["tool"] == "Torque Driver", "Fasten step must use Torque Driver"
