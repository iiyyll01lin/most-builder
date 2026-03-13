from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from ddm_v2.main import create_app


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "runtime-db.json"
    app = create_app(db_path=db_path)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def engineer_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": "engineer1", "password": "eng123"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def manager_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def regression_fixture() -> dict:
    fixture_path = "tests/regression/fixtures/most_reference.json"
    with open(fixture_path, "r", encoding="utf-8") as handle:
        return json.load(handle)
