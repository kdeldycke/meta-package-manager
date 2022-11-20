# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
# All Rights Reserved.
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

import subprocess
from pathlib import Path

import pytest
from click_extra.run import env_copy
from click_extra.tests.conftest import destructive, unless_macos


@pytest.fixture
def install_cask():
    packages = set()

    def get_cask_path():
        """Default location of Homebrew Cask formulas on macOS.

        This is supposed to be a shallow copy of the following Git repository:
        https://github.com/Homebrew/homebrew-cask
        """
        process = subprocess.run(
            ("brew", "--repository"),
            capture_output=True,
            encoding="utf-8",
        )
        assert process.returncode == 0
        assert not process.stderr
        assert process.stdout

        brew_root = Path(process.stdout.strip())
        assert brew_root.is_absolute()
        assert brew_root.exists()
        assert brew_root.is_dir()

        cask_repo = brew_root.joinpath("Library/Taps/homebrew/homebrew-cask/Casks/")
        assert cask_repo.is_absolute()
        assert cask_repo.exists()
        assert cask_repo.is_dir()
        return cask_repo

    def git_checkout(package_id, commit):
        process = subprocess.run(
            ("git", "-C", get_cask_path(), "checkout", commit, f"{package_id}.rb")
        )
        assert not process.stderr
        assert process.returncode == 0

    def brew_cleanup():
        process = subprocess.run(
            ("brew", "cleanup", "-s", "--prune=all"),
            env=env_copy({"HOMEBREW_NO_AUTO_UPDATE": "1"}),
        )
        assert not process.stderr
        assert process.returncode == 0

    def brew_uninstall(package_id):
        process = subprocess.run(("brew", "uninstall", "--cask", "--force", package_id))
        assert not process.stderr
        assert process.returncode == 0

    def _install_cask(package_id, commit):
        packages.add(package_id)

        # Fetch locally the old version of the Cask's formula.
        git_checkout(package_id, commit)
        brew_cleanup()

        # Install the cask but bypass its local cache auto-update: we want to
        # force brew to rely on our formula from the past.
        process = subprocess.run(
            ("brew", "reinstall", "--cask", package_id),
            capture_output=True,
            encoding="utf-8",
            env=env_copy(
                {"HOMEBREW_NO_ENV_HINTS": "1", "HOMEBREW_NO_AUTO_UPDATE": "1"}
            ),
        )

        # Restore old formula to its most recent version.
        git_checkout(package_id, "HEAD")
        brew_cleanup()

        # Check the cask has been properly installed.
        if process.stderr:
            assert "is already installed" not in process.stderr
        assert f"{package_id} was successfully installed!" in process.stdout
        assert process.returncode == 0
        return process.stdout

    yield _install_cask

    # Remove all installed packages.
    for package_id in packages:
        brew_uninstall(package_id)


@destructive
@unless_macos
class TestCask:
    @pytest.mark.xdist_group(name="avoid_concurrent_git_tweaks")
    def test_autoupdate_unicode_name(self, invoke, install_cask):
        """See #16."""
        # Install an old version of a package with a unicode name.
        # Old Cask formula for ubersicht 1.6.69.
        output = install_cask("ubersicht", "9870e8ffaa8dc83403973580415b2c56dc760f15")
        assert "Uebersicht-1.6.69.app.zip" in output
        assert "Übersicht.app" in output
        assert "Übersicht.app" not in output

        # Ubersicht is not reported as outdated because is tagged as
        # auto-update.
        result = invoke("--cask", "outdated")
        assert result.exit_code == 0
        assert "ubersicht" not in result.stdout
        assert "Übersicht" not in result.stdout

        # Try with explicit option.
        result = invoke("--ignore-auto-updates", "--cask", "outdated")
        assert result.exit_code == 0
        assert "ubersicht" not in result.stdout
        assert "Übersicht" not in result.stdout

        # Look for reported available upgrade.
        result = invoke("--include-auto-updates", "--cask", "outdated")
        assert result.exit_code == 0
        assert "ubersicht" in result.stdout
        # Outdated subcommand does not fetch the unicode name by default.
        assert "Übersicht" not in result.stdout

    @pytest.mark.xdist_group(name="avoid_concurrent_git_tweaks")
    def test_multiple_names(self, invoke, install_cask):
        """See #26."""
        # Install an old version of a package with multiple names.
        # Old Cask formula for xld 20210101,153.1.
        output = install_cask("xld", "6be43816ea729c18219322f656c62a702e1c2440")
        assert "xld-20210101.dmg" in output
        assert "XLD.app" in output

        # Look for reported available upgrade.
        result = invoke("--include-auto-updates", "--cask", "outdated")
        assert result.exit_code == 0
        assert "xld" in result.stdout
        # Outdated subcommand does not fetch the unicode name by default.
        assert "X Lossless Decoder" not in result.stdout
