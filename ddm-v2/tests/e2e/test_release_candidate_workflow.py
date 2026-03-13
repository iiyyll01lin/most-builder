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

    actions = []
    for index, item in enumerate(breakdown, start=1):
        actions.append(
            {
                "id": f"act-e2e-{index}",
                "seq_type": item["seq_type"],
                "description": item["auto_sentence"],
                "tmu": item["tmu"],
                "seconds": round(item["tmu"] * 0.036, 2),
                "params": {"seed": index},
                "station_id": f"ST-{index}",
                "component": item["object"],
                "tool": "Torque Driver",
                "is_ctq": True,
                "primary_action": item["action"],
                "hand": item["hand"],
                "object_category": item["object_category"],
                "glove_type": item["glove_type"],
                "frequency": item["frequency"],
            }
        )

    save_actions = client.put(f"/api/v1/sop/versions/{sop_id}/actions", headers=engineer_headers, json=actions)
    assert save_actions.status_code == 200

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
