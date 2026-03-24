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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root_dir = Path(os.getenv("DDM_ROOT_DIR", Path(__file__).resolve().parents[2])).resolve()
    data_dir = _resolve_path(os.getenv("DDM_DATA_DIR"), root_dir / "data", root_dir)
    static_dir = _resolve_path(os.getenv("DDM_STATIC_DIR"), root_dir / "src" / "ddm_v2" / "static", root_dir)
    db_path = _resolve_path(os.getenv("DDM_DB_PATH"), data_dir / "runtime-db.json", root_dir)
    return Settings(
        root_dir=root_dir,
        data_dir=data_dir,
        static_dir=static_dir,
        db_path=db_path,
        app_name=os.getenv("DDM_APP_NAME", "DDM v2"),
        app_version=os.getenv("DDM_APP_VERSION", "2.0.0-rc1"),
        secret_key=os.getenv("DDM_SECRET_KEY", "ddm-v2-release-candidate-202603-rc1-secure-key"),
        access_token_expire_hours=int(os.getenv("DDM_ACCESS_TOKEN_EXPIRE_HOURS", "8")),
        tmu_factor=float(os.getenv("DDM_TMU_FACTOR", "0.036")),
        cors_allow_origins=_parse_csv(os.getenv("DDM_CORS_ALLOW_ORIGINS"), ["*"]),
        cors_allow_credentials=_parse_bool(os.getenv("DDM_CORS_ALLOW_CREDENTIALS"), True),
        cors_allow_methods=_parse_csv(os.getenv("DDM_CORS_ALLOW_METHODS"), ["*"]),
        cors_allow_headers=_parse_csv(os.getenv("DDM_CORS_ALLOW_HEADERS"), ["*"]),
    )


ROOT_DIR = get_settings().root_dir
DATA_DIR = get_settings().data_dir
STATIC_DIR = get_settings().static_dir
DB_PATH = get_settings().db_path

SECRET_KEY = get_settings().secret_key
ACCESS_TOKEN_EXPIRE_HOURS = get_settings().access_token_expire_hours
TMU_FACTOR = get_settings().tmu_factor

APP_NAME = get_settings().app_name
APP_VERSION = get_settings().app_version
