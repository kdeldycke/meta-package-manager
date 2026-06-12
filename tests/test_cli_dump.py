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

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

import pytest

from meta_package_manager.brewfile import (
    BUNDLE_ENTRY_TYPES,
    build_brewfile,
    format_entry,
    format_header,
    quote,
    tap_from_package_id,
)
from meta_package_manager.package import Package


@dataclass
class _StubManager:
    """Minimal manager stand-in for ``build_brewfile`` unit tests.

    Avoids spinning up the full manager class hierarchy (CLI discovery, version
    parsing, ...) for what is a pure-function rendering test.
    """

    id: str
    brewfile_entry_type: str | None
    installed_packages: tuple[Package, ...]

    @property
    def installed(self):
        return iter(self.installed_packages)

    def brewfile_entry(self, package: Package):
        """Default-shape hook matching :py:meth:`PackageManager.brewfile_entry`."""
        return package.id, None


def _pkg(manager_id: str, package_id: str, name: str | None = None) -> Package:
    return Package(
        id=package_id, manager_id=manager_id, name=name, installed_version="1.0.0",
    )


def test_quote_ascii():
    assert quote("git") == '"git"'


def test_quote_escapes_backslash_and_quote():
    assert quote('a"b\\c') == '"a\\"b\\\\c"'


def test_quote_non_ascii_passes_through():
    # ensure_ascii=False keeps the codepoint inline, which Ruby's double-quoted
    # string parser accepts.
    assert quote("café") == '"café"'


def test_format_entry_bare():
    assert format_entry("brew", "git") == 'brew "git"'


def test_format_entry_with_scalar_int():
    assert (
        format_entry("mas", "Xcode", {"id": 497799835})
        == 'mas "Xcode", id: 497799835'
    )


def test_format_entry_with_list():
    assert (
        format_entry("flatpak", "org.mozilla.firefox", {"with": ["flathub"]})
        == 'flatpak "org.mozilla.firefox", with: ["flathub"]'
    )


def test_format_entry_with_bool():
    assert (
        format_entry("tap", "user/repo", {"trusted": True})
        == 'tap "user/repo", trusted: true'
    )


def test_tap_from_package_id_third_party():
    assert tap_from_package_id("gromgit/fuse/ntfs-3g-mac") == "gromgit/fuse"


def test_tap_from_package_id_default_tap_returns_none():
    assert tap_from_package_id("homebrew/core/git") is None
    assert tap_from_package_id("homebrew/cask/iterm2") is None


def test_tap_from_package_id_bare_name_returns_none():
    assert tap_from_package_id("git") is None
    assert tap_from_package_id("python@3.11") is None


def test_format_header_lists_coverage_and_skipped():
    header = format_header(
        coverage={"brew": 12, "cask": 3},
        skipped={"apt": 841, "pip": 12},
        platform="macOS",
    )
    assert "Coverage: brew=12, cask=3" in header
    assert "Skipped:  apt=841, pip=12" in header
    assert "Source platform: macOS" in header
    assert "WARNING" in header
    assert "brew bundle cleanup" in header


def test_format_header_empty_coverage_marker():
    header = format_header({}, {}, "linux")
    assert "Coverage: (empty)" in header
    assert "Skipped:  (none)" in header


def test_bundle_entry_types_ordering():
    # `tap` must come first so a downstream `brew`/`cask` finds its source.
    assert BUNDLE_ENTRY_TYPES[0] == "tap"
    # Phase 1 only emits brew + cask; both must be present in the canonical order.
    assert "brew" in BUNDLE_ENTRY_TYPES
    assert "cask" in BUNDLE_ENTRY_TYPES


def test_build_brewfile_brew_cask_sorted_alphabetically():
    brew_mgr = _StubManager(
        id="brew",
        brewfile_entry_type="brew",
        installed_packages=(_pkg("brew", "git"), _pkg("brew", "ack")),
    )
    cask_mgr = _StubManager(
        id="cask",
        brewfile_entry_type="cask",
        installed_packages=(_pkg("cask", "rectangle"), _pkg("cask", "iterm2")),
    )
    output = build_brewfile([brew_mgr, cask_mgr], include_header=False)
    lines = [ln for ln in output.splitlines() if ln.strip()]
    assert lines == [
        'brew "ack"',
        'brew "git"',
        'cask "iterm2"',
        'cask "rectangle"',
    ]


def test_build_brewfile_emits_tap_lines_for_third_party_taps():
    brew_mgr = _StubManager(
        id="brew",
        brewfile_entry_type="brew",
        installed_packages=(
            _pkg("brew", "git"),
            _pkg("brew", "gromgit/fuse/ntfs-3g-mac"),
        ),
    )
    output = build_brewfile([brew_mgr], include_header=False)
    lines = [ln for ln in output.splitlines() if ln.strip()]
    assert 'tap "gromgit/fuse"' in lines
    # No tap line for the implicit homebrew/core.
    assert not any(ln.startswith('tap "homebrew/core"') for ln in lines)


def test_build_brewfile_skips_managers_without_entry_type():
    skipped = _StubManager(
        id="apt",
        brewfile_entry_type=None,
        installed_packages=(_pkg("apt", "vim"),),
    )
    output = build_brewfile([skipped], include_header=False)
    assert output.strip() == ""


def test_build_brewfile_header_records_skipped_counts():
    brew_mgr = _StubManager(
        id="brew",
        brewfile_entry_type="brew",
        installed_packages=(_pkg("brew", "git"),),
    )
    output = build_brewfile(
        [brew_mgr],
        include_header=True,
        skipped_counts={"apt": 841, "pip": 12},
        platform="macOS",
    )
    assert "Coverage: brew=1" in output
    assert "Skipped:  apt=841, pip=12" in output
    assert 'brew "git"' in output


