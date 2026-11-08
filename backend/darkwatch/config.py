"""Every environment variable DarkWatch reads, in one place.

Values are read on each call rather than frozen at import, so tests can
monkeypatch the environment and a Databricks App picks up injected secrets.
A ``.env`` file at the repo root (or the working directory) is loaded once if
python-dotenv is installed. Real environment variables always win.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_PORT = 8741
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_FISH_MODEL = "s2.1-pro-free"
# Aria, an English female voice from the public Fish Audio library.
DEFAULT_FISH_VOICE_ID = "933563129e564b19a115bedd57b7406a"
DEFAULT_GFW_DATASET = "public-global-sar-presence:latest"


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in (Path(__file__).resolve().parents[2] / ".env", Path.cwd() / ".env"):
        if candidate.is_file():
            load_dotenv(candidate, override=False)


_load_dotenv()


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def port() -> int:
    return int(_get("DATABRICKS_APP_PORT") or _get("PORT") or DEFAULT_PORT)


def darkwatch_root() -> str:
    return _get("DARKWATCH_ROOT")


def cesium_ion_token() -> str:
    return _get("CESIUM_ION_TOKEN")


def gemini_api_key() -> str:
    return _get("GEMINI_API_KEY")


def gemini_model() -> str:
    return _get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)


def fish_audio_api_key() -> str:
    return _get("FISH_AUDIO_API_KEY")


def fish_audio_voice_id() -> str:
    return _get("FISH_AUDIO_VOICE_ID", DEFAULT_FISH_VOICE_ID)


def fish_audio_voice_id_set() -> bool:
    return bool(_get("FISH_AUDIO_VOICE_ID"))


def fish_audio_model() -> str:
    return _get("FISH_AUDIO_MODEL", DEFAULT_FISH_MODEL)


def tiger_database_url() -> str:
    return _get("TIGER_DATABASE_URL")


def gfw_api_token() -> str:
    return _get("GFW_API_TOKEN")


def gfw_dataset() -> str:
    return _get("GFW_DATASET", DEFAULT_GFW_DATASET)


def wdpa_api_token() -> str:
    return _get("WDPA_API_TOKEN")


def xview3_weights() -> str:
    return _get("XVIEW3_WEIGHTS")


def xview3_repo() -> str:
    return _get("XVIEW3_REPO")


def darkwatch_catalog() -> str:
    return _get("DARKWATCH_CATALOG", "workspace")


def darkwatch_schema() -> str:
    return _get("DARKWATCH_SCHEMA", "darkwatch")


def databricks_warehouse_id() -> str:
    return _get("DATABRICKS_WAREHOUSE_ID")


def databricks_host() -> str:
    """Injected by the Databricks Apps platform. The SDK reads its own auth vars."""
    return _get("DATABRICKS_HOST")


def ais_zip() -> str:
    """Optional local path to an already-downloaded Danish AIS day zip."""
    return _get("AIS_ZIP")


def aisstream_api_key() -> str:
    """AISStream WebSocket key. Never log or return this value."""
    return _get("AISSTREAM_API_KEY")


def ais_global_refresh() -> bool:
    return _get("AIS_GLOBAL_REFRESH", "0") == "1"


def ais_global_interval_min() -> int:
    return int(_get("AIS_GLOBAL_INTERVAL_MIN", "20"))


def ais_global_listen_s() -> int:
    return int(_get("AIS_GLOBAL_LISTEN_S", "180"))


def ais_global_max_ships() -> int:
    return int(_get("AIS_GLOBAL_MAX_SHIPS", "5000"))


def ais_global_max_age_h() -> float:
    return float(_get("AIS_GLOBAL_MAX_AGE_H", "12"))


def integrations() -> dict[str, bool]:
    """Which optional services are configured. Booleans only, never values."""
    return {
        "gemini": bool(gemini_api_key()),
        "fish_audio": bool(fish_audio_api_key()),
        "tiger": bool(tiger_database_url()),
        "gfw": bool(gfw_api_token()),
        "cesium_ion": bool(cesium_ion_token()),
        "xview3": bool(xview3_weights() and xview3_repo()),
        "sql_warehouse": bool(databricks_warehouse_id() and databricks_host()),
        "wdpa": bool(wdpa_api_token()),
        "aisstream": bool(aisstream_api_key()),
    }


def configure_gdal() -> None:
    """GDAL settings for windowed COG reads over HTTP. Only sets unset keys."""
    os.environ.setdefault("CPL_VSIL_CURL_USE_HEAD", "NO")
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    os.environ.setdefault("GDAL_HTTP_TIMEOUT", "120")
    os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "3")
    os.environ.setdefault("VSI_CACHE", "TRUE")
