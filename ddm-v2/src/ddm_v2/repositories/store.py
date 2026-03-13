from __future__ import annotations

import json
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
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.state = build_default_state()
        self.load()

    def load(self) -> None:
        if not self.db_path.exists():
            self.save()
            return
        payload = json.loads(self.db_path.read_text(encoding="utf-8"))
        self.state = payload

    def save(self) -> None:
        self.db_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

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
