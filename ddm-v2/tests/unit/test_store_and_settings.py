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


@pytest.mark.unit
def test_json_store_ttl_cache_serves_snapshot_and_invalidates_on_save(tmp_path):
    """TTL cache contract:

    1. First read populates the cache and returns an immutable snapshot.
    2. A direct mutation of ``store.state`` (simulating an out-of-band change)
       is NOT visible on the next read because the cache is still hot.
    3. Calling ``store.save()`` flushes the cache; the subsequent read returns
       the freshly mutated data from ``self.state``.
    """
    db_path = tmp_path / "runtime-db.json"
    store = JsonStore(db_path)

    # 1. First read — populates cache
    first_read = store.list_collection("syntax_library")
    initial_count = len(first_read)
    assert initial_count > 0, "seed data expected in syntax_library"

    # 2. Directly mutate store.state WITHOUT calling save() — cache must
    #    shield callers from this unsaved, in-flight change.
    store.state["syntax_library"].append(
        {"id": "syn-test-probe", "action_verb": "TestProbe", "code_most": "TP", "parameter_range": "N/A", "tmu_value": 0}
    )
    cached_read = store.list_collection("syntax_library")
    assert len(cached_read) == initial_count, (
        "Cache should return the old snapshot; unsaved state mutation must not be visible"
    )

    # 3. save() must invalidate the cache — next read sees the new item
    store.save()
    fresh_read = store.list_collection("syntax_library")
    assert len(fresh_read) == initial_count + 1, (
        "After save() the cache is cleared; the new item must be visible"
    )
    assert any(item["id"] == "syn-test-probe" for item in fresh_read)


@pytest.mark.unit
def test_json_store_ttl_cache_does_not_affect_non_cacheable_collections(tmp_path):
    """Operational collections (sop_versions, simulation_results, …) must always
    return a live reference so that callers can mutate them directly."""
    db_path = tmp_path / "runtime-db.json"
    store = JsonStore(db_path)

    live_ref = store.list_collection("simulation_results")
    live_ref.append({"id": "sim-probe", "project_id": "x"})

    # Without calling save(), the mutation must be immediately visible
    second_read = store.list_collection("simulation_results")
    assert any(item["id"] == "sim-probe" for item in second_read), (
        "Non-cacheable collections must return a live reference — direct mutation must be visible immediately"
    )
