from __future__ import annotations

import json
from pathlib import Path

import pytest

from ddm_v2.repositories.store import JsonStore
from ddm_v2 import settings as settings_module


@pytest.mark.unit
def test_get_settings_supports_environment_overrides(monkeypatch, tmp_path):
    custom_root = tmp_path / "workspace-root"
    custom_root.mkdir()
    monkeypatch.setenv("DDM_ROOT_DIR", str(custom_root))
    monkeypatch.setenv("DDM_DB_PATH", "runtime/custom-db.sqlite3")
    monkeypatch.setenv("DDM_SECRET_KEY", "override-secret")
    monkeypatch.setenv("DDM_CORS_ALLOW_ORIGINS", "https://example.com,https://ops.example.com")
    monkeypatch.setenv("DDM_CORS_ALLOW_METHODS", "GET,POST,PUT")
    monkeypatch.setenv("DDM_CORS_ALLOW_HEADERS", "Authorization,Content-Type")
    monkeypatch.setenv("DDM_CORS_ALLOW_CREDENTIALS", "false")
    settings_module.get_settings.cache_clear()

    settings = settings_module.get_settings()

    assert settings.root_dir == custom_root
    assert settings.db_path == custom_root / "runtime" / "custom-db.sqlite3"
    assert settings.secret_key == "override-secret"
    assert settings.cors_allow_origins == ["https://example.com", "https://ops.example.com"]
    assert settings.cors_allow_methods == ["GET", "POST", "PUT"]
    assert settings.cors_allow_headers == ["Authorization", "Content-Type"]
    assert settings.cors_allow_credentials is False

    settings_module.get_settings.cache_clear()


@pytest.mark.unit
def test_sqlite_store_persists_collections(tmp_path):
    db_path = tmp_path / "runtime-db.sqlite3"
    store = JsonStore(db_path)
    store.state["projects"].append({"id": "proj-1", "name": "Atlas"})

    store.save()

    assert db_path.exists() is True
    reloaded = JsonStore(db_path)
    assert reloaded.find_by_id("projects", "proj-1")["name"] == "Atlas"


@pytest.mark.unit
def test_sqlite_store_migrates_legacy_json_payload(tmp_path):
    db_path = tmp_path / "runtime-db.sqlite3"
    legacy_json = tmp_path / "runtime-db.json"
    legacy_json.write_text(json.dumps({"projects": [{"id": "proj-legacy", "name": "Legacy Project"}]}), encoding="utf-8")

    store = JsonStore(db_path)

    assert store.find_by_id("projects", "proj-legacy")["name"] == "Legacy Project"
    assert (tmp_path / "runtime-db.legacy-json.json").exists() is True