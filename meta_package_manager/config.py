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

"""Configuration utilities for ``mpm``.

Hosts the schema of the ``[mpm]`` configuration section consumed by
:py:mod:`click_extra` and the per-manager attribute override mechanism driven by
``[mpm.managers.<id>]`` sections of the same configuration file.

The override mechanism keeps the pool and the configuration concerns separate:
:py:class:`meta_package_manager.pool.ManagerPool` owns the live manager instances
and the per-manager ``overridden_fields`` tracking dict, while this module owns the
schema (which fields are overridable, how to coerce values) and the application
logic. The pool is mutated through the :py:func:`apply_manager_overrides` helper,
keeping all configuration policy out of :py:mod:`meta_package_manager.pool`.
"""

from __future__ import annotations

import importlib.resources
import logging
import os
import re
import stat
import sys
import urllib.parse
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import tomli_w
from click import get_app_dir
from click_extra import echo
from click_extra.config import (
    CONFIG_PATH_METADATA_KEY,
    ConfigValidator,
    ValidationError,
    read_file,
)
from click_extra.context import CONF_FULL
from click_extra.theme import get_current_theme as theme
from extra_platforms import ALL_GROUP_IDS, ALL_PLATFORMS

from .manager import ManagerDefinition, OperationSpec, build_manager_class

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from typing import Any, Final

    import click

    from .manager import PackageManager
    from .pool import ManagerPool


@dataclass
class MpmConfig:
    """Schema for ``mpm`` configuration files.

    Defines the recognized options for the ``[mpm]`` (or ``[tool.mpm]``)
    configuration section.  Each field corresponds to a CLI option on the root
    ``mpm`` group.

    .. note::
        Dynamic manager selectors (``brew = true``, ``pip = false``, etc.),
        click-extra built-in options (``verbosity``, ``table_format``) and
        one-shot utility flags (``--bar-plugin-path``, ``--xkcd``) are handled
        by the ``default_map`` pipeline and do not appear here.

    .. note::
        Multi-word fields pin their config path through
        ``CONFIG_PATH_METADATA_KEY``: mpm's configuration convention is
        underscored keys (matching Click parameter names, the
        ``--validate-config`` checks and every documented example), while
        click-extra would otherwise kebab-case field names in the rendered
        ``click:config`` reference.
    """

    all_managers: bool = field(
        default=False,
        metadata={CONFIG_PATH_METADATA_KEY: "all_managers"},
    )
    """Force evaluation of all managers, including unsupported and deprecated."""

    ignore_auto_updates: bool = field(
        default=True,
        metadata={CONFIG_PATH_METADATA_KEY: "ignore_auto_updates"},
    )
    """Exclude auto-updating packages from outdated/upgrade results."""

    stop_on_error: bool = field(
        default=False,
        metadata={CONFIG_PATH_METADATA_KEY: "stop_on_error"},
    )
    """Stop on first manager CLI error instead of continuing."""

    dry_run: bool = field(
        default=False,
        metadata={CONFIG_PATH_METADATA_KEY: "dry_run"},
    )
    """Simulate CLI calls without performing any action."""

    sudo: bool | None = None
    """Force privileged manager operations with (``True``) or without (``False``)
    ``sudo``. Unset by default: system managers escalate, user-level managers do
    not. Overridden per manager by a ``sudo`` entry in ``[mpm.managers.<id>]``."""

    timeout: int | None = None
    """Maximum duration in seconds for each manager CLI call. When unset, a
    per-operation default applies: ``120`` for read-only queries (``installed``,
    ``outdated``, ``search``) and ``500`` for state-changing operations. A set
    value overrides every operation."""

    jobs: int | str = "auto"
    """Maximum number of managers to run concurrently. Accepts an integer, or the
    keywords ``auto`` (one fewer than the logical CPU count, the default) and
    ``max`` (every logical CPU); set ``1`` to run sequentially."""

    cooldown: str = ""
    """Minimum release age (like ``7 days`` or ``1 week``) a package version must
    reach before it can be installed or upgraded. Empty disables the gate."""

    require_cooldown_support: bool = field(
        default=True,
        metadata={CONFIG_PATH_METADATA_KEY: "require_cooldown_support"},
    )
    """Require managers to natively support a requested cooldown to run
    install/upgrade: skip those that cannot (fail-closed). Set to ``False`` to run
    them anyway, without the safeguard."""

    description: bool = False
    """Show package description in results."""

    sort_by: list[str] = field(
        default_factory=lambda: ["manager_id"],
        metadata={CONFIG_PATH_METADATA_KEY: "sort_by"},
    )
    """Default fields to sort results by, in priority order."""

    summary: bool = True
    """Print an end-of-run summary on stderr: a count line of per-manager totals
    plus any subcommand-specific follow-up notes."""

    network: bool = False
    """Opt into network calls during the run. Today this only affects
    ``mpm sbom``, which queries OSV.dev for vulnerability data."""

    suggest_contribs: bool = field(
        default=True,
        metadata={CONFIG_PATH_METADATA_KEY: "suggest_contribs"},
    )
    """Print a contribution invitation when a user override targets a field that
    likely indicates an upstream detection bug."""

    managers: dict[str, dict] = field(default_factory=dict)
    """Per-manager attribute overrides keyed by manager ID.

    Typed as ``dict[str, dict]`` so click-extra treats the sub-tree as opaque:
    its keys are manager IDs (data, not flag names) and its leaf entries are
    validated by :py:func:`validate_manager_overrides_section` registered as a
    :class:`click_extra.ConfigValidator`. The field carries no CLI flag — it
    only exists in the schema to declare opacity and to enable ``--validate-config``
    coverage of the override block."""


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


