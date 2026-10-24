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
"""Pip-specific tests for bundled-app detection, interpreter discovery and metadata."""

from __future__ import annotations

import email
import importlib.metadata
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from meta_package_manager.execution import CLIExecutor
from meta_package_manager.managers.pip import _PIP_PROBE_MARKER, Pip, _split_dep_spec
from meta_package_manager.package import (
    EMPTY_METADATA,
    Dependency,
    Originator,
    PackageMetadata,
    Supplier,
)

PATCH_DIST = "meta_package_manager.managers.pip.importlib.metadata.distribution"
PATCH_PREFIX = "meta_package_manager.managers.pip.sys.prefix"
PATCH_EXEC = "meta_package_manager.managers.pip.sys.executable"
PATCH_RUN = "meta_package_manager.managers.pip.subprocess.run"


def _installer_dist(installer):
    """Mock distribution exposing the given `INSTALLER` dist-info record."""
    dist = MagicMock()
    dist.read_text = lambda name: f"{installer}\n" if name == "INSTALLER" else None
    return dist


# --- Guard one: mpm's own distributor-managed bundle. ------------------------


def test_bundled_app_detected_under_cellar():
    """A `sys.prefix` under a Homebrew Cellar is conclusive on its own."""
    cellar = "/opt/homebrew/Cellar/meta-package-manager/7.0.0/libexec"
    with (
        patch(PATCH_PREFIX, cellar),
        # The INSTALLER lookup must not even be consulted when Cellar matches.
        patch(PATCH_DIST, side_effect=AssertionError("must not be called")),
    ):
        assert Pip._running_from_bundled_app() is True


@pytest.mark.parametrize(
    "prefix",
    ["/usr", "/home/kde/.venv", "/opt/homebrew", "/opt/homebrew/opt/python@3.14"],
)
def test_bundled_app_detected_by_brew_installer(prefix):
    """Outside Cellar, an `INSTALLER` of `brew` still flags the bundle."""
    with (
        patch(PATCH_PREFIX, prefix),
        patch(PATCH_DIST, return_value=_installer_dist("brew")),
    ):
        assert Pip._running_from_bundled_app() is True


def test_brew_installer_case_and_whitespace_insensitive():
    """The `INSTALLER` tag is matched case- and whitespace-insensitively."""
    with (
        patch(PATCH_PREFIX, "/usr"),
        patch(PATCH_DIST, return_value=_installer_dist("  Brew  ")),
    ):
        assert Pip._running_from_bundled_app() is True


@pytest.mark.parametrize("installer", ["pip", "uv", "poetry", ""])
def test_user_install_not_flagged(installer):
    """A user-managed install (pip/uv/...) outside Cellar is not a bundle."""
    with (
        patch(PATCH_PREFIX, "/home/kde/project/.venv"),
        patch(PATCH_DIST, return_value=_installer_dist(installer)),
    ):
        assert Pip._running_from_bundled_app() is False


def test_bundled_app_false_when_mpm_absent():
    """Running from source (`mpm` not installed) is not a bundle."""
    with (
        patch(PATCH_PREFIX, "/home/kde/project/.venv"),
        patch(PATCH_DIST, side_effect=importlib.metadata.PackageNotFoundError("x")),
    ):
        assert Pip._running_from_bundled_app() is False


# --- Guard two: PEP 668 externally-managed, non-virtualenv interpreters. ------


def _completed(stdout, returncode=0):
    """Mock a `subprocess.run` result carrying the given stdout and exit code."""
    result = MagicMock()
    result.stdout = stdout
    result.returncode = returncode
    return result


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [("1\n", True), ("1", True), ("0\n", False), ("", False), ("oops", False)],
)
def test_pip_install_blocked_parses_probe(stdout, expected):
    """The probe's `1`/`0` output maps to blocked/not-blocked."""
    candidate = Path("/usr/bin/python3")
    with patch(PATCH_RUN, return_value=_completed(stdout)) as run:
        assert Pip()._pip_install_blocked(candidate) is expected
    # The candidate interpreter runs the externally-managed one-liner. Compare
    # against the same str() conversion the probe applies, so the expectation
    # holds on Windows where the path stringifies with backslashes.
    command = run.call_args.args[0]
    assert command[0] == str(candidate)
    assert command[1] == "-c"
    assert "EXTERNALLY-MANAGED" in command[2]


