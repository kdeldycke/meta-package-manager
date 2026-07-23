# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

"""Guard the CI test matrix against drifting away from the project metadata.

`repomatic` generates the GitHub Actions test matrix from a hard-coded set of
Python versions, independently of the project's `requires-python`. Nothing
forces the two to agree, so a `requires-python` bump that forgets the matrix,
or a `repomatic` release that shifts its floor, would silently leave the
declared floor untested. These tests turn that drift into a failing check, as
recommended by [repomatic's test-matrix guide](https://kdeldycke.github.io/repomatic/test-matrix.html).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from extra_platforms.pytest import skip_guix_build

from .conftest import tomllib

PROJECT_ROOT = Path(__file__).parent.parent

PYTHON_CLASSIFIER_PREFIX = "Programming Language :: Python :: "
"""Prefix of the trove classifiers enumerating supported Python versions."""


def _load_pyproject() -> dict:
    """Parse the project's `pyproject.toml` into a dictionary."""
    path = PROJECT_ROOT.joinpath("pyproject.toml")
    content = path.read_text(encoding="UTF-8")
    return tomllib.loads(content)  # type: ignore[no-any-return]


def _major_minor(version: str) -> tuple[int, int]:
    """Extract the `(major, minor)` tuple from a Python version string.

    Tolerates a non-numeric suffix like the `t` of free-threaded `3.14t`.
    """
    match = re.match(r"(\d+)\.(\d+)", version)
    assert match, f"Cannot parse Python version {version!r}."
    return int(match.group(1)), int(match.group(2))


def _python_floor_of(matrix: dict) -> tuple[int, int]:
    """Return the lowest `(major, minor)` Python version a matrix tests."""
    return min(_major_minor(version) for version in matrix["python-version"])


def _requires_python_floor(pyproject: dict) -> tuple[int, int]:
    """Return the `(major, minor)` lower bound of `requires-python`."""
    requirement = pyproject["project"]["requires-python"]
    match = re.search(r">=\s*(\d+)\.(\d+)", requirement)
    assert match, f"No >= lower bound in requires-python {requirement!r}."
    return int(match.group(1)), int(match.group(2))


def _pinned_repomatic() -> str:
    """Read the `repomatic` version pinned by the test-matrix workflow.

    Keeps this guard in lock-step with the exact `repomatic` release CI runs
    to generate the matrix, rather than resolving a possibly-different latest.
    """
    workflow = PROJECT_ROOT.joinpath(".github", "workflows", "tests.yaml")
    match = re.search(
        r"repomatic==(\d+\.\d+\.\d+)", workflow.read_text(encoding="UTF-8")
    )
    assert match, "No pinned repomatic version found in tests.yaml."
    return match.group(1)


def test_requires_python_floor_in_classifiers():
    """The `requires-python` floor equals the lowest declared classifier.

    A network-free companion to the matrix check below: it catches a
    `requires-python` bump that forgets to update the trove classifiers, or
    the reverse, the most common metadata drift.
    """
    pyproject = _load_pyproject()
    classifier_versions = sorted(
        _major_minor(match.group(1))
        for classifier in pyproject["project"]["classifiers"]
        if (
            match := re.fullmatch(
                re.escape(PYTHON_CLASSIFIER_PREFIX) + r"(\d+\.\d+)", classifier
            )
        )
    )
    assert classifier_versions, "No versioned Python classifiers found."
    assert classifier_versions[0] == _requires_python_floor(pyproject)


@skip_guix_build
def test_matrix_python_floor_matches_requires_python():
    """The generated matrix's lowest Python equals the `requires-python` floor.

    Drives the real `repomatic` CLI, the same one CI invokes, so the assertion
    reflects what is actually tested rather than a re-derivation. Skips, instead
    of failing, when the tool cannot be fetched (offline or sandboxed builds).
    """
    uvx = shutil.which("uvx")
    if uvx is None:
        pytest.skip("uvx is required to generate the repomatic test matrix.")
    try:
        result = subprocess.run(
            (
                uvx,
                "--no-progress",
                f"repomatic=={_pinned_repomatic()}",
                "metadata",
                "--format",
                "json",
                "test_matrix",
                "test_matrix_pr",
            ),
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="UTF-8",
            timeout=300,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        pytest.skip(f"Could not run repomatic to read the matrix: {error}")

    payload = json.loads(result.stdout)
    floor = _requires_python_floor(_load_pyproject())
    for matrix_id in ("test_matrix", "test_matrix_pr"):
        tested_floor = _python_floor_of(payload[matrix_id])
        assert tested_floor == floor, (
            f"{matrix_id} floor {tested_floor} differs from requires-python {floor}."
        )