INVALIDATED_CACHED_PROPS: Final[tuple[str, ...]] = (
    "available",
    "cli_path",
    "executable",
    "fresh",
    "supported",
    "version",
)
"""Cached properties on :py:class:`meta_package_manager.manager.PackageManager` that may
have been computed from attributes covered by :data:`OVERRIDABLE_FIELDS`.

Any pre-computed values are popped from the manager instance's ``__dict__`` after an
override is applied so the next access recomputes them against the new attribute
values. Safe to pop even if nothing was cached.
"""


CONTRIBUTION_HINT_FIELDS: Final[frozenset[str]] = frozenset({
    "cli_names",
    "cli_search_path",
    "requirement",
    "version_cli_options",
    "version_regexes",
})
"""Subset of :data:`OVERRIDABLE_FIELDS` whose override probably reflects a real
upstream detection bug rather than a personal preference.

When the user overrides one of these, mpm did not find the binary, used the wrong
binary name, rejected a valid version, or failed to parse one. The other overridable
fields (``timeout``, ``ignore_auto_updates``, ``pre_args``, etc.) are user
preferences and do not warrant a contribution invitation.
"""


ISSUE_TRACKER_NEW_URL: Final[str] = (
    "https://github.com/kdeldycke/meta-package-manager/issues/new"
)
"""Base URL of the upstream GitHub issue tracker's new-issue endpoint."""


MAX_ISSUE_URL_LENGTH: Final[int] = 8192
"""Practical upper bound on the length of a pre-filled GitHub new-issue URL.

GitHub silently truncates very long URLs, which yields a broken issue form when
the user clicks the invitation. Anything past 8 KiB is treated as a bug in the
URL builder rather than a configuration we should tolerate."""


@dataclass(frozen=True)
class ContributionHint:
    """A user override of a detection-related field, candidate for upstream
    contribution.

    Captured at override time by :py:func:`apply_manager_overrides` so the user can
    later be invited to file an upstream issue with a pre-filled bug-report URL.
    """

    manager_id: str
    """ID of the manager whose attribute was overridden."""

    field: str
    """Name of the overridden :py:class:`~meta_package_manager.manager.PackageManager`
    attribute."""

    user_value: Any
    """Value the user supplied in their config file, after type coercion."""

    detected_cli_path: str | None
    """The CLI path mpm resolved with the built-in defaults, before the override
    took effect. ``None`` when mpm could not find the binary, which is itself a
    strong signal that the upstream search heuristics need help."""


