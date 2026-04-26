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

import importlib.metadata
import json
import re
import sys
from functools import cached_property
from pathlib import Path

from extra_platforms import ALL_PLATFORMS

from ..base import PackageManager
from ..capabilities import search_capabilities, version_not_implemented

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Iterator

    from ..base import Package
    from ..version import TokenizedString


class Pip(PackageManager):
    """We will use the Python binary to call out ``pip`` as a module instead of a CLI.

    This is a more robust way of managing packages: "if you're on Windows there
    is an added benefit to using `python -m pip` as it lets `pip` update itself."
    Source: https://snarky.ca/why-you-should-use-python-m-pip/

    .. note::

        All operations target the default pip scope (system site-packages, or the
        active virtualenv). Per-scope targeting (system vs user vs venv) and
        multi-binary discovery (e.g. multiple pythons via pyenv) are tracked in
        :issue:`1725`.
    """

    homepage_url = "https://pip.pypa.io"

    platforms = ALL_PLATFORMS

    requirement = ">=10.0.0"

    _SEARCH_REGEXP = re.compile(
        r"""
        ^(?P<package_id>\S+)  # A string with a char at least.
        \                     # A space.
        \((?P<version>.*?)\)  # Content between parenthesis.
        [ ]+-                 # A space or more, then a dash.
        (?P<description>      # Start of the multi-line desc group.
            (?:[ ]+.*\s)+     # Lines of strings prefixed by spaces.
        )
        """,
        re.MULTILINE | re.VERBOSE,
    )

    # Targets `python3` CLI first to allow for some systems (like macOS) to keep the
    # default `python` CLI tied to the Python 2.x ecosystem.
    cli_names = ("python3", "python")

    pre_args = (
        "-m",
        "pip",  # Canonical call to Python's pip module.
        "--no-color",  # Suppress colored output.
    )

    version_cli_options = (*pre_args, "--version")
    version_regexes = (r"pip\s+(?P<version>\S+)",)
    """
    .. code-block:: shell-session

        $ python -m pip --no-color --version
        pip 2.0.2 from /usr/local/lib/python/site-packages/pip (python 3.7)
    """

    def search_all_cli(
        self,
        cli_names: Iterable[str],
        env=None,
    ) -> Generator[Path, None, None]:
        """Prepend the current Python executable to the list of found binaries.

        .. todo::

            Evaluate `pythonfinder <https://github.com/sarugaku/pythonfinder>`_ to
            replace our custom search logic.
        """
        # Get current Python executable.
        current_python = None
        current_exec = sys.executable
        if current_exec:
            current_python = Path(current_exec)
            yield current_python

        # Return the rest of the Python executables found on the system as usual.
        for py_path in super().search_all_cli(cli_names=cli_names, env=env):
            # Do not yield the current Python executable twice.
            if current_python and py_path != current_python:
                yield py_path

    @cached_property
    def version(self) -> TokenizedString | None:
        """Print Python's own version before Pip's.

        This gives much more context to the user about the environment when a Python
        executable is found but Pip is not.

        Runs:

            .. code-block:: shell-session
                $ python --version --version
                Python 3.10.10 (Feb  8 2023, 05:34) [Clang 14.0.0 (clang-1400.0.29.202)]
        """
        if self.executable:
            self.run_cli(
                ("--version", "--version"),
                auto_pre_cmds=False,
                auto_pre_args=False,
                auto_post_args=False,
                force_exec=True,
            )

        # XXX The sentence below gets modernized with `super().version` by ruff.
        # See: https://beta.ruff.rs/docs/rules/#pyupgrade-up
        # But we're explicitly using the old syntax to bypass `cached_property`.
        return super(Pip, self).version  # noqa: UP008

    @property
    def installed(self) -> Iterator[Package]:
        """Fetch installed packages.

        .. code-block:: shell-session

            $ python -m pip --no-color list --format=json --verbose --quiet \
            > | jq
            [
             {
                "version": "1.3",
                "name": "backports.functools-lru-cache",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": "pip"
              },
              {
                "version": "0.9999999",
                "name": "html5lib",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": "pip"
              },
              {
                "name": "setuptools",
                "version": "46.0.0",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": ""
              },
              {
                "version": "2.8",
                "name": "Jinja2",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": ""
              },
              (...)
            ]
        """
        # --quiet is required here to silence warning and error messages
        # mangling the JSON content.
        output = self.run_cli(
            "list", "--format=json", "--verbose", "--quiet", must_succeed=True
        )

        if output:
            for package in json.loads(output):
                yield self.package(
                    id=package["name"],
                    installed_version=package["version"],
                )

    @staticmethod
    def _own_dependency_names() -> frozenset[str]:
        """Collect :pep:`503`-normalized names of all packages in
        ``meta-package-manager``'s dependency tree.

        ``pip list --not-required`` is supposed to filter transitive
        dependencies, but it relies on ``Requires-Dist`` metadata in each
        installed distribution to reconstruct the dependency graph. Homebrew's
        Python formula packaging breaks this assumption: each dependency is
        declared as an independent ``resource`` block in the formula and
        ``pip install``-ed individually into the formula's virtualenv. Because
        each resource is installed in isolation, pip never sees that (for
        example) ``lxml`` is required by ``jsonschema[format-nongpl]`` which is
        required by ``cyclonedx-python-lib[validation]`` which is required by
        ``meta-package-manager``. From pip's perspective every resource looks
        like a top-level package, so ``--not-required`` lets them through and
        they all appear as outdated.

        When ``meta-package-manager`` is installed via ``uv`` or ``pip``
        directly the metadata is intact and ``--not-required`` filters
        correctly. The tree walk is gated on the ``INSTALLER`` dist-info
        record: only installations attributed to ``pip`` (which includes
        Homebrew's internal pip) trigger the walk. Modern installers like
        ``uv`` write their own installer tag, so the walk is skipped entirely
        in those environments.

        The walk starts at ``meta-package-manager`` and recursively collects
        every reachable dependency name via ``importlib.metadata``. If the
        distribution is not found (running from source without installing),
        the method returns an empty set and the filter is skipped.

        See :issue:`1767`.
        """
        # Only Homebrew-style pip installations break --not-required metadata.
        # Modern installers (uv, poetry, etc.) preserve Requires-Dist and are
        # identified by their INSTALLER tag, so we skip the walk for them.
        try:
            mpm_dist = importlib.metadata.distribution("meta-package-manager")
        except importlib.metadata.PackageNotFoundError:
            return frozenset()
        installer = (mpm_dist.read_text("INSTALLER") or "").strip().lower()
        if installer != "pip":
            return frozenset()

        seen: set[str] = set()
        queue = ["meta-package-manager"]
        while queue:
            raw_name = queue.pop()
            # PEP 503 normalization: lowercase, collapse separator runs.
            normalized = re.sub(r"[-_.]+", "-", raw_name).lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            try:
                dist = importlib.metadata.distribution(raw_name)
            except importlib.metadata.PackageNotFoundError:
                continue
            for req_str in dist.requires or []:
                match = re.match(r"[A-Za-z0-9][-A-Za-z0-9_.]*", req_str)
                if match:
                    queue.append(match.group())
        # Keep only dependencies; mpm itself should still appear if outdated.
        seen.discard("meta-package-manager")
        return frozenset(seen)

    @property
    def outdated(self) -> Iterator[Package]:
        """Fetch outdated packages.

        .. note::

            The ``--not-required`` flag filters out transitive dependencies,
            restricting results to top-level packages only. Upgrading transitive
            dependencies can break version constraints of their parent packages.
            See :issue:`1214`.

        .. caution::

            Results are additionally filtered against ``meta-package-manager``'s
            own dependency tree to suppress false positives caused by Homebrew's
            per-resource installation layout. See
            :py:meth:`_own_dependency_names` and :issue:`1767`.

        .. code-block:: shell-session

            $ python -m pip --no-color list --format=json --outdated \
            > --not-required --verbose --quiet | jq
            [
              {
                "latest_filetype": "wheel",
                "version": "0.7.9",
                "name": "alabaster",
                "latest_version": "0.7.10",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": "pip"
              },
              {
                "latest_filetype": "wheel",
                "version": "0.9999999",
                "name": "html5lib",
                "latest_version": "0.999999999",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": "pip"
               },
              {
                "latest_filetype": "wheel",
                "version": "2.8",
                "name": "Jinja2",
                "latest_version": "2.9.5",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": "pip"
               },
              {
                "latest_filetype": "wheel",
                "version": "0.5.3",
                "name": "mccabe",
                "latest_version": "0.6.1",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": "pip"
               },
              {
                "latest_filetype": "wheel",
                "version": "2.2.0",
                "name": "pycodestyle",
                "latest_version": "2.3.1",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": "pip"
               },
              {
                "latest_filetype": "wheel",
                "version": "2.1.3",
                "name": "Pygments",
                "latest_version": "2.2.0",
                "location": "/usr/local/lib/python3.7/site-packages",
                "installer": ""
               }
            ]
        """
        # --quiet is required here to silence warning and error messages
        # mangling the JSON content.
        output = self.run_cli(
            "list",
            "--format=json",
            "--outdated",
            "--not-required",
            "--verbose",
            "--quiet",
            must_succeed=True,
        )

        if output:
            own_deps = self._own_dependency_names()
            for package in json.loads(output):
                pkg_name = package["name"]
                # Skip packages that belong to mpm's own dependency tree.
                if re.sub(r"[-_.]+", "-", pkg_name).lower() in own_deps:
                    continue
                yield self.package(
                    id=pkg_name,
                    installed_version=package["version"],
                    latest_version=package["latest_version"],
                )

    @search_capabilities(extended_support=False, exact_support=False)
    def search_xxx_disabled(
        self,
        query: str,
        extended: bool,
        exact: bool,
    ) -> Iterator[Package]:
        """Fetch matching packages.

        .. warning::
            That function was previously named ``search`` but has been renamed
            to make it invisible from the ``mpm`` framework, disabling search
            feature altogether for ``pip``.

            This had to be done has Pip's maintainers disabled the server-side
            API because of unmanageable high-load. See:
            https://github.com/pypa/pip/issues/5216#issuecomment-744605466

        .. caution::
            Search is extended by default. So we returns the best subset of results and
            let :py:meth:`meta_package_manager.base.PackageManager.refiltered_search`
            refine them

        .. code-block:: shell-session

            $ python -m pip --no-color search abc
            ABC (0.0.0)                 - UNKNOWN
            micropython-abc (0.0.1)     - Dummy abc module for MicroPython
            abc1 (1.2.0)                - a list about my think
            abcd (0.3.0)                - AeroGear Build Cli for Digger
            abcyui (1.0.0)              - Sorry ,This is practice!
            astroabc (1.4.2)            - A Python implementation of an
                                          Approximate Bayesian Computation
                                          Sequential Monte Carlo (ABC SMC)
                                          sampler for parameter estimation.
            collective.js.abcjs (1.10)  - UNKNOWN
            cosmo (1.0.5)               - Python ABC sampler
        """
        output = self.run_cli("search", query)

        for package_id, version, description in self._SEARCH_REGEXP.findall(output):
            yield self.package(
                id=package_id,
                description=description,
                latest_version=version,
            )

    @version_not_implemented
    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package.

        .. code-block:: shell-session

            $ python -m pip --no-color install arrow
            Collecting arrow
              Using cached arrow-1.1.1-py3-none-any.whl (60 kB)
            Collecting python-dateutil>=2.7.0
              Using cached python_dateutil-2.8.2-py2.py3-none-any.whl (247 kB)
            Requirement already satisfied: six>=1.5 in python3.9/site-packages (1.16.0)
            Installing collected packages: python-dateutil, arrow
            Successfully installed arrow-1.1.1 python-dateutil-2.8.2
        """
        return self.run_cli("install", package_id)

    @version_not_implemented
    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Generates the CLI to upgrade the package provided as parameter.

        .. code-block:: shell-session

            $ python -m pip --no-color install --upgrade six
            Collecting six
              Using cached six-1.15.0-py2.py3-none-any.whl (10 kB)
            Installing collected packages: six
              Attempting uninstall: six
                Found existing installation: six 1.14.0
                Uninstalling six-1.14.0:
                  Successfully uninstalled six-1.14.0
            Successfully installed six-1.15.0

        .. note::

            Pip lacks support of a proper full upgrade command. Raising an error let the
            parent class upgrade packages one by one.

            See: https://github.com/pypa/pip/issues/59
        """
        return self.build_cli("install", "--upgrade", package_id)

    def remove(self, package_id: str) -> str:
        """Remove one package.

        .. code-block:: shell-session

            $ python -m pip --no-color uninstall --yes arrow
        """
        return self.run_cli("uninstall", "--yes", package_id)

    def cleanup(self) -> None:
        """Removes things we don't need anymore.

        .. code-block:: shell-session

            $ python -m pip --no-color cache purge
        """
        self.run_cli("cache", "purge")
