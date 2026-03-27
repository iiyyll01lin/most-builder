from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _parse_csv(value: str | None, fallback: list[str]) -> list[str]:
    if not value:
        return fallback
    parsed = [item.strip() for item in value.split(",") if item.strip()]
    return parsed or fallback


def _parse_bool(value: str | None, fallback: bool) -> bool:
    if value is None:
        return fallback
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_path(raw: str | None, default: Path, root_dir: Path) -> Path:
    if not raw:
        return default
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (root_dir / candidate).resolve()
    return candidate


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    data_dir: Path
    static_dir: Path
    db_path: Path
    app_name: str
    app_version: str
    secret_key: str
    access_token_expire_hours: int
    tmu_factor: float
    cors_allow_origins: list[str]
    cors_allow_credentials: bool
    cors_allow_methods: list[str]
    cors_allow_headers: list[str]
    # ── Phase 4: PostgreSQL connection URL ───────────────────────────────────
    # Scheme must be ``postgresql+asyncpg://`` for production or
    # ``sqlite+aiosqlite://`` for lightweight test runs.
    database_url: str
    # ── Phase 5: Vision Engine ───────────────────────────────────────────────
    # Directory where uploaded workstation videos are persisted on disk.
    # Defaults to ``<data_dir>/videos/``.  Must be writable by the process.
    video_upload_dir: Path    # ── Phase 6: Celery / Redis task queue ─────────────────────────────────────
    celery_broker_url: str
    celery_result_backend: str
    # ── Phase 7: MQTT IoT telemetry broker ──────────────────────────────────
    mqtt_broker_host: str
    mqtt_broker_port: int

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root_dir = Path(os.getenv("DDM_ROOT_DIR", Path(__file__).resolve().parents[2])).resolve()
    data_dir = _resolve_path(os.getenv("DDM_DATA_DIR"), root_dir / "data", root_dir)
    static_dir = _resolve_path(os.getenv("DDM_STATIC_DIR"), root_dir / "src" / "ddm_v2" / "static", root_dir)
    db_path = _resolve_path(os.getenv("DDM_DB_PATH"), data_dir / "runtime-db.json", root_dir)
    video_upload_dir = _resolve_path(
        os.getenv("DDM_VIDEO_UPLOAD_DIR"), data_dir / "videos", root_dir
    )
    return Settings(
        root_dir=root_dir,
        data_dir=data_dir,
        static_dir=static_dir,
        db_path=db_path,
        video_upload_dir=video_upload_dir,
        app_name=os.getenv("DDM_APP_NAME", "DDM v2"),
        app_version=os.getenv("DDM_APP_VERSION", "2.0.0-rc1"),
        secret_key=os.getenv("DDM_SECRET_KEY", "ddm-v2-release-candidate-202603-rc1-secure-key"),
        access_token_expire_hours=int(os.getenv("DDM_ACCESS_TOKEN_EXPIRE_HOURS", "8")),
        tmu_factor=float(os.getenv("DDM_TMU_FACTOR", "0.036")),
        cors_allow_origins=_parse_csv(os.getenv("DDM_CORS_ALLOW_ORIGINS"), ["*"]),
        cors_allow_credentials=_parse_bool(os.getenv("DDM_CORS_ALLOW_CREDENTIALS"), True),
        cors_allow_methods=_parse_csv(os.getenv("DDM_CORS_ALLOW_METHODS"), ["*"]),
        cors_allow_headers=_parse_csv(os.getenv("DDM_CORS_ALLOW_HEADERS"), ["*"]),
        database_url=os.getenv(
            "DDM_DATABASE_URL",
            "postgresql+asyncpg://ddm:ddm_secret@localhost:5432/ddm",
        ),
        celery_broker_url=os.getenv("DDM_CELERY_BROKER_URL", "redis://localhost:6379/0"),
        celery_result_backend=os.getenv("DDM_CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
        mqtt_broker_host=os.getenv("DDM_MQTT_BROKER_HOST", "localhost"),
        mqtt_broker_port=int(os.getenv("DDM_MQTT_BROKER_PORT", "1883")),
    )


# Convenience alias so other modules can do: from ddm_v2.settings import VIDEO_UPLOAD_DIR
VIDEO_UPLOAD_DIR = get_settings().video_upload_dir


ROOT_DIR = get_settings().root_dir
DATA_DIR = get_settings().data_dir
STATIC_DIR = get_settings().static_dir
DB_PATH = get_settings().db_path

SECRET_KEY = get_settings().secret_key
ACCESS_TOKEN_EXPIRE_HOURS = get_settings().access_token_expire_hours
TMU_FACTOR = get_settings().tmu_factor

APP_NAME = get_settings().app_name
APP_VERSION = get_settings().app_version