def _build_issue_url(hint: ContributionHint) -> str:
    """Build a GitHub new-issue URL targeting the bug-report template, with the
    relevant fields pre-filled from ``hint``.

    Returns the URL only: it's the caller's job to render and surface it. Length
    stays well under GitHub's URL-length cap because the body summarizes the
    override and asks the user to paste their full ``mpm --verbosity DEBUG``
    output rather than embedding it.

    A pathological override value could still blow past
    :data:`MAX_ISSUE_URL_LENGTH`; the assertion below catches that in tests
    rather than letting the user click a URL GitHub will truncate.
    """
    detected = (
        f"`{hint.detected_cli_path}`"
        if hint.detected_cli_path
        else "**not found** (mpm could not resolve the binary on my system)"
    )
    # Render the override as valid TOML rather than Python repr so the user can
    # paste the snippet straight into their config file (or back into the issue
    # body) without translating tuples to TOML lists by hand.
    override_toml = tomli_w.dumps(
        {"mpm": {"managers": {hint.manager_id: {hint.field: hint.user_value}}}},
    ).rstrip()
    bug_description = (
        f"While running `mpm`, I had to override the "
        f"`{hint.field}` attribute on the `{hint.manager_id}` manager because "
        f"the upstream defaults did not work for my setup.\n"
        f"\n"
        f"My override:\n"
        f"\n"
        f"```toml\n"
        f"{override_toml}\n"
        f"```\n"
        f"\n"
        f"What mpm detected without the override:\n"
        f"\n"
        f"- `cli_path`: {detected}\n"
        f"\n"
        f"This invitation was generated automatically by `mpm` to help improve "
        f"the upstream detection heuristics. Please attach the diagnostic "
        f"command outputs requested in the sections below before submitting."
    )

    params = urllib.parse.urlencode(
        {
            "template": "bug-report.yml",
            "title": (
                f"[detection] {hint.manager_id}: "
                f"upstream defaults need adjustment for `{hint.field}`"
            ),
            "labels": "🐛 bug",
            "bug-description": bug_description,
        },
        quote_via=urllib.parse.quote,
    )
    url = f"{ISSUE_TRACKER_NEW_URL}?{params}"
    assert len(url) <= MAX_ISSUE_URL_LENGTH, (
        f"Pre-filled GitHub issue URL is {len(url)} characters, exceeding the "
        f"{MAX_ISSUE_URL_LENGTH}-character practical limit. GitHub would "
        f"truncate this URL and the user would land on a broken issue form. "
        f"Trim the bug-description template or fall back to a non-prefilled "
        f"link for oversized overrides."
    )
    return url


def format_contribution_hints(hints: list[ContributionHint]) -> str:
    """Render a multi-line, human-readable batch message inviting the user to
    contribute their overrides back upstream.

    Returns an empty string for an empty list so the caller can branch on
    truthiness without a length check.
    """
    if not hints:
        return ""

    arrow = theme().invoked_command("↗")
    lines = [
        f"{arrow} Detected user override(s) on fields that often indicate an "
        f"upstream detection bug.",
        "  Filing an issue helps improve mpm's detection heuristics for everyone:",
        "",
    ]
    for hint in hints:
        url = _build_issue_url(hint)
        lines.extend((
            f"  - {theme().invoked_command(hint.manager_id)}: "
            f"override on `{hint.field}`",
            f"    File a report: {url}",
        ))
    lines.extend((
        "",
        "  (Disable with `--no-suggest-contribs` or `[mpm] suggest_contribs = false`.)",
    ))
    return "\n".join(lines)


def validate_manager_overrides_section(
    section: Mapping[str, Any],
    *,
    pool: ManagerPool,
) -> None:
    """Strict validator for the ``[mpm.managers.<id>]`` configuration sub-tree.

    Pure function: inspects ``section`` against the pool's registered managers
    and :data:`OVERRIDABLE_FIELDS`, raises the first
    :class:`click_extra.ValidationError` it encounters, never mutates the pool.
    Suitable for registration as a :class:`click_extra.ConfigValidator` and for
    direct invocation by :py:func:`apply_manager_overrides` so both the
    ``--validate-config`` path and the runtime application path enforce the
    same rules.

    A section keyed by a built-in manager ID is validated as an *override* (its
    fields must be a subset of :data:`OVERRIDABLE_FIELDS`). A section keyed by any
    other ID is validated as a brand-new manager *definition* via
    :py:func:`parse_manager_definition`.

    :raises click_extra.ValidationError: when ``section`` is not a mapping, an
        override sets an unknown field or a wrong-typed value, or a definition is
        malformed. The ``path`` of the raised error is relative to the
        ``[mpm.managers]`` section root (e.g. ``"winget.cli_searchpath"``);
        click-extra prepends the app prefix when surfacing the error.
    """
    if not section:
        return
    if not isinstance(section, dict):
        raise ValidationError("", f"expected a table, got {type(section).__name__}")
    for manager_id, fields in section.items():
        if manager_id in pool.known_manager_ids:
            _validate_override_fields(manager_id, fields)
        else:
            # A section for an unknown ID that carries neither a definition's
            # required identity nor operations is most likely a typo of a built-in
            # ID rather than a new manager: report it as such for a clearer message.
            if (
                isinstance(fields, dict)
                and "operations" not in fields
                and "platforms" not in fields
            ):
                raise ValidationError(
                    manager_id,
                    f"unknown manager ID {manager_id!r}. To define a new manager, "
                    "declare 'platforms' and an [operations] table (see docs/overrides.md).",
                    code="unknown_manager",
                )
            parse_manager_definition(manager_id, fields)


