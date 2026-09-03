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

Defines {class}`meta_package_manager.manager.PackageManager`, the class each concrete
manager in {mod}`meta_package_manager.managers` inherits from, together with its
{class}`meta_package_manager.manager.MetaPackageManager` metaclass and the
{class}`meta_package_manager.manager.ManagerScope` classification.

A subclass declares its identity (supported platforms, version requirement, maintenance
status) and implements the operations it supports (`installed`, `outdated`,
`install`, `upgrade`, ...). The CLI-execution engine it inherits lives in
{mod}`meta_package_manager.execution`, the operation vocabulary in
{mod}`meta_package_manager.capabilities`, and the package objects operations yield in
{mod}`meta_package_manager.package`. On top of the engine, this module adds the
availability policy: whether the manager is supported, fresh, and ready to use.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from enum import Enum
from functools import cached_property
from typing import ClassVar, cast

from extra_platforms import (
    Group,
    Platform,
    current_platform,
    extract_members,
)

from .cooldown import CooldownPolicy
from .execution import CLIError, CLIExecutor, highlight_cli_name
from .package import EMPTY_METADATA, Package, PackageMetadata
from .version import VersionRange

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping
    from pathlib import Path
    from typing import Any

    from .version import TokenizedString


COOLDOWN_EXEMPT = datetime.min.replace(tzinfo=timezone.utc)
"""Sentinel a {meth}`PackageManager.release_date` probe returns for a package
outside the cooldown gate's scope.

A hybrid manager can serve two registries with different threat models: an AUR
helper resolves the live, self-published AUR next to Arch's official
repositories, whose archive stages releases on its own (see the N/A rows of
`docs/cooldown.md`). The out-of-scope half reads as infinitely aged, so the
hold logic of {meth}`PackageManager.cooldown_hold_reason` lets it through
untouched, and the constant's name keeps the probe's intent readable where a
bare `datetime.min` would read as a bug.
"""


JSON_FIELD_SELECTOR_REGEX = re.compile(
    r"^(?P<key>[^\[\]]+?)(?:\[(?P<index>\d+)\])?$",
)
"""Parse a JSON field selector: a key name with an optional `[N]` list index.

A bare `version` maps the package field to the item's `version` key. A
`versions[0]` selector additionally picks one element out of a list-valued key
(zerobrew reports each package's installed versions as an array). Anything more
nested stays out on purpose: a query needing real JSON traversal is better served
by a custom parser. Shared by {meth}`PackageManager.parse_json_items` and the
declarative-manager validation in {mod}`meta_package_manager.definitions`.
"""


def _navigate_json(data: object, list_path: str | None) -> list:
    """Walk `list_path` into a parsed JSON document and return the package array.

    Returns an empty list when the path does not resolve to a list, so a malformed or
    unexpected payload yields no packages rather than raising.
    """
    if list_path:
        for key in list_path.split("."):
            if not isinstance(data, dict):
                return []
            data = data.get(key)
    return data if isinstance(data, list) else []


def _json_field(item: dict, selector: str) -> Any:
    """Resolve a field `selector` against one JSON package `item`.

    A bare key returns the key's value; a `key[N]` selector picks the `N`-th
    element out of a list-valued key (see {data}`JSON_FIELD_SELECTOR_REGEX`).
    Anything that does not resolve — missing key, non-list value under an indexed
    selector, out-of-range index — returns `None`, so an unexpected payload
    yields incomplete packages rather than raising.
    """
    match = JSON_FIELD_SELECTOR_REGEX.match(selector)
    assert match is not None, f"unvalidated selector {selector!r}"
    value = item.get(match.group("key"))
    index = match.group("index")
    if index is None:
        return value
    if not isinstance(value, list):
        return None
    position = int(index)
    return value[position] if position < len(value) else None


