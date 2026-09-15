"""Fail CI when edited dependency inputs no longer match the committed locks."""
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def requirements(path):
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("-r "):
            yield from requirements(path.parent / line[3:].strip())
        elif line and not line.startswith(("#", "--")):
            yield Requirement(line.rstrip("\\").strip())


@pytest.mark.parametrize("source,lock", [
    ("requirements-ci.in", "requirements-ci.lock"),
    ("requirements-tooth-marking-cpu.txt", "requirements-tooth-marking-cpu.lock"),
])
def test_lock_satisfies_dependency_inputs(source, lock):
    locked = {
        canonicalize_name(req.name): req
        for req in requirements(ROOT / "app" / lock)
    }
    for req in requirements(ROOT / "app" / source):
        pin = locked[canonicalize_name(req.name)]
        specs = list(pin.specifier)
        assert len(specs) == 1 and specs[0].operator == "==", str(pin)
        assert req.specifier.contains(specs[0].version), f"Regenerate {lock}: {req} conflicts with {pin}"
