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
"""In-memory package manager for CLI plumbing tests.

Real-manager iteration leaks the host environment into the test suite: a
runner without `apk` skips it, a runner without `brew` skips it, and
assertions about package counts or table rendering become a function of which
binaries happen to be on PATH. The {class}`~tests.fake_manager.FakeManager` below sidesteps
that by reporting as available on every platform and yielding a fixed catalog
of packages without ever invoking a subprocess.

Tests opt in via the `fake_pool` fixture in {mod}`tests.conftest`, which
monkeypatches {meth}`meta_package_manager.pool.ManagerPool.select_managers`
to yield a single fake instead of the real-manager iteration.
"""

from __future__ import annotations

import sys
from functools import cached_property
from pathlib import Path
from typing import ClassVar

from extra_platforms import ALL_PLATFORMS

from meta_package_manager.execution import CLIError
from meta_package_manager.manager import PackageManager
from meta_package_manager.version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from meta_package_manager.package import Package
    from meta_package_manager.version import TokenizedString


class FakeManager(PackageManager):
    """Always-available manager with deterministic outputs.

    Reports as supported on every platform and short-circuits the
    discovery properties ({attr}`cli_path`, {attr}`executable`,
    {attr}`fresh`, {attr}`version`) so the pool never tries to
    introspect a real binary. Subcommand methods yield fixed package
    sets so tests can assert on counts and ordering.
    """

    homepage_url = "https://example.invalid/fake-manager"
    platforms = ALL_PLATFORMS
    cli_names = ("fake-mpm",)
    requirement = ">=0"

    @cached_property
    def cli_path(self) -> Path:
        return Path(sys.executable)

    @cached_property
    def executable(self) -> bool:
        return True

    @cached_property
    def fresh(self) -> bool:
        return True

    @cached_property
    def version(self) -> TokenizedString | None:
        return parse_version("1.0.0")

    @property
    def installed(self) -> Iterator[Package]:
        yield self.package(id="fake-pkg-alpha", installed_version="1.0.0")
        yield self.package(id="fake-pkg-beta", installed_version="2.5.3")

    @property
    def outdated(self) -> Iterator[Package]:
        yield self.package(
            id="fake-pkg-alpha",
            installed_version="1.0.0",
            latest_version="1.1.0",
        )

    @property
    def orphans(self) -> Iterator[Package]:
        yield self.package(id="fake-orphan-alpha", installed_version="0.9.1")

    def search(
        self,
        query: str,
        extended: bool,
        exact: bool,
    ) -> Iterator[Package]:
        if "match" in query:
            yield self.package(id=f"matched-{query}", latest_version="1.0.0")

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Static upgrade CLIs declare the upgrade capabilities.

        Never invoked by
        {meth}`meta_package_manager.bar_plugin_renderer.BarPluginRenderer.add_upgrade_cli`,
        which routes menu actions through `mpm` itself, but their presence is what
        makes {func}`meta_package_manager.capabilities.implements` report the
        `upgrade` and `upgrade_all` operations as supported, so the fake manager's
        menu lines carry an action.
        """
        return (str(self.cli_path), "upgrade", "--all")

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        return (str(self.cli_path), "upgrade", package_id)


class ChangingFakeManager(FakeManager):
    """Variant whose inventory changes when a command acts on it.

    Models what the change report reads on a real host. Every operation runs the
    interpreter on a no-op, so it spawns a real subprocess that exits `0`, then
    applies its change to {attr}`inventory`, unless the run only simulates:

    - a full upgrade moves one outdated package, leaves the pinned one behind,
      moves a third package back, pulls a dependency in and drops the orphan;
    - a single-package upgrade moves its package and pulls the same dependency
      in, and leaves the pinned one alone;
    - an install adds its package and that dependency, and fails on an ID that
      contains `broken`;
    - a removal drops its package, and its cascading variant drops the orphan
      too;
    - the orphan sweep drops the orphan.

    A package no operation touches stays in {attr}`inventory` as it is.
    """

    DEPENDENCY = ("fake-pkg-gamma", "0.1.0")
    """The dependency an install or an upgrade pulls in, with its version."""

    LATEST: ClassVar = {"fake-pkg-alpha": "1.1.0", "fake-pkg-beta": "2.6.0"}
    """The outdated packages, each with the version it can move to."""

    ORPHAN = "fake-pkg-epsilon"
    """The package nothing requires, which the orphan sweeps drop."""

    PINNED = "fake-pkg-beta"
    """The outdated package every upgrade leaves behind."""

    def __init__(self) -> None:
        super().__init__()
        self.inventory = {
            "fake-pkg-alpha": "1.0.0",
            "fake-pkg-beta": "2.5.3",
            "fake-pkg-delta": "4.0.0",
            "fake-pkg-epsilon": "5.2.0",
            "fake-pkg-zeta": "3.0.0",
        }
        """The installed version of each package, keyed by package ID."""

    @property
    def _simulating(self) -> bool:
        """Whether the run only simulates, and must leave the inventory alone."""
        return self.dry_run or self.plan

    def _no_op(self) -> str:
        """Run the interpreter on a no-op, as the CLI of each operation."""
        return self.run(str(self.cli_path), "-c", "pass")

    @property
    def installed(self) -> Iterator[Package]:
        for package_id, version in sorted(self.inventory.items()):
            yield self.package(id=package_id, installed_version=version)

    @property
    def outdated(self) -> Iterator[Package]:
        for package_id, latest in self.LATEST.items():
            version = self.inventory.get(package_id)
            if version is not None and version != latest:
                yield self.package(
                    id=package_id, installed_version=version, latest_version=latest
                )

    @property
    def orphans(self) -> Iterator[Package]:
        if self.ORPHAN in self.inventory:
            yield self.package(
                id=self.ORPHAN, installed_version=self.inventory[self.ORPHAN]
            )

    def search(
        self,
        query: str,
        extended: bool,
        exact: bool,
    ) -> Iterator[Package]:
        """Find any package, so an install left untied reaches its attempt."""
        yield self.package(id=query, latest_version="1.0.0")

    def install(self, package_id: str, version: str | None = None) -> str:
        if "broken" in package_id:
            raise CLIError(1, "", f"No {package_id} package available.")
        output = self._no_op()
        if not self._simulating:
            self.inventory[package_id] = version or "1.0.0"
            self.inventory.setdefault(*self.DEPENDENCY)
        return output

    def upgrade_all_cli(self) -> tuple[str, ...]:
        return (str(self.cli_path), "-c", "pass")

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        return (str(self.cli_path), "-c", "pass")

    def upgrade(
        self,
        package_id: str | None = None,
        version: str | None = None,
        *,
        outdated_ids: Iterable[str] | None = None,
    ) -> str:
        output = super().upgrade(package_id, version, outdated_ids=outdated_ids)
        if self._simulating:
            return output
        if package_id is None:
            self.inventory["fake-pkg-alpha"] = self.LATEST["fake-pkg-alpha"]
            self.inventory["fake-pkg-zeta"] = "2.9.0"
            self.inventory.pop(self.ORPHAN, None)
            self.inventory.setdefault(*self.DEPENDENCY)
        elif package_id in self.LATEST and package_id != self.PINNED:
            self.inventory[package_id] = self.LATEST[package_id]
            self.inventory.setdefault(*self.DEPENDENCY)
        return output

    def remove(self, package_id: str) -> str:
        output = self._no_op()
        if not self._simulating:
            self.inventory.pop(package_id, None)
        return output

    def remove_orphan(self, package_id: str) -> str:
        output = self.remove(package_id)
        if not self._simulating:
            self.inventory.pop(self.ORPHAN, None)
        return output

    def cleanup_orphan(self) -> None:
        self._no_op()
        if not self._simulating:
            self.inventory.pop(self.ORPHAN, None)


class TimingOutFakeManager(FakeManager):
    """Variant that runs a real subprocess long enough to trip `--timeout`.

    Used by {func}`tests.test_cli.test_timeout` to exercise the
    {exc}`subprocess.TimeoutExpired` branch in
    {meth}`meta_package_manager.execution.CLIExecutor.run`. The Python
    interpreter is invoked as the manager's CLI so the test stays
    cross-platform; the sleep duration is derived from
    {attr}`~meta_package_manager.execution.CLIExecutor.timeout` so the call is
    guaranteed to overshoot.
    """

    @property
    def outdated(self) -> Iterator[Package]:
        sleep_for = max((self.timeout or 1) * 10, 5)
        self.run_cli("-c", f"import time; time.sleep({sleep_for})")
        return iter(())