class ManagerScope(Enum):
    """Filesystem scope a package manager operates within."""

    SYSTEM = "system"
    """Manages software installed globally, machine-wide.

    All currently-maintained managers are system-scoped.
    """

    PROJECT = "project"
    """Manages dependencies confined to a project's working tree.

    Not supported yet. The user-facing rationale, the ecosystems this would
    cover and the architectural work it waits on are catalogued once in
    {doc}`/unsupported`; the extension point is
    {meth}`meta_package_manager.manager.PackageManager.discover_projects`.
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

    Defaults to {attr}`ManagerScope.SYSTEM`, which covers every manager maintained
    today: they install and query software machine-wide. Project-scoped managers (Poetry,
    Bundler, Maven, ...) resolve dependencies confined to a working tree and are not
    supported yet.
    """

    unmaintained: bool = False
    """A manager whose upstream project is no longer maintained.

    Covers projects that are officially retired and those we infer are abandoned:
    archived on their forge, left without a release or commit for years, formally
    superseded by a successor, or part of a discontinued platform. See the
    stability policy in `CLAUDE.md` for the full criteria.

    An unmaintained manager is hidden from package selection by default (you can
    still use it by explicitly calling for it on the command line), and is exempt
    from the project stability policy: it may be dropped, in part or in full, in
    any release and without notice, once keeping it working becomes too
    burdensome.

    Unmaintained managers are kept out of the functional and integration test
    matrices, so an unreliable or flaky one never blocks a release and we save CI
    resources. The commitment is to keep the wrapper for as long as that stays
    cheap: the cheap static invariants (ID format, attribute ordering, ...) still
    apply for as long as the manager's code lives in the source tree, to keep that
    code valid.

    Every unmaintained manager must document itself through
    {attr}`unmaintained_message`.
    """

    unmaintained_message: str | None = None
    """Evidence and rationale for the {attr}`unmaintained` flag, as a MyST
    markdown block.

    Rendered into the documentation (the manager's page, and a `⚠️` marker in the
    manager tables). May embed markdown links to the archival notice, the successor
    project, or the discontinuation announcement. Required for every manager whose
    {attr}`unmaintained` flag is set, and only meaningful on such managers.
    Enforced by `test_unmaintained`.
    """

    maintenance_note: str | None = None
    """A watch note about a still-maintained upstream whose activity is slowing or
    whose status is ambiguous, as a MyST markdown block.

    Unlike {attr}`~meta_package_manager.manager.PackageManager.unmaintained`, this is
    purely informational: the manager stays in the default selection and in the test
    matrices. It renders as a ``{note}``
    admonition atop the manager's documentation page, flagging upstreams worth
    keeping an eye on (a slow release cadence, superseded-but-still-shipped tools, a
    discontinued platform still under vendor support). May embed markdown links.
    Mutually exclusive with
    {attr}`~meta_package_manager.manager.PackageManager.unmaintained`: a
    confirmed-dead manager carries an
    {attr}`~meta_package_manager.manager.PackageManager.unmaintained_message`
    instead. Enforced by `test_maintenance_note`.
    """

    id: str
    """Package manager's ID.

    Derived by defaults from the lower-cased class name in which underscores `_` are
    replaced by dashes `-`.

    This ID must be unique among all package manager definitions and lower-case, as
    they're used as feature flags for the {program}`mpm` CLI.
    """

    name: str
    """Return package manager's common name.

    Default value is based on class name.
    """

    homepage_url: str | None = None
    """Home page of the project, only used in documentation for reference."""

    logo: str | None = None
    """Slug of the brand mark standing for this manager in the documentation.

    Names an SVG vendored under `docs/assets/managers/`, whose provenance and license
    are recorded in `docs/assets/managers/logos.yaml`. Inlined at the top of the
    manager's page by `meta_package_manager._docs`; a manager leaving it unset
    keeps the page's default package glyph.

    Several managers legitimately share one slug, either because they wrap the same
    upstream (`brew` and `cask`) or because the tool has no mark of its own and its
    ecosystem's stands in (`apt` under Debian's swirl, `cargo` under Rust's gear).
    Documentation-only, like {attr}`homepage_url`: no CLI output reads it.
    """

    keywords: tuple[str, ...] = ()
    """Well-known names for this manager that its {attr}`id` does not already carry.

    Merged into the PyPI keywords of `pyproject.toml` by
    {func}`docs_update.update_keywords`, alongside every manager ID and the globally
    curated `KEYWORDS_EXTRAS`. Declare an alias here rather than in that tuple
    whenever it names *this* manager: an alias living beside the class it describes
    cannot outlive it, where a central entry silently rots once the manager is
    renamed or dropped.

    Reserve `KEYWORDS_EXTRAS` for terms belonging to no manager in particular, like
    `cyclonedx` or `package manager`. Documentation-only: no CLI output reads it.
    """

    brewfile_entry_type: ClassVar[str | None] = None
    """Name of the Brewfile DSL entry type this manager maps to, or `None` if the
    manager has no Brewfile equivalent.

    Set by the subset of managers Homebrew Bundle's DSL covers, and consumed by
    {mod}`meta_package_manager.brewfile` when rendering the output of
    `mpm dump --brewfile`. Which manager maps to which entry is tabulated from
    these declarations in {doc}`/dump`, section "Brewfile", where the export's
    own quirks are documented too.
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
    `frozenset` of `Platform` instances at instantiation.
    """

    requirement: str | None = None
    """Version requirement specifier.

    Supports a comma-separated range of constraints (e.g. `">=1.20.0,<2.0.0"`).
    A bare version string like `"1.20.0"` is treated as `>=1.20.0`.

    Parsed by {class}`meta_package_manager.version.VersionRange`.

    Defaults to `None`, which deactivates version check entirely.
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
    """Default `<package_id>-<version>` splitter for managers whose listings pack the
    name and version into one dash-joined token (`apk`, `nix`, `xbps`), consumed
    through {meth}`split_name_version`.

    The `.+` name segment is greedy, so the version starts at the *last* hyphen
    followed by a digit: dashes inside the name (`python3`) stay with the name, while
    trailing ecosystem suffixes (Alpine `-r<release>`, XBPS `_<revision>`) stay with
    the version. Managers with a different layout override it (`pkg` allows a
    non-numeric version lead, `pkcon` a non-greedy name).
    """

    def split_name_version(self, token: str) -> tuple[str, str] | None:
        """Split a dash-joined `<package_id>-<version>` token into its two parts.

        Matches `token` against {data}`_NAME_VERSION_REGEXP` (or the subclass's
        override of it) and returns the `(package_id, version)` pair, or `None`
        when the token carries no recognizable version. Shared by every manager
        whose listings glue the name and version together.
        """
        match = self._NAME_VERSION_REGEXP.match(token)
        if not match:
            return None
        return match.group("package_id"), match.group("version")

    def parse_json(self, output: str) -> Any | None:
        """Parse a query's JSON `output`, tolerating empty and malformed captures.

        The shared first step of every JSON-emitting query, for built-in managers
        and config-defined operations alike (see
        {func}`meta_package_manager.definitions._parse_spec_output`). Returns `None`
        when the command produced no output (a manager with nothing to report often
        prints nothing at all), and when the output is not valid JSON, which logs
        one warning tagged with the manager ID instead of raising: a query that
        cannot be parsed yields no packages, mirroring how the fan-out commands
        swallow a failed CLI call into an empty result.

        Queries whose failure semantics differ keep their own parsing: a per-line
        NDJSON stream (`pkg search`), a hard
        {exc}`~meta_package_manager.execution.CLIError` on malformed
        payloads (`pwsh-gallery`), a best-effort metadata enrichment logging at
        `DEBUG` (`brew info`).
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

    def parse_regex_lines(
        self,
        pattern: re.Pattern[str],
        output: str,
    ) -> Iterator[Package]:
        """Yield one package per line of `output` matching `pattern`.

        The shared engine of every line-oriented text listing, for built-in
        managers and config-defined operations alike (see
        {func}`meta_package_manager.definitions._make_query_property`). The
        pattern is searched in each line, and its named groups map straight onto
        the package fields: `package_id` (required: a match without one is
        skipped), `installed_version`, `latest_version`, `name`,
        `description` and `arch`, empty and absent groups being dropped.

        Managers whose listings need per-line post-processing (multi-version
        reduction, name/version splitting, cross-query joins) keep their own
        loop and this stays their reference semantics.
        """
        for line in output.splitlines():
            match = pattern.search(line)
            if not match:
                continue
            groups = match.groupdict()
            package_id = groups.pop("package_id", None)
            if not package_id:
                continue
            yield self.package(
                id=package_id,
                **{field: value for field, value in groups.items() if value},
            )

    def parse_json_items(
        self,
        output: str,
        *,
        list_path: str | None = None,
        fields: Mapping[str, str],
    ) -> Iterator[Package]:
        """Yield one package per item of a JSON listing.

        The shared engine of every flat-JSON query, for built-in managers and
        config-defined operations alike (see
        {func}`meta_package_manager.definitions._make_query_property`). The
        document is parsed through {meth}`parse_json` (so a malformed payload
        warns and yields nothing), the package array is reached by walking the
        dotted `list_path` (`None` when the document is itself the array), and
        `fields` maps each package field (`package_id`, required, plus any of
        `installed_version`, `latest_version`, `name`, `description`,
        `arch`) to its JSON selector: a key name with an optional `[N]` list
        index, like `version` or `versions[0]` (see
        {data}`JSON_FIELD_SELECTOR_REGEX`). Items missing their `package_id`
        and fields resolving to `None` are dropped.
        """
        data = self.parse_json(output)
        if data is None:
            return
        for item in _navigate_json(data, list_path):
            if not isinstance(item, dict):
                continue
            raw_id = _json_field(item, fields["package_id"])
            if not raw_id:
                continue
            kwargs = {"id": str(raw_id)}
            for field, selector in fields.items():
                if field == "package_id":
                    continue
                value = _json_field(item, selector)
                if value is not None:
                    kwargs[field] = str(value)
            yield self.package(**kwargs)

    def package(self, **kwargs) -> Package:
        """Instantiate a `Package` object from the manager.

        Sets its `manage_id` to the manager it belongs to.
        """
        kwargs.setdefault("manager_id", self.id)
        return Package(**kwargs)

    def brewfile_entry(
        self, package: Package
    ) -> tuple[str, dict[str, object] | None] | None:
        """Return `(entry_name, entry_options)` for a Brewfile line, or `None`
        to skip the package.

        Default: emit {attr}`meta_package_manager.package.Package.id` as the entry name with no options.
        Override on managers whose Brewfile DSL counterpart expects a different
        shape: `mas` uses the app name with `id: ADAM_ID`, `flatpak` adds
        `with: ["remote"]`. Only called when {attr}`brewfile_entry_type` is
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

        Returns `True` only if the main CLI:

        1. is {attr}`supported on the current platform
           <meta_package_manager.manager.PackageManager.supported>`,
        2. was {attr}`found on the system
           <meta_package_manager.execution.CLIExecutor.cli_path>`,
        3. is {attr}`executable
           <meta_package_manager.execution.CLIExecutor.executable>`, and
        4. {attr}`match the version requirement
           <meta_package_manager.manager.PackageManager.fresh>`.
        """
        logging.debug(
            f"Unmaintained? {self.unmaintained}; "
            f"supported? {self.supported}; "
            f"found at: {highlight_cli_name(self.cli_path, self.cli_names)}; "
            f"executable? {self.executable}; "
            f"fresh? {self.fresh}.",
            extra={"label": self.id},
        )
        # Derived from unavailable_reason so the two can never drift: the reason
        # enumerates the same conditions, in the same priority order.
        return self.unavailable_reason is None

    @property
    def unavailable_reason(self) -> str | None:
        """Short, human-readable explanation of why {attr}`available` is
        `False`, or `None` if the manager is available.

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

    @cached_property
    def install_root(self) -> Path | None:
        """Root of the tree this manager's global installs write into.

        `None` on the base: most managers never need the question answered, and
        `cpan` cannot answer it (its target depends on `local::lib`,
        `INSTALL_BASE` and the perl in front, with no single verb speaking for
        the machine). A manager that knows its own discovery verb overrides
        this with a probe (`npm --global prefix`, `gem environment gemdir`),
        run through `force_exec` like the {attr}`version
        <meta_package_manager.execution.CLIExecutor.version>` probe, so a
        `--dry-run` or `--plan` run still resolves it for real.

        A host-probing property, like {attr}`cli_path
        <meta_package_manager.execution.CLIExecutor.cli_path>`: the
        documentation generators must never read it. Consumed through
        {func}`~meta_package_manager.sudo.inspect_install_root`, which adds the
        ownership reading.
        """
        return None

    @property
    def installed(self) -> Iterator[Package]:
        """List packages currently installed on the system.

        Optional. Will be simply skipped by {program}`mpm` if not implemented.
        """
        raise NotImplementedError

    def installed_or_empty(self) -> tuple[Package, ...]:
        """Materialized {attr}`installed`, or an empty tuple on CLI failure.

        Best-effort inventory snapshot for the `installed`, `dump` and
        `sbom` subcommands, and for the {attr}`installed_ids` lookup behind
        `remove` and `upgrade <packages>`: each wants "give me what's
        installed, and just skip this manager if its CLI blew up" rather than
        re-implementing the same
        {class}`meta_package_manager.execution.CLIError` swallow. Logs one
        canonical warning on error and returns `()` so the caller carries on
        with the other managers.
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
        """Installed package IDs, materialized once from {meth}`installed_or_empty`.

        Routed through the tolerant {meth}`installed_or_empty` rather than
        {meth}`installed` because its callers ask a *discovery* question: which
        managers have this package? A manager whose CLI just failed has no answer
        to give, which is not the same as a fatal error. Sourcing a spec for
        `remove` and `upgrade <packages>` reads this for every selected manager,
        so a single broken CLI would otherwise abort the whole command before the
        managers that do have the package are ever tried.

        Contrast {attr}`installed_version_map`, which deliberately keeps raising:
        it is read from inside an `outdated` parser, where an empty map does not
        mean "no answer" but silently reports every outdated package with an
        unknown installed version.
        """
        return frozenset(pkg.id for pkg in self.installed_or_empty())

    @cached_property
    def installed_version_map(self) -> dict[str, TokenizedString | str | None]:
        """Installed versions keyed by package ID, materialized once from
        {meth}`installed`.

        Convenience for `outdated` parsers that report each package's latest version
        but not its currently-installed one, and so must look the latter up by ID
        (`snap`, `xbps`). The value mirrors
        {attr}`meta_package_manager.package.Package.installed_version`, whose declared
        type still carries the transient `str` it normalizes away in `__post_init__`.
        """
        return {pkg.id: pkg.installed_version for pkg in self.installed}

    def package_metadata_batch(
        self,
        packages: Iterable[Package],
    ) -> Iterator[tuple[Package, PackageMetadata]]:
        """Yield `(package, metadata)` pairs enriched with whatever rich
        per-package data this manager can surface.

        Called by `mpm sbom` in `--bundled` mode to populate licenses,
        checksums, download URLs, supplier/originator, and the declared
        dependency graph. The base implementation yields
        {data}`meta_package_manager.package.EMPTY_METADATA` for each package and stays compatible
        with managers that do not (yet) expose richer metadata: their SBOM
        entries stay at the minimal `Package` level, matching the
        historical and `--minimal` modes.

        Manager subclasses override this with their native query path:

        - bulk shell-outs when the CLI accepts a package list
          (`brew info --json=v2 --installed`, `dpkg-query -W`,
          `apt-cache show`);
        - on-disk parsing when the metadata already lives on the filesystem
          (pip's `.dist-info` directories, Homebrew's per-formula
          `sbom.spdx.json`, dpkg's `.md5sums`).

        The yielded pairs do not need to preserve the input order; the SBOM
        renderer matches by `Package` identity. Implementations are
        expected to swallow per-package extraction errors and yield
        {data}`meta_package_manager.package.EMPTY_METADATA` for the affected packages rather than
        failing the whole scan: a single misbehaving formula must not abort
        an enrichment pass spanning hundreds of packages.

        ```{todo}
        Today every extractor is local-only (shell-outs to the
        manager's CLI, plus on-disk reads). When extractors start
        reaching for network resources (PyPI's JSON API, npm's
        registry, crates.io, GitHub's security advisories) the
        `--bundled` flag will no longer be a fine-grained enough
        knob: some users will want enrichment but not network
        traffic (offline scans, CI without egress). The natural
        split is a future `--network/--no-network` flag layered
        under `--bundled` to gate the network-touching code paths
        specifically, leaving local enrichment always-on for
        `--bundled`.
        ```
        """
        for package in packages:
            yield package, EMPTY_METADATA

    @property
    def outdated(self) -> Iterator[Package]:
        """List installed packages with available upgrades.

        Optional. Will be simply skipped by {program}`mpm` if not implemented.
        """
        raise NotImplementedError

    @property
    def refiltered_outdated(self) -> Iterator[Package]:
        """Wraps {meth}`outdated` with a version-equality filter.

        Some package managers report packages as outdated when the version
        strings differ at the character level but are numerically equal after
        parsing (e.g., Perl floating-point versions `2.0000` vs
        `2.000000`). This filter drops those false positives.
        """
        for pkg in self.outdated:
            if (
                pkg.installed_version is None
                or pkg.latest_version is None
                or pkg.installed_version != pkg.latest_version
            ):
                yield pkg

    def release_date(self, package_id: str) -> datetime | None:
        """Publication timestamp of the latest release of a package.

        The probe behind the synthesized per-package cooldown gate (see
        {meth}`cooldown_hold_reason`): a manager without a native
        {attr}`~meta_package_manager.execution.CLIExecutor.cooldown_env_var`
        that implements this method becomes gateable, package by package.

        The contract binds the timestamp's provenance, not just its shape:

        - Returns a timezone-aware {class}`~datetime.datetime`, or `None` when
          the registry answers but carries no date (the gate then fails
          closed under the default `enforce` posture).
        - The timestamp must be **server-set**: stamped by the registry, store
          or build service at publication. A client-set or package-embedded
          date (a git commit date, an archive metadata field the author
          writes) is forgeable by exactly the attacker the cooldown exists to
          stop, and must never back this probe.
        - The date is the one of the **latest available release**, the version
          the manager would resolve absent a pin. Implementations should read
          it through the manager's own CLI, so the probe sees the same
          registry, mirrors and authentication as the install it guards.

        Optional. Will be simply skipped by {program}`mpm` if not implemented.
        """
        raise NotImplementedError

    def _probes_release_date(self) -> bool:
        """Whether a subclass implements the {meth}`release_date` probe.

        The override of the
        {meth}`~meta_package_manager.execution.CLIExecutor._probes_release_date`
        hook, which is what folds probe-backed managers into
        {attr}`~meta_package_manager.execution.CLIExecutor.supports_cooldown`.
        """
        return self._defines("release_date")

    @property
    def _cooldown_probe_engaged(self) -> bool:
        """Whether an active cooldown is enforced through the release-date probe.

        `True` only when a window is set, the manager implements
        {meth}`release_date`, no native environment variable already delegates
        the gate to the manager's own resolver, and a per-manager
        `cooldown_policy` override has not exempted it (`off`).
        """
        return (
            self.cooldown is not None
            and self.cooldown_env_var is None
            and self.cooldown_policy is not CooldownPolicy.off
            and self._probes_release_date()
        )

    def cooldown_hold_reason(self, package_id: str) -> str | None:
        """Decide whether the release-age cooldown holds back one package.

        The per-package half of the gate, for managers that implement the
        {meth}`release_date` probe instead of carrying a native
        {attr}`~meta_package_manager.execution.CLIExecutor.cooldown_env_var`.
        Returns `None` when the package may proceed: no active probe-backed
        cooldown, or a publication old enough to clear the window. Returns a
        human-readable hold reason otherwise, which the caller renders in its
        trail and logs.

        The probe is fail-closed: a publication date that cannot be read
        (probe failure, or a registry carrying no date) holds the package
        under the default `enforce` posture, and only a `best-effort` policy
        lets it through, unguarded.
        """
        if not self._cooldown_probe_engaged:
            return None
        # A --dry-run simulates every CLI call, the probe included, so there is
        # no date to read and nothing real to protect: let the simulation
        # proceed. --plan takes precedence and executes reads for real.
        if self.dry_run and not self.plan:
            return None
        published = None
        try:
            # The probe is a read-only query: stamp it as such so it resolves
            # the read-only timeout and executes for real under --plan.
            with self.acting_as("outdated"):
                published = self.release_date(package_id)
        except CLIError:
            pass
        assert self.cooldown is not None
        if published is None:
            if (
                self.cooldown_policy or CooldownPolicy.enforce
            ) is CooldownPolicy.best_effort:
                logging.info(
                    f"Cannot date the latest release of {package_id}; "
                    "running without the supply-chain safeguard.",
                    extra={"label": self.id},
                )
                return None
            return "its latest release cannot be dated (fail-closed)"
        # The contract wants an aware datetime; absorb a naive one as UTC
        # rather than crash the comparison below on a misimplemented probe.
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(tz=timezone.utc) - self.cooldown
        if published <= cutoff:
            return None
        return (
            "its latest release was published "
            f"{published.isoformat(sep=' ', timespec='seconds')}, "
            "within the cooldown window"
        )

    @property
    def orphans(self) -> Iterator[Package]:
        """List packages installed as dependencies that nothing requires anymore.

        The read-only counterpart of the `--orphans` action flags: where
        `mpm cleanup --orphans` removes the orphans, this query only reports them,
        through the manager's native listing (`pacman --query --deps --unrequired`,
        `brew autoremove --dry-run`, `dnf repoquery --unneeded`, ...).
        {program}`mpm` builds no dependency graph: the manager decides what is
        orphaned.

        Optional. Will be simply skipped by {program}`mpm` if not implemented.
        """
        raise NotImplementedError

    def search(self, query: str, extended: bool, exact: bool) -> Iterator[Package]:
        """Search packages available for install.

        There is no need for this method to be perfect and sensitive to `extended` and
        `exact` parameters. If the package manager is not supporting these kind of
        options out of the box, just returns the closest subset of matching package you
        can come up with. Finer refiltering will happens in the
        {meth}`meta_package_manager.manager.PackageManager.refiltered_search` method
        below.

        Optional. Will be simply skipped by {program}`mpm` if not implemented.
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
        {meth}`meta_package_manager.manager.PackageManager.search` results to either
        exclude non-extended or non-exact matches.

        Returns a generator producing the same data as the
        {meth}`meta_package_manager.manager.PackageManager.search` method above.

        ```{tip}

        If you are implementing a package manager definition, do not waste time to
        filter CLI results. Let this method do this job.

        Instead, just implement the core
        {meth}`meta_package_manager.manager.PackageManager.search` method above and
        try to produce results as precise as possible using the native filtering
        capabilities of the package manager CLI.
        ```
        """
        for match in self.search(query, extended, exact):
            # The per-package match decision lives on the data model, shared with
            # the `installed` and `outdated` query filters.
            if match.matches(query, extended, exact):
                yield match

    def install(self, package_id: str, version: str | None = None) -> str:
        """Install one package and one only.

        Allows a specific `version` to be provided.
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

        Allows a specific `version` to be provided.
        """
        raise NotImplementedError

    def upgrade_all_cli_excluding(
        self,
        package_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Returns the CLI upgrading all outdated packages except the named ones.

        Optional refinement of {meth}`upgrade_all_cli` for managers whose full
        upgrade is one transaction with a native exclusion flag (pacman's
        `--ignore`). Under an active probe-backed cooldown, `mpm` prefers this
        over per-package upgrades: the manager keeps its own transaction and
        dependency ordering, and only the held packages are left out.
        """
        raise NotImplementedError

    def upgrade(self, package_id: str | None = None, version: str | None = None) -> str:
        """Perform an upgrade of either all or one package.

        Executes the CLI provided by either
        {meth}`meta_package_manager.manager.PackageManager.upgrade_all_cli` or
        {meth}`meta_package_manager.manager.PackageManager.upgrade_one_cli`.

        If the manager doesn't provides a full upgrade one-liner (i.e. if
        {meth}`meta_package_manager.manager.PackageManager.upgrade_all_cli` raises
        {exc}`NotImplementedError`), then the list of all outdated packages will be
        fetched (via {meth}`meta_package_manager.manager.PackageManager.outdated`) and
        each package will be updated one by one by calling
        {meth}`meta_package_manager.manager.PackageManager.upgrade_one_cli`.

        See for example the case of
        {meth}`meta_package_manager.managers.pip.Pip.upgrade_one_cli`.

        An active probe-backed cooldown (see {meth}`cooldown_hold_reason`)
        routes through {meth}`_upgrade_all_with_cooldown` instead of the plain
        one-shot command, so individual too-fresh releases can be held back
        while the rest of the upgrade proceeds.
        """
        if package_id:
            cli = self.upgrade_one_cli(package_id, version=version)

        else:
            if self._cooldown_probe_engaged:
                logging.info(
                    "Active cooldown: hold back any release younger than the "
                    "window, and upgrade the rest.",
                    extra={"label": self.id},
                )
                return self._upgrade_all_with_cooldown()
            try:
                cli = self.upgrade_all_cli()
            except NotImplementedError:
                logging.debug(
                    "upgrade_all_cli operation not implemented. "
                    "Call single upgrade operation on each package, one-by-one.",
                )
                return self._upgrade_all_one_by_one()

        return self.run(cli, extra_env=self.extra_env)

    def _upgrade_all_with_cooldown(self) -> str:
        """Upgrade all outdated packages, holding back the too-fresh ones.

        The full-upgrade path of an active probe-backed cooldown: each
        outdated package is checked against {meth}`cooldown_hold_reason` and
        held back, with a `WARNING` naming the reason, rather than upgraded.

        A manager implementing {meth}`upgrade_all_cli_excluding` keeps its
        native one-transaction upgrade, the held packages riding its exclusion
        flag (and a run with nothing held falls back to the plain
        {meth}`upgrade_all_cli`). Every other manager upgrades the eligible
        packages one by one instead, deliberately even when nothing is held:
        its one-shot command may cover more than the packages enumerated here
        (`flatpak update` also pulls runtimes), and whatever the listing did
        not enumerate was never probed.
        """
        with self.acting_as("outdated"):
            outdated_packages = tuple(self.refiltered_outdated)
        held = []
        eligible = []
        for package in outdated_packages:
            hold = self.cooldown_hold_reason(package.id)
            if hold:
                logging.warning(
                    f"Hold {package.id}: {hold}.",
                    extra={"label": self.id},
                )
                held.append(package.id)
            else:
                eligible.append(package.id)
        if self._defines("upgrade_all_cli_excluding"):
            if held:
                cli = self.upgrade_all_cli_excluding(tuple(held))
            else:
                cli = self.upgrade_all_cli()
            return self.run(cli, extra_env=self.extra_env)
        logs = []
        for package_id in eligible:
            output = self.upgrade(package_id)
            if output:
                logs.append(output)
        return "\n".join(logs)

    def _upgrade_all_one_by_one(self) -> str:
        """Upgrade every outdated package through its own one-package CLI.

        The fallback behind managers with no native one-shot upgrade command.
        """
        # The listing is a read-only query, so it runs under the `outdated`
        # stamp: it resolves the short read-only timeout, and `mpm --plan`
        # executes it for real instead of capturing it, so the plan lists the
        # actual per-package upgrade commands.
        with self.acting_as("outdated"):
            outdated_packages = tuple(self.refiltered_outdated)
        logs = []
        for package in outdated_packages:
            output = self.upgrade(package.id)
            if output:
                logs.append(output)
        return "\n".join(logs)

    def remove(self, package_id: str) -> str:
        """Remove one package and one only.

        Optional. Will be simply skipped by {program}`mpm` if not implemented.
        """
        raise NotImplementedError

    def remove_orphan(self, package_id: str) -> str:
        """Remove one package together with the dependencies it alone pulled in.

        The opt-in counterpart to
        {meth}`meta_package_manager.manager.PackageManager.remove`, surfaced as
        `mpm remove --orphans`. It maps to the manager's native "remove and drop
        now-unneeded dependencies" verb (`apt remove --auto-remove`,
        `pacman --remove --recursive`, `dnf autoremove`, ...), so {program}`mpm`
        builds no dependency graph of its own.

        Optional. A manager with no such native verb leaves this
        {exc}`NotImplementedError`; `mpm remove --orphans` then falls back to
        {meth}`meta_package_manager.manager.PackageManager.remove` and logs one
        `INFO` capability-skip.
        """
        raise NotImplementedError

    def sync(self) -> None:
        """Refresh package metadata from remote repositories.

        Optional. Will be simply skipped by {program}`mpm` if not implemented.
        """
        raise NotImplementedError

    @classmethod
    def _defines(cls, method_name: str) -> bool:
        """Whether a non-base class in the manager's MRO defines `method_name`.

        The introspection primitive behind
        {func}`meta_package_manager.capabilities.implements_method` (which
        delegates here) and the {meth}`cleanup` composer below, hosted on the
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

        Not an operation managers define anymore: `cleanup` is the fixed
        composition of the non-destructive category methods a manager overrides
        ({meth}`cleanup_cache`, then {meth}`cleanup_repair`). The orphan
        sweep never joins in, native or synthesized: it is the one category that
        removes packages, so it only runs on an explicit `mpm cleanup --orphans`
        (or a direct {meth}`cleanup_orphan` call), keeping a plain `cleanup`
        package-preserving on every manager.

        A manager overriding no category method does not advertise the `cleanup`
        operation at all (see
        {func}`meta_package_manager.capabilities.implements`) and this composer
        is then a no-op.
        """
        for method_name in ("cleanup_cache", "cleanup_repair"):
            if self._defines(method_name):
                getattr(self, method_name)()

    def cleanup_orphan(self) -> None:
        """Remove every orphaned package on the system, sparing the caches.

        The system-wide "remove all packages nothing depends on anymore" sweep
        (`apt autoremove`, `brew autoremove`, `flatpak uninstall --unused`, ...).
        The one cleanup category that removes packages, so it is deliberately kept out
        of the plain {meth}`cleanup` composition and only runs on an explicit
        `mpm cleanup --orphans`.

        Distinct from
        {meth}`meta_package_manager.manager.PackageManager.remove_orphan`, which is
        scoped to one package's own orphaned dependencies. As with {meth}`cleanup`,
        {program}`mpm` builds no dependency graph: the manager decides what is orphaned.

        A manager with no native sweep verb is backfilled by this base implementation
        when it supports both the {attr}`orphans` query and package removal: list
        the orphans, remove each one (with {meth}`remove_orphan` when available, so
        every listed root takes its own now-orphaned subtree along), then re-query and
        repeat until the listing settles, since removing an orphan can orphan its own
        dependencies. The exact pattern of the synthesized full `upgrade --all`, and
        the in-process equivalent of Arch's classic `pacman -Rns $(pacman -Qtdq)`
        idiom. The re-query loop stops as soon as a round makes no progress, so
        removal failures cannot spin it forever.

        A manager implementing neither a native sweep nor the {attr}`orphans`
        query propagates {exc}`NotImplementedError`, and `mpm cleanup --orphans`
        simply skips it.
        """
        logging.debug(
            "No native orphan sweep. Remove listed orphans one by one.",
            extra={"label": self.id},
        )
        previous: frozenset[str] = frozenset()
        while True:
            # Raises NotImplementedError right here when the manager has no orphans
            # query, keeping the operation's optional contract. The listing is a
            # read-only query, so it runs under the `orphans` stamp: it resolves
            # the short read-only timeout, and `mpm --plan` executes it for real
            # instead of capturing it, so the plan lists the actual removals.
            with self.acting_as("orphans"):
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

        The cache category of {meth}`cleanup`, surfaced as
        `mpm cleanup --cache` and subtracted by `--skip-cache` (`apt clean`,
        `dnf clean all`, `brew cleanup`, `npm cache clean`, ...). The broadest
        category: for most managers the whole cleanup amounts to it.

        Optional. Will be simply skipped by {program}`mpm` if not implemented.
        """
        raise NotImplementedError

    def cleanup_repair(self) -> None:
        """Verify and repair the manager's local installation state.

        The repair category of {meth}`cleanup`, surfaced as
        `mpm cleanup --repair` and subtracted by `--skip-repair`
        (`flatpak repair --user`).

        Optional. Will be simply skipped by {program}`mpm` if not implemented.
        """
        raise NotImplementedError

    def doctor_cli(self) -> tuple[str, ...]:
        """Returns the complete CLI running the manager's native self-diagnosis.

        The invocation must be read-only (`brew doctor`, `pip check`,
        `pacman --database --check`, ...): {meth}`doctor` runs it, never mpm's
        mutating machinery. The surveyed doctor verbs share one convention this
        contract leans on: a non-zero exit code means problems were found.

        Optional. Will be simply skipped by {program}`mpm` if not implemented.
        """
        raise NotImplementedError

    def doctor(self) -> tuple[bool, str]:
        """Run the native self-diagnosis, returning `(healthy, report)`.

        Runs {meth}`doctor_cli` and interprets the outcome with a contract of
        its own, distinct from every other operation:

        - **Health is the exit code alone.**
          {meth}`~meta_package_manager.execution.CLIExecutor.run`'s failure gate
          tolerates a non-zero exit with a silent `<stderr>` (a benign status
          for query parsers), but for a diagnosis that exit *is* the verdict:
          `pip check` reports its conflicts on `<stdout>` only and would
          read as healthy under the gate.
        - **The report merges both streams.** The tools split their findings
          across them (`brew doctor` warns on `<stderr>`), and the report is
          relayed verbatim to the user: there is nothing to parse.
        - **The diagnosis is not an error.** The failure-gate entry an unhealthy
          exit may have accumulated is reclaimed from
          {attr}`~meta_package_manager.execution.CLIExecutor.cli_errors`, so
          the end-of-run error summary is not inflated by a verdict `mpm
          doctor` already reports on its own. The gate's `WARNING` diagnosis
          relay is skipped for the same reason (`doctor` sits in the gate's
          `_DIAGNOSIS_EXEMPT_OPERATIONS`): the findings land in the report,
          verbatim. A run that never completed
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

        Extension point reserved for {attr}`ManagerScope.PROJECT` managers: detecting
        virtual environments, lockfiles, or project manifests scattered across the
        filesystem.

        ```{caution}
        Not implemented for any manager yet. System-scoped managers (the default) own
        no project trees to discover.
        ```

        ```{todo}
        Implement project-scope discovery. The candidate ecosystems, the
        project files that signal each and the architecture this waits on are
        catalogued in {doc}`/unsupported`.
        ```
        """
        raise NotImplementedError
