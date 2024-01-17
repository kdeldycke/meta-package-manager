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
"""Homebrew-specific tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click_extra.testing import env_copy
from click_extra.tests.conftest import unless_macos


@pytest.fixture()
def install_cask():
    """A fixture to install a Cask from a specific commit."""

    packages = set()
    """List of installed packages."""

    def get_cask_tap_path():
        """Default location of Homebrew Cask formulas on macOS.

        This is supposed to be a `shallow copy of the official cask repository
        <https://github.com/Homebrew/homebrew-cask>`_.

        The later can be obtained with:

        .. code-block:: shell-session
            $ export HOMEBREW_NO_INSTALL_FROM_API="1"
            $ brew tap homebrew/cask
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

    def get_cask_folder(package_id: str):
        """Get the folder where a Cask is located.

        ..warning::
            As of `aa46114 <https://github.com/Homebrew/homebrew-cask/commit/aa46114>`_,
            casks have been moved to a subfolder named after their first letter.
        """
        cask_folder = get_cask_tap_path().joinpath(package_id[0])
        assert cask_folder.is_absolute()
        assert cask_folder.exists()
        assert cask_folder.is_dir()
        return cask_folder

    def git_checkout(package_id: str, commit: str):
        process = subprocess.run(
            (
                "git",
                "-C",
                get_cask_folder(package_id),
                "checkout",
                commit,
                f"{package_id}.rb",
            ),
        )
        assert not process.stderr
        assert process.returncode == 0

    def brew_cleanup():
        """Remove all downloads cached by Homebrew.

        .. note::
            ``brew`` does not cleanup ``~/Library/Caches/Homebrew``, see:
            https://github.com/Homebrew/brew/issues/3784#issuecomment-364675767

            We might need to force it with:

            .. code-block:: shell-session
                $ rm -rf $(brew --cache)
        """
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

        # XXX Work around the bad old ubersicht cask formula.
        # Replace ":yosemite" by ":el_capitan" like the last commit did at:
        # https://github.com/Homebrew/homebrew-cask/commit/5cddbd6
        # The day we have a new version of ubersicht after this commit, we will be able
        # to remove that hack, and have the install_cask() invocation from the
        # test_autoupdate_unicode_name() test below checkout ubersicht from that commit.
        if package_id == "ubersicht":
            cask_path = get_cask_tap_path().joinpath(f"{package_id}.rb")
            content = cask_path.read_text()
            cask_path.write_text(content.replace(":yosemite", ":el_capitan"))

        # Install the cask but bypass its local cache auto-update: we want to
        # force brew to rely on our formula from the past.
        process = subprocess.run(
            ("brew", "reinstall", "--cask", package_id),
            capture_output=True,
            encoding="utf-8",
            check=True,
            env=env_copy(
                {
                    # Do not let brew use its live API to fetch the latest version.
                    # This variable forces brew to use the local repository instead:
                    # https://github.com/Homebrew/brew/blob/10845a1/Library/Homebrew/env_config.rb#L314-L317
                    "HOMEBREW_NO_INSTALL_FROM_API": "1",
                    "HOMEBREW_NO_AUTO_UPDATE": "1",
                    "HOMEBREW_NO_ENV_HINTS": "1",
                },
            ),
        )

        # Restore old formula to its most recent version.
        git_checkout(package_id, "HEAD")
        brew_cleanup()

        # Check the cask has been properly installed.
        if process.stderr:
            assert "is already installed" not in process.stderr
        assert f"{package_id} was successfully installed!" in process.stdout
        return process.stdout

    yield _install_cask

    # Remove all installed packages.
    for package_id in packages:
        brew_uninstall(package_id)


@pytest.mark.destructive()
@unless_macos
# XXX The layout of the cask repository has changed, so we cannot go back in time too
# much and checkout old versions of casks. We need to wait for a couple of new releases
# of the casks we use in our tests, so we can have enough commit depth to test the
# upgrade process.
@pytest.mark.skip(
    reason="Cask repository structure changed too much to go back in time."
)
class TestCask:
    @pytest.mark.xdist_group(name="avoid_concurrent_git_tweaks")
    def test_autoupdate_unicode_name(self, invoke, install_cask):
        """See #16."""
        # Install an old version of a package with a unicode name.
        # Old Cask formula for ubersicht 1.6.69.
        # XXX Update this commit when a new version of ubersicht is released so we can
        # get rid of the hack above.
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
