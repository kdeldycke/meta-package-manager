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
runner without ``apk`` skips it, a runner without ``brew`` skips it, and
assertions about package counts or table rendering become a function of which
binaries happen to be on PATH. The :py:class:`FakeManager` below sidesteps
that by reporting as available on every platform and yielding a fixed catalog
of packages without ever invoking a subprocess.

Tests opt in via the ``fake_pool`` fixture in :mod:`tests.conftest`, which
monkeypatches :py:meth:`meta_package_manager.pool.ManagerPool.select_managers`
to yield a single fake instead of the real-manager iteration.
"""

from __future__ import annotations

import sys
from functools import cached_property
from pathlib import Path

from extra_platforms import ALL_PLATFORMS

from meta_package_manager.manager import PackageManager
from meta_package_manager.version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from meta_package_manager.package import Package
    from meta_package_manager.version import TokenizedString


class FakeManager(PackageManager):
    """Always-available manager with deterministic outputs.

    Reports as supported on every platform and short-circuits the
    discovery properties (:py:attr:`cli_path`, :py:attr:`executable`,
    :py:attr:`fresh`, :py:attr:`version`) so the pool never tries to
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

    def search(
        self,
        query: str,
        extended: bool,
        exact: bool,
    ) -> Iterator[Package]:
        if "match" in query:
            yield self.package(id=f"matched-{query}", latest_version="1.0.0")


class TimingOutFakeManager(FakeManager):
    """Variant that runs a real subprocess long enough to trip ``--timeout``.

    Used by :func:`tests.test_cli.test_timeout` to exercise the
    :py:exc:`subprocess.TimeoutExpired` branch in
    :py:meth:`meta_package_manager.manager.PackageManager.run`. The Python
    interpreter is invoked as the manager's CLI so the test stays
    cross-platform; the sleep duration is derived from
    :py:attr:`timeout` so the call is guaranteed to overshoot.
    """

    @property
    def outdated(self) -> Iterator[Package]:
        sleep_for = max((self.timeout or 1) * 10, 5)
        self.run_cli("-c", f"import time; time.sleep({sleep_for})")
        return iter(())
