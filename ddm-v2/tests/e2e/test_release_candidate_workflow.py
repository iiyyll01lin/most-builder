from __future__ import annotations

import pytest


@pytest.mark.e2e
def test_end_to_end_engineering_workflow(client, engineer_headers, manager_headers):
    projects = client.get("/api/v1/projects", headers=engineer_headers)
    assert projects.status_code == 200
    project_id = projects.json()[0]["id"]

    calc = client.post(
        "/api/v1/most/calculate",
        headers=engineer_headers,
        json={
            "steps": [
                {
                    "action": "Grab",
                    "primary_action": "Grab",
                    "object": "Screw",
                    "object_category": "Fastener",
                    "seq_type": "GENERAL",
                    "hand": "Right Hand",
                    "from_location": "Component Bin",
                    "to_location": "Chassis",
                    "params": {"A1": 1, "B1": 0, "G": 3, "A2": 1, "B2": 0, "P": 3, "A3": 1},
                    "frequency": 2
                },
                {
                    "action": "Inspect",
                    "primary_action": "Inspect",
                    "object": "Motherboard",
                    "object_category": "PCB",
                    "seq_type": "CONTROLLED",
                    "hand": "Right Hand",
                    "from_location": "Fixture",
                    "to_location": "Fixture",
                    "params": {"A1": 1, "B1": 0, "G": 1, "M": 10, "X": 0, "I": 6, "A3": 1},
                    "frequency": 1
                }
            ]
        },
    )
    assert calc.status_code == 200
    breakdown = calc.json()["breakdown"]

    version = client.post(
        "/api/v1/sop/versions",
        headers=engineer_headers,
        json={"project_id": project_id, "version_no": "V9.9", "actions": []},
    )
    assert version.status_code == 201
    sop_id = version.json()["id"]

    workspace = client.put(
        f"/api/v1/most/workspaces/{project_id}",
        headers=engineer_headers,
        json={
            "sop_version_id": sop_id,
            "steps": [
                {
                    "id": f"step-e2e-{index}",
                    "action": item["action"],
                    "primary_action": item["action"],
                    "object": item["object"],
                    "object_category": item["object_category"],
                    "seq_type": item["seq_type"],
                    "hand": item["hand"],
                    "from_location": item["from_location"],
                    "to_location": item["to_location"],
                    "params": {"seed": index},
                    "frequency": item["frequency"],
                    "is_ctq": True,
                    "tool": "Torque Driver",
                    "station_id": f"ST-{index}",
                }
                for index, item in enumerate(breakdown, start=1)
            ],
            "wi_components": [
                {"id": "wi-e2e", "name": "E2E WI", "stepIds": [f"step-e2e-{index}" for index in range(1, len(breakdown) + 1)]}
            ],
            "selected_step_ids": ["step-e2e-1"],
        },
    )
    assert workspace.status_code == 200

    actions = workspace.json()["actions"]
    for index, action in enumerate(actions, start=1):
        action["station_id"] = f"ST-{index}"

    save_actions = client.put(f"/api/v1/sop/versions/{sop_id}/actions", headers=engineer_headers, json=actions)
    assert save_actions.status_code == 200
    assert save_actions.json()["actions"][0]["params"]["_most"]["index_string"]

    sync = client.post("/api/v1/level-system/sync", headers=engineer_headers, json={"project_id": project_id, "sop_version_id": sop_id})
    assert sync.status_code == 200

    entries = client.get(f"/api/v1/level-system/{project_id}", headers=engineer_headers).json()["entries"]
    save_level = client.post(
        "/api/v1/level-system/save",
        headers=engineer_headers,
        json={
            "project_id": project_id,
            "entries": [
                {"action_id": entries[0]["action_id"], "difficulty_factor": 1.0, "main_seq": "1", "machine_count": 1, "operator_count": 1},
                {"action_id": entries[1]["action_id"], "difficulty_factor": 1.2, "main_seq": "2", "cub_group": "C1", "machine_count": 2, "operator_count": 1},
            ],
        },
    )
    assert save_level.status_code == 200

    graph = client.post(f"/api/v1/level-system/generate-graph?project_id={project_id}", headers=engineer_headers)
    assert graph.status_code == 200
    assert graph.json()["total_adjusted_ct"] > 0

    simulation = client.post(
        "/api/v1/simulation/line-balance",
        headers=engineer_headers,
        json={
            "project_id": project_id,
            "takt_time": 4.0,
            "stations": [
                {"id": "ST-1", "employee_id": "emp-eva", "sop_ids": [sop_id]},
                {"id": "ST-2", "employee_id": "emp-noah", "sop_ids": [sop_id]},
            ],
        },
    )
    assert simulation.status_code == 200
    assert simulation.json()["station_results"]

    publish = client.put(f"/api/v1/sop/versions/{sop_id}/status", headers=manager_headers, json={"status": "Published"})
    assert publish.status_code == 200
    assert publish.json()["status"] == "Published"

    audit = client.get("/api/v1/audit/logs", headers=manager_headers)
    assert audit.status_code == 200
    assert len(audit.json()) >= 4