@pytest.mark.parametrize(
    "error",
    [OSError("not a python"), subprocess.TimeoutExpired("python", 1)],
)
def test_pip_install_blocked_keeps_candidate_on_error(error):
    """A failed probe must not hide a candidate: default to not-blocked."""
    with patch(PATCH_RUN, side_effect=error):
        assert Pip()._pip_install_blocked(Path("/usr/bin/python3")) is False


# --- Discovery: both guards composed in search_all_cli. -----------------------


def _fake_base_search(self, cli_names, env=None):
    """Stand-in for the base `PATH` search yielding two fixed interpreters."""
    yield Path("/usr/bin/python3")
    yield Path("/usr/local/bin/python3")


def test_search_prepends_current_interpreter_for_user_install():
    """A normal install probes the running interpreter first."""
    fake_exec = "/home/kde/project/.venv/bin/python"
    with (
        patch(PATCH_EXEC, fake_exec),
        patch.object(Pip, "_running_from_bundled_app", return_value=False),
        patch.object(Pip, "_pip_install_blocked", return_value=False),
        patch.object(Pip, "_pip_module_missing", return_value=False),
        patch.object(CLIExecutor, "search_all_cli", _fake_base_search),
    ):
        found = list(Pip().search_all_cli(("python3", "python")))
    assert found == [
        Path(fake_exec),
        Path("/usr/bin/python3"),
        Path("/usr/local/bin/python3"),
    ]


def test_search_skips_bundled_interpreter():
    """A distributor bundle skips the running interpreter and falls back to PATH."""
    fake_exec = "/opt/homebrew/Cellar/meta-package-manager/7.0.0/libexec/bin/python"
    with (
        patch(PATCH_EXEC, fake_exec),
        patch.object(Pip, "_running_from_bundled_app", return_value=True),
        patch.object(Pip, "_pip_install_blocked", return_value=False),
        patch.object(Pip, "_pip_module_missing", return_value=False),
        patch.object(CLIExecutor, "search_all_cli", _fake_base_search),
    ):
        found = list(Pip().search_all_cli(("python3", "python")))
    assert Path(fake_exec) not in found
    assert found == [Path("/usr/bin/python3"), Path("/usr/local/bin/python3")]


def test_search_skips_pep668_blocked_candidate():
    """Externally-managed, non-virtualenv interpreters (PEP 668) are dropped."""
    fake_exec = "/home/kde/project/.venv/bin/python"
    blocked = Path("/usr/bin/python3")
    with (
        patch(PATCH_EXEC, fake_exec),
        patch.object(Pip, "_running_from_bundled_app", return_value=False),
        patch.object(
            Pip, "_pip_install_blocked", side_effect=lambda path: path == blocked
        ),
        patch.object(Pip, "_pip_module_missing", return_value=False),
        patch.object(CLIExecutor, "search_all_cli", _fake_base_search),
    ):
        found = list(Pip().search_all_cli(("python3", "python")))
    assert blocked not in found
    assert found == [Path(fake_exec), Path("/usr/local/bin/python3")]


def test_search_unavailable_when_all_candidates_blocked():
    """With every interpreter blocked, discovery yields nothing (pip unavailable)."""
    fake_exec = "/opt/homebrew/bin/python3"
    with (
        patch(PATCH_EXEC, fake_exec),
        patch.object(Pip, "_running_from_bundled_app", return_value=False),
        patch.object(Pip, "_pip_install_blocked", return_value=True),
        patch.object(Pip, "_pip_module_missing", return_value=False),
        patch.object(CLIExecutor, "search_all_cli", _fake_base_search),
    ):
        found = list(Pip().search_all_cli(("python3", "python")))
    assert found == []


# --- Guard three: interpreters carrying no pip to drive. ----------------------


