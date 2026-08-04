"""Packaging smoke test: build a real wheel and assert the installed
artifact would actually work — the shipped profile is inside, and the
runtime dependency set matches what the code imports.

Exists because the source tree lied once: tests passed while the built
wheel contained no nist_ai_rmf.yaml and declared no pyyaml (G-3 review
finding P1).
"""
from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def wheel(tmp_path_factory):
    out = tmp_path_factory.mktemp("wheel")
    # Default (isolated) build on purpose: pip installs build-system.requires
    # into a throwaway env, exactly as a stranger's `pip install` would.
    # --no-build-isolation broke on CI's Python 3.12, where setuptools is no
    # longer bundled in the test environment.
    build = subprocess.run(
        [
            sys.executable, "-m", "pip", "wheel", str(REPO_ROOT),
            "--no-deps", "-w", str(out), "-q",
        ],
        capture_output=True,
        text=True,
        check=False,  # asserted below with stderr in the failure message
    )
    assert build.returncode == 0, f"wheel build failed:\n{build.stderr}"
    wheels = list(out.glob("decision_governor-*.whl"))
    assert len(wheels) == 1, f"expected one wheel, found {wheels}"
    return wheels[0]


def test_wheel_ships_the_compliance_profile(wheel):
    names = zipfile.ZipFile(wheel).namelist()
    assert "decision_governor/checks/profiles/nist_ai_rmf.yaml" in names


def test_wheel_declares_the_runtime_deps_the_code_imports(wheel):
    z = zipfile.ZipFile(wheel)
    metadata_name = next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
    requires = [
        line for line in z.read(metadata_name).decode().splitlines()
        if line.startswith("Requires-Dist")
    ]
    joined = "\n".join(requires).lower()
    # compliance.py imports yaml on the base install.
    assert "pyyaml" in joined
    # The PinNotFrozen/ModelDepsMissing messages point at [llm]; the extra
    # must actually install the model stack. METADATA normalizes names to
    # hyphens (PEP 503), so compare in normalized form.
    normalized = [line.replace("_", "-") for line in requires]
    for dep in ("huggingface-hub", "sentence-transformers", "transformers",
                "openai", "anthropic"):
        assert any(dep in line and 'extra == "llm"' in line for line in normalized), (
            f"{dep} missing from the [llm] extra:\n" + "\n".join(requires)
        )
    # The G-7 middleware's extra ships FastAPI.
    assert any(
        "fastapi" in line and 'extra == "fastapi"' in line for line in normalized
    )
