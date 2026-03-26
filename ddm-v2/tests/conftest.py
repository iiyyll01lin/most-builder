from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from ddm_v2.main import create_app


@pytest.fixture
def client(tmp_path):
    # Use a file-based SQLite per test so the async engine sees the same DB
    # across the pool without the shared-memory cache URI complexity.
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    app = create_app(database_url=db_url)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def engineer_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": "Avery", "password": "avery"})
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
