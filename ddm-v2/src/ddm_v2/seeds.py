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
        "Avery": {
            "id": "usr-eng-1",
            "username": "Avery",
            "password": "avery",
            "role": UserRole.engineer.value,
            "name": "Avery, Yeh",
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
            "name": "K860G6-BASY",
            "sku": "W*3558",
            "version": "1.3",
            "process_type": "BASY",
            "factory": "SQT",
        },
        {
            "id": "proj-orion",
            "name": "K860G6-RACK",
            "sku": "W*3558-RACK",
            "version": "1.4",
            "process_type": "RACK",
            "factory": "SQT",
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
        # Fasteners
        {"id": "obj-screw", "name": "Screw", "category": "Fastener", "sub_category": "M3", "glove_type": "Finger Cot", "ctq": True},
        # PCB / Motherboard family
        {"id": "obj-board", "name": "Motherboard", "category": "PCB", "sub_category": "Main", "glove_type": "兩只半指手套", "ctq": True},
        {"id": "obj-mlb", "name": "MLB", "category": "主板/MLB", "sub_category": "MLB", "glove_type": "兩只半指手套", "ctq": True},
        {"id": "obj-server-mb", "name": "Server Motherboard", "category": "主板/MLB", "sub_category": "MLB", "glove_type": "兩只半指手套", "ctq": True},
        # Memory
        {"id": "obj-dimm", "name": "DIMM", "category": "記憶體", "sub_category": "DIMM", "glove_type": "兩只半指手套", "ctq": True},
        {"id": "obj-fake-dimm", "name": "Dummy DIMM", "category": "假件", "sub_category": "DIMM", "glove_type": "兩只半指手套", "ctq": False},
        # Processors
        {"id": "obj-cpu", "name": "CPU", "category": "處理器", "sub_category": "CPU", "glove_type": "兩只半指手套", "ctq": True, "required_skill": "FATP07"},
        # Storage
        {"id": "obj-ssd", "name": "SSD", "category": "儲存裝置", "sub_category": "SSD", "glove_type": "兩只半指手套", "ctq": True},
        # GPU / expansion cards
        {"id": "obj-gpu-riser", "name": "GPU Riser", "category": "擴充卡", "sub_category": "GPU", "glove_type": "兩只半指手套", "ctq": True},
        # Cables
        {"id": "obj-cable", "name": "Cable", "category": "線材", "sub_category": "Cable", "glove_type": "左手半指+右手指套", "ctq": False},
        # Labels
        {"id": "obj-label", "name": "Label", "category": "Label", "sub_category": "RFID", "glove_type": "General Glove", "ctq": False},
        # Chassis
        {"id": "obj-chassis", "name": "Chassis", "category": "機殼", "sub_category": "Chassis", "glove_type": "一般作業手套", "ctq": False},
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
        # High-value ESD-sensitive boards and processors → two half-finger gloves
        {"id": "glv-mlb", "object_category": "主板/MLB", "action": "*", "glove_type": "兩只半指手套"},
        {"id": "glv-dimm", "object_category": "記憶體", "action": "*", "glove_type": "兩只半指手套"},
        {"id": "glv-cpu", "object_category": "處理器", "action": "*", "glove_type": "兩只半指手套"},
        {"id": "glv-gpu", "object_category": "擴充卡", "action": "*", "glove_type": "兩只半指手套"},
        {"id": "glv-storage", "object_category": "儲存裝置", "action": "*", "glove_type": "兩只半指手套"},
        {"id": "glv-high-value", "object_category": "高單價物料", "action": "*", "glove_type": "兩只半指手套"},
        {"id": "glv-backplane", "object_category": "背板", "action": "*", "glove_type": "兩只半指手套"},
        # PCB general category (legacy/English names)
        {"id": "glv-pcb", "object_category": "PCB", "action": "*", "glove_type": "兩只半指手套"},
        # Cable routing → left half-finger + right finger cot
        {"id": "glv-cable", "object_category": "線材", "action": "*", "glove_type": "左手半指+右手指套"},
        # Fastener by specific action
        {"id": "glv-fastener", "object_category": "Fastener", "action": "Fasten", "glove_type": "Finger Cot"},
        # Packaging and structural parts → general gloves
        {"id": "glv-package", "object_category": "包材", "action": "*", "glove_type": "一般作業手套"},
        {"id": "glv-baffle", "object_category": "擋板", "action": "*", "glove_type": "一般作業手套"},
        {"id": "glv-chassis", "object_category": "機殼", "action": "*", "glove_type": "一般作業手套"},
        # Wildcard fallback
        {"id": "glv-default", "object_category": "*", "action": "*", "glove_type": "General Glove"},
    ],
    "ion_fan_bindings": [
        # LCD installation: mandates ion fan (ESD + fingerprint contamination risk)
        {"id": "ion-lcd", "object_category": "高單價物料", "object_name": "LCD", "note": "操作LCD時必須開啟離子風扇，避免ESD與指紋污染"},
        # MLB / Motherboard
        {"id": "ion-mlb", "object_category": "主板/MLB", "object_name": "MLB", "note": "操作MLB時必須開啟離子風扇"},
        {"id": "ion-mb", "object_category": "主板/MLB", "object_name": "Motherboard", "note": "ESD critical handling"},
        # DIMM / RAM
        {"id": "ion-dimm", "object_category": "記憶體", "object_name": "DIMM", "note": "操作DIMM記憶體時必須開啟離子風扇"},
        # CPU / Processor
        {"id": "ion-cpu", "object_category": "處理器", "object_name": "CPU", "note": "操作CPU時必須開啟離子風扇"},
        # GPU / Riser cards
        {"id": "ion-gpu", "object_category": "擴充卡", "object_name": "GPU Riser", "note": "操作GPU Riser時必須開啟離子風扇"},
        # PCB general category fallback
        {"id": "ion-pcb", "object_category": "PCB", "object_name": "PCB", "note": "ESD critical handling"},
    ],
    # MI Naming Convention: [Model5]_[Status]_[PickType]_[Process]_[CFI]_[Line]_[Area]_[CT]
    # Each field corresponds to one segment separated by '_'.
    "mi_naming_rules": [
        {"id": "rule-model5", "field": "model5", "label": "Model5", "required": True, "position": 1, "description": "5-digit model code (e.g. HDL50)"},
        {"id": "rule-status", "field": "status", "label": "Status", "required": True, "position": 2, "description": "SOP status (e.g. ASSY, PACK)"},
        {"id": "rule-pick-type", "field": "pick_type", "label": "PickType", "required": True, "position": 3, "description": "Pick type (e.g. FPT, MPT)"},
        {"id": "rule-process", "field": "process", "label": "Process", "required": True, "position": 4, "description": "Process type (ASSY/PACK/SUB/SMT)"},
        {"id": "rule-cfi", "field": "cfi", "label": "CFI", "required": False, "position": 5, "description": "CFI code (optional)"},
        {"id": "rule-line", "field": "line", "label": "Line", "required": True, "position": 6, "description": "Production line identifier"},
        {"id": "rule-area", "field": "area", "label": "Area", "required": True, "position": 7, "description": "Area or station zone"},
        {"id": "rule-ct", "field": "ct", "label": "CT", "required": True, "position": 8, "description": "Cycle time in seconds"},
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
        {"id": "emp-eva", "name": "Eva", "station_type": "Assembly", "skill_level": SkillLevel.expert.value, "efficiency_factor": 1.2, "certifications": ["FATP01", "FATP03", "FATP07", "FATP08"]},
        {"id": "emp-noah", "name": "Noah", "station_type": "Assembly", "skill_level": SkillLevel.proficient.value, "efficiency_factor": 1.0, "certifications": ["FATP01", "FATP03"]},
        {"id": "emp-li", "name": "Li", "station_type": "Assembly", "skill_level": SkillLevel.novice.value, "efficiency_factor": 0.8, "certifications": []},
    ],
    "stations": [
        {"id": "ST-3-1a", "name": "第3-1站 (DIMM)", "employee_id": "emp-eva"},
        {"id": "ST-3-1b", "name": "第3-1站 (假DIMM)", "employee_id": "emp-noah"},
        {"id": "ST-4-1", "name": "第4-1站 (主板)", "employee_id": "emp-li"},
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
