"""Locate the repository root and the folders under it.

The root is the directory holding the empty ``.darkwatch-root`` marker and
``data/``. Serverless ``spark_python_task`` does not set ``__file__`` on the
job script, so the refresh job passes ``argv0`` and ``--repo-root``.

Search order: ``DARKWATCH_ROOT``, the explicit ``extra`` (``--repo-root``),
``argv0`` and its parents, ``cwd`` and its parents, then this package's own
location as a last resort.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from darkwatch import config

MARKER = ".darkwatch-root"


def _is_root(path: Path) -> bool:
    return (path / MARKER).is_file() and (path / "data").is_dir()


def _with_parents(path: Path) -> list[Path]:
    return [path, *path.parents]


def repo_root(argv0: str | None = None, cwd: Path | None = None, extra: str | None = None) -> Path:
    here = cwd or Path.cwd()
    candidates: list[Path] = []
    env_root = config.darkwatch_root()
    if env_root:
        candidates.append(Path(env_root))
    if extra:
        candidates.append(Path(extra))
    if argv0:
        script = Path(argv0)
        if not script.is_absolute():
            script = here / script
        candidates.extend(_with_parents(script.resolve().parent))
    candidates.extend(_with_parents(here))
    candidates.append(here / "files")
    candidates.extend(_with_parents(Path(__file__).resolve().parent))
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if _is_root(resolved):
            return resolved
    raise FileNotFoundError(
        f"Could not find the DarkWatch repo root (expected {MARKER} and data/). "
        f"DARKWATCH_ROOT={env_root!r} argv0={argv0!r} cwd={here} extra={extra!r}"
    )


@lru_cache(maxsize=1)
def root() -> Path:
    return repo_root()


def data_dir() -> Path:
    return root() / "data"


def demo_dir() -> Path:
    return data_dir() / "demo"


def cache_dir() -> Path:
    return data_dir() / "cache"


def raw_dir() -> Path:
    return data_dir() / "raw"


def snapshot_dir() -> Path:
    return data_dir() / "snapshot"


def frontend_dir() -> Path:
    return root() / "frontend"


def models_dir() -> Path:
    return root() / "backend" / "models"


def evidence_dir() -> Path:
    return demo_dir() / "evidence"


def ais_global_cache() -> Path:
    return cache_dir() / "ais_global.json"


def ais_global_seed() -> Path:
    return demo_dir() / "ais_global_seed.json"
