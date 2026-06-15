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

import email.message
import importlib.metadata
import json
import re
import sys
from functools import cached_property
from pathlib import Path
from typing import cast

from extra_platforms import ALL_PLATFORMS

from ..capabilities import search_capabilities, version_not_implemented
from ..manager import PackageManager
from ..package import (
    EMPTY_METADATA,
    Dependency,
    DependencyScope,
    Originator,
    PackageMetadata,
    Supplier,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Iterator

    from ..package import Package
    from ..version import TokenizedString


_DEP_SPEC_SPLIT_REGEX = re.compile(
    r"^(?P<name>[A-Za-z0-9_.\-]+)(?P<extras>\[[^\]]+\])?(?P<rest>.*)$"
)


def _split_dep_spec(spec: str) -> tuple[str, str, str]:
    """Split a :pep:`508` requirement string into (name, extras, rest).

    Example: ``"cryptography[ssh]>=42"`` → ``("cryptography", "[ssh]", ">=42")``.
    Used by :py:meth:`Pip._distribution_metadata` to extract just the
    dependency name for relationship resolution while preserving the
    version constraint as portable metadata.
    """
    match = _DEP_SPEC_SPLIT_REGEX.match(spec.strip())
    if not match:
        return "", "", ""
    return match["name"], match["extras"] or "", match["rest"].strip()


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

    name = "Python pip"

    homepage_url = "https://pip.pypa.io"

    platforms = ALL_PLATFORMS

    requirement = ">=26.1.0"
    """`26.1 <https://github.com/pypa/pip/releases/tag/26.1>`_ is the first version to
    ship ``--uploaded-prior-to``, the release-age gate mpm uses for the supply-chain
    cooldown (see :py:attr:`cooldown_env_var`). Older pip releases silently ignore
    ``PIP_UPLOADED_PRIOR_TO``, so the floor avoids advertising a gate that does
    nothing.
    """

    cooldown_env_var = "PIP_UPLOADED_PRIOR_TO"
    """pip honors a release-age cooldown through its ``--uploaded-prior-to`` resolver
    option.

    pip maps any ``PIP_<UPPER_SNAKE>`` environment variable to a config setting, so
    ``PIP_UPLOADED_PRIOR_TO`` sets the option without touching the user's ``pip.conf``.
    The flag excludes from resolution any distribution uploaded after the given
    instant, which covers ``install`` and ``upgrade`` (with transitive dependencies).
    pip parses the RFC 3339 timestamp produced by the default
    :py:meth:`meta_package_manager.execution.CLIExecutor.cooldown_env_value`.

    See https://github.com/pypa/pip/issues/13674.
    """

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

    def package_metadata_batch(
        self,
        packages: Iterable[Package],
    ) -> Iterator[tuple[Package, PackageMetadata]]:
        """Enrich installed pip packages via :py:mod:`importlib.metadata`.

        Each installed distribution exposes its ``METADATA`` file (the
        ``Core Metadata`` from :pep:`621`) plus ``RECORD``, ``WHEEL``,
        and ``INSTALLER`` files in its ``.dist-info`` directory. This
        method reads them in-process: no shell-outs, no network, fast
        enough to enumerate hundreds of distributions in a fraction of a
        second.

        Maps ``Home-page`` / ``Project-URL`` lines into the portable
        ``homepage`` / ``vcs_url`` / ``issue_tracker_url`` slots, walks
        ``Requires-Dist`` into typed :py:class:`meta_package_manager.package.Dependency`
        edges, and promotes the upstream author or maintainer to
        :py:class:`meta_package_manager.package.Originator`.
        """
        package_list = list(packages)
        if not package_list:
            return

        for package in package_list:
            try:
                dist = importlib.metadata.distribution(package.id)
            except importlib.metadata.PackageNotFoundError:
                yield package, EMPTY_METADATA
                continue
            try:
                yield package, self._distribution_metadata(dist)
            except Exception:  # noqa: BLE001
                yield package, EMPTY_METADATA

    @staticmethod
    def _distribution_metadata(
        dist: importlib.metadata.Distribution,
    ) -> PackageMetadata:
        """Translate an ``importlib.metadata.Distribution`` into
        :py:class:`PackageMetadata`.
        """
        # ``Distribution.metadata`` returns an ``email.message.Message`` at
        # runtime, but the typeshed protocol omits ``.get()`` on the older
        # Python versions we still support.
        meta = cast("email.message.Message", dist.metadata)

        homepage = meta.get("Home-page") or None
        vcs_url = None
        issue_tracker_url = None
        # PEP 621 split the legacy Home-page header into the Project-URL
        # multi-value field with a ``label, url`` payload. The exact
        # labels vary across PyPI projects, so match on conventional
        # substrings while staying case-insensitive.
        for raw in meta.get_all("Project-URL") or ():
            if "," not in raw:
                continue
            label, _, url = raw.partition(",")
            label_key = label.strip().lower()
            url = url.strip()
            if not url:
                continue
            if not homepage and label_key in {"home", "homepage", "documentation"}:
                homepage = url
            if not vcs_url and label_key in {
                "source",
                "repository",
                "source code",
                "code",
                "github",
            }:
                vcs_url = url
            if not issue_tracker_url and label_key in {
                "issues",
                "issue tracker",
                "bug tracker",
                "tracker",
                "bugs",
            }:
                issue_tracker_url = url

        license_str = meta.get("License") or None
        if license_str and "\n" in license_str:
            # Some projects dump the full license text here. Truncate to
            # the first line so the SPDX parser has a fighting chance.
            license_str = license_str.splitlines()[0].strip()

        author_name = meta.get("Author") or meta.get("Maintainer") or None
        author_email = meta.get("Author-email") or meta.get("Maintainer-email") or None
        originator = None
        if author_name:
            # ``Author-email`` can carry a ``"Name <email>"`` payload.
            email_match = None
            if author_email and "<" in author_email and ">" in author_email:
                email_match = author_email.split("<", 1)[1].split(">", 1)[0].strip()
            elif author_email:
                email_match = author_email
            originator = Originator(name=author_name, email=email_match)

        # Requires-Dist lines look like ``cryptography>=42.0; python_version<'3.13'``.
        # Strip environment markers and version constraints to land just
        # the dependency name in ``target_id``; the version_constraint
        # column carries the rest for any downstream consumer that wants
        # it.
        deps: list[Dependency] = []
        for raw in meta.get_all("Requires-Dist") or ():
            if ";" in raw:
                spec, _, _marker = raw.partition(";")
            else:
                spec = raw
            spec = spec.strip()
            name, _, constraint = _split_dep_spec(spec)
            if name:
                deps.append(
                    Dependency(
                        target_id=name,
                        scope=DependencyScope.RUNTIME,
                        version_constraint=constraint or None,
                    )
                )

        extras: dict[str, object] = {}
        for keyword_header in ("Keywords",):
            value = meta.get(keyword_header)
            if value:
                extras[f"pip.{keyword_header.lower()}"] = value
        classifiers = meta.get_all("Classifier") or ()
        if classifiers:
            extras["pip.classifiers"] = list(classifiers)

        return PackageMetadata(
            download_url=meta.get("Download-URL") or None,
            homepage=homepage,
            vcs_url=vcs_url,
            issue_tracker_url=issue_tracker_url,
            license_declared=license_str,
            license_concluded=license_str,
            supplier=Supplier(name="PyPI", url="https://pypi.org"),
            originator=originator,
            summary=meta.get("Summary") or None,
            description=meta.get("Summary") or None,
            dependencies=tuple(deps),
            extras=extras,
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
        example) ``defusedxml`` is required by ``py-serializable`` which is
        required by ``cyclonedx-python-lib`` which is required by
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
            per-resource installation layout. See ``_own_dependency_names()``
            and :issue:`1767`.

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
            let :py:meth:`meta_package_manager.manager.PackageManager.refiltered_search`
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
