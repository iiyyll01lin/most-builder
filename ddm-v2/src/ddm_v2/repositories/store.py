from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ddm_v2.schemas import AuditAction
from ddm_v2.seeds import build_default_state


def _looks_like_json(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        head = path.read_text(encoding="utf-8", errors="ignore").lstrip()[:1]
    except OSError:
        return False
    return head in {"{", "["}


class SQLiteStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.state = build_default_state()
        self.load()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        try:
            connection.row_factory = sqlite3.Row
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS collection_meta (
                collection_name TEXT PRIMARY KEY,
                kind TEXT NOT NULL CHECK(kind IN ('list', 'dict'))
            );
            CREATE TABLE IF NOT EXISTS list_entries (
                collection_name TEXT NOT NULL,
                row_order INTEGER NOT NULL,
                item_id TEXT,
                payload TEXT NOT NULL,
                PRIMARY KEY (collection_name, row_order)
            );
            CREATE INDEX IF NOT EXISTS idx_list_entries_collection_id
            ON list_entries(collection_name, item_id);
            CREATE TABLE IF NOT EXISTS dict_entries (
                collection_name TEXT NOT NULL,
                entry_key TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (collection_name, entry_key)
            );
            """
        )

    def _database_has_state(self, connection: sqlite3.Connection) -> bool:
        row = connection.execute("SELECT COUNT(*) AS count FROM collection_meta").fetchone()
        return bool(row and row["count"])

    def _legacy_json_candidates(self, include_self: bool = True) -> list[Path]:
        candidates: list[Path] = []
        if include_self and _looks_like_json(self.db_path):
            candidates.append(self.db_path)
        if self.db_path.suffix != ".json":
            sibling = self.db_path.with_suffix(".json")
            if sibling != self.db_path and _looks_like_json(sibling):
                candidates.append(sibling)
        return candidates

    def _backup_legacy_json(self, path: Path) -> None:
        if path == self.db_path:
            backup_path = path.with_name(f"{path.stem}.legacy-json{path.suffix}")
        else:
            backup_path = path.with_name(f"{path.stem}.legacy-json{path.suffix}")
        path.replace(backup_path)

    def _merge_with_defaults(self, payload: dict[str, Any]) -> dict[str, Any]:
        merged = build_default_state()
        for key, value in payload.items():
            merged[key] = value
        return merged

    def _import_legacy_json(self) -> bool:
        for candidate in self._legacy_json_candidates():
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            self.state = self._merge_with_defaults(payload)
            self.save()
            self._backup_legacy_json(candidate)
            return True
        return False

    def _read_state(self, connection: sqlite3.Connection) -> dict[str, Any]:
        state = build_default_state()
        rows = connection.execute("SELECT collection_name, kind FROM collection_meta ORDER BY collection_name").fetchall()
        for row in rows:
            collection_name = row["collection_name"]
            if row["kind"] == "list":
                entries = connection.execute(
                    "SELECT payload FROM list_entries WHERE collection_name = ? ORDER BY row_order",
                    (collection_name,),
                ).fetchall()
                state[collection_name] = [json.loads(entry["payload"]) for entry in entries]
            else:
                entries = connection.execute(
                    "SELECT entry_key, payload FROM dict_entries WHERE collection_name = ? ORDER BY entry_key",
                    (collection_name,),
                ).fetchall()
                state[collection_name] = {entry["entry_key"]: json.loads(entry["payload"]) for entry in entries}
        return state

    def _write_state(self, connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM list_entries")
        connection.execute("DELETE FROM dict_entries")
        connection.execute("DELETE FROM collection_meta")

        for collection_name, value in self.state.items():
            if isinstance(value, list):
                connection.execute(
                    "INSERT INTO collection_meta(collection_name, kind) VALUES(?, 'list')",
                    (collection_name,),
                )
                for row_order, item in enumerate(value):
                    connection.execute(
                        "INSERT INTO list_entries(collection_name, row_order, item_id, payload) VALUES(?, ?, ?, ?)",
                        (
                            collection_name,
                            row_order,
                            item.get("id") if isinstance(item, dict) else None,
                            json.dumps(item, ensure_ascii=False),
                        ),
                    )
            elif isinstance(value, dict):
                connection.execute(
                    "INSERT INTO collection_meta(collection_name, kind) VALUES(?, 'dict')",
                    (collection_name,),
                )
                for entry_key, payload in value.items():
                    connection.execute(
                        "INSERT INTO dict_entries(collection_name, entry_key, payload) VALUES(?, ?, ?)",
                        (collection_name, str(entry_key), json.dumps(payload, ensure_ascii=False)),
                    )

    def load(self) -> None:
        if _looks_like_json(self.db_path) and self._import_legacy_json():
            return
        with self._connect() as connection:
            self._initialize_schema(connection)
            if self._database_has_state(connection):
                self.state = self._read_state(connection)
                return
        if self._import_legacy_json():
            return
        with self._connect() as connection:
            self._initialize_schema(connection)
            self.state = build_default_state()
            self._write_state(connection)

    def save(self) -> None:
        with self._connect() as connection:
            self._initialize_schema(connection)
            self._write_state(connection)

    def reset(self) -> None:
        self.state = build_default_state()
        self.save()

    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:8]}"

    def list_collection(self, key: str) -> list[dict[str, Any]]:
        value = self.state.setdefault(key, [])
        if not isinstance(value, list):
            raise TypeError(f"Collection {key} is not a list")
        return value

    def dict_collection(self, key: str) -> dict[str, Any]:
        value = self.state.setdefault(key, {})
        if not isinstance(value, dict):
            raise TypeError(f"Collection {key} is not a dict")
        return value

    def find_by_id(self, key: str, item_id: str) -> dict[str, Any] | None:
        for item in self.list_collection(key):
            if item.get("id") == item_id:
                return item
        return None

    def upsert_collection_item(self, key: str, item: dict[str, Any]) -> dict[str, Any]:
        collection = self.list_collection(key)
        for index, existing in enumerate(collection):
            if existing.get("id") == item.get("id"):
                collection[index] = item
                self.save()
                return item
        collection.append(item)
        self.save()
        return item

    def delete_collection_item(self, key: str, item_id: str) -> dict[str, Any] | None:
        collection = self.list_collection(key)
        for index, existing in enumerate(collection):
            if existing.get("id") == item_id:
                removed = collection.pop(index)
                self.save()
                return removed
        return None

    def audit(
        self,
        user: dict[str, Any],
        action: AuditAction,
        entity_type: str,
        entity_id: str,
        description: str,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "id": self.new_id("audit"),
            "timestamp": datetime.now(UTC).isoformat(),
            "user_id": user["id"],
            "user_name": user["name"],
            "action": action.value,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "description": description,
            "old_value": deepcopy(old_value),
            "new_value": deepcopy(new_value),
        }
        self.list_collection("audit_logs").append(entry)
        self.save()
        return entry


JsonStore = SQLiteStore
