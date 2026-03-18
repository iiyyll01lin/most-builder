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
