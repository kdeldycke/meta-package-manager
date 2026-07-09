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

import pytest

from meta_package_manager.pool import pool

from .conftest import (
    INSTALL_REMOVE_BLOCKERS,
    SHORT_FAILURE_TIMEOUT,
    maintained_manager_ids_and_dummy_package,
)
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

    @pytest.mark.parametrize("flag", ("--zero-exit", "-0"))
    def test_install_unresolved_zero_exit_opt_out(self, invoke, fake_pool, flag):
        """-0/--zero-exit keeps the exit code at 0 on per-package failures; the
        critical summary stays as the durable record."""
        result = invoke(flag, "install", "package-provided-by-no-manager")
        assert result.exit_code == 0
        assert "Could not install: package-provided-by-no-manager." in result.stderr

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

        .. caution::

            ``strict_selection_match`` is set to ``False`` because the ``install``
            subcommand will not try all managers selected by default. So a strict
            match is not possible.

            That's because ``install`` subcommand try each user-selected manager until
            it find one providing the package we seek to install, after which the
            process stop.

        .. note::

            Managers that cannot complete a real install in a given environment are not
            skipped: they are listed in ``INSTALL_REMOVE_BLOCKERS`` (``conftest.py``) and
            driven anyway. The blocked ``install`` is capped at ``SHORT_FAILURE_TIMEOUT``
            and asserted to fail the stable mpm way (exit ``1`` plus a ``Could not
            install:`` message). It runs at ``--verbosity INFO``: the minimum level at
            which the ``Installation priority`` dispatch signal is visible (the default
            ``WARNING`` would hide it and make :py:meth:`check_manager_selection` pass
            vacuously). No follow-up ``remove``: the failed install left nothing to
            remove, and the working managers already cover the removal path.
        """
        blocker = INSTALL_REMOVE_BLOCKERS.get(manager_id)
        if blocker and blocker():
            # This manager cannot complete a real install here. Drive the doomed install
            # anyway, capped at SHORT_FAILURE_TIMEOUT, and assert it fails the stable mpm
            # way. No remove leg: the failed install left nothing to remove, and the
            # working managers below already cover the removal path.
            result = invoke(
                f"--{manager_id}",
                "--verbosity",
                "INFO",
                "--timeout",
                str(SHORT_FAILURE_TIMEOUT),
                "install",
                package_id,
            )
            # The manager is not available on this host: mpm selected nothing. This
            # supersedes the blocker expectation, which only applies once the manager is
            # present and reaches its (doomed) install.
            if result.exit_code == 2:
                assert not result.stdout
                assert "critical: No manager selected.\n" in result.stderr
                return
            assert result.exit_code == 1
            assert f"Could not install: {package_id}" in result.stderr, (
                f"{manager_id} install: expected a 'Could not install:' failure in "
                f"stderr, got:\n{result.stderr}"
            )
            self.check_manager_selection(
                result,
                {manager_id},
                reference_set=pool.all_manager_ids,
                strict_selection_match=False,
            )
            return

        for command in ("install", "remove"):
            result = invoke(f"--{manager_id}", command, package_id)

            # The manager is not available on this host: mpm selected nothing.
            if result.exit_code == 2:
                assert not result.stdout
                assert "critical: No manager selected.\n" in result.stderr
                continue

            # npm, cargo, and winget installs are flaky on the CI runners: they
            # depend on live registries (npm, crates.io, the winget community
            # source) plus a healthy toolchain, and regularly surface transient
            # failures. Accept exit 1 like test_single_manager_upgrade_all does
            # for the same reason; the check_manager_selection below still
            # asserts mpm dispatched to the manager.
            if manager_id in {"cargo", "npm", "winget"}:
                assert result.exit_code in (0, 1)
            else:
                assert result.exit_code == 0
            self.check_manager_selection(
                result,
                {manager_id},
                reference_set=pool.all_manager_ids,
                strict_selection_match=False,
            )