@pytest.mark.parametrize(
    ("stdout", "returncode", "expected"),
    [
        pytest.param(f"{_PIP_PROBE_MARKER} 0\n", 0, True, id="no-pip"),
        pytest.param(f"{_PIP_PROBE_MARKER} 1\n", 0, False, id="pip-present"),
        # A candidate free to print before the probe answers still answers.
        pytest.param(
            f"warming up\n{_PIP_PROBE_MARKER} 1\n", 0, False, id="noisy-preamble"
        ),
        # Windows keeps `python3.exe` on PATH with no Python behind it: the advert
        # goes to stderr, stdout stays empty and it exits 9009. Measured on
        # Windows 11 24H2. Read as a Python, it shadowed every real interpreter.
        pytest.param("", 9009, True, id="app-execution-alias"),
        # Unexplained rather than refuted: it ran, said nothing we asked for, and
        # still succeeded, so discovery is left alone.
        pytest.param("oops", 0, False, id="unexpected-but-successful"),
        pytest.param("", 0, False, id="silent-but-successful"),
    ],
)
def test_pip_module_missing_parses_probe(stdout, returncode, expected):
    """The marked answer decides, and a failure without one drops the candidate."""
    candidate = Path("/usr/bin/python3")
    with patch(PATCH_RUN, return_value=_completed(stdout, returncode)) as run:
        assert Pip()._pip_module_missing(candidate) is expected
    # The candidate interpreter runs the pip-module one-liner. Compare against the
    # same str() conversion the probe applies, so the expectation holds on Windows
    # where the path stringifies with backslashes.
    command = run.call_args.args[0]
    assert command[0] == str(candidate)
    assert command[1] == "-c"
    assert "find_spec" in command[2]


@pytest.mark.parametrize(
    "error",
    [OSError("not a python"), subprocess.TimeoutExpired("python", 1)],
)
def test_pip_module_missing_keeps_candidate_on_error(error):
    """A failed probe must not hide a candidate: default to pip being present."""
    with patch(PATCH_RUN, side_effect=error):
        assert Pip()._pip_module_missing(Path("/usr/bin/python3")) is False


def test_search_skips_running_interpreter_without_pip():
    """A standalone-app virtualenv carries no pip, so discovery falls through.

    `uv tool install` and `pipx` build `mpm` its own virtualenv and seed no pip
    into it. Selecting that interpreter would leave every `python -m pip` call
    failing against an environment the user never asked mpm to manage.
    """
    fake_exec = "/home/kde/.local/share/uv/tools/meta-package-manager/bin/python"
    missing = Path(fake_exec)
    with (
        patch(PATCH_EXEC, fake_exec),
        patch.object(Pip, "_running_from_bundled_app", return_value=False),
        patch.object(Pip, "_pip_install_blocked", return_value=False),
        patch.object(
            Pip, "_pip_module_missing", side_effect=lambda path: path == missing
        ),
        patch.object(CLIExecutor, "search_all_cli", _fake_base_search),
    ):
        found = list(Pip().search_all_cli(("python3", "python")))
    assert Path(fake_exec) not in found
    assert found == [Path("/usr/bin/python3"), Path("/usr/local/bin/python3")]


# --- Metadata: the core metadata of each installed distribution. --------------

# METADATA headers of real distributions, trimmed to the fields the extractor reads
# and to a few classifiers at most. Every kept line is verbatim.

