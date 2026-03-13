from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
STATIC_DIR = ROOT_DIR / "src" / "ddm_v2" / "static"
DB_PATH = DATA_DIR / "runtime-db.json"

SECRET_KEY = "ddm-v2-release-candidate-202603-rc1-secure-key"
ACCESS_TOKEN_EXPIRE_HOURS = 8
TMU_FACTOR = 0.036

APP_NAME = "DDM v2"
APP_VERSION = "2.0.0-rc1"
