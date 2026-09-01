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
from functools import cached_property

from extra_platforms import ALL_PLATFORMS

from ..execution import VERSION_PROBE
from ..manager import PackageManager
from ..version import parse_version

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package
    from ..version import TokenizedString


class Roswell(PackageManager):
    """Roswell, a Common Lisp implementation installer and launcher.

    ```{important}
    A roswell package is a **Lisp implementation**, not a Lisp library. `ros
    install` accepts both an implementation and a Quicklisp system, but `ros
    list installed` answers for implementations alone: a system installed with
    `ros install cl-ppcre` never appears there. The two verbs disagree on their
    object, and this wrap resolves it the way {class}`~meta_package_manager.managers.rustup.RustUp`
    resolves the same question, by narrowing to what the listing can enumerate.
    ```

    ```{caution}
    `remove` is deliberately absent. `ros delete <impl>` reports success on
    every channel that matters, exiting `0` with `sbcl-bin was deleted
    successfully.` and an empty `<stderr>`, and leaves roswell unusable: its own
    runtime core was built against the implementation just deleted, so every
    later subcommand answers `<impl>/<version> does not exist.stop.`. Recovery
    means deleting `~/.roswell` and running `ros setup` again, `ros config set`
    being just as broken as the rest. mpm will not drive a removal that reports
    success and breaks the tool.
    ```

    ```{caution}
    `upgrade` is absent for the same reason `remove` is, one level up: `ros
    update` resolves its argument through `asdf:find-system`, so it upgrades
    Quicklisp systems, never the implementations {meth}`installed` reports.
    Mapping it here would upgrade something other than what mpm just listed.
    ```

    Documentation: [Roswell wiki](https://github.com/roswell/roswell/wiki).
    """

    name = "Roswell"

    homepage_url = "https://roswell.github.io/"
    logo = "commonlisp"

    platforms = ALL_PLATFORMS

    requirement = ">=22.12.14.113"
    """The oldest release whose listing this parser was checked against.

    `lisp/list-installed.lisp` is byte-identical from there through the current
    `26.02.116`, the `*error-output*` header included, so the shape below is not
    a property of the release that happened to be driven.
    """

    cli_names = ("ros",)

    _INSTALLED_REGEXP = re.compile(
        r"^(?P<package_id>[^/\s]+)/(?P<installed_version>\S+)$",
    )

    version_regexes = (r"roswell\s+(?P<version>[^\s(]+)",)
    """The trailing `(NO-GIT-REVISION)` is left out of the capture: it names the
    build, not the version, and a release tarball carries it in place of a
    commit.

    ```{code-block} shell-session

    $ ros --version
    roswell 26.02.116(NO-GIT-REVISION)
    ```
    """

    @cached_property
    def version(self) -> TokenizedString | None:
        """Parse the version off `<stderr>`, where roswell alone prints it.

        Both `ros --version` and `ros version` leave `<stdout>` empty and write
        to `<stderr>`, measured at 0 and 35 bytes respectively. The inherited
        probe reads the return value of
        {meth}`~meta_package_manager.execution.CLIExecutor.run_cli`, which is
        `<stdout>`, so it would find nothing and leave the manager permanently
        unavailable. The streams are reached through
        {attr}`~meta_package_manager.execution.CLIExecutor._last_run` instead,
        the same attribute `bin` and `gext` read for their own
        `<stderr>`-reporting operations.
        """
        if not self.executable:
            return None

        # Matches the inherited probe: a version check is a read-only liveness
        # test, so it takes the short timeout rather than the mutating one.
        self._active_operation = VERSION_PROBE
        output = self.run_cli(
            self.version_cli_options,
            auto_pre_cmds=False,
            auto_pre_args=False,
            auto_post_args=False,
            force_exec=True,
        )

        # Both streams are searched rather than `<stderr>` alone: roswell prints
        # there today, and a version that moved to `<stdout>` would otherwise
        # take the manager offline for no reason.
        error = self._last_run[2] if self._last_run else ""
        haystack = "\n".join(stream for stream in (output, error) if stream)

        for regex in self.version_regexes:
            match = re.compile(regex, re.MULTILINE).search(haystack)
            if match:
                version_string = match.groupdict().get("version")
                if version_string:
                    return parse_version(version_string)
        return None

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed Lisp implementations.

        Only the rows reach `<stdout>`; roswell prints its headings to
        `<stderr>`, so the payload arrives with no furniture to skip.

        An implementation is listed once per installed version, so the rows are
        reduced to the newest version of each.

        ```{caution}
        An empty listing is not proof of an empty machine. Roswell answers
        `0` with nothing on `<stdout>` and its diagnosis on `<stderr>` alone
        once it can no longer resolve the implementation it runs on, which a
        `ros delete` of the wrong version is enough to cause. `must_succeed`
        cannot catch that, keying on the exit code, so the two streams are
        compared instead and a silent failure is raised rather than reported as
        zero packages.
        ```

        ```{code-block} shell-session

        $ ros list installed
        sbcl-bin/2.6.8
        ```
        """
        output = self.run_cli("list", "installed")

        if not output.strip():
            _code, _stdout, error = self._last_run or (0, "", "")
            if error.strip():
                msg = (
                    "Roswell reported no installed implementation while writing "
                    f"to <stderr>, so the listing is unreliable: {error.strip()}"
                )
                raise RuntimeError(msg)

        newest: dict[str, str] = {}
        for match in map(self._INSTALLED_REGEXP.match, output.splitlines()):
            if not match:
                continue
            package_id = match.group("package_id")
            installed_version = match.group("installed_version")
            current = newest.get(package_id)
            if current is not None and parse_version(
                installed_version,
            ) <= parse_version(current):
                continue
            newest[package_id] = installed_version

        for package_id, installed_version in newest.items():
            yield self.package(id=package_id, installed_version=installed_version)

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one Lisp implementation.

        A version is appended to the implementation with a slash, the same
        `impl/version` spelling {meth}`installed` reports.

        ```{code-block} shell-session

        $ ros install sbcl-bin
        ```

        ```{code-block} shell-session

        $ ros install sbcl-bin/2.6.8
        ```
        """
        return self.run_cli(
            "install",
            f"{package_id}/{version}" if version else package_id,
        )