def _validate_override_fields(manager_id: str, fields: Any) -> None:
    """Validate one ``[mpm.managers.<built-in id>]`` override section.

    Each field must be a known :data:`OVERRIDABLE_FIELDS` attribute and carry a
    value its converter accepts. Raises :class:`click_extra.ValidationError` on the
    first problem.
    """
    if not isinstance(fields, dict):
        raise ValidationError(
            manager_id,
            f"expected a table, got {type(fields).__name__}",
            code="invalid_type",
        )
    for field_name, raw_value in fields.items():
        converter = OVERRIDABLE_FIELDS.get(field_name)
        if converter is None:
            raise ValidationError(
                f"{manager_id}.{field_name}",
                f"unknown field. Allowed: {', '.join(sorted(OVERRIDABLE_FIELDS))}",
                code="unknown_field",
            )
        try:
            converter(raw_value)
        except TypeError as ex:
            raise ValidationError(
                f"{manager_id}.{field_name}",
                str(ex),
                code="invalid_type",
            ) from ex


def apply_manager_overrides(
    pool: ManagerPool,
    overrides: Mapping[str, Mapping[str, Any]] | None,
) -> list[ContributionHint]:
    """Apply per-manager attribute overrides parsed from the user's config file.

    Expects ``overrides`` to be a mapping of manager ID to a mapping of attribute
    name to its new value, as returned by ``conf["mpm"]["managers"]``. ``None``
    and empty mappings are accepted as no-op shortcuts so callers can
    unconditionally forward whatever was parsed from the config file.

    Validation is delegated to
    :py:func:`validate_manager_overrides_section`, which raises
    :class:`click_extra.ValidationError` on the first issue. Both the
    runtime config-loading path and the explicit ``--validate-config`` path
    enforce the same rules through that single validator, so a config that
    survives one survives the other.

    After validation succeeds, every override is applied as an instance
    attribute (shadowing the class default for the lifetime of the process),
    recorded in :py:attr:`ManagerPool.overridden_fields` so
    :py:meth:`ManagerPool._select_managers` skips the matching global
    ``--<flag>`` defaults for that manager, and the cached properties derived
    from the affected attributes are evicted so the next access recomputes
    them. List-valued fields use *replace* semantics: the override fully
    supersedes the built-in default.

    Returns a list of :class:`ContributionHint` entries, one per accepted
    override that targets a :data:`CONTRIBUTION_HINT_FIELDS` field. Each hint
    captures the pre-override ``cli_path`` so the contribution invitation can
    show what mpm would have detected without the user's intervention.
    """
    if not overrides:
        return []

    validate_manager_overrides_section(overrides, pool=pool)

    hints: list[ContributionHint] = []
    for manager_id, fields in overrides.items():
        # Sections keyed by an ID mpm does not ship (neither a built-in class nor a
        # bundled definition) are brand-new manager definitions, handled by
        # register_config_managers, not attribute overrides.
        if manager_id not in pool.known_manager_ids:
            continue
        manager = pool.register[manager_id]
        for field_name, raw_value in fields.items():
            value = OVERRIDABLE_FIELDS[field_name](raw_value)

            # Capture mpm's pre-override detection state for the hint, before
            # the setattr below would change the binary search behavior. Reading
            # cli_path triggers the cached_property, which is fine: the loop
            # tail evicts it via INVALIDATED_CACHED_PROPS.
            detected_cli_path: str | None = None
            if field_name in CONTRIBUTION_HINT_FIELDS:
                cli_path = manager.cli_path
                detected_cli_path = str(cli_path) if cli_path else None

            setattr(manager, field_name, value)
            pool.overridden_fields.setdefault(manager_id, set()).add(field_name)
            logging.debug(
                f"Applied override [mpm.managers.{manager_id}].{field_name} "
                f"= {value!r}",
            )

            if field_name in CONTRIBUTION_HINT_FIELDS:
                hints.append(
                    ContributionHint(
                        manager_id=manager_id,
                        field=field_name,
                        user_value=value,
                        detected_cli_path=detected_cli_path,
                    )
                )

        for prop in INVALIDATED_CACHED_PROPS:
            manager.__dict__.pop(prop, None)

    return hints


def build_manager_overrides_validator(pool: ManagerPool) -> ConfigValidator:
    """Construct a :class:`click_extra.ConfigValidator` for the
    ``[mpm.managers]`` sub-tree, bound to a specific :class:`ManagerPool`.

    Used by the CLI bootstrap (``@group`` decorator) to register a validator
    against the live pool. Wrapping :py:func:`validate_manager_overrides_section`
    in a closure satisfies the
    :py:attr:`click_extra.ConfigValidator.validator` signature
    (``Callable[[dict], None]``) while keeping the underlying validator pool-agnostic
    and testable in isolation.
    """

    def _validator(section: dict[str, Any]) -> None:
        validate_manager_overrides_section(section, pool=pool)

    return ConfigValidator(
        extension_path="managers",
        validator=_validator,
        description="Per-manager attribute overrides (see docs/configuration.md).",
    )


