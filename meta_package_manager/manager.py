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
"""Abstract base class tying together every package manager definition.

Defines :py:class:`meta_package_manager.manager.PackageManager`, the class each concrete
manager in :py:mod:`meta_package_manager.managers` inherits from, together with its
:py:class:`meta_package_manager.manager.MetaPackageManager` metaclass and the
:py:class:`meta_package_manager.manager.ManagerScope` classification.

A subclass declares its identity (supported platforms, version requirement, deprecation
status) and implements the operations it supports (``installed``, ``outdated``,
``install``, ``upgrade``, ...). The CLI-execution engine it inherits lives in
:py:mod:`meta_package_manager.execution`, the operation vocabulary in
:py:mod:`meta_package_manager.capabilities`, and the package objects operations yield in
:py:mod:`meta_package_manager.package`. On top of the engine, this module adds the
availability policy: whether the manager is supported, fresh, and ready to use.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import ClassVar, cast

from extra_platforms import (
    Group,
    Platform,
    current_platform,
    extract_members,
    traits_from_ids,
)

from .execution import CLIError, CLIExecutor, highlight_cli_name
from .package import EMPTY_METADATA, Package, PackageMetadata
from .version import VersionRange

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

    from .version import TokenizedString


class ManagerScope(Enum):
    """Filesystem scope a package manager operates within."""

    SYSTEM = "system"
    """Manages software installed globally, machine-wide.

    All currently-maintained managers are system-scoped.
    """

    PROJECT = "project"
    """Manages dependencies confined to a project's working tree.

    Not supported yet. See
    :py:meth:`meta_package_manager.manager.PackageManager.discover_projects`.

    .. seealso::
        Microsoft's `Python Environment Tools (PET)
        <https://github.com/microsoft/python-environment-tools>`_ is a Rust tool
        that locates Python environments (venv, conda, pyenv, pipenv, Poetry, uv,
        ...) across a machine. It only discovers environments and does not
        inventory their packages, but is a useful reference and benchmark for
        implementing Python project-scope discovery.
    """


class MetaPackageManager(type):
    """Custom metaclass used as a class factory for package managers."""

    def __init__(cls, name, bases, dct) -> None:
        """Sets some class defaults, but only if they're not redefined in the final
        manager class.

        Also normalize list of platform, by ungrouping groups, deduplicate entries and
        freeze them into a set of unique platforms.
        """
        if "id" not in dct:
            cls.id = name.lower().replace("_", "-")

        if "name" not in dct:
            cls.name = name

        if "cli_names" not in dct:
            cls.cli_names = (cls.id,)

        if "virtual" not in dct:
            cls.virtual = name == "PackageManager" or not cls.cli_names

        if "platforms" in dct:
            cls.platforms = frozenset(extract_members(dct["platforms"]))
            assert all(isinstance(p, Platform) for p in cls.platforms), (
                f"Manager {cls} has invalid entries in its platforms list."
            )


class PackageManager(CLIExecutor, metaclass=MetaPackageManager):
    """Base class from which all package manager definitions inherits."""

    scope: ClassVar[ManagerScope] = ManagerScope.SYSTEM
    """Whether the manager operates on globally-installed software or project-local
    dependencies.

    Defaults to :py:attr:`ManagerScope.SYSTEM`, which covers every manager maintained
    today: they install and query software machine-wide. Project-scoped managers (Poetry,
    Bundler, Maven, ...) resolve dependencies confined to a working tree and are not
    supported yet.
    """

    deprecated: bool = False
    """A manager marked as deprecated is hidden from package selection by default.

    You can still use it by explicitly calling for it on the command line.

    A deprecated manager is exempt from the project stability policy: it may be dropped,
    in part or in full, in any release and without notice, once keeping it working
    becomes too burdensome. Every deprecation must be documented through
    :py:attr:`deprecation_url`.

    Deprecated managers are kept out of the functional and integration test matrices, so
    an unreliable or flaky deprecated manager never blocks a release. The cheap static
    invariants (ID format, attribute ordering, ...) still apply for as long as the
    manager's code lives in the source tree, to keep that code valid.
    """

    deprecation_url: str | None = None
    """Announcement from the official project, or evidence of abandonment of maintenance.

    Required for every manager whose :py:attr:`deprecated` flag is set, and only
    meaningful on such managers. Enforced by ``test_deprecated``.
    """

    id: str
    """Package manager's ID.

    Derived by defaults from the lower-cased class name in which underscores ``_`` are
    replaced by dashes ``-``.

    This ID must be unique among all package manager definitions and lower-case, as
    they're used as feature flags for the :program:`mpm` CLI.
    """

    name: str
    """Return package manager's common name.

    Default value is based on class name.
    """

    homepage_url: str | None = None
    """Home page of the project, only used in documentation for reference."""

    brewfile_entry_type: ClassVar[str | None] = None
    """Name of the Brewfile DSL entry type this manager maps to, or ``None`` if the
    manager has no Brewfile equivalent.

    Set by the subset of managers covered by Homebrew Bundle's DSL (``brew``, ``cask``,
    ``mas``, ``vscode``, ``npm``, ``cargo``, ``uv``, ``winget``, ``flatpak``). Consumed
    by :py:mod:`meta_package_manager.brewfile` when rendering the output of
    ``mpm dump --brewfile``.
    """

    brewfile_skip_warning: ClassVar[str | None] = None
    """Optional stderr warning emitted when this manager's installed packages are
    excluded from a Brewfile dump.

    Set on managers where silently dropping the entries would mislead the user. The
    string supports a single ``{count}`` placeholder for the installed-package count.
    """

    platforms: frozenset[Platform] | Group | Platform | Iterable[Platform | Group] = (
        frozenset()
    )
    """List of platforms supported by the manager.

    Allows for a mishmash of platforms and groups of platforms. Will be normalized into a
    `frozenset` of ``Platform`` instances at instantiation.
    """

    requirement: str | None = None
    """Version requirement specifier.

    Supports a comma-separated range of constraints (e.g. ``">=1.20.0,<2.0.0"``).
    A bare version string like ``"1.20.0"`` is treated as ``>=1.20.0``.

    Parsed by :py:class:`meta_package_manager.version.VersionRange`.

    Defaults to ``None``, which deactivates version check entirely.
    """

    virtual: bool
    """Should we expose the package manager to the user?

    Virtual package manager are just skeleton classes used to factorize code among
    managers of the same family.
    """

    ignore_auto_updates: bool = True
    """Some managers can report or ignore packages which have their own auto-update
    mechanism."""

    _NAME_VERSION_REGEXP: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<package_id>.+)-(?P<version>\d\S*)$",
    )
    """Default ``<package_id>-<version>`` splitter for managers whose listings pack the
    name and version into one dash-joined token (``apk``, ``nix``, ``xbps``).

    The ``.+`` name segment is greedy, so the version starts at the *last* hyphen
    followed by a digit: dashes inside the name (``python3``) stay with the name, while
    trailing ecosystem suffixes (Alpine ``-r<release>``, XBPS ``_<revision>``) stay with
    the version. Managers with a different layout override it (``pkg`` allows a
    non-numeric version lead).
    """

    def package(self, **kwargs) -> Package:
        """Instantiate a ``Package`` object from the manager.

        Sets its ``manage_id`` to the manager it belongs to.
        """
        kwargs.setdefault("manager_id", self.id)
        return Package(**kwargs)

    def brewfile_entry(
        self, package: Package
    ) -> tuple[str, dict[str, object] | None] | None:
        """Return ``(entry_name, entry_options)`` for a Brewfile line, or ``None``
        to skip the package.

        Default: emit :py:attr:`meta_package_manager.package.Package.id` as the entry name with no options.
        Override on managers whose Brewfile DSL counterpart expects a different
        shape: ``mas`` uses the app name with ``id: ADAM_ID``, ``flatpak`` adds
        ``with: ["remote"]``. Only called when :py:attr:`brewfile_entry_type` is
        set.
        """
        return package.id, None

    @cached_property
    def supported(self) -> bool:
        """Is the package manager supported on that platform?"""
        # After metaclass initialization, platforms is always a frozenset[Platform].
        platforms = cast("frozenset[Platform]", self.platforms)
        return any(p.current for p in platforms)

    @cached_property
    def fresh(self) -> bool:
        """Does the package manager match the version requirement?"""
        # Version is mandatory.
        if not self.version:
            return False
        if self.requirement and self.version not in VersionRange(self.requirement):
            logging.debug(
                f"{self.version} does not satisfy "
                f"{self.requirement!r} version requirement.",
                extra={"label": self.id},
            )
            return False
        return True

    @cached_property
    def available(self) -> bool:
        """Is the package manager available and ready-to-use on the system?

        Returns ``True`` only if the main CLI:

        1. is :py:attr:`supported on the current platform
           <meta_package_manager.manager.PackageManager.supported>`,
        2. was :py:attr:`found on the system
           <meta_package_manager.execution.CLIExecutor.cli_path>`,
        3. is :py:attr:`executable
           <meta_package_manager.execution.CLIExecutor.executable>`, and
        4. :py:attr:`match the version requirement
           <meta_package_manager.manager.PackageManager.fresh>`.
        """
        logging.debug(
            f"Deprecated? {self.deprecated}; "
            f"supported? {self.supported}; "
            f"found at: {highlight_cli_name(self.cli_path, self.cli_names)}; "
            f"executable? {self.executable}; "
            f"fresh? {self.fresh}.",
            extra={"label": self.id},
        )
        return bool(self.supported and self.cli_path and self.executable and self.fresh)

    @property
    def unavailable_reason(self) -> str | None:
        """Short, human-readable explanation of why :py:attr:`available` is
        ``False``, or ``None`` if the manager is available.

        Returned in priority order so the most actionable cause is reported
        first: platform support, then CLI lookup, then executable bit, then
        version requirement.
        """
        if self.supported is False:
            return f"not supported on {current_platform().name}"
        if not self.cli_path:
            cli_names = ", ".join(self.cli_names) or self.id
            return f"no executable named {cli_names!r} found in PATH"
        if not self.executable:
            return f"{self.cli_path!r} is not executable"
        if not self.fresh:
            if not self.version:
                return f"could not parse version from {self.cli_path!r} output"
            return (
                f"version {self.version} does not satisfy "
                f"{self.requirement!r} requirement"
            )
        return None

    @property
    def installed(self) -> Iterator[Package]:
        """List packages currently installed on the system.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    def installed_or_empty(self) -> tuple[Package, ...]:
        """Materialized :py:attr:`installed`, or an empty tuple on CLI failure.

        Best-effort inventory snapshot for the ``installed``, ``dump`` and
        ``sbom`` subcommands: each wants "give me what's installed, and just
        skip this manager if its CLI blew up" rather than re-implementing the
        same :py:class:`meta_package_manager.execution.CLIError` swallow. Logs
        one canonical warning on error and returns ``()`` so the caller carries
        on with the other managers.
        """
        try:
            return tuple(self.installed)
        except CLIError:
            logging.warning(
                "Could not list installed packages.",
                extra={"label": self.id},
            )
            return ()

    @cached_property
    def installed_ids(self) -> frozenset[str]:
        """Installed package IDs, materialized once from :py:meth:`installed`."""
        return frozenset(pkg.id for pkg in self.installed)

    @cached_property
    def installed_version_map(self) -> dict[str, TokenizedString | str | None]:
        """Installed versions keyed by package ID, materialized once from
        :py:meth:`installed`.

        Convenience for ``outdated`` parsers that report each package's latest version
        but not its currently-installed one, and so must look the latter up by ID
        (``snap``, ``xbps``). The value mirrors
        :py:attr:`meta_package_manager.package.Package.installed_version`, whose declared
        type still carries the transient ``str`` it normalizes away in ``__post_init__``.
        """
        return {pkg.id: pkg.installed_version for pkg in self.installed}

    def package_metadata_batch(
        self,
        packages: Iterable[Package],
    ) -> Iterator[tuple[Package, PackageMetadata]]:
        """Yield ``(package, metadata)`` pairs enriched with whatever rich
        per-package data this manager can surface.

        Called by ``mpm sbom`` in ``--bundled`` mode to populate licenses,
        checksums, download URLs, supplier/originator, and the declared
        dependency graph. The base implementation yields
        :py:data:`meta_package_manager.package.EMPTY_METADATA` for each package and stays compatible
        with managers that do not (yet) expose richer metadata: their SBOM
        entries stay at the minimal ``Package`` level, matching the
        historical and ``--minimal`` modes.

        Manager subclasses override this with their native query path:

        - bulk shell-outs when the CLI accepts a package list
          (``brew info --json=v2 --installed``, ``dpkg-query -W``,
          ``apt-cache show``);
        - on-disk parsing when the metadata already lives on the filesystem
          (pip's ``.dist-info`` directories, Homebrew's per-formula
          ``sbom.spdx.json``, dpkg's ``.md5sums``).

        The yielded pairs do not need to preserve the input order; the SBOM
        renderer matches by ``Package`` identity. Implementations are
        expected to swallow per-package extraction errors and yield
        :py:data:`meta_package_manager.package.EMPTY_METADATA` for the affected packages rather than
        failing the whole scan: a single misbehaving formula must not abort
        an enrichment pass spanning hundreds of packages.

        .. todo::
            Today every extractor is local-only (shell-outs to the
            manager's CLI, plus on-disk reads). When extractors start
            reaching for network resources (PyPI's JSON API, npm's
            registry, crates.io, GitHub's security advisories) the
            ``--bundled`` flag will no longer be a fine-grained enough
            knob: some users will want enrichment but not network
            traffic (offline scans, CI without egress). The natural
            split is a future ``--network/--no-network`` flag layered
            under ``--bundled`` to gate the network-touching code paths
            specifically, leaving local enrichment always-on for
            ``--bundled``.
        """
        for package in packages:
            yield package, EMPTY_METADATA

    @property
    def outdated(self) -> Iterator[Package]:
        """List installed packages with available upgrades.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    @property
    def refiltered_outdated(self) -> Iterator[Package]:
        """Wraps :py:meth:`outdated` with a version-equality filter.

        Some package managers report packages as outdated when the version
        strings differ at the character level but are numerically equal after
        parsing (e.g., Perl floating-point versions ``2.0000`` vs
        ``2.000000``). This filter drops those false positives.
        """
        for pkg in self.outdated:
            if (
                pkg.installed_version is None
                or pkg.latest_version is None
                or pkg.installed_version != pkg.latest_version
            ):
                yield pkg

    @classmethod
    def query_parts(cls, query: str) -> set[str]:
        """Returns a set of all contiguous alphanumeric string segments.

        Thin delegator to
        :py:meth:`meta_package_manager.package.Package.query_parts`, the canonical
        tokenizer, kept here as a convenience for manager-side search code.
        """
        return Package.query_parts(query)

    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Search packages available for install.

        There is no need for this method to be perfect and sensitive to ``extended`` and
        ``exact`` parameters. If the package manager is not supporting these kind of
        options out of the box, just returns the closest subset of matching package you
        can come up with. Finer refiltering will happens in the
        :py:meth:`meta_package_manager.manager.PackageManager.refiltered_search` method
        below.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    def refiltered_search(
        self,
        query: str,
        extended: bool,
        exact: bool,
    ) -> Iterator[Package]:
        """Returns search results with extra manual refiltering to refine gross
        matchings.

        Some package managers returns unbounded results, and/or don't support fine
        search criterions. In which case we use this method to manually refilters
        :py:meth:`meta_package_manager.manager.PackageManager.search` results to either
        exclude non-extended or non-exact matches.

        Returns a generator producing the same data as the
        :py:meth:`meta_package_manager.manager.PackageManager.search` method above.

        .. tip::

            If you are implementing a package manager definition, do not waste time to
            filter CLI results. Let this method do this job.

            Instead, just implement the core
            :py:meth:`meta_package_manager.manager.PackageManager.search` method above and
            try to produce results as precise as possible using the native filtering
            capabilities of the package manager CLI.
        """
        for match in self.search(query, extended, exact):
            # The per-package match decision lives on the data model, shared with
            # the `installed` and `outdated` query filters.
            if match.matches(query, extended, exact):
                yield match

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package and one only.

        Allows a specific ``version`` to be provided.
        """
        raise NotImplementedError

    def upgrade_all_cli(self) -> tuple[str, ...]:
        """Returns the complete CLI to upgrade all outdated packages on the system."""
        raise NotImplementedError

    def upgrade_one_cli(
        self,
        package_id: str,
        version: str | None = None,
    ) -> tuple[str, ...]:
        """Returns the complete CLI to upgrade one package and one only.

        Allows a specific ``version`` to be provided.
        """
        raise NotImplementedError

    def upgrade(self, package_id: str | None = None, version: str | None = None) -> str:
        """Perform an upgrade of either all or one package.

        Executes the CLI provided by either
        :py:meth:`meta_package_manager.manager.PackageManager.upgrade_all_cli` or
        :py:meth:`meta_package_manager.manager.PackageManager.upgrade_one_cli`.

        If the manager doesn't provides a full upgrade one-liner (i.e. if
        :py:meth:`meta_package_manager.manager.PackageManager.upgrade_all_cli` raises
        :py:exc:`NotImplementedError`), then the list of all outdated packages will be
        fetched (via :py:meth:`meta_package_manager.manager.PackageManager.outdated`) and
        each package will be updated one by one by calling
        :py:meth:`meta_package_manager.manager.PackageManager.upgrade_one_cli`.

        See for example the case of
        :py:meth:`meta_package_manager.managers.pip.Pip.upgrade_one_cli`.
        """
        if package_id:
            cli = self.upgrade_one_cli(package_id, version=version)

        else:
            try:
                cli = self.upgrade_all_cli()
            except NotImplementedError:
                logging.debug(
                    "upgrade_all_cli operation not implemented. "
                    "Call single upgrade operation on each package, one-by-one.",
                )
                logs = []
                for package in self.refiltered_outdated:
                    output = self.upgrade(package.id)
                    if output:
                        logs.append(output)
                return "\n".join(logs)

        return self.run(cli, extra_env=self.extra_env)

    def remove(self, package_id: str) -> str:
        """Remove one package and one only.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    def sync(self) -> None:
        """Refresh package metadata from remote repositories.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    def cleanup(self) -> None:
        """Prune left-overs, remove orphaned dependencies and clear caches.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    def discover_projects(self) -> Iterator[Path]:
        """Locate project trees this manager governs by scanning the filesystem.

        Extension point reserved for :py:attr:`ManagerScope.PROJECT` managers: detecting
        virtual environments, lockfiles, or project manifests scattered across the
        filesystem.

        .. caution::
            Not implemented for any manager yet. System-scoped managers (the default) own
            no project trees to discover.

        .. todo::
            Candidate ecosystems for project-scope discovery. Listed with the
            project files that signal each, grouped by whether ``mpm`` already
            ships a system-scoped manager that could grow a project mode.

            Already covered by a manager (``npm``, ``yarn``, ``pnpm``, ``pip``,
            ``uv``, ``cargo``, ``gem``, ``composer``, ``cpan``):

            - JavaScript: ``package.json``, ``package-lock.json``, ``yarn.lock``,
              ``pnpm-lock.yaml``
            - Python: ``requirements.txt``, ``pyproject.toml``, ``poetry.lock``,
              ``uv.lock``
            - Rust: ``Cargo.toml``, ``Cargo.lock``
            - Ruby: ``Gemfile``, ``Gemfile.lock``
            - PHP: ``composer.json``, ``composer.lock``
            - Perl: ``cpanfile``

            No manager yet:

            - Java: ``pom.xml`` (Maven), ``build.gradle`` (Gradle), ``ivy.xml``
            - Go: ``go.mod``, ``go.sum``
            - .NET: ``*.csproj``, ``packages.config`` (NuGet)
            - Swift: ``Package.swift``, ``Package.resolved``
            - CocoaPods: ``Podfile``, ``Podfile.lock``
            - C/C++: ``conanfile.txt`` (Conan), ``vcpkg.json`` (vcpkg)
            - Conda: ``conda-lock.yml``
        """
        raise NotImplementedError


# Configuration-defined managers.
#
# Everything below turns a declarative ``[mpm.managers.<id>]`` definition (parsed and
# validated in :py:mod:`meta_package_manager.config`) into a live
# :py:class:`PackageManager` subclass. The schema dataclasses (:class:`OperationSpec`,
# :class:`ManagerDefinition`) are the contract between that validation layer and the
# :func:`build_manager_class` factory here; they live in this module, beside the base
# class they extend, so :py:mod:`meta_package_manager.config` can import them without a
# circular dependency.


@dataclass(frozen=True)
class OperationSpec:
    """Declarative specification of one operation of a config-defined manager."""

    args: tuple[str, ...]
    """CLI arguments appended after the resolved binary, before
    :py:attr:`~meta_package_manager.execution.CLIExecutor.post_args`.

    May embed the ``{package_id}`` and ``{query}`` placeholders, substituted at call
    time. ``{version}`` is intentionally unsupported: config-defined managers do not
    pin versions (see :func:`_make_install`).
    """

    cli: str | None = None
    """Alternate binary name for this operation, or ``None`` for the manager's main
    :py:attr:`~meta_package_manager.execution.CLIExecutor.cli_path`.

    Resolved with :py:meth:`~meta_package_manager.manager.PackageManager.which` at
    call time, so one definition can span sibling binaries (``urpmi``/``urpme``/
    ``urpmq``, ``cast``/``dispel``/``gaze``). The operation fails with
    :py:exc:`FileNotFoundError` when the binary is missing rather than silently
    falling back to the main CLI.
    """

    sudo: bool = False
    """Mark the operation as privileged, mirroring the ``sudo=True`` flag built-in
    managers pass to :py:meth:`~meta_package_manager.execution.CLIExecutor.run_cli`.

    Escalation still follows the per-manager policy: the definition's
    ``default_sudo``, overridden by the user's ``--sudo``/``--no-sudo``. Only command
    operations may set it; queries stay unprivileged.
    """

    parse_mode: str = "none"
    """How to turn the command's stdout into packages: ``"regex"`` (per-line named
    groups), ``"json"`` (structured extraction), or ``"none"`` for command-only
    operations that produce no inventory (install, remove, sync, ...)."""

    regex: str | None = None
    """Regular expression matched against each stdout line in ``"regex"`` mode.

    Recognized named groups: ``package_id`` (required), ``installed_version`` and
    ``latest_version`` (optional). Compiled with :py:data:`re.MULTILINE`.
    """

    list_path: str | None = None
    """Dotted path to the package array inside the JSON document in ``"json"`` mode.

    ``None`` or empty means the document is itself the array.
    """

    fields: dict[str, str] | None = None
    """Mapping of recognized package field (``package_id``, ``installed_version``,
    ``latest_version``) to its JSON key, in ``"json"`` mode."""


@dataclass(frozen=True)
class ManagerDefinition:
    """A brand-new package manager declared from a ``[mpm.managers.<id>]`` section.

    Produced by :py:func:`meta_package_manager.config.parse_manager_definition` after
    validation, consumed by :func:`build_manager_class`.
    """

    manager_id: str
    """Manager ID, taken from the configuration section name."""

    name: str
    """Human-readable manager name."""

    platforms: tuple[str, ...]
    """Platform and group ID strings, resolved to
    :py:class:`extra_platforms.Platform` members at build time."""

    homepage_url: str | None
    """Project home page, for documentation reference only."""

    cli_fields: dict[str, object]
    """Overridable CLI-execution attributes (``cli_names``, ``requirement``,
    ``version_regexes``, ...), pre-coerced to their runtime types."""

    operations: dict[str, OperationSpec]
    """Declared operations keyed by name (``installed``, ``install``, ...)."""


class ConfigDrivenManager(PackageManager):
    """Base class for managers synthesized from configuration.

    Carries no operation methods on purpose: only the dynamically-created subclass
    returned by :func:`build_manager_class` defines the operations the user actually
    declared, so :py:func:`meta_package_manager.capabilities.implements` reports an
    accurate capability set. Defining an operation here would make *every*
    config-defined manager falsely advertise it.

    Exists mainly as a marker (``isinstance(manager, ConfigDrivenManager)``
    distinguishes user-defined managers from built-ins) and as a shared home for any
    future config-driven behavior.
    """

    definition_source: str | None = None
    """Repo-relative path to the bundled TOML file this manager was defined in.

    Set by :py:func:`meta_package_manager.config.build_bundled_managers` for the
    managers mpm ships as package data; stays ``None`` for a manager defined in a
    user's own configuration file. The documentation generator links a bundled
    manager's benchmark entry to this file, a config-defined manager having no Python
    source line to point at.
    """


def _render_args(args: tuple[str, ...], **substitutions: str) -> list[str]:
    """Substitute ``{token}`` placeholders in each CLI argument.

    Only the explicitly-passed tokens are replaced; an argument with no placeholder
    passes through untouched. Substitution is textual on already-split arguments, never
    a shell expansion, so an injected value stays a single argv element.
    """
    rendered = []
    for arg in args:
        for token, value in substitutions.items():
            arg = arg.replace("{" + token + "}", value)
        rendered.append(arg)
    return rendered


def _navigate_json(data: object, list_path: str | None) -> list:
    """Walk ``list_path`` into a parsed JSON document and return the package array.

    Returns an empty list when the path does not resolve to a list, so a malformed or
    unexpected payload yields no packages rather than raising.
    """
    if list_path:
        for key in list_path.split("."):
            if not isinstance(data, dict):
                return []
            data = data.get(key)
    return data if isinstance(data, list) else []


def _iter_parsed(
    output: str,
    spec: OperationSpec,
    compiled: re.Pattern[str] | None,
) -> Iterator[dict[str, str]]:
    """Yield ``Package`` keyword dicts extracted from a query command's ``output``.

    Honors :py:attr:`OperationSpec.parse_mode`: per-line named-group matching for
    ``"regex"``, key lookups under :py:attr:`OperationSpec.list_path` for ``"json"``.
    Skips entries with no ``package_id`` and version values that are absent or null.
    """
    if not output:
        return
    if spec.parse_mode == "regex":
        assert compiled is not None
        for line in output.splitlines():
            match = compiled.search(line)
            if not match:
                continue
            groups = match.groupdict()
            package_id = groups.get("package_id")
            if not package_id:
                continue
            kwargs = {"id": package_id}
            for role in ("installed_version", "latest_version"):
                if groups.get(role):
                    kwargs[role] = groups[role]
            yield kwargs
    elif spec.parse_mode == "json":
        assert spec.fields is not None
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            logging.warning("Could not parse JSON output for config-defined manager.")
            return
        for item in _navigate_json(data, spec.list_path):
            if not isinstance(item, dict):
                continue
            raw_id = item.get(spec.fields["package_id"])
            if not raw_id:
                continue
            kwargs = {"id": str(raw_id)}
            for role in ("installed_version", "latest_version"):
                json_key = spec.fields.get(role)
                if json_key is not None and item.get(json_key) is not None:
                    kwargs[role] = str(item[json_key])
            yield kwargs


def _op_cli_path(manager: PackageManager, spec: OperationSpec) -> Path | None:
    """Resolve the operation's alternate binary, or ``None`` for the main CLI.

    A declared-but-missing binary is an error: falling back to the main CLI would run
    the operation's arguments against the wrong program.
    """
    if not spec.cli:
        return None
    cli_path = manager.which(spec.cli)
    if not cli_path:
        msg = f"{spec.cli} not found"
        raise FileNotFoundError(msg)
    return cli_path


def _make_query_property(
    spec: OperationSpec, compiled: re.Pattern[str] | None
) -> property:
    """Build an ``installed``/``outdated`` property that runs the CLI and parses it."""

    def query(self: PackageManager) -> Iterator[Package]:
        output = self.run_cli(*spec.args, override_cli_path=_op_cli_path(self, spec))
        for kwargs in _iter_parsed(output, spec, compiled):
            yield self.package(**kwargs)

    return property(query)


def _make_search(
    spec: OperationSpec, compiled: re.Pattern[str] | None
) -> Callable[..., Iterator[Package]]:
    """Build a ``search`` method. Native exact/extended filtering is not expressed in
    the DSL, so :py:meth:`PackageManager.refiltered_search` refilters the raw results.
    """

    def search(
        self: PackageManager, query: str, extended: bool, exact: bool
    ) -> Iterator[Package]:
        output = self.run_cli(
            *_render_args(spec.args, query=query),
            override_cli_path=_op_cli_path(self, spec),
        )
        for kwargs in _iter_parsed(output, spec, compiled):
            yield self.package(**kwargs)

    # Same introspection surface as the search_capabilities decorator on class
    # managers: both refinements always rely on mpm's refiltering here.
    search.extended_support = False  # type: ignore[attr-defined]
    search.exact_support = False  # type: ignore[attr-defined]
    return search


def _warn_version_unsupported(version: str | None) -> None:
    """Log the standard warning when a version pin reaches a config-defined manager."""
    if version:
        logging.warning(
            "Configuration-defined managers do not support version pinning. "
            "Letting the package manager choose the version.",
        )


def _make_install(spec: OperationSpec) -> Callable[..., str]:
    """Build an ``install`` method substituting ``{package_id}`` into the args."""

    def install(
        self: PackageManager, package_id: str, version: str | None = None
    ) -> str:
        _warn_version_unsupported(version)
        return self.run_cli(
            *_render_args(spec.args, package_id=package_id),
            override_cli_path=_op_cli_path(self, spec),
            sudo=spec.sudo,
        )

    return install


def _make_remove(spec: OperationSpec) -> Callable[..., str]:
    """Build a ``remove`` method substituting ``{package_id}`` into the args."""

    def remove(self: PackageManager, package_id: str) -> str:
        return self.run_cli(
            *_render_args(spec.args, package_id=package_id),
            override_cli_path=_op_cli_path(self, spec),
            sudo=spec.sudo,
        )

    return remove


def _make_void(spec: OperationSpec) -> Callable[..., None]:
    """Build a ``sync``/``cleanup`` method that runs the CLI and discards its output."""

    def operation(self: PackageManager) -> None:
        self.run_cli(
            *spec.args,
            override_cli_path=_op_cli_path(self, spec),
            sudo=spec.sudo,
        )

    return operation


def _make_upgrade_one_cli(spec: OperationSpec) -> Callable[..., tuple[str, ...]]:
    """Build an ``upgrade_one_cli`` returning the per-package upgrade command line."""

    def upgrade_one_cli(
        self: PackageManager, package_id: str, version: str | None = None
    ) -> tuple[str, ...]:
        _warn_version_unsupported(version)
        return self.build_cli(
            *_render_args(spec.args, package_id=package_id),
            override_cli_path=_op_cli_path(self, spec),
            sudo=spec.sudo,
        )

    return upgrade_one_cli


def _make_upgrade_all_cli(spec: OperationSpec) -> Callable[..., tuple[str, ...]]:
    """Build an ``upgrade_all_cli`` returning the upgrade-everything command line."""

    def upgrade_all_cli(self: PackageManager) -> tuple[str, ...]:
        return self.build_cli(
            *spec.args,
            override_cli_path=_op_cli_path(self, spec),
            sudo=spec.sudo,
        )

    return upgrade_all_cli


def build_manager_class(definition: ManagerDefinition) -> type[ConfigDrivenManager]:
    """Synthesize a :py:class:`PackageManager` subclass from a validated definition.

    Assembles a class namespace from the definition's identity and CLI fields, then
    adds one method (or property) per declared operation. Only the declared operations
    land in the namespace, so :py:func:`meta_package_manager.capabilities.implements`
    reflects exactly what the user configured. Single- and all-package upgrades map to
    :py:meth:`~PackageManager.upgrade_one_cli` / :py:meth:`~PackageManager.upgrade_all_cli`
    so the inherited :py:meth:`~PackageManager.upgrade` orchestrator drives them, just
    like the built-in managers.
    """
    namespace: dict[str, object] = {
        "id": definition.manager_id,
        "name": definition.name,
        "homepage_url": definition.homepage_url,
        "platforms": traits_from_ids(*definition.platforms),
        "__module__": __name__,
        "__doc__": (
            f"Package manager {definition.manager_id!r} defined from configuration."
        ),
    }
    namespace.update(definition.cli_fields)

    for op_name, spec in definition.operations.items():
        compiled = None
        if spec.parse_mode == "regex":
            assert spec.regex is not None
            compiled = re.compile(spec.regex, re.MULTILINE)
        if op_name == "installed":
            namespace["installed"] = _make_query_property(spec, compiled)
        elif op_name == "outdated":
            namespace["outdated"] = _make_query_property(spec, compiled)
        elif op_name == "search":
            namespace["search"] = _make_search(spec, compiled)
        elif op_name == "install":
            namespace["install"] = _make_install(spec)
        elif op_name == "remove":
            namespace["remove"] = _make_remove(spec)
        elif op_name in ("sync", "cleanup"):
            namespace[op_name] = _make_void(spec)
        elif op_name == "upgrade_one":
            namespace["upgrade_one_cli"] = _make_upgrade_one_cli(spec)
        elif op_name == "upgrade_all":
            namespace["upgrade_all_cli"] = _make_upgrade_all_cli(spec)

    class_name = "Config_" + definition.manager_id.replace("-", "_")
    return cast(
        "type[ConfigDrivenManager]",
        MetaPackageManager(class_name, (ConfigDrivenManager,), namespace),
    )
