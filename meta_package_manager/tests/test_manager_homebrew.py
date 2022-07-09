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

import pytest
from click_extra.run import env_copy
from click_extra.tests.conftest import destructive, unless_macos

# Default location of Homebrew Cask formulas on macOS. This is supposed to be a
# shallow copy of the following Git repository:
# https://github.com/Homebrew/homebrew-cask
CASK_PATH = "/usr/local/Homebrew/Library/Taps/homebrew/homebrew-cask/Casks/"


@pytest.fixture
def install_cask():

    packages = set()

    def git_checkout(package_id, commit):
        process = subprocess.run(
            ("git", "-C", CASK_PATH, "checkout", commit, f"{package_id}.rb")
        )
        assert process.returncode == 0

    def _install_cask(package_id, commit):
        packages.add(package_id)
        # Fetch locally the old version of the Cask's formula.
        git_checkout(package_id, commit)
        # Install the cask but bypass its local cache auto-update: we want to
        # force brew to rely on our formula from the past.
        process = subprocess.run(
            ("brew", "reinstall", "--cask", package_id),
            capture_output=True,
            encoding="utf-8",
            env=env_copy({"HOMEBREW_NO_AUTO_UPDATE": "1"}),
        )
        # Restore old formula to its most recent version.
        git_checkout(package_id, "HEAD")
        # Check the cask has been properly installed.
        assert process.returncode == 0
        if process.stderr:
            assert "is already installed" not in process.stderr
        assert f"{package_id} was successfully installed!" in process.stdout
        return process.stdout

    yield _install_cask

    # Remove all installed packages.
    for package_id in packages:
        subprocess.run(("brew", "uninstall", "--cask", "--force", package_id))


@destructive
@unless_macos
class TestCask:
    @pytest.mark.xdist_group(name="avoid_concurrent_git_tweaks")
    def test_autoupdate_unicode_name(self, invoke, install_cask):
        """See #16."""
        # Install an old version of a package with a unicode name.
        # Old Cask formula for ubersicht 1.4.60.
        output = install_cask("ubersicht", "bb72da6c085c017f6bccebbfee5e3bc4837f3165")
        assert "Uebersicht-1.4.60.app.zip" in output
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
        # Old Cask formula for xld 2018.10.19.
        output = install_cask("xld", "89536da7075aa3ac9683a67189fddbed4a7d818c")
        assert "xld-20181019.dmg" in output
        assert "XLD.app" in output

        # Look for reported available upgrade.
        result = invoke("--include-auto-updates", "--cask", "outdated")
        assert result.exit_code == 0
        assert "xld" in result.stdout
        # Outdated subcommand does not fetch the unicode name by default.
        assert "X Lossless Decoder" not in result.stdout