SEMANTIC_VERSION_METADATA = """\
Metadata-Version: 2.1
Name: semantic-version
Version: 2.10.0
Summary: A library implementing the 'SemVer' scheme.
Home-page: https://github.com/rbarrois/python-semanticversion
Author: Raphaël Barrois
Author-email: raphael.barrois+semver@polytechnique.org
License: BSD
Keywords: semantic version,versioning,version
Classifier: Development Status :: 5 - Production/Stable
Classifier: Intended Audience :: Developers
Classifier: License :: OSI Approved :: BSD License
Requires-Dist: Django (>=1.11) ; extra == 'dev'
Requires-Dist: nose2 ; extra == 'dev'
Requires-Dist: tox ; extra == 'dev'
Requires-Dist: check-manifest ; extra == 'dev'
Requires-Dist: coverage ; extra == 'dev'
Requires-Dist: flake8 ; extra == 'dev'
Requires-Dist: wheel ; extra == 'dev'
Requires-Dist: zest.releaser[recommended] ; extra == 'dev'
Requires-Dist: readme-renderer (<25.0) ; (python_version == "3.4") and extra == 'dev'
Requires-Dist: colorama (<=0.4.1) ; (python_version == "3.4") and extra == 'dev'
Requires-Dist: Sphinx ; extra == 'doc'
Requires-Dist: sphinx-rtd-theme ; extra == 'doc'
"""

PYYAML_METADATA = """\
Metadata-Version: 2.4
Name: PyYAML
Version: 6.0.3
Summary: YAML parser and emitter for Python
Home-page: https://pyyaml.org/
Download-URL: https://pypi.org/project/PyYAML/
Author: Kirill Simonov
Author-email: xi@resolvent.net
License: MIT
Project-URL: Bug Tracker, https://github.com/yaml/pyyaml/issues
Project-URL: CI, https://github.com/yaml/pyyaml/actions
Project-URL: Documentation, https://pyyaml.org/wiki/PyYAMLDocumentation
Project-URL: Mailing lists, http://lists.sourceforge.net/lists/listinfo/yaml-core
Project-URL: Source Code, https://github.com/yaml/pyyaml
Classifier: Development Status :: 5 - Production/Stable
"""

ALABASTER_METADATA = """\
Metadata-Version: 2.1
Name: alabaster
Version: 1.0.0
Summary: A light, configurable Sphinx theme
Maintainer: Adam Turner
Maintainer-email: Jeff Forcier <jeff@bitprophet.org>
Classifier: Framework :: Sphinx :: Theme
Project-URL: Changelog, https://alabaster.readthedocs.io/en/latest/changelog.html
Project-URL: Documentation, https://alabaster.readthedocs.io/
Project-URL: Download, https://pypi.org/project/alabaster/
Project-URL: Homepage, https://alabaster.readthedocs.io/
Project-URL: Issue tracker, https://github.com/sphinx-doc/alabaster/issues
Project-URL: Source, https://github.com/sphinx-doc/alabaster
"""

# The `License` header of this one holds the license text, of which the first
# paragraph is kept.
SETUPTOOLS_SCM_METADATA = """\
Metadata-Version: 2.4
Name: setuptools-scm
Version: 9.2.2
Summary: the blessed package to manage your versions by scm tags
Author-email: Ronny Pfannschmidt <opensource@ronnypfannschmidt.de>
License: Permission is hereby granted, free of charge, to any person obtaining a copy
        of this software and associated documentation files (the "Software"), to deal
        in the Software without restriction, including without limitation the rights
        to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
        copies of the Software, and to permit persons to whom the Software is
        furnished to do so, subject to the following conditions:
Project-URL: documentation, https://setuptools-scm.readthedocs.io/
Project-URL: repository, https://github.com/pypa/setuptools-scm/
Classifier: License :: OSI Approved :: MIT License
Requires-Dist: packaging>=20
Requires-Dist: setuptools
Requires-Dist: tomli>=1; python_version < "3.11"
Requires-Dist: typing-extensions; python_version < "3.10"
"""

WEBCOLORS_METADATA = """\
Metadata-Version: 2.1
Name: webcolors
Version: 25.10.0
Summary: A library for working with the color formats defined by HTML and CSS.
Keywords: color,css,html,web
Author: James Bennett
License: BSD-3-Clause
Project-URL: Documentation, https://webcolors.readthedocs.io
Project-URL: Source Code, https://github.com/ubernostrum/webcolors
"""

PYPI_SUPPLIER = Supplier(name="PyPI", url="https://pypi.org")


