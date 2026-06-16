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

import logging
import urllib.parse
from dataclasses import dataclass, field

import tomli_w
from click_extra import ConfigValidator, ValidationError, echo
from click_extra.theme import get_current_theme as theme

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
        Dynamic manager selectors (``brew = true``, ``pip = false``, etc.) and
        click-extra built-in options (``verbosity``, ``table_format``) are handled
        by the ``default_map`` pipeline and do not appear here.
    """

    all_managers: bool = False
    """Force evaluation of all managers, including unsupported and deprecated."""

    ignore_auto_updates: bool = True
    """Exclude auto-updating packages from outdated/upgrade results."""

    stop_on_error: bool = False
    """Stop on first manager CLI error instead of continuing."""

    dry_run: bool = False
    """Simulate CLI calls without performing any action."""

    timeout: int = 500
    """Maximum duration in seconds for each manager CLI call."""

    cooldown: str = ""
    """Minimum release age (like ``7 days`` or ``1 week``) a package version must
    reach before it can be installed or upgraded. Empty disables the gate."""

    allow_no_cooldown: bool = False
    """Let managers without native cooldown support run install/upgrade anyway,
    instead of skipping them when a cooldown is requested."""

    description: bool = False
    """Show package description in results."""

    sort_by: str = "manager_id"
    """Default field to sort results by."""

    stats: bool = True
    """Print per-manager package statistics."""

    suggest_contribs: bool = True
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

    :raises click_extra.ValidationError: when ``section`` is not a mapping,
        references an unknown manager ID, sets an unknown override field, or
        provides a value of the wrong type for a known field. The ``path`` of
        the raised error is relative to the ``[mpm.managers]`` section root
        (e.g. ``"winget.cli_searchpath"``); click-extra prepends the app
        prefix when surfacing the error.
    """
    if not section:
        return
    if not isinstance(section, dict):
        raise ValidationError("", f"expected a table, got {type(section).__name__}")
    for manager_id, fields in section.items():
        if manager_id not in pool.register:
            raise ValidationError(
                manager_id,
                f"unknown manager ID {manager_id!r}",
                code="unknown_manager",
            )
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


def apply_manager_overrides_from_context(
    ctx: click.Context,
    pool: ManagerPool,
) -> None:
    """Read the ``[mpm.managers.<id>]`` sections from the loaded config and apply
    them to ``pool``.

    Reads ``ctx.meta["click_extra.conf_full"]`` (the full parsed config exposed by
    :py:mod:`click_extra` after configuration discovery) and forwards the
    ``["mpm"]["managers"]`` subtree to :py:func:`apply_manager_overrides`. Returns
    silently when no configuration file was loaded or when the section is absent.

    Any :class:`ContributionHint` returned by :py:func:`apply_manager_overrides` is
    stashed under :data:`CTX_HINTS_KEY` for :py:func:`print_contribution_hints` to
    surface at the end of the run.
    """
    conf_full = ctx.meta.get("click_extra.conf_full") or {}
    mpm_section = conf_full.get("mpm") if isinstance(conf_full, dict) else None
    overrides = mpm_section.get("managers") if isinstance(mpm_section, dict) else None
    hints = apply_manager_overrides(pool, overrides)
    if hints:
        ctx.meta.setdefault(CTX_HINTS_KEY, []).extend(hints)


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
