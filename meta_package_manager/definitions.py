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
"""Declarative package managers: the TOML schema and its class factory.

A ``[mpm.managers.<id>]`` configuration section describes a manager as data. This
module owns everything that turns such a description into a live
:py:class:`~meta_package_manager.manager.PackageManager` subclass:

- the **schema vocabulary**: which manager attributes a section may set, both on a
  shipped manager (:data:`OVERRIDABLE_FIELDS`) and on a brand-new definition
  (:data:`DEFINITION_CLI_FIELDS`, the operations DSL constants);
- the **validation and parsing** layer (:func:`parse_manager_definition`), shared
  by ``--validate-config`` and the runtime registration path so a config that
  survives one survives the other;
- the **class factory** (:func:`build_manager_class`), which synthesizes a
  :class:`ConfigDrivenManager` subclass implementing exactly the operations the
  definition declares;
- the **bundled-definition loader** (:func:`load_bundled_definitions`,
  :func:`build_bundled_managers`): mpm ships some managers as ``*.toml`` package
  data under ``meta_package_manager/managers/``, each a single
  ``[mpm.managers.<id>]`` section in the exact schema a user would write.

The runtime *policy* around definitions stays in
:py:mod:`meta_package_manager.config`: where sections may be loaded from, the
trust gate on local files, the override-application pass and the registration
passes wired into the CLI. The split keeps this module dependent on
:py:mod:`meta_package_manager.manager` only, so the configuration layer can build
on it without a circular import.
"""

from __future__ import annotations

import importlib.resources
import logging
import re
import sys
from dataclasses import dataclass
from functools import cache
from typing import cast

from click_extra.config import ValidationError
from extra_platforms import ALL_GROUP_IDS, ALL_PLATFORMS, traits_from_ids

from .manager import MetaPackageManager, PackageManager

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping
    from pathlib import Path
    from typing import Any, Final

    from .package import Package


def _to_str(value: Any) -> str:
    """Validate that the value is a string."""
    if not isinstance(value, str):
        raise TypeError(f"expected a string, got {type(value).__name__}: {value!r}")
    return value


def _to_bool(value: Any) -> bool:
    """Validate that the value is a boolean."""
    if not isinstance(value, bool):
        raise TypeError(f"expected a boolean, got {type(value).__name__}: {value!r}")
    return value


def _to_int(value: Any) -> int:
    """Validate that the value is an integer.

    Rejects ``bool`` because :py:class:`bool` is a subclass of :py:class:`int`
    in Python, but configuration intent is unambiguous: a boolean is never an
    acceptable integer.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"expected an integer, got {type(value).__name__}: {value!r}")
    return value


def _to_str_tuple(value: Any) -> tuple[str, ...]:
    """Validate that the value is a list/tuple of strings, return a tuple."""
    if not isinstance(value, (list, tuple)):
        raise TypeError(
            f"expected a list of strings, got {type(value).__name__}: {value!r}"
        )
    for item in value:
        if not isinstance(item, str):
            raise TypeError(
                f"expected all entries to be strings, "
                f"got {type(item).__name__}: {item!r}"
            )
    return tuple(value)


def _to_str_dict(value: Any) -> dict[str, str]:
    """Validate that the value is a mapping of strings to strings."""
    if not isinstance(value, dict):
        raise TypeError(
            f"expected a table of string-to-string, "
            f"got {type(value).__name__}: {value!r}"
        )
    for k, v in value.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise TypeError(
                f"expected a table of string-to-string entries, got {k!r} = {v!r}"
            )
    return dict(value)


OVERRIDABLE_FIELDS: Final[Mapping[str, Callable[[Any], Any]]] = {
    "cli_names": _to_str_tuple,
    "cli_search_path": _to_str_tuple,
    "deprecated": _to_bool,
    "dry_run": _to_bool,
    "extra_env": _to_str_dict,
    "ignore_auto_updates": _to_bool,
    "post_args": _to_str_tuple,
    "pre_args": _to_str_tuple,
    "pre_cmds": _to_str_tuple,
    "requirement": _to_str,
    "stop_on_error": _to_bool,
    "sudo": _to_bool,
    "timeout": _to_int,
    "version_cli_options": _to_str_tuple,
    "version_regexes": _to_str_tuple,
}
"""Per-manager attributes a user is allowed to override from the ``[mpm.managers.<id>]``
configuration section.

Each entry maps a :py:class:`meta_package_manager.manager.PackageManager` attribute name
to a converter that validates the raw TOML value and returns the value as the
attribute's expected runtime type. Lists are coerced into tuples to match the
attributes' tuple types.