def _dist_info(
    tmp_path: Path, metadata: str, encoding: str = "UTF-8"
) -> importlib.metadata.PathDistribution:
    """Install `metadata` as the `METADATA` file of a `.dist-info` directory.

    The directory is named after the `Name` and `Version` headers, the way an
    installer lays it out.
    """
    headers = email.message_from_string(metadata)
    dist_info = tmp_path / f"{headers['Name']}-{headers['Version']}.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_bytes(metadata.encode(encoding))
    return importlib.metadata.PathDistribution(dist_info)


@pytest.mark.parametrize(
    ("spec", "expected"),
    (
        # The example of the docstring.
        ("cryptography[ssh]>=42", ("cryptography", "[ssh]", ">=42")),
        # From click-extra 9.4.1.
        ("tabulate[widechars]>=0.9", ("tabulate", "[widechars]", ">=0.9")),
        # From semantic-version 2.10.0, as left before its `;` marker.
        ("Django (>=1.11) ", ("Django", "", "(>=1.11)")),
        ("zest.releaser[recommended] ", ("zest.releaser", "[recommended]", "")),
        # From setuptools-scm 9.2.2.
        ("setuptools", ("setuptools", "", "")),
        ("", ("", "", "")),
    ),
)
def test_split_dep_spec(spec, expected):
    """A requirement splits into its name, its extras and its version constraint."""
    assert _split_dep_spec(spec) == expected


@pytest.mark.parametrize(
    ("metadata", "expected"),
    (
        pytest.param(
            SEMANTIC_VERSION_METADATA,
            PackageMetadata(
                homepage="https://github.com/rbarrois/python-semanticversion",
                license_declared="BSD",
                license_concluded="BSD",
                supplier=PYPI_SUPPLIER,
                originator=Originator(
                    name="Raphaël Barrois",
                    email="raphael.barrois+semver@polytechnique.org",
                ),
                summary="A library implementing the 'SemVer' scheme.",
                description="A library implementing the 'SemVer' scheme.",
                dependencies=(
                    Dependency("Django", version_constraint="(>=1.11)"),
                    Dependency("nose2"),
                    Dependency("tox"),
                    Dependency("check-manifest"),
                    Dependency("coverage"),
                    Dependency("flake8"),
                    Dependency("wheel"),
                    Dependency("zest.releaser"),
                    Dependency("readme-renderer", version_constraint="(<25.0)"),
                    Dependency("colorama", version_constraint="(<=0.4.1)"),
                    Dependency("Sphinx"),
                    Dependency("sphinx-rtd-theme"),
                ),
                extras={
                    "pip.keywords": "semantic version,versioning,version",
                    "pip.classifiers": [
                        "Development Status :: 5 - Production/Stable",
                        "Intended Audience :: Developers",
                        "License :: OSI Approved :: BSD License",
                    ],
                },
            ),
            id="author-keywords-and-markers",
        ),
        pytest.param(
            PYYAML_METADATA,
            PackageMetadata(
                download_url="https://pypi.org/project/PyYAML/",
                homepage="https://pyyaml.org/",
                vcs_url="https://github.com/yaml/pyyaml",
                issue_tracker_url="https://github.com/yaml/pyyaml/issues",
                license_declared="MIT",
                license_concluded="MIT",
                supplier=PYPI_SUPPLIER,
                originator=Originator(name="Kirill Simonov", email="xi@resolvent.net"),
                summary="YAML parser and emitter for Python",
                description="YAML parser and emitter for Python",
                extras={
                    "pip.classifiers": ["Development Status :: 5 - Production/Stable"]
                },
            ),
            id="home-page-over-project-urls",
        ),
        pytest.param(
            ALABASTER_METADATA,
            PackageMetadata(
                homepage="https://alabaster.readthedocs.io/",
                vcs_url="https://github.com/sphinx-doc/alabaster",
                issue_tracker_url="https://github.com/sphinx-doc/alabaster/issues",
                supplier=PYPI_SUPPLIER,
                originator=Originator(name="Adam Turner", email="jeff@bitprophet.org"),
                summary="A light, configurable Sphinx theme",
                description="A light, configurable Sphinx theme",
                extras={"pip.classifiers": ["Framework :: Sphinx :: Theme"]},
            ),
            id="maintainer-fallback",
        ),
        pytest.param(
            SETUPTOOLS_SCM_METADATA,
            PackageMetadata(
                homepage="https://setuptools-scm.readthedocs.io/",
                vcs_url="https://github.com/pypa/setuptools-scm/",
                license_declared=(
                    "Permission is hereby granted, free of charge, to any person "
                    "obtaining a copy"
                ),
                license_concluded=(
                    "Permission is hereby granted, free of charge, to any person "
                    "obtaining a copy"
                ),
                supplier=PYPI_SUPPLIER,
                summary="the blessed package to manage your versions by scm tags",
                description="the blessed package to manage your versions by scm tags",
                dependencies=(
                    Dependency("packaging", version_constraint=">=20"),
                    Dependency("setuptools"),
                    Dependency("tomli", version_constraint=">=1"),
                    Dependency("typing-extensions"),
                ),
                extras={"pip.classifiers": ["License :: OSI Approved :: MIT License"]},
            ),
            id="license-text-and-no-author-name",
        ),
        pytest.param(
            WEBCOLORS_METADATA,
            PackageMetadata(
                homepage="https://webcolors.readthedocs.io",
                vcs_url="https://github.com/ubernostrum/webcolors",
                license_declared="BSD-3-Clause",
                license_concluded="BSD-3-Clause",
                supplier=PYPI_SUPPLIER,
                originator=Originator(name="James Bennett"),
                summary=(
                    "A library for working with the color formats defined by HTML "
                    "and CSS."
                ),
                description=(
                    "A library for working with the color formats defined by HTML "
                    "and CSS."
                ),
                extras={"pip.keywords": "color,css,html,web"},
            ),
            id="author-without-address",
        ),
    ),
)
def test_distribution_metadata(tmp_path, metadata, expected):
    """The core metadata of a distribution fills the portable fields.

    A `Home-page` header wins over every `Project-URL`, whose labels otherwise
    pick the homepage, the repository and the tracker. A license text keeps its
    first line. The maintainer stands in for a missing author, and the address
    of a `Name <address>` field is kept alone. A requirement keeps its name and
    its constraint, but loses its extras and its environment marker.
    """
    assert Pip._distribution_metadata(_dist_info(tmp_path, metadata)) == expected


