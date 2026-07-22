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
from enum import Enum
from functools import cached_property
from typing import ClassVar, cast

from extra_platforms import (
    Group,
    Platform,
    current_platform,
    extract_members,
)

from .execution import CLIError, CLIExecutor, highlight_cli_name
from .package import EMPTY_METADATA, Package, PackageMetadata
from .version import VersionRange

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path
    from typing import Any

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
    name and version into one dash-joined token (``apk``, ``nix``, ``xbps``), consumed
    through :py:meth:`split_name_version`.

    The ``.+`` name segment is greedy, so the version starts at the *last* hyphen
    followed by a digit: dashes inside the name (``python3``) stay with the name, while
    trailing ecosystem suffixes (Alpine ``-r<release>``, XBPS ``_<revision>``) stay with
    the version. Managers with a different layout override it (``pkg`` allows a
    non-numeric version lead, ``pkcon`` a non-greedy name).
    """

    def split_name_version(self, token: str) -> tuple[str, str] | None:
        """Split a dash-joined ``<package_id>-<version>`` token into its two parts.

        Matches ``token`` against :data:`_NAME_VERSION_REGEXP` (or the subclass's
        override of it) and returns the ``(package_id, version)`` pair, or ``None``
        when the token carries no recognizable version. Shared by every manager
        whose listings glue the name and version together.
        """
        match = self._NAME_VERSION_REGEXP.match(token)
        if not match:
            return None
        return match.group("package_id"), match.group("version")

    def parse_json(self, output: str) -> Any | None:
        """Parse a query's JSON ``output``, tolerating empty and malformed captures.

        The shared first step of every JSON-emitting query, for built-in managers
        and config-defined operations alike (see
        :py:func:`meta_package_manager.definitions._iter_parsed`). Returns ``None``
        when the command produced no output (a manager with nothing to report often
        prints nothing at all), and when the output is not valid JSON, which logs
        one warning tagged with the manager ID instead of raising: a query that
        cannot be parsed yields no packages, mirroring how the fan-out commands
        swallow a failed CLI call into an empty result.

        Queries whose failure semantics differ keep their own parsing: a per-line
        NDJSON stream (``pkg search``), a hard :py:exc:`CLIError` on malformed
        payloads (``pwsh-gallery``), a best-effort metadata enrichment logging at
        ``DEBUG`` (``brew info``).
        """
        if not output:
            return None
        try:
            return json.loads(output)
        except json.JSONDecodeError as ex:
            logging.warning(
                f"Could not parse JSON output: {ex}",
                extra={"label": self.id},
            )
            return None

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

    @property
    def orphans(self) -> Iterator[Package]:
        """List packages installed as dependencies that nothing requires anymore.

        The read-only counterpart of the ``--orphans`` action flags: where
        ``mpm cleanup --orphans`` removes the orphans, this query only reports them,
        through the manager's native listing (``pacman --query --deps --unrequired``,
        ``brew autoremove --dry-run``, ``dnf repoquery --unneeded``, ...).
        :program:`mpm` builds no dependency graph: the manager decides what is
        orphaned.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

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

    def remove_orphan(self, package_id: str) -> str:
        """Remove one package together with the dependencies it alone pulled in.

        The opt-in counterpart to
        :py:meth:`meta_package_manager.manager.PackageManager.remove`, surfaced as
        ``mpm remove --orphans``. It maps to the manager's native "remove and drop
        now-unneeded dependencies" verb (``apt remove --auto-remove``,
        ``pacman --remove --recursive``, ``dnf autoremove``, ...), so :program:`mpm`
        builds no dependency graph of its own.

        Optional. A manager with no such native verb leaves this
        :py:exc:`NotImplementedError`; ``mpm remove --orphans`` then falls back to
        :py:meth:`meta_package_manager.manager.PackageManager.remove` and logs one
        ``INFO`` capability-skip.
        """
        raise NotImplementedError

    def sync(self) -> None:
        """Refresh package metadata from remote repositories.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    @classmethod
    def _defines(cls, method_name: str) -> bool:
        """Whether a non-base class in the manager's MRO defines ``method_name``.

        The introspection primitive behind
        :py:func:`meta_package_manager.capabilities.implements_method` (which
        delegates here) and the :py:meth:`cleanup` composer below, hosted on the
        class to stay importable from both sides without a cycle.
        """
        for klass in cls.mro():
            if klass is PackageManager:
                return False
            if method_name in klass.__dict__:
                return True
        return False

    def cleanup(self) -> None:
        """Run the manager's non-destructive cleanup categories.

        Not an operation managers define anymore: ``cleanup`` is the fixed
        composition of the non-destructive category methods a manager overrides
        (:py:meth:`cleanup_cache`, then :py:meth:`cleanup_repair`). The orphan
        sweep never joins in, native or synthesized: it is the one category that
        removes packages, so it only runs on an explicit ``mpm cleanup --orphans``
        (or a direct :py:meth:`cleanup_orphan` call), keeping a plain ``cleanup``
        package-preserving on every manager.

        A manager overriding no category method does not advertise the ``cleanup``
        operation at all (see
        :py:func:`meta_package_manager.capabilities.implements`) and this composer
        is then a no-op.
        """
        for method_name in ("cleanup_cache", "cleanup_repair"):
            if self._defines(method_name):
                getattr(self, method_name)()

    def cleanup_orphan(self) -> None:
        """Remove every orphaned package on the system, sparing the caches.

        The system-wide "remove all packages nothing depends on anymore" sweep
        (``apt autoremove``, ``brew autoremove``, ``flatpak uninstall --unused``, ...).
        The one cleanup category that removes packages, so it is deliberately kept out
        of the plain :py:meth:`cleanup` composition and only runs on an explicit
        ``mpm cleanup --orphans``.

        Distinct from
        :py:meth:`meta_package_manager.manager.PackageManager.remove_orphan`, which is
        scoped to one package's own orphaned dependencies. As with :py:meth:`cleanup`,
        :program:`mpm` builds no dependency graph: the manager decides what is orphaned.

        A manager with no native sweep verb is backfilled by this base implementation
        when it supports both the :py:attr:`orphans` query and package removal: list
        the orphans, remove each one (with :py:meth:`remove_orphan` when available, so
        every listed root takes its own now-orphaned subtree along), then re-query and
        repeat until the listing settles, since removing an orphan can orphan its own
        dependencies. The exact pattern of the synthesized full ``upgrade --all``, and
        the in-process equivalent of Arch's classic ``pacman -Rns $(pacman -Qtdq)``
        idiom. The re-query loop stops as soon as a round makes no progress, so
        removal failures cannot spin it forever.

        A manager implementing neither a native sweep nor the :py:attr:`orphans`
        query propagates :py:exc:`NotImplementedError`, and ``mpm cleanup --orphans``
        simply skips it.
        """
        logging.debug(
            "No native orphan sweep. Remove listed orphans one by one.",
            extra={"label": self.id},
        )
        previous: frozenset[str] = frozenset()
        while True:
            # Raises NotImplementedError right here when the manager has no orphans
            # query, keeping the operation's optional contract.
            orphan_ids = [package.id for package in self.orphans]
            current = frozenset(orphan_ids)
            if not current or current == previous:
                break
            previous = current
            for package_id in orphan_ids:
                try:
                    self.remove_orphan(package_id)
                except NotImplementedError:
                    self.remove(package_id)

    def cleanup_cache(self) -> None:
        """Prune the manager's caches, downloads and other left-over artifacts.

        The cache category of :py:meth:`cleanup`, surfaced as
        ``mpm cleanup --cache`` and subtracted by ``--skip-cache`` (``apt clean``,
        ``dnf clean all``, ``brew cleanup``, ``npm cache clean``, ...). The broadest
        category: for most managers the whole cleanup amounts to it.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    def cleanup_repair(self) -> None:
        """Verify and repair the manager's local installation state.

        The repair category of :py:meth:`cleanup`, surfaced as
        ``mpm cleanup --repair`` and subtracted by ``--skip-repair``
        (``flatpak repair --user``).

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    def doctor_cli(self) -> tuple[str, ...]:
        """Returns the complete CLI running the manager's native self-diagnosis.

        The invocation must be read-only (``brew doctor``, ``pip check``,
        ``pacman --database --check``, ...): :py:meth:`doctor` runs it, never mpm's
        mutating machinery. The surveyed doctor verbs share one convention this
        contract leans on: a non-zero exit code means problems were found.

        Optional. Will be simply skipped by :program:`mpm` if not implemented.
        """
        raise NotImplementedError

    def doctor(self) -> tuple[bool, str]:
        """Run the native self-diagnosis, returning ``(healthy, report)``.

        Runs :py:meth:`doctor_cli` and interprets the outcome with a contract of
        its own, distinct from every other operation:

        - **Health is the exit code alone.** :py:meth:`run`'s failure gate
          tolerates a non-zero exit with a silent ``<stderr>`` (a benign status
          for query parsers), but for a diagnosis that exit *is* the verdict:
          ``pip check`` reports its conflicts on ``<stdout>`` only and would
          read as healthy under the gate.
        - **The report merges both streams.** The tools split their findings
          across them (``brew doctor`` warns on ``<stderr>``), and the report is
          relayed verbatim to the user: there is nothing to parse.
        - **The diagnosis is not an error.** The failure-gate entry an unhealthy
          exit may have accumulated is reclaimed from
          :py:attr:`~meta_package_manager.execution.CLIExecutor.cli_errors`, so
          the end-of-run error summary is not inflated by a verdict ``mpm
          doctor`` already reports on its own. A run that never completed
          (timeout, interrupt, missing binary) keeps its entry: that is a
          genuine plumbing error, and the manager reports unhealthy.
        """
        cli = self.doctor_cli()
        before = len(self.cli_errors)
        output = self.run(cli, extra_env=self.extra_env)
        last = self._last_run
        if last is None:
            return False, output
        code, _output, error = last
        del self.cli_errors[before:]
        report = "\n".join(part for part in (output, error) if part)
        return code == 0, report

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
