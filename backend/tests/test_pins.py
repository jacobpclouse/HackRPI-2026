"""constraints.txt is the only place versions live. The job YAML must agree."""

import re
from pathlib import Path

import yaml

from nimbus import paths

BACKEND = paths.root() / "backend"
JOB_YAML = paths.root() / "databricks" / "resources" / "nimbus_refresh.job.yml"


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.split("[", 1)[0]).strip().lower()


def _constraints() -> dict[str, str]:
    pins = {}
    for line in (BACKEND / "constraints.txt").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, _, version = line.partition("==")
        assert version, f"constraints.txt line is not an exact pin: {line!r}"
        key = _norm(name)
        assert key not in pins, f"{key} is pinned twice in constraints.txt"
        pins[key] = version.strip()
    return pins


def _names(path: Path) -> set[str]:
    names = set()
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        assert "=" not in line and "<" not in line and ">" not in line, (
            f"{path.name} must list names only; put the version in constraints.txt: {line!r}"
        )
        names.add(_norm(line))
    return names


def _job_dependencies() -> dict[str, str]:
    job = yaml.safe_load(JOB_YAML.read_text())
    envs = job["resources"]["jobs"]["nimbus_refresh"]["environments"]
    deps = {}
    for env in envs:
        for item in env["spec"]["dependencies"]:
            name, _, version = item.partition("==")
            deps[_norm(name)] = version.strip()
    return deps


def test_requirements_files_use_the_constraints():
    for name in ("requirements.txt", "requirements-job.txt", "requirements-dev.txt"):
        text = (BACKEND / name).read_text()
        assert "-c constraints.txt" in text, f"{name} must start with -c constraints.txt"


def test_every_required_package_is_pinned():
    pins = _constraints()
    for name in ("requirements.txt", "requirements-job.txt", "requirements-dev.txt"):
        missing = _names(BACKEND / name) - set(pins)
        assert not missing, f"{name} lists packages with no pin: {sorted(missing)}"


def test_job_yaml_matches_constraints():
    pins = _constraints()
    deps = _job_dependencies()
    assert set(deps) == _names(BACKEND / "requirements-job.txt"), (
        "job YAML dependencies and requirements-job.txt list different packages"
    )
    wrong = {name: (version, pins.get(name)) for name, version in deps.items() if pins.get(name) != version}
    assert not wrong, f"job YAML pins disagree with constraints.txt (yaml, constraints): {wrong}"
