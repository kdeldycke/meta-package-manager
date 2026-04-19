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

import os
import re
import shlex
from pathlib import Path

from click_extra.testing import args_cleanup
from extra_platforms import LINUX_LIKE, MACOS

from ..base import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..base import Package


_SDKMAN_DIR = os.environ.get("SDKMAN_DIR", str(Path.home() / ".sdkman"))
"""Resolve the SDKMAN installation directory from the environment variable or default."""


class SDKMAN(PackageManager):
    """SDKMAN! manages parallel versions of multiple Software Development Kits on
    Unix-based systems.

    .. note::
        SDKMAN! primarily serves the JVM ecosystem: Java, Gradle, Maven,
        Kotlin, Scala, and ~115 other candidates.

    .. caution::
        The ``sdk`` command is a shell function, not a standalone binary. Every
        invocation is wrapped in ``bash -c 'source <init> && sdk <args>'``.
    """

    homepage_url = "https://sdkman.io"

    platforms = LINUX_LIKE, MACOS

    requirement = ">=5.0.0"

    cli_names = ("sdkman-init.sh",)
    """Detect SDKMAN by the presence of its init script."""

    cli_search_path = (str(Path(_SDKMAN_DIR) / "bin"),)

    extra_env = {  # noqa: RUF012
        "sdkman_colour_enable": "false",
        "sdkman_auto_answer": "true",
    }
    """Disable ANSI colors and auto-accept interactive prompts."""

    version_cli_options = ("version",)

    version_regexes = (r"script:\s+(?P<version>\S+)",)
    """
    .. code-block:: shell-session

        $ sdk version
        SDKMAN!
        script: 5.18.2
        native: 0.4.6
    """

    _INSTALLED_REGEXP = re.compile(
        r"^(?P<package_id>\w[\w-]*):\s+(?P<installed_version>\S+)$",
        re.MULTILINE,
    )

    _OUTDATED_REGEXP = re.compile(
        r"^(?P<package_id>\w[\w-]*)"
        r"\s+\(local:\s+(?P<installed_version>[^,;]+)"
        r".*?;\s+default:\s+(?P<latest_version>\S+)\)",
        re.MULTILINE,
    )

    def build_cli(self, *args, **kwargs) -> tuple[str, ...]:
        """Wrap all CLI invocations to source the SDKMAN init script in bash.

        .. note::
            The ``**kwargs`` accepted by the base class (``auto_pre_args``,
            ``sudo``, etc.) are accepted but ignored because every invocation
            goes through the ``bash -c`` wrapper and SDKMAN never requires
            elevated privileges.
        """
        clean_args = args_cleanup(*args)
        sdk_cmd = " ".join(shlex.quote(a) for a in clean_args)
        init_path = shlex.quote(str(self.cli_path))
        return ("bash", "-c", f"source {init_path} && sdk {sdk_cmd}")

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ sdk current
            Using:
            groovy: 4.0.22
            java: 21.0.4-tem
            scala: 3.4.2
        """
        output = self.run_cli("current")
        for match in self._INSTALLED_REGEXP.finditer(output):
            yield self.package(
                id=match.group("package_id"),
                installed_version=match.group("installed_version"),
            )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. code-block:: shell-session

            $ echo n | sdk upgrade
            Available defaults:
            gradle (local: 2.3, 1.11; default: 8.9)
            java (local: 21.0.4-tem; default: 25.0.2-tem)

            Use prescribed default version(s)? (Y/n):

        .. note::
            Pipes ``n`` to ``sdk upgrade`` to obtain the outdated list without
            actually performing the upgrade. Overrides ``sdkman_auto_answer``
            to ``false`` so the command prints the candidate list before
            prompting.
        """
        init_path = shlex.quote(str(self.cli_path))
        output = self.run(
            "bash",
            "-c",
            f"source {init_path} && echo n | sdk upgrade",
            extra_env={
                "sdkman_colour_enable": "false",
                "sdkman_auto_answer": "false",
            },
        )
        for match in self._OUTDATED_REGEXP.finditer(output):
            yield self.package(
                id=match.group("package_id"),
                installed_version=match.group("installed_version"),
                latest_version=match.group("latest_version"),
            )

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ sdk install java 21.0.4-tem
        """
        return self.run_cli("install", package_id, version)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generates the CLI to upgrade all packages.

        .. code-block:: shell-session

            $ sdk upgrade
        """
        return self.build_cli("upgrade")

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade one package.

        .. code-block:: shell-session

            $ sdk upgrade java
        """
        return self.build_cli("upgrade", package_id)

    def sync(self) -> None:
        """Sync package metadata.

        .. code-block:: shell-session

            $ sdk update
        """
        self.run_cli("update")

    def cleanup(self) -> None:
        """Clear SDKMAN caches.

        .. code-block:: shell-session

            $ sdk flush
        """
        self.run_cli("flush")
