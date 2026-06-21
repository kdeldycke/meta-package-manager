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

import re
import subprocess

import pytest
from extra_platforms import is_linux

from meta_package_manager.pool import pool

from .conftest import maintained_manager_ids_and_dummy_package
from .test_cli import CLISubCommandTests


@pytest.fixture
def subcmd():
    return "install", "arrow"


class TestInstallRemove(CLISubCommandTests):
    """Install and remove operations are siblings and sensible, so we regroup them under
    the same test suite.

    .. tip::

        Where we can, we invoke the ``install`` subcommand to install ``mpm`` with
        itself, so we can `test externally contributed packaging
        <https://github.com/kdeldycke/meta-package-manager/issues/527>`_.
    """

    @staticmethod
    def evaluate_signals(mid, stdout, stderr):
        yield from (
            # install announces the managers it will try, in priority order.
            bool(
                re.search(
                    rf"Installation priority:.*\b{mid}\b",
                    stderr,
                ),
            ),
            # remove dispatches to each manager that has the package installed.
            bool(
                re.search(
                    rf"Remove \S+ with\b.*\b{mid}\b",
                    stderr,
                ),
            ),
            bool(
                re.search(
                    rf"has been installed with {mid}\.",
                    stderr,
                ),
            ),
        )

    @pytest.mark.parametrize("operation", ("install", "remove"))
    def test_no_package_id(self, invoke, operation):
        result = invoke(operation)
        assert result.exit_code == 2
        assert not result.stdout
        assert "Error: Missing argument 'PACKAGES_SPECS...'." in result.stderr

    def test_install_unresolved_exits_nonzero(self, invoke, fake_pool):
        """install exits non-zero when no manager can provide the requested package.

        Guards against a regression where a failed install was swallowed and the
        command still exited ``0`` (see the ``install`` command in ``cli.py``).
        """
        result = invoke("install", "package-provided-by-no-manager")
        assert result.exit_code == 1

    def test_remove_absent_package_is_idempotent(self, invoke, fake_pool):
        """Removing a package no manager has installed is a no-op, not a failure.

        ``remove`` only fails when a manager that *has* the package fails to remove it.
        """
        result = invoke("remove", "package-installed-by-no-manager")
        assert result.exit_code == 0

    @pytest.mark.destructive()
    @maintained_manager_ids_and_dummy_package
    def test_single_manager_install_and_remove(self, invoke, manager_id, package_id):
        """Test the installation and removal of a package with each manager.

        .. caution.

            ``strict_selection_match`` is set to ``False`` because the ``install``
            subcommand will not try all managers selected by default. So a strict
            match is not possible.

            That's because ``install`` subcommand try each user-selected manager until
            it find one providing the package we seek to install, after which the
            process stop.
        """
        # XXX Skip this test on GitHub Actions as it's too slow:
        #
        # $ mpm --mas install 747648890
        # <output> stream:
        #   (...)
        #   info: Installation priority: > mas
        #
        # <exit_code>: 1
        #
        # Traceback (most recent call last):
        #   (...)
        #   File ".../lib/python3.10/subprocess.py", line 1198, in _check_timeout
        #     raise TimeoutExpired(
        # subprocess.TimeoutExpired: Command '('/opt/homebrew/bin/mas', 'install',
        # '747648890')' timed out after 500 seconds
        if manager_id == "mas":
            pytest.skip("mas timeout on GitHub Actions.")

        # XXX Skip the RPM-family managers on Linux: the RPM stack has no usable
        # repositories, and its database at /var/lib/rpm is inaccessible even with
        # sudo on the Debian-based ubuntu CI runners (both x86_64 and aarch64),
        # causing errors like:
        #
        #   error: Unable to open sqlite database /var/lib/rpm/rpmdb.sqlite:
        #   unable to open database file
        #   error: cannot open Packages index using sqlite - Operation not
        #   permitted (1)
        #   error: cannot open Packages database in /var/lib/rpm
        if manager_id in {"dnf", "dnf5", "yum", "zypper"} and is_linux():
            pytest.skip(f"{manager_id} RPM stack not usable on Linux CI runners.")

        # XXX Skip snap and flatpak on Linux: the unprivileged test process cannot
        # drive them on CI runners. snap install requires root (mpm does not elevate),
        # and flatpak has no remote configured to resolve apps from. Both used to
        # appear to pass only because a failed install historically exited 0.
        if manager_id in {"snap", "flatpak"} and is_linux():
            pytest.skip(
                f"{manager_id} cannot install in the unprivileged CI environment.",
            )

        # XXX Skip pwsh-gallery when PowerShell cannot load the PSResourceGet
        # module. This can happen when the CI runner has .NET 10 installed: the
        # assembly binding for System.Collections.Specialized resolves to
        # Version=10.0.0.0, which is incompatible with PowerShell 7.x's .NET 8
        # runtime. The crash manifests as:
        #
        #   System.IO.FileLoadException: The given assembly name was invalid.
        #   File name: 'System.Collections.Specialized, Version=10.0.0.0'
        if manager_id == "pwsh-gallery":
            probe = subprocess.run(
                [
                    "pwsh",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Get-Command Install-PSResource -ErrorAction Stop",
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
            if probe.returncode != 0:
                pytest.skip(
                    "pwsh cannot load PSResourceGet: "
                    + probe.stderr.decode(errors="replace").strip()
                )

        for command in ("install", "remove"):
            result = invoke(f"--{manager_id}", command, package_id)

            if result.exit_code == 2:
                assert not result.stdout
                assert (
                    "\x1b[31m\x1b[1mcritical\x1b[0m: No manager selected.\n"
                    in result.stderr
                )
            else:
                assert result.exit_code == 0
                self.check_manager_selection(
                    result,
                    {manager_id},
                    reference_set=pool.all_manager_ids,
                    strict_selection_match=False,
                )