def dump_manager_overrides(manager: PackageManager) -> dict[str, Any]:
    """Return the current overridable attributes of ``manager`` as a TOML-ready
    dict.

    Walks :data:`OVERRIDABLE_FIELDS` in alphabetical order, reads each attribute
    from the manager instance, and converts tuples to lists so :py:mod:`tomli_w`
    can serialize the result without translation. Attributes whose value is
    ``None`` are skipped: TOML cannot express ``None`` and the user cannot
    override a field *to* ``None`` either, so emitting the key would be
    misleading.

    Every other overridable field is emitted, including ones still at the class
    default. The output is meant to be a canonical override template: paste,
    prune the rows that don't apply, and customize the rest.
    """
    result: dict[str, Any] = {}
    for field_name in sorted(OVERRIDABLE_FIELDS):
        value = getattr(manager, field_name)
        if value is None:
            continue
        if isinstance(value, tuple):
            value = list(value)
        result[field_name] = value
    return result


CTX_HINTS_KEY: Final[str] = "mpm.contribution_hints"
"""``ctx.meta`` key under which collected :class:`ContributionHint` entries are
accumulated between :py:func:`apply_manager_overrides_from_context` and
:py:func:`print_contribution_hints`."""


def _managers_section(ctx: click.Context) -> Mapping[str, Any] | None:
    """Return the ``[mpm.managers]`` mapping from the loaded config, or ``None``.

    Reads the full parsed config :py:mod:`click_extra` exposes under
    :data:`~click_extra.context.CONF_FULL` and drills into ``["mpm"]["managers"]``,
    tolerating a missing or malformed layer at each step. Shared by
    :py:func:`apply_manager_overrides_from_context` (the override pass) and
    :py:func:`register_config_managers_from_context` (the definition pass).
    """
    conf_full = ctx.meta.get(CONF_FULL) or {}
    mpm_section = conf_full.get("mpm") if isinstance(conf_full, dict) else None
    return mpm_section.get("managers") if isinstance(mpm_section, dict) else None


def apply_manager_overrides_from_context(
    ctx: click.Context,
    pool: ManagerPool,
) -> None:
    """Read the ``[mpm.managers.<id>]`` sections from the loaded config and apply
    them to ``pool``.

    Reads the full parsed config that :py:mod:`click_extra` exposes under
    :data:`~click_extra.context.CONF_FULL` after configuration discovery and
    forwards the ``["mpm"]["managers"]`` subtree to
    :py:func:`apply_manager_overrides`. Returns silently when no configuration
    file was loaded or when the section is absent.

    Any :class:`ContributionHint` returned by :py:func:`apply_manager_overrides` is
    stashed under :data:`CTX_HINTS_KEY` for :py:func:`print_contribution_hints` to
    surface at the end of the run.
    """
    overrides = _managers_section(ctx)
    _warn_risky_overrides_from_untrusted_source(ctx, pool, overrides)
    hints = apply_manager_overrides(pool, overrides)
    if hints:
        ctx.meta.setdefault(CTX_HINTS_KEY, []).extend(hints)


def _warn_risky_overrides_from_untrusted_source(
    ctx: click.Context,
    pool: ManagerPool,
    overrides: Mapping[str, Any] | None,
) -> None:
    """Warn when a command-redirecting override is read from an untrusted config source.

    Overrides on built-in managers still apply (for backward compatibility), but a
    :data:`RISKY_OVERRIDE_FIELDS` override (``pre_cmds``, ``cli_names``,
    ``cli_search_path``, ``sudo``) sourced from a remote URL or an unsafe-permission file
    can make mpm run an arbitrary binary, or run one as root, so it earns a loud
    heads-up. See ``docs/security.md``.
    """
    if not overrides:
        return
    source, source_is_url = _config_source(ctx)
    if not source_is_url and (source is None or config_file_is_trusted(source)):
        return
    for manager_id, fields in overrides.items():
        if manager_id not in pool.known_manager_ids or not isinstance(fields, dict):
            continue
        risky = RISKY_OVERRIDE_FIELDS.intersection(fields)
        if risky:
            origin = "a remote URL" if source_is_url else f"untrusted file {source}"
            logging.warning(
                f"Override of {', '.join(sorted(risky))} on "
                f"{theme().invoked_command(manager_id)} comes from {origin}; "
                "these fields can run arbitrary commands (see docs/security.md).",
            )


def print_contribution_hints(ctx: click.Context) -> None:
    """Print the collected contribution hints to ``<stderr>``.

    Reads from :data:`CTX_HINTS_KEY` and writes via :py:func:`click_extra.echo`
    rather than the logging module, so the message survives ``--verbosity
    CRITICAL`` and the ``logging.disable()`` block that suppresses log output for
    serialization formats. Caller is expected to gate this on the user's
    ``suggest_contribs`` preference.
    """
    hints = ctx.meta.get(CTX_HINTS_KEY) or []
    message = format_contribution_hints(hints)
    if message:
        echo(message, err=True)


