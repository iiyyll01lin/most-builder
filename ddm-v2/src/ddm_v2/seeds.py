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
    # ── Auto-binding Precaution Rules (ddm-struct-0819.xlsx spec) ─────────────
    # Each rule is matched per SOP action:
    #   trigger_type = "component" → match action["component"] (case-insensitive substring)
    #   trigger_type = "tool"      → match action["tool"]      (case-insensitive substring)
    # Matched texts are appended to action["precautions"] and StationResult.precautions.
    "precaution_rules": [
        {
            "id": "prule-lcd-1",
            "trigger_type": "component",
            "trigger_value": "LCD",
            "text": "擦拭LCD时需用手扶着LCD",
            "category": "Handling",
        },
        {
            "id": "prule-lcd-2",
            "trigger_type": "component",
            "trigger_value": "LCD",
            "text": "禁止用任何液体直接倒在LCD Panel上",
            "category": "Handling",
        },
        {
            "id": "prule-elec-driver",
            "trigger_type": "tool",
            "trigger_value": "电动起子",
            "text": "电动起子高度需距离机台 22~35cm",
            "category": "Tooling",
        },
        {
            "id": "prule-tp-tool",
            "trigger_type": "tool",
            "trigger_value": "TP压合治具",
            "text": "需記錄气压值 (Mpa) 與压强值 (N/cm²)",
            "category": "Equipment",
        },
        {
            "id": "prule-lock-tool",
            "trigger_type": "tool",
            "trigger_value": "开机键锁附治具",
            "text": "需記錄气压值 (Mpa) 與压强值 (N/cm²)",
            "category": "Equipment",
        },
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
            "actions": [
                # 7 representative GENERAL actions — used by SOP Editor E2E tests
                {"id": "act-seed-1", "seq_type": "GENERAL", "description": "伸手 抓取螺絲", "tmu": 3, "seconds": 0.11, "params": {}, "station_id": "ST-3-1a", "is_ctq": False, "frequency": 1, "is_simo": False, "component": None, "tool": None, "image_url": None, "glove_type": None, "object_category": None},
                {"id": "act-seed-2", "seq_type": "GENERAL", "description": "鎖附 螺絲", "tmu": 8, "seconds": 0.29, "params": {}, "station_id": "ST-3-1a", "is_ctq": False, "frequency": 1, "is_simo": False, "component": None, "tool": None, "image_url": None, "glove_type": None, "object_category": None},
                {"id": "act-seed-3", "seq_type": "GENERAL", "description": "移動 並放置", "tmu": 5, "seconds": 0.18, "params": {}, "station_id": "ST-3-1b", "is_ctq": False, "frequency": 1, "is_simo": False, "component": None, "tool": None, "image_url": None, "glove_type": None, "object_category": None},
                {"id": "act-seed-4", "seq_type": "GENERAL", "description": "拿取 主板", "tmu": 10, "seconds": 0.36, "params": {}, "station_id": "ST-4-1", "is_ctq": True, "frequency": 1, "is_simo": False, "component": None, "tool": None, "image_url": None, "glove_type": "兩只半指手套", "object_category": "MLB"},
                {"id": "act-seed-5", "seq_type": "GENERAL", "description": "安裝 DIMM", "tmu": 12, "seconds": 0.43, "params": {}, "station_id": "ST-3-1a", "is_ctq": True, "frequency": 1, "is_simo": False, "component": None, "tool": None, "image_url": None, "glove_type": "兩只半指手套", "object_category": "DIMM"},
                {"id": "act-seed-6", "seq_type": "CONTROLLED", "description": "確認 螺絲力矩", "tmu": 6, "seconds": 0.22, "params": {}, "station_id": "ST-3-1a", "is_ctq": True, "frequency": 1, "is_simo": False, "component": None, "tool": None, "image_url": None, "glove_type": None, "object_category": None},
                {"id": "act-seed-7", "seq_type": "GENERAL", "description": "放置 組件至托盤", "tmu": 4, "seconds": 0.14, "params": {}, "station_id": "ST-3-1b", "is_ctq": False, "frequency": 1, "is_simo": False, "component": None, "tool": None, "image_url": None, "glove_type": None, "object_category": None},
            ],
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


# ─────────────────────────────────────────────────────────────────────────────
#  Phase 10: Ultimate Demo Seed — "Project Alpha: Smart Speaker Assembly"
# ─────────────────────────────────────────────────────────────────────────────

# Station IDs used by the demo orchestrator (must stay in sync with
# scripts/demo_orchestrator.py).
ALPHA_STATIONS: list[dict] = [
    {"id": "ALPHA-ST-1",  "name": "ST-1  Chassis Prep",                "employee_id": "emp-alpha-b", "1p2m": False},
    {"id": "ALPHA-ST-2a", "name": "ST-2A Driver Install [1P2M · A]",   "employee_id": "emp-alpha-a", "1p2m": True},
    {"id": "ALPHA-ST-2b", "name": "ST-2B Driver Install [1P2M · B]",   "employee_id": "emp-alpha-a", "1p2m": True},
    {"id": "ALPHA-ST-3",  "name": "ST-3  PCB & Audio Module (CTQ)",     "employee_id": "emp-alpha-a", "1p2m": False},
    {"id": "ALPHA-ST-4",  "name": "ST-4  Cable Routing",                "employee_id": "emp-alpha-b", "1p2m": False},
    {"id": "ALPHA-ST-5",  "name": "ST-5  Final QA & Barcode Scan",      "employee_id": "emp-alpha-b", "1p2m": False},
]


async def seed_ultimate_demo(session: "AsyncSession") -> dict:  # type: ignore[name-defined]
    """Insert 'Project Alpha: Smart Speaker Assembly' showcase demo data.

    Idempotent: if the project already exists the function returns immediately
    without modifying any rows, making ``make demo`` safe to re-run.

    Returns a summary dict with inserted record counts.
    """
    import random
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from ddm_v2.models.domain import (
        EmployeeRow,
        LevelEntryRow,
        ProjectRow,
        SimulationResultRow,
        SopActionRow,
        SopVersionRow,
        StationRow,
        VideoUploadRow,
    )

    _UTC = timezone.utc

    # ── Idempotency guard ────────────────────────────────────────────────────
    existing = (
        await session.execute(select(ProjectRow).where(ProjectRow.id == "proj-alpha"))
    ).scalar_one_or_none()
    if existing is not None:
        return {"skipped": True, "reason": "Project Alpha already seeded"}

    now = datetime.now(_UTC)

    # ── Project ──────────────────────────────────────────────────────────────
    session.add(ProjectRow(
        id="proj-alpha",
        name="Smart Speaker Assembly",
        sku="SSA-X2026",
        version="2.0",
        process_type="BASY",
        factory="SQT",
    ))

    # ── Demo employees ────────────────────────────────────────────────────────
    session.add(EmployeeRow(
        id="emp-alpha-a", name="Alex Chen", station_type="Assembly",
        skill_level="Expert", efficiency_factor=1.15,
        certifications=["FATP01", "FATP07", "FATP09"],
    ))
    session.add(EmployeeRow(
        id="emp-alpha-b", name="Blake Park", station_type="Assembly",
        skill_level="Proficient", efficiency_factor=1.0,
        certifications=["FATP01", "FATP03"],
    ))

    # ── 6 stations (including 1P2M pair) ─────────────────────────────────────
    for st in ALPHA_STATIONS:
        session.add(StationRow(id=st["id"], name=st["name"], employee_id=st["employee_id"]))

    await session.flush()

    # ── SOP Version V1.0 (Published) ─────────────────────────────────────────
    sop_v1_id = "sop-alpha-v1"
    session.add(SopVersionRow(
        id=sop_v1_id, project_id="proj-alpha", version_no="V1.0",
        status="Published",
        created_by="usr-eng-1",       created_at=now - timedelta(days=45),
        reviewed_by="usr-admin",      reviewed_at=now - timedelta(days=40),
        published_by="usr-admin",     published_at=now - timedelta(days=38),
    ))
    await session.flush()

    # ── Actions for V1.0 ─────────────────────────────────────────────────────
    # Columns: (id, sort_idx, station_id, seq_type, description,
    #           tmu, component, tool, is_ctq, frequency,
    #           object_category, glove_type, required_skill, equipment_params)
    _TMU_F = 0.036
    _ACTIONS_V1: list[tuple] = [
        # Station 1 — Chassis Prep (1P1M)
        ("alpha-act-01", 0,  "ALPHA-ST-1", "GENERAL",    "Grab Chassis from component bin",
         40,  "Chassis",        None,              False, 1, "機殼",       "一般作業手套",    None,      None),
        ("alpha-act-02", 1,  "ALPHA-ST-1", "GENERAL",    "Place Chassis on assembly fixture",
         50,  "Chassis",        None,              False, 1, "機殼",       "一般作業手套",    None,      None),
        ("alpha-act-03", 2,  "ALPHA-ST-1", "GENERAL",    "Inspect Chassis alignment and orientation",
         24,  None,             None,              False, 1, None,        "General Glove",  None,      None),
        # Station 2A — Driver Install Machine A (1P2M)
        ("alpha-act-04", 3,  "ALPHA-ST-2a", "GENERAL",   "Grab Speaker Driver Unit ×2",
         80,  "Speaker Driver", None,              True,  2, "高單價物料", "兩只半指手套",    None,      None),
        ("alpha-act-05", 4,  "ALPHA-ST-2a", "GENERAL",   "Place Speaker Driver into enclosure",
         50,  "Speaker Driver", None,              True,  1, "高單價物料", "兩只半指手套",    None,      None),
        ("alpha-act-06", 5,  "ALPHA-ST-2a", "CONTROLLED", "Fasten Speaker Driver M3×4 screws (CTQ)",
         72,  "Screw",          "Torque Driver",   True,  4, "Fastener",  "Finger Cot",     None,
         {"torque_spec_nm": 0.6, "bit_type": "PH1"}),
        # Station 2B — Driver Install Machine B (1P2M — parallel with 2A)
        ("alpha-act-07", 6,  "ALPHA-ST-2b", "GENERAL",   "Grab Speaker Driver Unit ×2",
         80,  "Speaker Driver", None,              True,  2, "高單價物料", "兩只半指手套",    None,      None),
        ("alpha-act-08", 7,  "ALPHA-ST-2b", "GENERAL",   "Place Speaker Driver into enclosure",
         50,  "Speaker Driver", None,              True,  1, "高單價物料", "兩只半指手套",    None,      None),
        ("alpha-act-09", 8,  "ALPHA-ST-2b", "CONTROLLED", "Fasten Speaker Driver M3×4 screws (CTQ)",
         72,  "Screw",          "Torque Driver",   True,  4, "Fastener",  "Finger Cot",     None,
         {"torque_spec_nm": 0.6, "bit_type": "PH1"}),
        # Station 3 — PCB & Audio Module (CTQ + ESD + skill gate)
        ("alpha-act-10", 9,  "ALPHA-ST-3", "GENERAL",    "Grab PCB Audio Module (ion fan ON, anti-static)",
         40,  "Motherboard",    None,              True,  1, "PCB",       "兩只半指手套",    "FATP07",  None),
        ("alpha-act-11", 10, "ALPHA-ST-3", "GENERAL",    "Seat PCB into chassis ZIF connector",
         50,  "Motherboard",    None,              True,  1, "PCB",       "兩只半指手套",    "FATP07",  None),
        ("alpha-act-12", 11, "ALPHA-ST-3", "GENERAL",    "Scan PCB barcode for traceability",
         10,  "Label",          "Barcode Scanner", False, 1, "Label",     "General Glove",  None,      None),
        # Station 4 — Cable Routing
        ("alpha-act-13", 12, "ALPHA-ST-4", "GENERAL",    "Grab cable harness from component bin",
         40,  "Cable",          None,              False, 1, "線材",       "左手半指+右手指套", None,   None),
        ("alpha-act-14", 13, "ALPHA-ST-4", "GENERAL",    "Route cable through chassis guide clips",
         60,  "Cable",          None,              False, 1, "線材",       "左手半指+右手指套", None,   None),
        # Station 5 — Final QA & Barcode Scan
        ("alpha-act-15", 14, "ALPHA-ST-5", "GENERAL",    "Inspect completed assembly (visual & tactile)",
         24,  None,             None,              False, 1, None,        "General Glove",  None,      None),
        ("alpha-act-16", 15, "ALPHA-ST-5", "GENERAL",    "Scan finished product RFID label",
         10,  "Label",          "Barcode Scanner", False, 1, "Label",     "General Glove",  None,      None),
    ]

    for (aid, sidx, stn, stype, desc, tmu, comp, tool,
         ctq, freq, obj_cat, glove, req_skill, eq_params) in _ACTIONS_V1:
        session.add(SopActionRow(
            id=aid, sop_version_id=sop_v1_id, sort_idx=sidx,
            seq_type=stype, description=desc,
            tmu=tmu, seconds=round(tmu * _TMU_F, 2),
            params={}, precautions=[],
            station_id=stn, component=comp, tool=tool,
            is_ctq=ctq, frequency=freq,
            object_category=obj_cat, glove_type=glove,
            required_skill=req_skill, equipment_params=eq_params,
            is_simo=False,
            # Vision-engine anchors — pre-linked to the historical video
            video_timestamp_start=round(sidx * 20.5, 1),
            video_timestamp_end=round(sidx * 20.5 + tmu * _TMU_F * 1.8, 1),
        ))

    # ── SOP Version V2.0 (Under Review — streamlined 1P2M actions) ───────────
    sop_v2_id = "sop-alpha-v2"
    session.add(SopVersionRow(
        id=sop_v2_id, project_id="proj-alpha", version_no="V2.0",
        status="UnderReview",
        created_by="usr-eng-1", created_at=now - timedelta(days=10),
        reviewed_by=None, reviewed_at=None,
        published_by=None, published_at=None,
    ))
    await session.flush()

    # V2.0 combines the driver-grab into a single SIMO step (3 fewer actions)
    _ACTIONS_V2: list[tuple] = [
        ("alpha-v2-act-01", 0,  "ALPHA-ST-1",  "GENERAL",    "Grab & Place Chassis on fixture",
         90,  "Chassis",        None,           False, 1, "機殼",       "一般作業手套",    None,      None),
        ("alpha-v2-act-02", 1,  "ALPHA-ST-2a", "GENERAL",    "SIMO: Both drivers loaded simultaneously",
         130, "Speaker Driver", None,           True,  2, "高單價物料", "兩只半指手套",    None,      None),
        ("alpha-v2-act-03", 2,  "ALPHA-ST-2a", "CONTROLLED", "Fasten both enclosures ×4 each (1P2M CTQ)",
         144, "Screw",          "Torque Driver",True,  8, "Fastener",  "Finger Cot",     None,
         {"torque_spec_nm": 0.6, "bit_type": "PH1"}),
        ("alpha-v2-act-04", 3,  "ALPHA-ST-3",  "GENERAL",    "Grab & Seat PCB (ion fan ON)",
         90,  "Motherboard",    None,           True,  1, "PCB",       "兩只半指手套",    "FATP07",  None),
        ("alpha-v2-act-05", 4,  "ALPHA-ST-3",  "GENERAL",    "Scan PCB barcode",
         10,  "Label",          "Barcode Scanner",False,1, "Label",     "General Glove",  None,      None),
        ("alpha-v2-act-06", 5,  "ALPHA-ST-4",  "GENERAL",    "Route cable harness",
         100, "Cable",          None,           False, 1, "線材",       "左手半指+右手指套", None,   None),
        ("alpha-v2-act-07", 6,  "ALPHA-ST-5",  "GENERAL",    "Final inspect & RFID scan",
         34,  "Label",          "Barcode Scanner",False,1, "Label",     "General Glove",  None,      None),
    ]
    for (aid, sidx, stn, stype, desc, tmu, comp, tool,
         ctq, freq, obj_cat, glove, req_skill, eq_params) in _ACTIONS_V2:
        session.add(SopActionRow(
            id=aid, sop_version_id=sop_v2_id, sort_idx=sidx,
            seq_type=stype, description=desc,
            tmu=tmu, seconds=round(tmu * _TMU_F, 2),
            params={}, precautions=[],
            station_id=stn, component=comp, tool=tool,
            is_ctq=ctq, frequency=freq,
            object_category=obj_cat, glove_type=glove,
            required_skill=req_skill, equipment_params=eq_params,
            is_simo=(sidx == 1),
        ))

    # ── Historical video upload (pre-linked to V1.0) ─────────────────────────
    session.add(VideoUploadRow(
        id="vid-alpha-001",
        sop_version_id=sop_v1_id,
        project_id="proj-alpha",
        original_filename="line_b_station2_assembly_2026-02-14.mp4",
        stored_filename="vid-alpha-001.mp4",
        file_size=1_247_832_064,       # ~1.16 GB
        duration_seconds=340.5,
        width=1920, height=1080, fps=30.0,
        status="ready",
        uploaded_by="usr-eng-1",
        uploaded_at=now - timedelta(days=41),
    ))

    # ── 100+ Simulation Results (30 days of line-balance history) ─────────────
    rng = random.Random(42)   # deterministic so re-runs produce the same data
    _ST_IDS = [s["id"] for s in ALPHA_STATIONS]
    _BASE_TMUS = {
        "ALPHA-ST-1":  114,
        "ALPHA-ST-2a": 202,
        "ALPHA-ST-2b": 202,
        "ALPHA-ST-3":  245,   # natural bottleneck
        "ALPHA-ST-4":  100,
        "ALPHA-ST-5":   34,
    }
    _sim_count = 0
    for day_offset in range(30, 0, -1):
        runs_today = rng.randint(3, 4)
        for run_idx in range(runs_today):
            # Gradual improvement arc: efficiency rises from ~72 % to ~93 % over 30 days
            base_eff = 72.0 + (30 - day_offset) * 0.72 + rng.gauss(0, 3.5)
            eff = max(62.0, min(96.5, base_eff))

            st_tmus = {
                sid: max(20, round(rng.gauss(_BASE_TMUS[sid], _BASE_TMUS[sid] * 0.06)))
                for sid in _ST_IDS
            }
            bottleneck = max(st_tmus, key=lambda k: st_tmus[k])
            takt_s = round(st_tmus[bottleneck] * _TMU_F * (100 / eff), 2)
            run_ts = (now - timedelta(days=day_offset, hours=run_idx * 2)).isoformat()

            station_results = [
                {
                    "station_id": sid,
                    "station_name": next(s["name"] for s in ALPHA_STATIONS if s["id"] == sid),
                    "total_tmu": st_tmus[sid],
                    "operator_count": 1,
                    "machine_count": 2 if "ST-2" in sid else 1,
                    "efficiency_factor": round(rng.uniform(0.88, 1.12), 2),
                    "is_1p2m": "ST-2" in sid,
                }
                for sid in _ST_IDS
            ]

            sim_id = f"simr-alpha-{day_offset:02d}-{run_idx}"
            session.add(SimulationResultRow(
                id=sim_id,
                project_id="proj-alpha",
                timestamp=run_ts,
                created_by="usr-eng-1",
                data={
                    "station_results": station_results,
                    "summary": {
                        "total_tmu": sum(st_tmus.values()),
                        "takt_time_seconds": takt_s,
                        "line_efficiency_pct": round(eff, 1),
                        "bottleneck_station": bottleneck,
                        "operator_count": 5,
                        "configuration": "1P2M at ST-2A/ST-2B",
                        "sop_version": "V1.0",
                    },
                },
            ))
            _sim_count += 1

    # ── Level Entries for all V1.0 actions ────────────────────────────────────
    scope_key = f"proj-alpha::sop-alpha-v1"
    for i, (aid, sidx, stn, *_rest) in enumerate(_ACTIONS_V1):
        session.add(LevelEntryRow(
            id=f"le-alpha-{i:02d}",
            scope_key=scope_key,
            action_id=aid,
            difficulty_factor=round(1.0 + (i % 3) * 0.1, 1),
            main_seq="MAIN",
            order_seq=str(i + 1),
            machine_count=2 if "ST-2" in stn else 1,
            operator_count=1,
            sort_order=i,
        ))

    await session.flush()

    return {
        "skipped": False,
        "inserted": {
            "project": 1,
            "employees": 2,
            "stations": len(ALPHA_STATIONS),
            "sop_versions": 2,
            "actions_v1": len(_ACTIONS_V1),
            "actions_v2": len(_ACTIONS_V2),
            "video_uploads": 1,
            "simulation_results": _sim_count,
            "level_entries": len(_ACTIONS_V1),
        },
    }


# TYPE_CHECKING import kept at module scope to avoid a hard runtime dependency
# on SQLAlchemy in contexts where it may not be installed.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
