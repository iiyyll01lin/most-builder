from __future__ import annotations

from copy import deepcopy

from ddm_v2.schemas import SkillLevel, SOPStatus, UserRole


DEFAULT_STATE = {
    "users": {
        "admin": {
            "id": "usr-admin",
            "username": "admin",
            "password": "admin123",
            "role": UserRole.manager.value,
            "name": "System Manager",
        },
        "engineer1": {
            "id": "usr-eng-1",
            "username": "engineer1",
            "password": "eng123",
            "role": UserRole.engineer.value,
            "name": "Lead Engineer",
        },
        "operator1": {
            "id": "usr-op-1",
            "username": "operator1",
            "password": "op123",
            "role": UserRole.operator.value,
            "name": "Line Operator",
        },
    },
    "projects": [
        {
            "id": "proj-atlas",
            "name": "Atlas Server Build",
            "sku": "ATLAS-2U",
            "version": "2.3",
            "process_type": "Assembly",
            "factory": "TPE-1",
        },
        {
            "id": "proj-orion",
            "name": "Orion Storage Build",
            "sku": "ORION-1U",
            "version": "1.8",
            "process_type": "Assembly",
            "factory": "KHH-2",
        },
    ],
    "syntax_library": [
        {"id": "syn-grab", "action_verb": "Grab", "code_most": "G", "parameter_range": "G1-G3", "tmu_value": 10},
        {"id": "syn-place", "action_verb": "Place", "code_most": "P", "parameter_range": "P1-P3", "tmu_value": 10},
        {"id": "syn-inspect", "action_verb": "Inspect", "code_most": "I", "parameter_range": "I6-I32", "tmu_value": 6},
        {"id": "syn-fasten", "action_verb": "Fasten", "code_most": "X", "parameter_range": "Fixed", "tmu_value": 6},
    ],
    "component_library": [
        {"id": "comp-mb", "name_cn": "主機板", "name_en": "Motherboard", "category": "Main Part"},
        {"id": "comp-ssd", "name_cn": "固態硬碟", "name_en": "SSD", "category": "Storage"},
    ],
    "tool_library": [
        {"id": "tool-driver", "name": "Torque Driver", "spec": "0.6 Nm", "bit": "PH1"},
        {"id": "tool-scanner", "name": "Barcode Scanner", "spec": "USB", "bit": None},
    ],
    "location_library": [
        {"id": "loc-bin", "name": "Bin"},
        {"id": "loc-fixture", "name": "Fixture"},
    ],
    "object_library": [
        {"id": "obj-screw", "name": "Screw", "category": "Fastener", "sub_category": "M3", "glove_type": "Finger Cot", "ctq": True},
        {"id": "obj-board", "name": "Motherboard", "category": "PCB", "sub_category": "Main", "glove_type": "ESD Glove", "ctq": True},
        {"id": "obj-label", "name": "Label", "category": "Label", "sub_category": "RFID", "glove_type": "General Glove", "ctq": False},
    ],
    "from_locations": [
        {"id": "from-bin", "name": "Component Bin"},
        {"id": "from-rack", "name": "Rack"},
    ],
    "to_locations": [
        {"id": "to-fixture", "name": "Fixture"},
        {"id": "to-chassis", "name": "Chassis"},
    ],
    "reference_points": [
        {"id": "ref-a", "name": "Datum A"},
        {"id": "ref-b", "name": "Datum B"},
    ],
    "precautions": [
        {"id": "pre-esd", "process": "Assembly", "category": "ESD", "description": "Enable ion fan for exposed PCB handling."},
        {"id": "pre-torque", "process": "Assembly", "category": "Tooling", "description": "Verify torque tool calibration before shift start."},
    ],
    "glove_rules": [
        {"id": "glv-pcb", "object_category": "PCB", "action": "*", "glove_type": "ESD Glove"},
        {"id": "glv-fastener", "object_category": "Fastener", "action": "Fasten", "glove_type": "Finger Cot"},
        {"id": "glv-default", "object_category": "*", "action": "*", "glove_type": "General Glove"},
    ],
    "ion_fan_bindings": [
        {"id": "ion-pcb", "object_category": "PCB", "object_name": "Motherboard", "note": "ESD critical handling"},
    ],
    "mi_naming_rules": [
        {"id": "rule-project", "field": "project", "label": "Project", "required": True},
        {"id": "rule-line", "field": "line", "label": "Line", "required": True},
        {"id": "rule-station", "field": "station", "label": "Station", "required": True},
        {"id": "rule-seconds", "field": "seconds", "label": "Seconds", "required": True},
    ],
    "level_system_templates": [
        {"id": "lvl-1", "level": 1, "description": "Main sequencing between material families."},
        {"id": "lvl-2", "level": 2, "description": "Order and cub grouping constraints."},
    ],
    "level_guidelines": [
        {"id": "guide-main", "title": "Main", "body": "Use Main for top-level precedence across material groups."},
        {"id": "guide-cub", "title": "Cub", "body": "Use Cub for indivisible action blocks that must stay in the same station."},
    ],
    "employees": [
        {"id": "emp-eva", "name": "Eva", "station_type": "Assembly", "skill_level": SkillLevel.expert.value, "efficiency_factor": 1.2},
        {"id": "emp-noah", "name": "Noah", "station_type": "Assembly", "skill_level": SkillLevel.proficient.value, "efficiency_factor": 1.0},
        {"id": "emp-li", "name": "Li", "station_type": "Assembly", "skill_level": SkillLevel.novice.value, "efficiency_factor": 0.8},
    ],
    "stations": [
        {"id": "ST-1", "name": "Station 1", "employee_id": "emp-eva"},
        {"id": "ST-2", "name": "Station 2", "employee_id": "emp-noah"},
        {"id": "ST-3", "name": "Station 3", "employee_id": "emp-li"},
    ],
    "sop_versions": [
        {
            "id": "sop-atlas-v1",
            "project_id": "proj-atlas",
            "version_no": "V1.0",
            "status": SOPStatus.draft.value,
            "actions": [],
            "created_by": "usr-eng-1",
            "created_at": "2026-03-13T00:00:00+00:00",
            "reviewed_by": None,
            "reviewed_at": None,
            "published_by": None,
            "published_at": None,
        }
    ],
    "most_workspaces": [],
    "level_entries": {},
    "audit_logs": [],
    "simulation_results": [],
}


def build_default_state() -> dict:
    return deepcopy(DEFAULT_STATE)
