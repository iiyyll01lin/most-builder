from __future__ import annotations

import json
from pathlib import Path

import pytest

from ddm_v2 import settings as settings_module
from ddm_v2.repositories.store import JsonStore


@pytest.mark.unit
def test_get_settings_supports_environment_overrides(monkeypatch, tmp_path):
    custom_root = tmp_path / "workspace-root"
    custom_root.mkdir()
    monkeypatch.setenv("DDM_ROOT_DIR", str(custom_root))
    monkeypatch.setenv("DDM_DB_PATH", "runtime/custom-db.json")
    monkeypatch.setenv("DDM_SECRET_KEY", "override-secret")
    monkeypatch.setenv("DDM_CORS_ALLOW_ORIGINS", "https://example.com,https://ops.example.com")
    monkeypatch.setenv("DDM_CORS_ALLOW_METHODS", "GET,POST,PUT")
    monkeypatch.setenv("DDM_CORS_ALLOW_HEADERS", "Authorization,Content-Type")
    monkeypatch.setenv("DDM_CORS_ALLOW_CREDENTIALS", "false")
    settings_module.get_settings.cache_clear()

    settings = settings_module.get_settings()

    assert settings.root_dir == custom_root
    assert settings.db_path == custom_root / "runtime" / "custom-db.json"
    assert settings.secret_key == "override-secret"
    assert settings.cors_allow_origins == ["https://example.com", "https://ops.example.com"]
    assert settings.cors_allow_methods == ["GET", "POST", "PUT"]
    assert settings.cors_allow_headers == ["Authorization", "Content-Type"]
    assert settings.cors_allow_credentials is False

    settings_module.get_settings.cache_clear()


@pytest.mark.unit
def test_json_store_save_uses_atomic_file_and_lock(tmp_path):
    db_path = tmp_path / "runtime-db.json"
    store = JsonStore(db_path)
    store.state["projects"].append({"id": "proj-1", "name": "Atlas"})

    store.save()

    assert db_path.exists() is True
    assert store.lock_path.exists() is True
    payload = json.loads(db_path.read_text(encoding="utf-8"))
    assert payload["projects"][-1]["id"] == "proj-1"
    temp_files = list(tmp_path.glob("tmp*"))
    assert temp_files == []


@pytest.mark.unit
def test_json_store_recovers_from_corrupt_payload(tmp_path):
    db_path = tmp_path / "runtime-db.json"
    db_path.write_text("{not-valid-json", encoding="utf-8")

    store = JsonStore(db_path)

    recovered_files = list(tmp_path.glob("runtime-db.corrupt-*.json"))
    assert recovered_files
    assert Path(recovered_files[0]).read_text(encoding="utf-8") == "{not-valid-json"
    assert "projects" in store.state
    assert json.loads(db_path.read_text(encoding="utf-8"))["projects"] == store.state["projects"]