def test_mas_brewfile_entry_uses_name_and_numeric_id():
    """``mas`` Brewfile entries take the app display name + ``id:`` keyword."""
    from meta_package_manager.managers.mas import MAS

    package = Package(
        id="497799835",
        manager_id="mas",
        name="Xcode",
        installed_version="15.4",
    )
    name, options = MAS.brewfile_entry(MAS, package)
    assert name == "Xcode"
    assert options == {"id": 497799835}


def test_mas_brewfile_entry_skips_non_numeric_id():
    """A mas Package without a numeric adamID cannot round-trip; skip it."""
    from meta_package_manager.managers.mas import MAS

    package = Package(
        id="not-a-number",
        manager_id="mas",
        name="Mystery App",
        installed_version="1.0",
    )
    assert MAS.brewfile_entry(MAS, package) is None


def test_mas_brewfile_entry_falls_back_to_id_when_name_missing():
    """A mas Package with no display name uses the adamID string as the entry."""
    from meta_package_manager.managers.mas import MAS

    package = Package(
        id="497799835",
        manager_id="mas",
        installed_version="15.4",
    )
    name, options = MAS.brewfile_entry(MAS, package)
    assert name == "497799835"
    assert options == {"id": 497799835}


def test_vscodium_brewfile_skip_warning_set():
    """VSCodium overrides VSCode's ``brewfile_entry_type`` to ``None`` so its
    extensions are not silently emitted as ``vscode`` (which would install to VS
    Code instead of VSCodium). The warning is the audible signal."""
    from meta_package_manager.managers.vscode import VSCode, VSCodium

    assert VSCode.brewfile_entry_type == "vscode"
    assert VSCodium.brewfile_entry_type is None
    assert VSCodium.brewfile_skip_warning is not None
    assert "{count}" in VSCodium.brewfile_skip_warning


def test_phase_2_to_4_managers_have_brewfile_entry_types():
    """Every brew-bundle-supported manager except ``go`` and ``krew`` has a
    mapping. Catches regressions if a manager's class is reorganized and the
    attribute is dropped."""
    from meta_package_manager.managers.cargo import Cargo
    from meta_package_manager.managers.flatpak import Flatpak
    from meta_package_manager.managers.homebrew import Brew, Cask
    from meta_package_manager.managers.mas import MAS
    from meta_package_manager.managers.npm import NPM
    from meta_package_manager.managers.uv import UV, UVX
    from meta_package_manager.managers.vscode import VSCode
    from meta_package_manager.managers.winget import WinGet

    assert Brew.brewfile_entry_type == "brew"
    assert Cask.brewfile_entry_type == "cask"
    assert MAS.brewfile_entry_type == "mas"
    assert VSCode.brewfile_entry_type == "vscode"
    assert NPM.brewfile_entry_type == "npm"
    assert Cargo.brewfile_entry_type == "cargo"
    assert UVX.brewfile_entry_type == "uv"
    assert WinGet.brewfile_entry_type == "winget"
    assert Flatpak.brewfile_entry_type == "flatpak"
    # The pip-style UV manager intentionally has no mapping: its packages are
    # environment-level Python deps, not top-level tools.
    assert UV.brewfile_entry_type is None


def test_build_brewfile_round_trip_format_is_parseable_by_ruby_inspect():
    """The emitted lines should round-trip through Ruby ``String#inspect`` rules.

    ``quote`` uses ``json.dumps(ensure_ascii=False)`` which produces double-quoted
    strings with backslash escapes for control chars: a subset of what Ruby's
    inspect emits, accepted as a valid Ruby literal.
    """
    brew_mgr = _StubManager(
        id="brew",
        brewfile_entry_type="brew",
        installed_packages=(
            _pkg("brew", "git"),
            _pkg("brew", "python@3.11"),
            _pkg("brew", "gromgit/fuse/ntfs-3g-mac"),
        ),
    )
    output = build_brewfile([brew_mgr], include_header=False)
    # Every non-empty data line must start with a known entry type followed by
    # a double-quoted string.
    for line in output.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        entry_type, rest = line.split(" ", 1)
        assert entry_type in BUNDLE_ENTRY_TYPES, line
        assert rest.startswith('"'), line


@pytest.mark.skipif(
    shutil.which("brew") is None,
    reason="`brew` not on PATH; cannot validate Brewfile round-trip.",
)
def test_brew_bundle_check_parses_generated_brewfile(tmp_path):
    """Pipe :py:func:`build_brewfile` output through ``brew bundle check`` to
    catch DSL drift early.

    Uses a synthetic package set so the test runs in milliseconds rather than
    iterating the real manager pool. The point of the check is format validity
    (does brew parse what we emit?), not "does mpm see what brew sees on this
    host?".
    """
    brew_mgr = _StubManager(
        id="brew",
        brewfile_entry_type="brew",
        installed_packages=(_pkg("brew", "git"),),
    )
    target = tmp_path / "Brewfile.test"
    target.write_text(build_brewfile([brew_mgr], include_header=True))

    completed = subprocess.run(
        ["brew", "bundle", "check", "--file", str(target), "--no-upgrade"],
        capture_output=True,
        text=True,
        check=False,
    )
    # 0 = file parses, every entry already installed.
    # 1 = file parses, at least one entry is missing.
    # Anything else means brew rejected the file shape itself.
    assert completed.returncode in (0, 1), (
        f"brew bundle check failed to parse the Brewfile.\n"
        f"stdout: {completed.stdout}\n"
        f"stderr: {completed.stderr}"
    )
    assert "Invalid Brewfile" not in completed.stderr