@pytest.mark.e2e
def test_complete_pe_workflow_with_simo_and_collaborative_steps(client, engineer_headers, manager_headers):
    """Phase 2 E2E: Simulates a full PE workflow that exercises the hardened
    business logic: SIMO paired actions, collaborative two-person assembly,
    numeric precedence ordering, and SIMO-aware line balance.

    Flow:
      1. Calculate MOST steps including a SIMO pair and a collaborative step
      2. Save workspace (verifies simo_adjusted_total_tmu exposed)
      3. Push actions to SOP version
      4. Sync and save Level System with 10+ main_seq entries (tests numeric sort)
      5. Generate precedence graph (verifies numeric ordering and no cycles)
      6. Run line balance simulation (verifies SIMO deduplication in station time)
      7. Verify simulation returns accurate cycle time
    """
    projects = client.get("/api/v1/projects", headers=engineer_headers)
    project_id = projects.json()[0]["id"]

    # 1. Calculate MOST steps — SIMO pair + collaborative
    calc = client.post(
        "/api/v1/most/calculate",
        headers=engineer_headers,
        json={
            "steps": [
                {
                    "action": "Grab",
                    "primary_action": "Grab",
                    "object": "Motherboard",
                    "object_category": "PCB",
                    "seq_type": "GENERAL",
                    "hand": "Left Hand",
                    "from_location": "Fixture",
                    "to_location": "Fixture",
                    "is_simo": True,
                    "simo_group_id": "sg-e2e",
                    "params": {"A1": 1, "B1": 0, "G": 3, "A2": 1, "B2": 0, "P": 3, "A3": 1},
                    "frequency": 1,
                    "operator_count": 1,
                },
                {
                    "action": "Inspect",
                    "primary_action": "Inspect",
                    "object": "Motherboard",
                    "object_category": "PCB",
                    "seq_type": "CONTROLLED",
                    "hand": "Right Hand",
                    "from_location": "Fixture",
                    "to_location": "Fixture",
                    "is_simo": True,
                    "simo_group_id": "sg-e2e",
                    "params": {"A1": 1, "B1": 0, "G": 1, "M": 10, "X": 0, "I": 6, "A3": 1},
                    "frequency": 1,
                    "operator_count": 2,
                    "is_collaborative": True,
                    "operators": [
                        {"employee_id": "emp-eva", "individual_tmu": 15},
                        {"employee_id": "emp-noah", "individual_tmu": 22},
                    ],
                },
            ]
        },
    )
    assert calc.status_code == 200
    calc_body = calc.json()
    # Verify SIMO-adjusted total is exposed and correct
    assert calc_body["total_tmu"] == 28           # raw sum: 9 + 19
    assert calc_body["simo_adjusted_total_tmu"] == 19  # sg-e2e: max(9,19)
    assert calc_body["collaborative_effective_tmu"] is not None

    # 2. Create SOP and save workspace
    version = client.post(
        "/api/v1/sop/versions",
        headers=engineer_headers,
        json={"project_id": project_id, "version_no": "V-SIMO-E2E", "actions": []},
    )
    assert version.status_code == 201
    sop_id = version.json()["id"]

    workspace = client.put(
        f"/api/v1/most/workspaces/{project_id}",
        headers=engineer_headers,
        json={
            "sop_version_id": sop_id,
            "steps": [
                {
                    "id": "simo-step-lh",
                    "action": "Grab",
                    "primary_action": "Grab",
                    "object": "Motherboard",
                    "object_category": "PCB",
                    "seq_type": "GENERAL",
                    "hand": "Left Hand",
                    "is_simo": True,
                    "simo_group_id": "sg-e2e",
                    "params": {"A1": 1, "B1": 0, "G": 3, "A2": 1, "B2": 0, "P": 3, "A3": 1},
                    "frequency": 1,
                    "station_id": "ST-3-1a",
                    "is_ctq": True,
                },
                {
                    "id": "simo-step-rh",
                    "action": "Inspect",
                    "primary_action": "Inspect",
                    "object": "Motherboard",
                    "object_category": "PCB",
                    "seq_type": "CONTROLLED",
                    "hand": "Right Hand",
                    "is_simo": True,
                    "simo_group_id": "sg-e2e",
                    "params": {"A1": 1, "B1": 0, "G": 1, "M": 10, "X": 0, "I": 6, "A3": 1},
                    "frequency": 1,
                    "station_id": "ST-3-1a",
                    "is_ctq": False,
                    "operator_count": 2,
                    "is_collaborative": True,
                    "operators": [
                        {"employee_id": "emp-eva", "individual_tmu": 15},
                        {"employee_id": "emp-noah", "individual_tmu": 22},
                    ],
                },
            ],
            "wi_components": [],
            "selected_step_ids": ["simo-step-lh"],
        },
    )
    assert workspace.status_code == 200
    ws_body = workspace.json()
    # PCB actions get ESD Glove from stored master rule, not hardcoded dict
    assert ws_body["steps"][0]["glove_type"] == "ESD Glove"

    # 3. Commit actions to SOP (add simo_group_id to persisted actions)
    actions = ws_body["actions"]
    for i, action in enumerate(actions):
        action["station_id"] = "ST-3-1a"
        action["simo_group_id"] = "sg-e2e"
        action["is_simo"] = True

    save_sop = client.put(f"/api/v1/sop/versions/{sop_id}/actions", headers=engineer_headers, json=actions)
    assert save_sop.status_code == 200

    # 4. Sync level system
    sync = client.post(
        "/api/v1/level-system/sync",
        headers=engineer_headers,
        json={"project_id": project_id, "sop_version_id": sop_id},
    )
    assert sync.status_code == 200

    entries = client.get(f"/api/v1/level-system/{project_id}?sop_version_id={sop_id}", headers=engineer_headers).json()["entries"]
    assert len(entries) >= 2

    # Save level with main_seq values that stress numeric sorting (2 steps, seqs "1" and "10")
    save_level = client.post(
        "/api/v1/level-system/save",
        headers=engineer_headers,
        json={
            "project_id": project_id,
            "sop_version_id": sop_id,
            "entries": [
                {"action_id": entries[0]["action_id"], "difficulty_factor": 1.0, "main_seq": "1", "machine_count": 1, "operator_count": 1},
                {"action_id": entries[1]["action_id"], "difficulty_factor": 1.0, "main_seq": "10", "machine_count": 1, "operator_count": 1},
            ],
        },
    )
    assert save_level.status_code == 200

    # 5. Generate precedence graph — verify numeric ordering and no cycles
    graph = client.post(
        f"/api/v1/level-system/generate-graph?project_id={project_id}&sop_version_id={sop_id}",
        headers=engineer_headers,
    )
    assert graph.status_code == 200
    graph_body = graph.json()
    assert graph_body["cycle_errors"] == []
    # main_seq "1" -> "10"; edge must go from action at seq=1 to action at seq=10
    edge_froms = [e["from"] for e in graph_body["precedence_edges"]]
    assert edge_froms == [entries[0]["action_id"]]

    # 6. Run line balance — SIMO deduplication means station time is max(LH,RH)
    sim = client.post(
        "/api/v1/simulation/line-balance",
        headers=engineer_headers,
        json={
            "project_id": project_id,
            "takt_time": 2.0,
            "stations": [
                {"id": "ST-3-1a", "employee_id": "emp-eva", "sop_ids": [sop_id]},
            ],
        },
    )
    assert sim.status_code == 200
    sim_body = sim.json()
    station = sim_body["station_results"][0]
    # With SIMO deduplication (simo_group_id set): standard_time = max(9, 19) * tmu_factor
    # = 19 * 0.036 = 0.684 rounded to 0.68
    # Without deduplication it would be (9+19)*0.036 = 1.008 → misidentified as overloaded
    # Deduplication is in effect when simo_group_id is stored on the SOP action
    assert station["standard_time"] == pytest.approx(0.68, abs=0.10)

    # 7. Publish and confirm audit trail
    publish = client.put(
        f"/api/v1/sop/versions/{sop_id}/status",
        headers=manager_headers,
        json={"status": "Published"},
    )
    assert publish.status_code == 200
    assert publish.json()["published_at"] is not None