.. note::
    ``id``, ``name``, ``platforms``, ``homepage_url`` and ``virtual`` are
    intentionally excluded: they are identity, lookup or platform-classification
    attributes that the pool's registration relies on. Phase 1 of TOML-driven
    configuration only exposes attributes whose runtime override is safe.
"""


VALID_PLATFORM_TOKENS: Final[frozenset[str]] = frozenset(
    {platform.id for platform in ALL_PLATFORMS} | set(ALL_GROUP_IDS),
)
"""Platform and group IDs accepted in a definition's ``platforms`` list.

Union of every :py:class:`extra_platforms.Platform` ID and every group ID, so both a
specific platform (``ubuntu``) and a group (``linux``, ``all_platforms``) resolve.
"""


DEFINITION_CLI_FIELDS: Final[Mapping[str, Callable[[Any], Any]]] = {
    **{
        name: OVERRIDABLE_FIELDS[name]
        for name in (
            "cli_names",
            "cli_search_path",
            "extra_env",
            "post_args",
            "pre_args",
            "pre_cmds",
            "requirement",
            "timeout",
            "version_cli_options",
            "version_regexes",
        )
    },
    # Definition-only fields, with no OVERRIDABLE_FIELDS counterpart: a built-in
    # manager's escalation policies, version probe and Brewfile mapping are reviewed
    # code, while a definition declares them as data.
    "brewfile_entry_type": _to_str,
    "brewfile_skip_warning": _to_str,
    "default_sudo": _to_bool,
    "internal_sudo": _to_bool,
    "version_cli": _to_str,
}
"""CLI-execution attributes a definition may set, mostly reusing the override
converters.

The runtime-preference fields (``deprecated``, ``dry_run``, ``ignore_auto_updates``,
``stop_on_error``) are excluded: they are command-line/global concerns, not part of a
manager's identity, and resolve through the usual option precedence.

Five fields are definition-only:

- ``brewfile_entry_type`` maps the manager onto a Homebrew Bundle DSL entry so its
  installed packages join ``mpm dump --brewfile`` exports (see
  :py:attr:`~meta_package_manager.manager.PackageManager.brewfile_entry_type`).
- ``brewfile_skip_warning`` is the message emitted when the manager's packages are
  deliberately left out of such an export (see
  :py:attr:`~meta_package_manager.manager.PackageManager.brewfile_skip_warning`).
- ``default_sudo`` is the manager's built-in escalation policy (see
  :py:attr:`~meta_package_manager.execution.CLIExecutor.default_sudo`). Operations
  marked ``sudo = true`` escalate by default, while the user's global ``--no-sudo``
  flag or a ``sudo`` override still win.
- ``internal_sudo`` marks a manager whose CLI invokes ``sudo`` itself mid-run (see
  :py:attr:`~meta_package_manager.execution.CLIExecutor.internal_sudo`). mpm never
  wraps its commands in ``sudo``; priming instead reuses a warm credential cache
  for these internal escalations. See ``docs/sudo.md``.
- ``version_cli`` names an alternate binary for the version probe (see
  :py:attr:`~meta_package_manager.execution.CLIExecutor.version_cli`), for suites
  whose own binaries expose no version flag (OpenBSD's ``pkg_add``).
"""


DEFINITION_IDENTITY_FIELDS: Final[frozenset[str]] = frozenset(
    {"name", "platforms", "homepage_url", "operations"},
)
"""Top-level keys of a definition section that are not CLI-execution fields."""


QUERY_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"installed", "outdated", "search"},
)
"""Operations that parse the command's stdout into packages."""


COMMAND_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"install", "remove", "sync", "cleanup", "upgrade_one", "upgrade_all"},
)
"""Operations that only run a command and produce no inventory to parse."""


ALL_DEFINITION_OPERATIONS: Final[frozenset[str]] = QUERY_OPERATIONS | COMMAND_OPERATIONS
"""Every operation name a definition may declare."""


RECOGNIZED_PARSE_FIELDS: Final[frozenset[str]] = frozenset(
    {"package_id", "installed_version", "latest_version"},
)
"""Named regex groups / JSON field keys a query parser may map to a package."""


REQUIRED_PARSE_FIELDS: Final[Mapping[str, frozenset[str]]] = {
    "installed": frozenset({"package_id"}),
    "outdated": frozenset({"package_id", "latest_version"}),
    "search": frozenset({"package_id"}),
}
"""Parse fields each query operation must extract to be useful.

``installed`` needs only the package ID: some tools genuinely track no per-package
version (Clear Linux bundles under ``swupd``, Cygwin listings under ``apt-cyg``), and
mpm's package model treats the installed version as optional everywhere. ``outdated``
without a ``latest_version`` would report nothing actionable, so there the version
capture stays mandatory.
"""


