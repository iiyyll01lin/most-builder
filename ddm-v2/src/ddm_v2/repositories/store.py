from __future__ import annotations

import fcntl
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ddm_v2.schemas import AuditAction
from ddm_v2.seeds import build_default_state


class JsonStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.lock_path = db_path.with_suffix(f"{db_path.suffix}.lock")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.state = build_default_state()
        self.load()

    @contextmanager
    def _exclusive_lock(self):
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _write_state_locked(self) -> None:
        payload = json.dumps(self.state, ensure_ascii=False, indent=2)
        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, dir=self.db_path.parent, encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                temp_path = handle.name
            os.replace(temp_path, self.db_path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def _recover_from_corruption(self) -> None:
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        corrupt_path = self.db_path.with_name(f"{self.db_path.stem}.corrupt-{timestamp}{self.db_path.suffix}")
        shutil.move(self.db_path, corrupt_path)
        self.state = build_default_state()
        self._write_state_locked()

    def load(self) -> None:
        with self._exclusive_lock():
            if not self.db_path.exists():
                self._write_state_locked()
                return
            try:
                payload = json.loads(self.db_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._recover_from_corruption()
                return
            self.state = payload

    def save(self) -> None:
        with self._exclusive_lock():
            self._write_state_locked()

    def reset(self) -> None:
        self.state = build_default_state()
        self.save()

    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:8]}"

    def list_collection(self, key: str) -> list[dict[str, Any]]:
        return self.state.setdefault(key, [])

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