# Brand-new manager definitions.
#
# Everything below turns a ``[mpm.managers.<id>]`` section whose ID is *not* a built-in
# into a live manager. This module owns the schema and the policy (what a definition may
# contain, where it may be loaded from); the class-building factory lives in
# :py:mod:`meta_package_manager.manager`. The split mirrors the override mechanism above:
# the pool owns instances, this module owns configuration policy.


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
    # manager's escalation default, version probe and Brewfile mapping are reviewed
    # code, while a definition declares them as data.
    "brewfile_entry_type": _to_str,
    "brewfile_skip_warning": _to_str,
    "default_sudo": _to_bool,
    "version_cli": _to_str,
}
"""CLI-execution attributes a definition may set, mostly reusing the override
converters.

The runtime-preference fields (``deprecated``, ``dry_run``, ``ignore_auto_updates``,
``stop_on_error``) are excluded: they are command-line/global concerns, not part of a
manager's identity, and resolve through the usual option precedence.

Four fields are definition-only:

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


ALLOWED_ARG_PLACEHOLDERS: Final[Mapping[str, frozenset[str]]] = {
    "install": frozenset({"package_id"}),
    "remove": frozenset({"package_id"}),
    "search": frozenset({"query"}),
    "upgrade_one": frozenset({"package_id"}),
}
"""Placeholders each operation's ``args`` may reference.

Operations absent from this mapping take no placeholder at all. Any ``{token}``
outside the operation's set is rejected at parse time: a typoed ``{qeury}`` would
otherwise reach the CLI as a literal argument and fail in silent, tool-specific ways.
"""


ARG_PLACEHOLDER_REGEX: Final = re.compile(r"\{([a-z_]+)\}")
"""Match ``{placeholder}`` tokens in an operation's args, for validation."""


QUERY_OPERATION_KEYS: Final[frozenset[str]] = frozenset(
    {"args", "cli", "regex", "format", "fields", "list_path"},
)
"""Keys allowed in a query operation's table.

``cli`` names an alternate binary for this operation, resolved on the search path at
call time: it lets one definition span sibling binaries (``urpmq`` querying while
``urpmi`` installs). Queries never take a ``sudo`` key: read-only operations stay
unprivileged.
"""


COMMAND_OPERATION_KEYS: Final[frozenset[str]] = frozenset({"args", "cli", "sudo"})
"""Keys allowed in a command operation's table.

``cli`` is the same alternate-binary hook as on query operations. ``sudo = true``
marks the operation as privileged, mirroring the ``sudo=True`` flag built-in managers
pass to ``run_cli``: escalation then follows the per-manager policy (the definition's
``default_sudo``, overridden by the user's ``--sudo``/``--no-sudo``).
"""


RISKY_OVERRIDE_FIELDS: Final[frozenset[str]] = frozenset(
    {"pre_cmds", "cli_names", "cli_search_path", "sudo"},
)
"""Override fields that can redirect mpm to run an arbitrary binary (or ``sudo``).

When such an override is read from an untrusted config source,
:py:func:`apply_manager_overrides_from_context` logs a warning. See ``docs/security.md``.
"""


def config_file_is_trusted(path: Path) -> bool:
    """Whether a config file is safe to load executable manager definitions from.

    Trusted on POSIX when both the file and its parent directory are owned by the
    current user or root and are not group- or world-writable, mirroring how ``ssh``,
    ``git`` and ``sudo`` reason about config-file trust: a writable file (or a writable
    directory that lets an attacker swap the file) could inject arbitrary commands.

    On platforms without ``os.getuid`` (Windows), the POSIX ownership model does not
    apply and the check is skipped (returns ``True``); see ``docs/security.md`` for the
    rationale and the residual risk.
    """
    if not hasattr(os, "getuid"):
        return True
    trusted_owners = {os.getuid(), 0}
    for target, is_dir in ((path, False), (path.parent, True)):
        try:
            stats = target.stat()
        except OSError:
            return False
        if stats.st_uid not in trusted_owners:
            return False
        writable_by_others = stats.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        sticky = stats.st_mode & stat.S_ISVTX
        # A group/world-writable directory is safe only if sticky (like ``/tmp``):
        # the sticky bit stops others renaming or replacing the config file. A
        # group/world-writable file is always unsafe.
        if writable_by_others and not (is_dir and sticky):
            return False
    return True