OPERATION_ARG_PLACEHOLDER: Final[Mapping[str, str]] = {
    "install": "package_id",
    "remove": "package_id",
    "upgrade_one": "package_id",
}
"""Placeholder each operation's ``args`` must reference, so a value is actually passed
to the CLI (a ``remove`` with no ``{package_id}`` would target nothing).

``search`` is deliberately absent: its ``{query}`` placeholder is optional. A tool
with no real search command can still declare the operation by listing its whole
catalog (``opkg list``, ``swupd bundle-list --all``) and letting
:py:meth:`meta_package_manager.manager.PackageManager.refiltered_search` narrow the
results, mirroring the search-from-scratch augmentation some built-in managers use.
"""


SEARCH_REFINEMENT_KEYS: Final[frozenset[str]] = frozenset(
    {"exact_args", "extended_args", "id_name_only_args"},
)
"""Optional per-refinement argument templates of the ``search`` operation.

Each key holds the CLI arguments spliced into the ``args`` template — at the
position of the matching ``{exact_args}``-style marker — when the refinement is
active: ``exact_args`` for an ``--exact`` search, ``extended_args`` for an
``--extended`` one, and ``id_name_only_args`` for the default ID/name-restricted
mode (mpm's ``--id-name-only``, for tools like Chocolatey whose *unrestricted*
search is the default and take a flag to narrow it). An inactive refinement
expands its marker to nothing.

Declaring a key advertises native support for the matching mpm flag
(``exact_args`` sets the ``search`` method's ``exact_support`` introspection
attribute, either of the other two sets ``extended_support``), which feeds the
augmentations documentation.
:py:meth:`meta_package_manager.manager.PackageManager.refiltered_search` still
refines the results client-side either way, exactly as for the built-in managers.
"""


ALLOWED_ARG_PLACEHOLDERS: Final[Mapping[str, frozenset[str]]] = {
    "install": frozenset({"package_id"}),
    "remove": frozenset({"package_id"}),
    "search": frozenset({"query"}) | SEARCH_REFINEMENT_KEYS,
    "upgrade_one": frozenset({"package_id"}),
}
"""Placeholders each operation's ``args`` may reference.

Operations absent from this mapping take no placeholder at all. Any ``{token}``
outside the operation's set is rejected at parse time: a typoed ``{qeury}`` would
otherwise reach the CLI as a literal argument and fail in silent, tool-specific ways.
"""


ARG_PLACEHOLDER_REGEX: Final = re.compile(r"\{([a-z_]+)\}")
"""Match ``{placeholder}`` tokens in an operation's args, for validation."""


JSON_FIELD_SELECTOR_REGEX: Final = re.compile(
    r"^(?P<key>[^\[\]]+?)(?:\[(?P<index>\d+)\])?$",
)
"""Parse a JSON field selector: a key name with an optional ``[N]`` list index.

A bare ``version`` maps the package field to the item's ``version`` key. A
``versions[0]`` selector additionally picks one element out of a list-valued key
(zerobrew reports each package's installed versions as an array). Anything more
nested stays out of the DSL on purpose: a manager needing real JSON traversal is
better served by a Python class.
"""


QUERY_OPERATION_KEYS: Final[frozenset[str]] = frozenset(
    {"args", "cli", "regex", "format", "fields", "list_path", "sudo"},
)
"""Keys allowed in a query operation's table.

``cli`` is the same alternate-binary hook as on command operations. ``sudo = true``
marks the query as privileged, for the rare tool that gates even its read-only
listings behind root (``deb-get``'s upgradable check); escalation then follows the
usual per-manager policy.
"""


SEARCH_OPERATION_KEYS: Final[frozenset[str]] = (
    QUERY_OPERATION_KEYS | SEARCH_REFINEMENT_KEYS
)
"""Keys allowed in the ``search`` operation's table: a query operation plus the
per-refinement argument templates of :data:`SEARCH_REFINEMENT_KEYS`."""