def test_package_metadata_batch_skips_an_empty_inventory():
    """No package to enrich means no distribution lookup."""
    with patch(PATCH_DIST, side_effect=AssertionError("looked up")) as distribution:
        assert list(Pip().package_metadata_batch([])) == []
    distribution.assert_not_called()


@pytest.mark.parametrize(
    ("encoding", "enriched"),
    (
        pytest.param("UTF-8", True, id="decodable"),
        pytest.param("latin-1", False, id="undecodable"),
    ),
)
def test_package_metadata_batch_enriches_each_package_alone(
    tmp_path, encoding, enriched
):
    """A package whose metadata cannot be read stays bare beside the others.

    One package is unknown to the environment. In the second case, the
    `METADATA` file of the other one is no valid UTF-8, like the file of an old
    installer that wrote in the platform encoding.
    """
    distributions = {
        "semantic-version": _dist_info(tmp_path, SEMANTIC_VERSION_METADATA, encoding)
    }

    def distribution(name):
        if name not in distributions:
            raise importlib.metadata.PackageNotFoundError(name)
        return distributions[name]

    manager = Pip()
    packages = [
        manager.package(id="semantic-version"),
        manager.package(id="requests"),
    ]
    with patch(PATCH_DIST, side_effect=distribution):
        results = list(manager.package_metadata_batch(packages))

    assert [package.id for package, _ in results] == ["semantic-version", "requests"]
    (_, semantic_version), (_, requests) = results
    assert (semantic_version is EMPTY_METADATA) is not enriched
    assert semantic_version.summary == (
        "A library implementing the 'SemVer' scheme." if enriched else None
    )
    assert requests is EMPTY_METADATA