def _is_remote_url(location: str) -> bool:
    """Whether a config location string points at a remote URL, not a local path."""
    return location.startswith(("http://", "https://"))


def _config_source(ctx: click.Context) -> tuple[Path | None, bool]:
    """Return ``(local_path, is_url)`` for the config file click-extra loaded.

    Reads the location click-extra records under
    :data:`~click_extra.config.CONFIG_PATH_METADATA_KEY`. A remote URL yields
    ``(None, True)``; a local file yields ``(Path, False)``; nothing loaded yields
    ``(None, False)``.
    """
    raw = ctx.meta.get(CONFIG_PATH_METADATA_KEY)
    if not raw:
        return None, False
    text = str(raw)
    if _is_remote_url(text):
        return None, True
    return Path(text), False


def parse_manager_definition(
    manager_id: str,
    section: Any,
) -> ManagerDefinition:
    """Validate and parse one ``[mpm.managers.<id>]`` definition section.

    Returns a :py:class:`~meta_package_manager.manager.ManagerDefinition` ready for
    :py:func:`~meta_package_manager.manager.build_manager_class`. Raises
    :class:`click_extra.ValidationError` (path relative to the ``[mpm.managers]``
    root) on any problem, so the same function backs both ``--validate-config`` and
    the runtime registration path.
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
    allowed_keys = QUERY_OPERATION_KEYS if is_query else COMMAND_OPERATION_KEYS
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

    if is_query:
        return _parse_query_spec(path, op_name, args, raw, cli=cli)

    sudo = False
    if "sudo" in raw:
        try:
            sudo = _to_bool(raw["sudo"])
        except TypeError as ex:
            raise ValidationError(f"{path}.sudo", str(ex), code="invalid_type") from ex
    return OperationSpec(args=args, cli=cli, sudo=sudo)


def _parse_query_spec(
    path: str,
    op_name: str,
    args: tuple[str, ...],
    raw: dict[str, Any],
    cli: str | None = None,
) -> OperationSpec:
    """Validate the parser half of a query operation (``regex`` or JSON ``fields``)."""
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
        return OperationSpec(args=args, cli=cli, parse_mode="regex", regex=regex)

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
    list_path = None
    if "list_path" in raw:
        try:
            list_path = _to_str(raw["list_path"])
        except TypeError as ex:
            raise ValidationError(
                f"{path}.list_path", str(ex), code="invalid_type"
            ) from ex
    return OperationSpec(
        args=args, cli=cli, parse_mode="json", list_path=list_path, fields=fields
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


def register_config_managers(
    pool: ManagerPool,
    definitions: Mapping[str, ManagerDefinition],
    *,
    source: Path | None = None,
    source_is_url: bool = False,
) -> list[str]:
    """Build and register config-defined managers into ``pool``, applying the trust gate.

    A definition is skipped (with a warning) when its ID collides with a built-in, when
    it comes from a remote URL config, or when its local config file fails
    :py:func:`config_file_is_trusted`. Returns the IDs actually registered. Definitions
    whose ID is already in the pool (e.g. registered by the eager pre-load) are silently
    skipped so the eager and callback passes are idempotent.
    """
    registered = []
    for manager_id, definition in definitions.items():
        if manager_id in pool.known_manager_ids:
            logging.warning(
                f"Ignoring config-defined manager {manager_id!r}: "
                "a built-in or bundled manager already uses this ID.",
            )
            continue
        if manager_id in pool.register:
            continue
        if source_is_url:
            logging.warning(
                f"Refusing to define manager {manager_id!r} from a remote config URL "
                "for safety (see docs/security.md).",
            )
            continue
        if source is not None and not config_file_is_trusted(source):
            logging.warning(
                f"Refusing to define manager {manager_id!r} from {source}: "
                "unsafe config file ownership or permissions (see docs/security.md).",
            )
            continue
        pool.add_manager(build_manager_class(definition)())
        registered.append(manager_id)
        logging.info(
            f"Defined manager {theme().invoked_command(manager_id)} "
            f"from {source or 'configuration'}.",
        )
    return registered


def _collect_definitions(
    pool: ManagerPool,
    sections: Mapping[str, Any],
) -> dict[str, ManagerDefinition]:
    """Parse the non-built-in sections of ``[mpm.managers]`` into definitions.

    Sections keyed by a built-in ID (overrides) and any that fail to parse are skipped:
    parse failures were already surfaced by the load-time validator, so re-raising here
    would only duplicate the error.
    """
    definitions = {}
    for manager_id, section in sections.items():
        if manager_id in pool.known_manager_ids or manager_id in pool.register:
            continue
        try:
            definitions[manager_id] = parse_manager_definition(manager_id, section)
        except ValidationError:
            continue
    return definitions


def register_config_managers_from_context(
    ctx: click.Context,
    pool: ManagerPool,
) -> None:
    """Register config-defined managers from the loaded config (authoritative pass).

    Reads the parsed config under :data:`~click_extra.context.CONF_FULL`, parses the
    non-built-in ``[mpm.managers.<id>]`` sections, and registers them through
    :py:func:`register_config_managers`. This is the source of truth for *availability*:
    a manager defined in a config the eager pre-load could not reach (a URL, a custom
    path) still works from here, it just does not get a dedicated CLI flag.
    """
    sections = _managers_section(ctx)
    if not sections:
        return
    source, source_is_url = _config_source(ctx)
    register_config_managers(
        pool,
        _collect_definitions(pool, sections),
        source=source,
        source_is_url=source_is_url,
    )


def _candidate_config_path() -> tuple[Path | None, bool]:
    """Best-effort resolution of the config path for the eager pre-load.

    Mirrors click-extra's default discovery enough to find new-manager definitions
    before the CLI is built, without re-implementing all of it: an explicit
    ``MPM_CONFIG`` env var or ``--config`` argument wins, otherwise the first config
    file in the default application directory is used. Returns ``(path, is_url)``;
    URLs are reported but not read here (the authoritative pass handles them).
    """
    raw = os.environ.get("MPM_CONFIG")
    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg == "--config" and index + 1 < len(argv):
            raw = argv[index + 1]
        elif arg.startswith("--config="):
            raw = arg.split("=", 1)[1]
    if raw:
        if _is_remote_url(raw):
            return None, True
        candidate = Path(raw).expanduser()
        return (candidate if candidate.is_file() else None), False
    app_dir = Path(get_app_dir("mpm"))
    if app_dir.is_dir():
        for pattern in ("*.toml", "*.json", "*.ini"):
            for match in sorted(app_dir.glob(pattern)):
                if match.is_file():
                    return match, False
    return None, False


def discover_config_definitions(
    pool: ManagerPool,
) -> tuple[dict[str, ManagerDefinition], Path | None]:
    """Eagerly read new-manager definitions before the CLI group is built.

    Best-effort and local-only: any error (no config, parse failure, missing reader)
    yields no definitions so CLI startup never breaks. URL configs are deferred to the
    authoritative :py:func:`register_config_managers_from_context` pass. Supports both
    the standalone ``[mpm.managers]`` layout and ``[tool.mpm.managers]`` in
    ``pyproject.toml``.
    """
    try:
        path, is_url = _candidate_config_path()
        if is_url or path is None:
            return {}, None
        data = read_file(path) or {}
        root = data.get("mpm")
        if not isinstance(root, dict) and isinstance(data.get("tool"), dict):
            root = data["tool"].get("mpm")
        sections = root.get("managers") if isinstance(root, dict) else None
        if not isinstance(sections, dict):
            return {}, None
        return _collect_definitions(pool, sections), path
    except Exception as ex:  # noqa: BLE001
        # Eager discovery must never break startup; the authoritative pass re-runs it.
        logging.debug(f"Eager config-definition discovery skipped: {ex!r}")
        return {}, None


def register_eager_config_managers(pool: ManagerPool) -> None:
    """Register config-defined managers before the CLI group is constructed.

    Called from ``__main__.main()`` ahead of importing the Click group, so the dynamic
    ``--<id>`` / ``--no-<id>`` selectors enumerate the augmented pool and config-defined
    managers become first-class flags alongside the built-ins.
    """
    definitions, source = discover_config_definitions(pool)
    if definitions:
        register_config_managers(pool, definitions, source=source)


# Bundled manager definitions.
#
# mpm ships a few managers as data rather than Python classes: a TOML file per manager
# under meta_package_manager/managers/, each a single [mpm.managers.<id>] section in the
# exact schema a user would write. They are parsed and built through the same
# parse_manager_definition / build_manager_class path as any user definition, then loaded
# into the pool at construction time (ManagerPool.register), so they are always available
# and earn first-class --<id> flags. The trust gate guarding user definitions does not
# apply: package data shipped in the wheel is read-only and as trusted as the Python
# modules beside it.


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
    ``test_bundled_definitions`` keeps the shipped files valid.
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

    Each :py:class:`~meta_package_manager.manager.ConfigDrivenManager` subclass records
    the TOML file it came from in
    :py:attr:`~meta_package_manager.manager.ConfigDrivenManager.definition_source`, so the
    documentation generator can link to it. Called once by
    :py:attr:`meta_package_manager.pool.ManagerPool.register`.
    """
    managers: list[PackageManager] = []
    for definition, source in load_bundled_definitions():
        klass = build_manager_class(definition)
        klass.definition_source = source
        managers.append(klass())
    return managers
