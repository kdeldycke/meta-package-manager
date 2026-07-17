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

from extra_platforms import LINUX_LIKE, MACOS, WINDOWS

from ..capabilities import search_capabilities
from ..manager import PackageManager

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..package import Package


class Conda(PackageManager):
    """Conda cross-language package and environment manager.

    Reads go through conda's ``--json`` mode: installed packages come from
    ``conda list --json`` and search from ``conda search "*query*" --json``.
    conda has no dedicated outdated command, so the upgrade the solver would
    perform is simulated with ``conda update --all --dry-run --json`` and its
    ``UNLINK`` (current) and ``LINK`` (candidate) sets are diffed by name: a
    name in both is an in-place upgrade, while a ``LINK``-only entry is a
    freshly pulled dependency and is not reported.

    .. note::

        Every operation targets conda's *currently active* environment, which is
        ``base`` when none is activated. mpm neither activates nor switches
        environments: it inspects and mutates whatever environment conda resolves
        from the inherited ``CONDA_PREFIX`` / ``CONDA_DEFAULT_ENV``, exactly as a
        bare ``conda`` call in the same shell would. Per-environment targeting is
        not supported yet.

    .. note::

        The ``>=4.6.0`` floor is the release where ``update --dry-run --json``
        settled on an ``actions`` mapping whose ``LINK`` / ``UNLINK`` values are
        package dicts, the shape the outdated diff parses. Much older conda
        wrapped ``actions`` in a list and emitted bare
        ``channel::name-version-build`` strings instead.
    """

    name = "Conda"

    homepage_url = "https://conda.org"

    platforms = LINUX_LIKE, MACOS, WINDOWS

    requirement = ">=4.6.0"
    """``4.6.0`` is a conservative floor. By this release ``conda update
    --dry-run --json`` reports ``actions`` as a single mapping whose ``LINK`` /
    ``UNLINK`` values are lists of package dicts: the exact shape
    :py:meth:`outdated` parses. Much older conda wrapped ``actions`` in a list
    and emitted bare ``channel::name-version-build`` strings instead of dicts,
    which the parser below does not handle. The ``--json`` output of ``list`` and
    ``search`` predates this floor by years.

    See `4.6.0 release
    <https://github.com/conda/conda/releases/tag/4.6.0>`_.
    """

    version_regexes = (r"conda\s+(?P<version>\S+)",)
    """
    .. code-block:: shell-session

        $ conda --version
        conda 24.5.0
    """

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ conda list --json
            [
              {
                "base_url": "https://repo.anaconda.com/pkgs/main",
                "build_number": 0,
                "build_string": "py312hca03da5_0",
                "channel": "pkgs/main",
                "dist_name": "pip-24.0-py312hca03da5_0",
                "name": "pip",
                "platform": "osx-arm64",
                "version": "24.0"
              },
              {
                "base_url": "https://repo.anaconda.com/pkgs/main",
                "build_number": 0,
                "build_string": "py312_0",
                "channel": "pkgs/main",
                "dist_name": "pytz-2024.1-py312_0",
                "name": "pytz",
                "platform": "osx-arm64",
                "version": "2024.1"
              }
            ]
        """
        output = self.run_cli("list", "--json", must_succeed=True)

        data = self.parse_json(output)
        if data:
            for package in data:
                yield self.package(
                    id=package["name"],
                    installed_version=package["version"],
                )

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        There is no dedicated ``conda outdated`` command, so the upgrade the
        solver *would* perform is simulated with ``--dry-run`` and the
        ``UNLINK`` (current) / ``LINK`` (candidate) sets are diffed by name. A
        package appearing in both is an in-place upgrade; one appearing in only
        ``LINK`` is a freshly-pulled dependency and one in only ``UNLINK`` is a
        removal, so neither is reported.

        .. code-block:: shell-session

            $ conda update --all --dry-run --json
            {
              "actions": {
                "FETCH": [],
                "LINK": [
                  {
                    "base_url": "https://repo.anaconda.com/pkgs/main",
                    "build_number": 0,
                    "build_string": "py312_0",
                    "channel": "pkgs/main",
                    "dist_name": "pytz-2024.2-py312_0",
                    "name": "pytz",
                    "platform": "osx-arm64",
                    "version": "2024.2"
                  }
                ],
                "UNLINK": [
                  {
                    "base_url": "https://repo.anaconda.com/pkgs/main",
                    "build_number": 0,
                    "build_string": "py312_0",
                    "channel": "pkgs/main",
                    "dist_name": "pytz-2024.1-py312_0",
                    "name": "pytz",
                    "platform": "osx-arm64",
                    "version": "2024.1"
                  }
                ],
                "PREFIX": "/opt/conda"
              },
              "dry_run": true,
              "prefix": "/opt/conda",
              "success": true
            }

        When the environment is already current, conda omits the ``actions`` key
        entirely:

        .. code-block:: shell-session

            $ conda update --all --dry-run --json
            {
              "message": "All requested packages already installed.",
              "success": true
            }
        """
        output = self.run_cli(
            "update", "--all", "--dry-run", "--json", must_succeed=True
        )

        data = self.parse_json(output)
        actions = data.get("actions") if data else None
        if not actions:
            return

        installed = {pkg["name"]: pkg["version"] for pkg in actions.get("UNLINK", ())}
        for pkg in actions.get("LINK", ()):
            # Only a name present in both sets is an in-place upgrade. A LINK-only
            # entry is a new dependency the upgrade would pull in, not an outdated
            # package.
            if pkg["name"] in installed:
                yield self.package(
                    id=pkg["name"],
                    installed_version=installed[pkg["name"]],
                    latest_version=pkg["version"],
                )

    @search_capabilities(extended_support=False, exact_support=False)
    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Fetch matching packages.

        .. caution::
            Search does not support extended or exact matching. The query is
            wrapped in ``*`` wildcards to get the broadest substring match conda
            offers, and
            :py:meth:`meta_package_manager.manager.PackageManager.refiltered_search`
            narrows the results down. conda exposes no package description in its
            search output, so extended matching has nothing to match against.

        conda returns every available build of every matching package, grouped by
        name and sorted by ascending version, so the last record of each group
        carries the latest version.

        .. code-block:: shell-session

            $ conda search "*pytz*" --json
            {
              "pytz": [
                {
                  "arch": null,
                  "build": "py27_0",
                  "build_number": 0,
                  "channel": "https://repo.anaconda.com/pkgs/main/osx-arm64",
                  "name": "pytz",
                  "version": "2013b"
                },
                {
                  "arch": null,
                  "build": "py312_0",
                  "build_number": 0,
                  "channel": "https://repo.anaconda.com/pkgs/main/osx-arm64",
                  "name": "pytz",
                  "version": "2024.1"
                }
              ]
            }
        """
        output = self.run_cli("search", f"*{query}*", "--json")

        data = self.parse_json(output)
        if data:
            # A query matching nothing is reported as a non-zero exit carrying an
            # error payload ({"error": ..., "exception_name":
            # "PackagesNotFoundError"}) rather than an empty object, so skip any
            # value that is not a build list.
            for package_id, builds in data.items():
                if isinstance(builds, list) and builds:
                    yield self.package(
                        id=package_id,
                        latest_version=builds[-1]["version"],
                    )

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package, optionally pinned to a version.

        conda accepts a ``MatchSpec`` so the version is appended with ``=``.

        .. code-block:: shell-session

            $ conda install --yes pytz

            ## Package Plan ##

              environment location: /opt/conda

              added / updated specs:
                - pytz

            Preparing transaction: done
            Verifying transaction: done
            Executing transaction: done

        .. code-block:: shell-session

            $ conda install --yes pytz=2024.1
        """
        spec = package_id if version is None else f"{package_id}={version}"
        return self.run_cli("install", "--yes", spec)

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Generate the CLI to upgrade all packages.

        .. code-block:: shell-session

            $ conda update --all --yes
        """
        return self.build_cli("update", "--all", "--yes")

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generate the CLI to upgrade a single package, optionally to a version.

        .. code-block:: shell-session

            $ conda update --yes pytz

        .. code-block:: shell-session

            $ conda update --yes pytz=2024.2
        """
        spec = package_id if version is None else f"{package_id}={version}"
        return self.build_cli("update", "--yes", spec)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ conda remove --yes pytz

            ## Package Plan ##

              environment location: /opt/conda

              removed specs:
                - pytz

            Preparing transaction: done
            Verifying transaction: done
            Executing transaction: done
        """
        return self.run_cli("remove", "--yes", package_id)

    def cleanup(self) -> None:
        """Removes tarballs, unused packages and index caches.

        .. code-block:: shell-session

            $ conda clean --all --yes
            Will remove 42 (123.4 MB) tarball(s).
            Will remove 1 index cache(s).
            Will remove 7 (45.6 MB) package(s).
        """
        self.run_cli("clean", "--all", "--yes")