COMMAND_OPERATION_KEYS: Final[frozenset[str]] = frozenset({"args", "cli", "sudo"})
"""Keys allowed in a command operation's table.

``cli`` names an alternate binary for this operation, resolved on the search path
at call time: it lets one definition span sibling binaries (``urpmq`` querying
while ``urpmi`` installs). ``sudo = true`` marks the operation as privileged,
mirroring the ``sudo=True`` flag built-in managers pass to ``run_cli``: escalation
then follows the per-manager policy (the definition's ``default_sudo``, overridden
by the user's ``--sudo``/``--no-sudo``).
"""


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
    ``default_sudo``, overridden by the user's ``--sudo``/``--no-sudo``. Command
    operations are the usual bearers; a query may also set it, for the rare tool
    that gates its read-only listings behind root (``deb-get``).
    """

    exact_args: tuple[str, ...] | None = None
    """Arguments spliced at the ``{exact_args}`` marker of a ``search``'s ``args``
    when an exact match is requested, or ``None`` when the tool has no native
    exact mode. See :data:`SEARCH_REFINEMENT_KEYS`."""

    extended_args: tuple[str, ...] | None = None
    """Arguments spliced at the ``{extended_args}`` marker of a ``search``'s
    ``args`` when the extended (description-reaching) mode is requested, or
    ``None`` when the tool has no native switch for it. See
    :data:`SEARCH_REFINEMENT_KEYS`."""

    id_name_only_args: tuple[str, ...] | None = None
    """Arguments spliced at the ``{id_name_only_args}`` marker of a ``search``'s
    ``args`` when the default ID/name-restricted mode is requested, for tools
    whose unrestricted search is the default (Chocolatey's ``--by-id-only``), or
    ``None``. See :data:`SEARCH_REFINEMENT_KEYS`."""

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
    ``latest_version``) to its JSON selector, in ``"json"`` mode.

    A selector is a key name with an optional ``[N]`` list index
    (``versions[0]``); see :data:`JSON_FIELD_SELECTOR_REGEX`.
    """


@dataclass(frozen=True)
class ManagerDefinition:
    """A brand-new package manager declared from a ``[mpm.managers.<id>]`` section.

    Produced by :py:func:`parse_manager_definition` after validation, consumed by
    :func:`build_manager_class`.
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

    Set by :py:func:`build_bundled_managers` for the managers mpm ships as package
    data; stays ``None`` for a manager defined in a user's own configuration file.
    The documentation generator links a bundled manager's benchmark entry to this
    file, a config-defined manager having no Python source line to point at.
    """


def parse_manager_definition(
    manager_id: str,
    section: Any,
) -> ManagerDefinition:
    """Validate and parse one ``[mpm.managers.<id>]`` definition section.

    Returns a :py:class:`ManagerDefinition` ready for :py:func:`build_manager_class`.
    Raises :class:`click_extra.ValidationError` (path relative to the
    ``[mpm.managers]`` root) on any problem, so the same function backs both
    ``--validate-config`` and the runtime registration path.
    """
    if not isinstance(section, dict):
        raise ValidationError(
            manager_id,
            f"expected a table, got {type(section).__name__}",
            code="invalid_type",
        )
    if not re.fullmatch(r"[a-z][a-z0-9-]*", manager_id):
        raise ValidationError(
            manager_id,
            f"invalid manager ID {manager_id!r}: use lowercase letters, digits and "
            "dashes (e.g. 'my-tool').",
            code="invalid_id",
        )
    for required in ("platforms", "operations"):
        if required not in section:
            raise ValidationError(
                f"{manager_id}.{required}",
                f"a config-defined manager must declare {required!r}.",
                code="missing_field",
            )

    try:
        platforms = _to_str_tuple(section["platforms"])
    except TypeError as ex:
        raise ValidationError(
            f"{manager_id}.platforms", str(ex), code="invalid_type"
        ) from ex
    if not platforms:
        raise ValidationError(
            f"{manager_id}.platforms",
            "must list at least one platform or group.",
            code="invalid_value",
        )
    for token in platforms:
        if token.lower() not in VALID_PLATFORM_TOKENS:
            raise ValidationError(
                f"{manager_id}.platforms",
                f"unknown platform or group {token!r}.",
                code="unknown_platform",
            )

    name = manager_id
    if "name" in section:
        try:
            name = _to_str(section["name"])
        except TypeError as ex:
            raise ValidationError(
                f"{manager_id}.name", str(ex), code="invalid_type"
            ) from ex
    homepage_url = None
    if "homepage_url" in section:
        try:
            homepage_url = _to_str(section["homepage_url"])
        except TypeError as ex:
            raise ValidationError(
                f"{manager_id}.homepage_url", str(ex), code="invalid_type"
            ) from ex

    cli_fields: dict[str, Any] = {}
    for key, value in section.items():
        if key in DEFINITION_IDENTITY_FIELDS:
            continue
        converter = DEFINITION_CLI_FIELDS.get(key)
        if converter is None:
            allowed = sorted(set(DEFINITION_CLI_FIELDS) | DEFINITION_IDENTITY_FIELDS)
            raise ValidationError(
                f"{manager_id}.{key}",
                f"unknown field. Allowed: {', '.join(allowed)}.",
                code="unknown_field",
            )
        try:
            cli_fields[key] = converter(value)
        except TypeError as ex:
            raise ValidationError(
                f"{manager_id}.{key}", str(ex), code="invalid_type"
            ) from ex

    operations = _parse_operations(manager_id, section["operations"])
    return ManagerDefinition(
        manager_id=manager_id,
        name=name,
        platforms=platforms,
        homepage_url=homepage_url,
        cli_fields=cli_fields,
        operations=operations,
    )


def _parse_operations(
    manager_id: str,
    raw: Any,
) -> dict[str, OperationSpec]:
    """Validate and parse the ``[mpm.managers.<id>.operations]`` sub-table."""
    if not isinstance(raw, dict) or not raw:
        raise ValidationError(
            f"{manager_id}.operations",
            "must be a non-empty table of operations.",
            code="invalid_type",
        )
    operations = {}
    for op_name, op_section in raw.items():
        if op_name not in ALL_DEFINITION_OPERATIONS:
            raise ValidationError(
                f"{manager_id}.operations.{op_name}",
                f"unknown operation. Allowed: "
                f"{', '.join(sorted(ALL_DEFINITION_OPERATIONS))}.",
                code="unknown_operation",
            )
        operations[op_name] = _parse_operation_spec(manager_id, op_name, op_section)
    return operations


def _parse_operation_spec(
    manager_id: str,
    op_name: str,
    raw: Any,
) -> OperationSpec:
    """Validate and parse one operation table into an :class:`OperationSpec`."""
    path = f"{manager_id}.operations.{op_name}"
    if not isinstance(raw, dict):
        raise ValidationError(
            path, f"expected a table, got {type(raw).__name__}", code="invalid_type"
        )

    is_query = op_name in QUERY_OPERATIONS
    if op_name == "search":
        allowed_keys = SEARCH_OPERATION_KEYS
    elif is_query:
        allowed_keys = QUERY_OPERATION_KEYS
    else:
        allowed_keys = COMMAND_OPERATION_KEYS
    for key in raw:
        if key not in allowed_keys:
            raise ValidationError(
                f"{path}.{key}",
                f"unknown key. Allowed: {', '.join(sorted(allowed_keys))}.",
                code="unknown_field",
            )

    if "args" not in raw:
        raise ValidationError(f"{path}.args", "required.", code="missing_field")
    try:
        args = _to_str_tuple(raw["args"])
    except TypeError as ex:
        raise ValidationError(f"{path}.args", str(ex), code="invalid_type") from ex
    if not args:
        raise ValidationError(
            f"{path}.args", "must be a non-empty list.", code="invalid_value"
        )

    found_placeholders = {
        token for arg in args for token in ARG_PLACEHOLDER_REGEX.findall(arg)
    }
    allowed_placeholders = ALLOWED_ARG_PLACEHOLDERS.get(op_name, frozenset())
    unknown_placeholders = found_placeholders - allowed_placeholders
    if unknown_placeholders:
        listing = ", ".join("{" + p + "}" for p in sorted(unknown_placeholders))
        if allowed_placeholders:
            hint = "Allowed: " + ", ".join(
                "{" + p + "}" for p in sorted(allowed_placeholders)
            )
        else:
            hint = f"{op_name} args take no placeholder"
        raise ValidationError(
            f"{path}.args",
            f"unknown placeholder(s): {listing}. {hint}.",
            code="invalid_value",
        )
    placeholder = OPERATION_ARG_PLACEHOLDER.get(op_name)
    if placeholder and placeholder not in found_placeholders:
        raise ValidationError(
            f"{path}.args",
            f"{op_name} args must reference the {{{placeholder}}} placeholder.",
            code="invalid_value",
        )

    cli = None
    if "cli" in raw:
        try:
            cli = _to_str(raw["cli"])
        except TypeError as ex:
            raise ValidationError(f"{path}.cli", str(ex), code="invalid_type") from ex
        if not cli:
            raise ValidationError(
                f"{path}.cli", "must be a non-empty string.", code="invalid_value"
            )

    sudo = False
    if "sudo" in raw:
        try:
            sudo = _to_bool(raw["sudo"])
        except TypeError as ex:
            raise ValidationError(f"{path}.sudo", str(ex), code="invalid_type") from ex

    common = _parse_search_refinements(path, args, raw, found_placeholders)
    common.update(cli=cli, sudo=sudo)

    if is_query:
        return _parse_query_spec(path, op_name, args, raw, common)

    return OperationSpec(args=args, **common)


def _parse_search_refinements(
    path: str,
    args: tuple[str, ...],
    raw: dict[str, Any],
    found_placeholders: set[str],
) -> dict[str, Any]:
    """Validate and parse the per-refinement argument templates of a ``search``.

    Returns the :data:`SEARCH_REFINEMENT_KEYS` entries of the
    :class:`OperationSpec` constructor. Only ``search`` can carry them (the
    key filter upstream rejects them elsewhere), so for every other operation
    this collapses to three ``None`` values. Each declared refinement must pair
    with its ``{marker}`` in ``args`` — a marker with no argument list would
    leak into the CLI as a literal token, a list with no marker would never
    render — and the marker must stand as a whole argument, since a list cannot
    expand inside a larger string.
    """
    refinements: dict[str, Any] = {}
    for refinement in sorted(SEARCH_REFINEMENT_KEYS):
        marker = "{" + refinement + "}"
        for arg in args:
            if marker in arg and arg != marker:
                raise ValidationError(
                    f"{path}.args",
                    f"{marker} must be a standalone argument, not embedded in {arg!r}.",
                    code="invalid_value",
                )
        if refinement not in raw:
            refinements[refinement] = None
            if refinement in found_placeholders:
                raise ValidationError(
                    f"{path}.args",
                    f"references {marker} but declares no {refinement!r} list.",
                    code="invalid_value",
                )
            continue
        try:
            values = _to_str_tuple(raw[refinement])
        except TypeError as ex:
            raise ValidationError(
                f"{path}.{refinement}", str(ex), code="invalid_type"
            ) from ex
        for value in values:
            if ARG_PLACEHOLDER_REGEX.search(value):
                raise ValidationError(
                    f"{path}.{refinement}",
                    f"{value!r} may not carry a placeholder.",
                    code="invalid_value",
                )
        if refinement not in found_placeholders:
            raise ValidationError(
                f"{path}.args",
                f"declares {refinement!r} but the args have no {marker} marker.",
                code="invalid_value",
            )
        refinements[refinement] = values
    return refinements


def _parse_query_spec(
    path: str,
    op_name: str,
    args: tuple[str, ...],
    raw: dict[str, Any],
    common: dict[str, Any],
) -> OperationSpec:
    """Validate the parser half of a query operation (``regex`` or JSON ``fields``).

    ``common`` carries the constructor entries already validated upstream (the
    alternate ``cli``, the ``sudo`` marker, the search refinements).
    """
    has_regex = "regex" in raw
    has_json = raw.get("format") == "json" or "fields" in raw
    if has_regex and has_json:
        raise ValidationError(
            path, "use either 'regex' or JSON 'fields', not both.", code="invalid_value"
        )
    if not has_regex and not has_json:
        raise ValidationError(
            path,
            "a query operation needs a 'regex' or a JSON 'fields' parser.",
            code="missing_field",
        )
    required = REQUIRED_PARSE_FIELDS[op_name]

    if has_regex:
        try:
            regex = _to_str(raw["regex"])
        except TypeError as ex:
            raise ValidationError(f"{path}.regex", str(ex), code="invalid_type") from ex
        try:
            compiled = re.compile(regex)
        except re.error as ex:
            raise ValidationError(
                f"{path}.regex",
                f"invalid regular expression: {ex}.",
                code="invalid_value",
            ) from ex
        _check_parse_fields(f"{path}.regex", set(compiled.groupindex), required)
        return OperationSpec(args=args, parse_mode="regex", regex=regex, **common)

    if "fields" not in raw:
        raise ValidationError(
            f"{path}.fields",
            "JSON parsing requires a 'fields' mapping.",
            code="missing_field",
        )
    try:
        fields = _to_str_dict(raw["fields"])
    except TypeError as ex:
        raise ValidationError(f"{path}.fields", str(ex), code="invalid_type") from ex
    _check_parse_fields(f"{path}.fields", set(fields), required)
    for role, selector in fields.items():
        if not JSON_FIELD_SELECTOR_REGEX.match(selector):
            raise ValidationError(
                f"{path}.fields",
                f"invalid selector {selector!r} for {role}: use a key name with "
                "an optional [N] list index, like 'version' or 'versions[0]'.",
                code="invalid_value",
            )
    list_path = None
    if "list_path" in raw:
        try:
            list_path = _to_str(raw["list_path"])
        except TypeError as ex:
            raise ValidationError(
                f"{path}.list_path", str(ex), code="invalid_type"
            ) from ex
    return OperationSpec(
        args=args, parse_mode="json", list_path=list_path, fields=fields, **common
    )


def _check_parse_fields(path: str, present: set[str], required: frozenset[str]) -> None:
    """Reject unrecognized parse fields and require the mandatory ones."""
    unknown = present - RECOGNIZED_PARSE_FIELDS
    if unknown:
        raise ValidationError(
            path,
            f"unrecognized field(s): {', '.join(sorted(unknown))}. "
            f"Allowed: {', '.join(sorted(RECOGNIZED_PARSE_FIELDS))}.",
            code="invalid_value",
        )
    missing = required - present
    if missing:
        raise ValidationError(
            path,
            f"missing required field(s): {', '.join(sorted(missing))}.",
            code="invalid_value",
        )


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


def _json_field(item: dict, selector: str) -> Any:
    """Resolve a field ``selector`` against one JSON package ``item``.

    A bare key returns the key's value; a ``key[N]`` selector picks the ``N``-th
    element out of a list-valued key (see :data:`JSON_FIELD_SELECTOR_REGEX`,
    which validated the syntax at parse time). Anything that does not resolve —
    missing key, non-list value under an indexed selector, out-of-range index —
    returns ``None``, so an unexpected payload yields incomplete packages rather
    than raising.
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


def _iter_parsed(
    manager: PackageManager,
    output: str,
    spec: OperationSpec,
    compiled: re.Pattern[str] | None,
) -> Iterator[dict[str, str]]:
    """Yield ``Package`` keyword dicts extracted from a query command's ``output``.

    Honors :py:attr:`OperationSpec.parse_mode`: per-line named-group matching for
    ``"regex"``, key lookups under :py:attr:`OperationSpec.list_path` for ``"json"``
    (parsed through the shared
    :py:meth:`~meta_package_manager.manager.PackageManager.parse_json`, so a
    malformed payload warns and yields nothing, exactly like the built-in
    managers). Skips entries with no ``package_id`` and version values that are
    absent or null.
    """
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
        data = manager.parse_json(output)
        if data is None:
            return
        for item in _navigate_json(data, spec.list_path):
            if not isinstance(item, dict):
                continue
            raw_id = _json_field(item, spec.fields["package_id"])
            if not raw_id:
                continue
            kwargs = {"id": str(raw_id)}
            for role in ("installed_version", "latest_version"):
                selector = spec.fields.get(role)
                if selector is not None:
                    value = _json_field(item, selector)
                    if value is not None:
                        kwargs[role] = str(value)
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
        output = self.run_cli(
            *spec.args,
            override_cli_path=_op_cli_path(self, spec),
            sudo=spec.sudo,
        )
        for kwargs in _iter_parsed(self, output, spec, compiled):
            yield self.package(**kwargs)

    return property(query)


def _expand_search_args(
    spec: OperationSpec, query: str, extended: bool, exact: bool
) -> list[str]:
    """Render a ``search``'s ``args`` template for one query.

    Each :data:`SEARCH_REFINEMENT_KEYS` marker expands, in place, to its
    argument list when the matching refinement is active and to nothing
    otherwise (``id_name_only_args`` being active when ``extended`` is *not*
    requested). The ``{query}`` placeholder is substituted last.
    """
    active: dict[str, tuple[str, ...] | None] = {
        "exact_args": spec.exact_args if exact else (),
        "extended_args": spec.extended_args if extended else (),
        "id_name_only_args": spec.id_name_only_args if not extended else (),
    }
    expanded: list[str] = []
    for arg in spec.args:
        token = arg[1:-1] if arg.startswith("{") and arg.endswith("}") else None
        if token in active:
            expanded.extend(active[token] or ())
        else:
            expanded.append(arg)
    return _render_args(tuple(expanded), query=query)


def _make_search(
    spec: OperationSpec, compiled: re.Pattern[str] | None
) -> Callable[..., Iterator[Package]]:
    """Build a ``search`` method.

    The per-refinement argument templates (see :data:`SEARCH_REFINEMENT_KEYS`)
    render the tool's native exact/extended switches when declared;
    :py:meth:`~meta_package_manager.manager.PackageManager.refiltered_search`
    refilters the raw results either way, exactly as for the built-in managers.
    """

    def search(
        self: PackageManager, query: str, extended: bool, exact: bool
    ) -> Iterator[Package]:
        output = self.run_cli(
            *_expand_search_args(spec, query, extended, exact),
            override_cli_path=_op_cli_path(self, spec),
            sudo=spec.sudo,
        )
        for kwargs in _iter_parsed(self, output, spec, compiled):
            yield self.package(**kwargs)

    # Same introspection surface as the search_capabilities decorator on class
    # managers: a declared refinement template advertises native support, its
    # absence signals reliance on mpm's refiltering.
    search.extended_support = (  # type: ignore[attr-defined]
        spec.extended_args is not None or spec.id_name_only_args is not None
    )
    search.exact_support = spec.exact_args is not None  # type: ignore[attr-defined]
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
    """Synthesize a :py:class:`~meta_package_manager.manager.PackageManager` subclass
    from a validated definition.

    Assembles a class namespace from the definition's identity and CLI fields, then
    adds one method (or property) per declared operation. Only the declared operations
    land in the namespace, so :py:func:`meta_package_manager.capabilities.implements`
    reflects exactly what the user configured. Single- and all-package upgrades map to
    :py:meth:`~meta_package_manager.manager.PackageManager.upgrade_one_cli` /
    :py:meth:`~meta_package_manager.manager.PackageManager.upgrade_all_cli` so the
    inherited :py:meth:`~meta_package_manager.manager.PackageManager.upgrade`
    orchestrator drives them, just like the built-in managers.
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


# Bundled manager definitions.
#
# mpm ships a few managers as data rather than Python classes: a TOML file per manager
# under meta_package_manager/managers/, each a single [mpm.managers.<id>] section in the
# exact schema a user would write. They are parsed and built through the same
# parse_manager_definition / build_manager_class path as any user definition, then loaded
# into the pool at construction time (ManagerPool.register), so they are always available
# and earn first-class --<id> flags. The trust gate guarding user definitions (see
# meta_package_manager.config) does not apply: package data shipped in the wheel is
# read-only and as trusted as the Python modules beside it.
#
# Each bundled file also carries a top-level [samples] table: source-derived output
# fixtures locking the version probe and the declared parsers, the config-defined twin
# of the shell-session samples embedded in class docstrings. The loader below only
# consumes the "mpm" key, so samples never reach the runtime; they feed the hermetic
# test_bundled_version_regex and test_bundled_parsing suites, which glob the shipped
# files and derive their parametrizes from them.


BUNDLED_DEFINITIONS_PACKAGE: Final[str] = "meta_package_manager.managers"
"""Import package whose ``*.toml`` resources hold mpm's bundled manager definitions."""


@cache
def load_bundled_definitions() -> tuple[tuple[ManagerDefinition, str], ...]:
    """Parse every bundled ``[mpm.managers.<id>]`` definition shipped as package data.

    Reads each ``*.toml`` resource of :data:`BUNDLED_DEFINITIONS_PACKAGE` via
    :py:mod:`importlib.resources` (so it works the same from an unpacked install, a zip
    or a Nuitka onefile), and validates every section with
    :py:func:`parse_manager_definition`. Returns ``(definition, source)`` pairs, where
    ``source`` is the repo-relative path used to link the manager's documentation. Cached
    because the shipped files never change at runtime.

    A malformed bundled file is a packaging bug, but it is logged and skipped rather than
    raised so one bad resource cannot break ``mpm`` startup for everyone. The hermetic
    ``test_bundled_inventory`` and ``test_bundled_registered`` keep the shipped files
    valid.
    """
    definitions: list[tuple[ManagerDefinition, str]] = []
    resources = importlib.resources.files(BUNDLED_DEFINITIONS_PACKAGE)
    for resource in sorted(resources.iterdir(), key=lambda item: item.name):
        if not resource.name.endswith(".toml"):
            continue
        source = f"meta_package_manager/managers/{resource.name}"
        try:
            data = tomllib.loads(resource.read_text(encoding="UTF-8"))
        except (OSError, tomllib.TOMLDecodeError) as ex:
            logging.warning(f"Skipping unreadable bundled definition {source}: {ex}")
            continue
        sections = data.get("mpm", {}).get("managers", {})
        for manager_id, section in sections.items():
            try:
                definitions.append(
                    (parse_manager_definition(manager_id, section), source),
                )
            except ValidationError as ex:
                logging.warning(
                    f"Skipping invalid bundled manager {manager_id!r} in {source}: {ex}",
                )
    return tuple(definitions)


def bundled_manager_ids() -> frozenset[str]:
    """IDs of the managers mpm ships as bundled configuration definitions."""
    return frozenset(
        definition.manager_id for definition, _ in load_bundled_definitions()
    )


def build_bundled_managers() -> list[PackageManager]:
    """Instantiate every bundled definition into a live, pool-ready manager.

    Each :py:class:`ConfigDrivenManager` subclass records the TOML file it came from
    in :py:attr:`ConfigDrivenManager.definition_source`, so the documentation
    generator can link to it. Called once by
    :py:attr:`meta_package_manager.pool.ManagerPool.register`.
    """
    managers: list[PackageManager] = []
    for definition, source in load_bundled_definitions():
        klass = build_manager_class(definition)
        klass.definition_source = source
        managers.append(klass())
    return managers
