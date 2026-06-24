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
            driven anyway, capped at ``SHORT_FAILURE_TIMEOUT`` and asserted to fail the
            *expected* way. The install runs at ``--verbosity DEBUG`` because the raw
            tool error mpm surfaces is logged at ``DEBUG``. The follow-up ``remove`` is
            an idempotent no-op (the failed install left nothing to remove), so it only
            asserts a clean exit, not a dispatch.
        """
        blocker = INSTALL_REMOVE_BLOCKERS.get(manager_id)
        blocked_here = bool(blocker and blocker[0]())
        # The substring the blocked install's DEBUG stderr must contain (None for an
        # inert manager that no-ops to a clean exit). Only consulted when blocked_here.
        install_signal = blocker[1] if blocker else None

        for command in ("install", "remove"):
            if blocked_here:
                result = invoke(
                    f"--{manager_id}",
                    "--verbosity",
                    "DEBUG",
                    "--timeout",
                    str(SHORT_FAILURE_TIMEOUT),
                    command,
                    package_id,
                )
            else:
                result = invoke(f"--{manager_id}", command, package_id)

            # The manager is not available on this host: mpm selected nothing. This
            # supersedes any blocker expectation, which only applies once the manager
            # is present and reaches its (doomed) install.
            if result.exit_code == 2:
                assert not result.stdout
                assert "critical: No manager selected.\n" in result.stderr
                continue

            if blocked_here:
                if command == "install":
                    if install_signal is None:
                        # An inert package that no-ops to a clean exit (fwupd).
                        assert result.exit_code == 0
                    else:
                        assert result.exit_code == 1
                        assert install_signal in result.stderr, (
                            f"{manager_id} install: expected {install_signal!r} in "
                            f"stderr, got:\n{result.stderr}"
                        )
                    self.check_manager_selection(
                        result,
                        {manager_id},
                        reference_set=pool.all_manager_ids,
                        strict_selection_match=False,
                    )
                else:
                    # remove after a failed install is a no-op: nothing got installed,
                    # so mpm removes nothing and exits cleanly without dispatching.
                    assert result.exit_code == 0
                continue

            # npm and cargo installs are flaky on the CI runners: they depend on
            # the live npm registry and crates.io plus a healthy toolchain, and
            # regularly surface transient failures. Accept exit 1 like
            # test_single_manager_upgrade_all does for the same reason; the
            # check_manager_selection below still asserts mpm dispatched to the
            # manager.
            if manager_id in {"cargo", "npm"}:
                assert result.exit_code in (0, 1)
            else:
                assert result.exit_code == 0
            self.check_manager_selection(
                result,
                {manager_id},
                reference_set=pool.all_manager_ids,
                strict_selection_match=False,
            )
