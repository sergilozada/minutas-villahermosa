from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"
DATA_DIR = ROOT_DIR / "data"
CONFIG_DIR = ROOT_DIR / "config"
TEMPLATE_DIR = ROOT_DIR / "templates"

DATABASE_PATH = Path(os.getenv("VH_DATABASE_PATH", DATA_DIR / "villahermosa.db"))
DATABASE_URL = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()
TEMPLATE_PATH = Path(
    os.getenv("VH_TEMPLATE_PATH", TEMPLATE_DIR / "minuta_financiado_template.docx")
)
SCHEMA_PATH = CONFIG_DIR / "minute_schema.json"

IS_VERCEL = bool(os.getenv("VERCEL"))
IS_CLOUD_RUN = bool(os.getenv("K_SERVICE"))
IS_RENDER = os.getenv("RENDER", "").lower() == "true"
IS_HOSTED = IS_VERCEL or IS_CLOUD_RUN or IS_RENDER
HOST = os.getenv("VH_HOST", "0.0.0.0" if IS_HOSTED else "127.0.0.1")
PORT = int(os.getenv("PORT") or os.getenv("VH_PORT", "8000"))
SESSION_TTL_SECONDS = int(os.getenv("VH_SESSION_TTL_SECONDS", str(60 * 60 * 10)))
COOKIE_SECURE = os.getenv(
    "VH_COOKIE_SECURE", "1" if IS_HOSTED else "0"
) == "1"
SESSION_COOKIE = "__Host-vh_session" if COOKIE_SECURE else "vh_session"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_MINUTES_PER_USER = int(os.getenv("VH_MAX_MINUTES_PER_USER", "5000"))

ADMIN_EMAIL = os.getenv("VH_ADMIN_EMAIL", "admin@villahermosa.com").lower()
ASESOR_EMAIL = os.getenv("VH_ASESOR_EMAIL", "asesor@villahermosa.com").lower()


def _initial_password(variable: str) -> str | None:
    value = os.getenv(variable)
    if value is None or not value.strip():
        return None
    if len(value) < 16:
        raise RuntimeError(f"{variable} debe tener al menos 16 caracteres.")
    return value


ADMIN_PASSWORD = _initial_password("VH_ADMIN_PASSWORD")
ASESOR_PASSWORD = _initial_password("VH_ASESOR_PASSWORD")


def ensure_runtime_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
