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

"""Tests for the per-manager override mechanism.

Driven by the `[mpm.overrides.<id>]` configuration section.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import fields
from pathlib import Path
from textwrap import dedent

import click
import pytest
import tomli_w
from boltons.strutils import strip_ansi
from click_extra import ValidationError

from meta_package_manager.config import (
    AUTO_UPDATES_REPLACEMENT,
    CONTRIBUTION_HINT_FIELDS,
    INVALIDATED_CACHED_PROPS,
    MAX_ISSUE_URL_LENGTH,
    RISKY_OVERRIDE_FIELDS,
    ContributionHint,
    MpmConfig,
    _build_issue_url,
    _warn_risky_overrides_from_untrusted_source,
    apply_manager_overrides,
    dump_manager_overrides,
    format_contribution_hints,
    validate_manager_overrides_section,
)
from meta_package_manager.cooldown import CooldownPolicy
from meta_package_manager.definitions import (
    OVERRIDABLE_FIELDS,
    OVERRIDES_SECTION,
    buildable_operations,
    parse_operation_overrides,
)
from meta_package_manager.manager import PackageManager
from meta_package_manager.pool import pool

from .conftest import all_manager_ids, tomllib
from .test_manager_definition import skip_windows

OVERRIDE_TARGET = "pip"
"""Manager ID used as a fixture target for override tests.

`pip` is portable across all test platforms and never unmaintained, so its presence in
the pool is stable.
"""


def _clean_override_target() -> None:
    """Pop overridable fields and cached props from the override target."""
    manager = pool[OVERRIDE_TARGET]
    for field in (*OVERRIDABLE_FIELDS, "operation_extra_args"):
        manager.__dict__.pop(field, None)
    for prop in INVALIDATED_CACHED_PROPS:
        manager.__dict__.pop(prop, None)
    pool.overridden_fields.pop(OVERRIDE_TARGET, None)


@pytest.fixture
def reset_overrides():
    """Restore the override target's instance state before and after each test.

    The `pool` is a module-level singleton: any attribute we shadow on a manager
    instance via `apply_manager_overrides()` would leak to the next test. This
    fixture pops every overridable field and every cache-invalidated property from
    the instance `__dict__`, and clears the pool's overridden-fields tracking dict
    so the next test starts from class defaults.

    Cleanup runs both before (in case a prior test in the same xdist worker left the
    pool dirty) and after (to not pollute subsequent tests).
    """
    _clean_override_target()
    yield
    _clean_override_target()


def test_overridable_fields_match_base_attributes():
    """Every overridable field must exist on the `PackageManager` base class.

    Drift between {data}`~meta_package_manager.definitions.OVERRIDABLE_FIELDS` and
    the base class is silent at runtime (`setattr` happily creates new attributes)
    so this test acts as the safety net.
    """
    for field in OVERRIDABLE_FIELDS:
        assert hasattr(PackageManager, field), (
            f"OVERRIDABLE_FIELDS lists {field!r} but PackageManager has no such "
            "attribute"
        )


@pytest.mark.parametrize("section", (None, {}), ids=("none", "empty"))
def test_empty_section_is_noop(reset_overrides, section):
    """An absent or empty `[mpm.overrides]` section applies and validates as a no-op."""
    apply_manager_overrides(pool, section)
    validate_manager_overrides_section(section, pool=pool)
    assert OVERRIDE_TARGET not in pool.overridden_fields


def test_non_dict_top_level_raises():
    with pytest.raises(ValidationError, match=r"expected a table"):
        apply_manager_overrides(pool, "not a table")  # type: ignore[arg-type]


def test_unknown_manager_raises():
    with pytest.raises(ValidationError, match=r"unknown manager ID"):
        apply_manager_overrides(pool, {"definitely-not-a-manager": {"timeout": 99}})


def test_non_dict_manager_section_raises():
    with pytest.raises(ValidationError, match=r"expected a table"):
        apply_manager_overrides(
            pool,
            {OVERRIDE_TARGET: "not a table"},  # type: ignore[dict-item]
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        pytest.param("made_up_field", 99, r"unknown field", id="unknown-field"),
        pytest.param(
            "cli_search_path",
            "/single/path",
            r"expected a list of strings",
            id="string-list-given-a-string",
        ),
        pytest.param(
            "cli_search_path",
            ["/ok", 42],
            r"expected all entries to be strings",
            id="string-list-given-a-number",
        ),
        pytest.param("stop_on_error", 1, r"expected a boolean", id="boolean-given-1"),
        # `bool` subclasses `int` in Python, yet a boolean is no integer override.
        pytest.param("timeout", True, r"expected an integer", id="integer-given-true"),
        pytest.param("timeout", "42", r"expected an integer", id="integer-given-text"),
        pytest.param("requirement", 23, r"expected a string", id="string-given-23"),
        pytest.param("sudo", 1, r"expected a boolean", id="sudo-given-1"),
        pytest.param(
            "extra_env",
            {"K": 1},
            r"expected a table of string-to-string",
            id="table-given-a-number-value",
        ),
        pytest.param(
            "extra_env",
            ["PIP_INDEX_URL=https://example.test"],
            r"expected a table of string-to-string",
            id="table-given-a-list",
        ),
        pytest.param(
            "cooldown_policy",
            "strict",
            r"expected one of enforce, best-effort, off",
            id="policy-given-an-unknown-keyword",
        ),
        pytest.param(
            "cooldown_policy",
            True,
            r"expected one of enforce, best-effort, off",
            id="policy-given-a-boolean",
        ),
    ),
)
def test_override_rejects(reset_overrides, field, value, message):
    """An unknown field or a value of the wrong type stops the override.

    The error names what the field accepts.
    """
    with pytest.raises(ValidationError, match=message):
        apply_manager_overrides(pool, {OVERRIDE_TARGET: {field: value}})


def test_str_tuple_override_replaces_default(reset_overrides):
    new_path = ("/opt/custom/bin", "/usr/local/special")
    apply_manager_overrides(
        pool, {OVERRIDE_TARGET: {"cli_search_path": list(new_path)}}
    )
    assert pool[OVERRIDE_TARGET].cli_search_path == new_path
    assert "cli_search_path" in pool[OVERRIDE_TARGET].__dict__


def test_str_tuple_override_coerces_list_to_tuple(reset_overrides):
    apply_manager_overrides(
        pool, {OVERRIDE_TARGET: {"cli_names": ["pip3", "pip", "pip2"]}}
    )
    assert pool[OVERRIDE_TARGET].cli_names == ("pip3", "pip", "pip2")
    assert isinstance(pool[OVERRIDE_TARGET].cli_names, tuple)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    (
        pytest.param("stop_on_error", True, True, id="boolean"),
        pytest.param("timeout", 42, 42, id="integer"),
        pytest.param("requirement", ">=20.0", ">=20.0", id="string"),
        pytest.param("sudo", True, True, id="sudo"),
        # The policy keyword is read like the `--cooldown` option reads it,
        # whatever its case.
        pytest.param(
            "cooldown_policy",
            "Best-Effort",
            CooldownPolicy.best_effort,
            id="policy-in-any-case",
        ),
    ),
)
def test_override_applies(reset_overrides, field, value, expected):
    """An override of the right type sets the field on the manager.

    As the type the field holds.
    """
    apply_manager_overrides(pool, {OVERRIDE_TARGET: {field: value}})
    applied = getattr(pool[OVERRIDE_TARGET], field)
    assert applied == expected
    assert type(applied) is type(expected)


def test_dict_override(reset_overrides):
    apply_manager_overrides(
        pool,
        {OVERRIDE_TARGET: {"extra_env": {"PIP_INDEX_URL": "https://example.test"}}},
    )
    assert pool[OVERRIDE_TARGET].extra_env == {"PIP_INDEX_URL": "https://example.test"}


def test_dict_override_adds_to_shipped_variables():
    """An `extra_env` override adds its variables to those the manager ships.

    Its value wins for a name both set. Each application starts again from the shipped
    variables, so a name a later configuration drops is gone.
    """
    manager = pool["cask"]
    shipped = dict(type(manager).extra_env)
    try:
        apply_manager_overrides(
            pool,
            {"cask": {"extra_env": {"HOMEBREW_NO_ANALYTICS": "0", "LANG": "C"}}},
        )
        assert manager.extra_env == {
            **shipped,
            "HOMEBREW_NO_ANALYTICS": "0",
            "LANG": "C",
        }
        assert manager.extra_env["HOMEBREW_NO_AUTO_UPDATE"] == "1"

        apply_manager_overrides(pool, {"cask": {"extra_env": {"TZ": "UTC"}}})
        assert manager.extra_env == {**shipped, "TZ": "UTC"}
    finally:
        manager.__dict__.pop("extra_env", None)
        pool.overridden_fields.pop("cask", None)


def test_multiple_fields_in_one_call(reset_overrides):
    apply_manager_overrides(
        pool,
        {
            OVERRIDE_TARGET: {
                "cli_search_path": ["/x"],
                "timeout": 60,
                "stop_on_error": True,
            }
        },
    )
    manager = pool[OVERRIDE_TARGET]
    assert manager.cli_search_path == ("/x",)
    assert manager.timeout == 60
    assert manager.stop_on_error is True


def test_cached_property_evicted_on_override(reset_overrides):
    """Force a cached_property to be computed, then verify the override evicts it."""
    manager = pool[OVERRIDE_TARGET]
    # Force computation; the value itself doesn't matter, only that it is now cached.
    _ = manager.cli_path
    # `cli_path` may or may not have been resolved on this host; what matters is that
    # if it WAS computed, the cache entry is cleared so a follow-up access recomputes.
    apply_manager_overrides(
        pool, {OVERRIDE_TARGET: {"cli_search_path": ["/elsewhere"]}}
    )
    assert "cli_path" not in manager.__dict__


@pytest.mark.parametrize(
    ("field", "override", "global_value"),
    (
        pytest.param("timeout", 42, 999, id="timeout"),
        pytest.param("stop_on_error", True, False, id="stop-on-error"),
        # A manager can opt out of escalation, or into it, whatever the global
        # `--sudo`.
        pytest.param("sudo", False, True, id="sudo"),
    ),
)
def test_per_manager_override_beats_global_default(
    reset_overrides, field, override, global_value
):
    """A per-manager override survives the global `setattr` loop.

    The loop in `_select_managers`: the most specific value wins.
    """
    apply_manager_overrides(pool, {OVERRIDE_TARGET: {field: override}})
    selected = list(
        pool._select_managers(
            keep=(OVERRIDE_TARGET,),
            drop_not_found=False,
            **{field: global_value},
        )
    )
    assert len(selected) == 1
    kept = getattr(selected[0], field)
    assert kept == override
    assert type(kept) is type(override)


@pytest.mark.parametrize(
    ("override", "expected"),
    (
        pytest.param(None, 999, id="global-timeout-reaches-detection"),
        pytest.param(42, 42, id="per-manager-override-survives-detection"),
    ),
)
def test_timeout_binds_detection_phase(
    reset_overrides, monkeypatch, override, expected
):
    """`_select_managers` binds the probes to the resolved timeout first.

    The version-detection probes are bound *before* `warm_availability` runs them: the
    global `--timeout` reaches a plain candidate, while a per-manager override still
    keeps precedence.
    """
    if override is not None:
        apply_manager_overrides(pool, {OVERRIDE_TARGET: {"timeout": override}})

    # Capture each candidate's timeout at the moment detection would fire.
    recorded: dict[str, int | None] = {}

    class _StopProbe(Exception):
        """Halt the generator right after the recording point.

        So the test never reaches the real availability loop and stays hermetic.
        """

    def fake_warm(managers):
        for manager in managers:
            recorded[manager.id] = manager.timeout
        raise _StopProbe

    monkeypatch.setattr("meta_package_manager.pool.warm_availability", fake_warm)

    with pytest.raises(_StopProbe):
        list(
            pool._select_managers(
                keep=(OVERRIDE_TARGET,),
                drop_not_found=True,
                timeout=999,
            )
        )

    assert recorded[OVERRIDE_TARGET] == expected


def test_global_default_still_applies_without_override():
    """Sanity: with no per-manager override, the global default reaches the manager."""
    selected = list(
        pool._select_managers(
            keep=("uv",),
            drop_not_found=False,
            timeout=77,
        )
    )
    assert len(selected) == 1
    assert selected[0].timeout == 77
    # Reset for following tests.
    pool["uv"].__dict__.pop("timeout", None)


def test_sudo_is_a_risky_override_field():
    """An untrusted `sudo = true` override trips the untrusted-source warning.

    `[mpm.overrides.<id>] sudo = true` from an untrusted source can run a binary as
    root, like pre_cmds.
    """
    assert "sudo" in RISKY_OVERRIDE_FIELDS


@pytest.mark.parametrize(
    ("source", "is_url", "trusted", "origin"),
    (
        pytest.param(None, True, True, "a remote URL", id="remote-url"),
        pytest.param(
            Path("/etc/mpm/config.toml"),
            False,
            False,
            f"untrusted file {Path('/etc/mpm/config.toml')}",
            id="unsafe-file",
        ),
        pytest.param(Path("/etc/mpm/config.toml"), False, True, None, id="safe-file"),
        pytest.param(None, False, True, None, id="no-config"),
    ),
)
def test_risky_override_from_untrusted_source_warns(
    monkeypatch, caplog, source, is_url, trusted, origin
):
    """One warning per shipped manager whose override sets a risky field.

    When the configuration comes from a remote URL or an unsafe file.

    The source and its trust are stubbed, so the test reads the same on every
    platform. An unknown ID and a section that is not a table carry no field to
    warn about.
    """
    monkeypatch.setattr(
        "meta_package_manager.config._config_source", lambda ctx: (source, is_url)
    )
    monkeypatch.setattr(
        "meta_package_manager.config.config_file_is_trusted", lambda path: trusted
    )
    _warn_risky_overrides_from_untrusted_source(
        click.Context(click.Command("mpm")),
        pool,
        {
            OVERRIDE_TARGET: {
                "pre_cmds": ["env"],
                "cli_names": ["pip3"],
                "timeout": 60,
            },
            "cask": {"timeout": 60},
            "fictional-manager": {"pre_cmds": ["env"]},
            "uv": "not a table",
        },
    )
    warnings = [
        strip_ansi(record.getMessage())
        for record in caplog.records
        if "Override of" in record.getMessage()
    ]
    expected = (
        f"Override of cli_names, pre_cmds on {OVERRIDE_TARGET} comes from "
        f"{origin}; these fields can run arbitrary commands (see docs/security.md)."
    )
    assert warnings == ([] if origin is None else [expected])


# Per-operation extra arguments.


def test_operations_override_sets_extra_args(reset_overrides):
    apply_manager_overrides(
        pool,
        {OVERRIDE_TARGET: {"operations": {"install": {"extra_args": ["--user"]}}}},
    )
    assert pool[OVERRIDE_TARGET].operation_extra_args == {"install": ("--user",)}
    assert "operation_extra_args" in pool.overridden_fields[OVERRIDE_TARGET]


def test_operations_override_reaches_its_command_alone(reset_overrides):
    """Operation arguments reach the commands of their operation alone.

    The override, the stamp of the operation method and `build_cli` put them there, and
    nowhere else.
    """
    apply_manager_overrides(
        pool,
        {OVERRIDE_TARGET: {"operations": {"upgrade_one": {"extra_args": ["--user"]}}}},
    )
    manager = pool[OVERRIDE_TARGET]
    assert "--user" in manager.upgrade_one_cli("lemon")
    assert "--user" not in manager.build_cli("list")


@pytest.mark.parametrize(
    ("operations", "message"),
    (
        pytest.param("--user", r"expected a table, got str", id="not-a-table"),
        pytest.param(
            {"install": "--user"}, r"expected a table, got str", id="entry-not-a-table"
        ),
        pytest.param(
            {"upgrade_all": {"extra_args": ["--user"]}},
            r"builds no upgrade_all command",
            id="one-by-one-upgrade",
        ),
        pytest.param(
            {"cleanup": {"extra_args": []}},
            r"builds no cleanup command",
            id="unknown-operation",
        ),
        pytest.param(
            {"install": {"args": ["install"]}},
            r"unknown key\. Allowed: extra_args",
            id="redefinition",
        ),
        pytest.param(
            {"install": {"extra_args": "--user"}},
            r"expected a list of strings",
            id="bare-string",
        ),
    ),
)
def test_operations_override_rejects(reset_overrides, operations, message):
    with pytest.raises(ValidationError, match=message):
        apply_manager_overrides(pool, {OVERRIDE_TARGET: {"operations": operations}})


def test_removed_auto_updates_field_names_replacement(reset_overrides):
    with pytest.raises(ValidationError, match=r"removed field") as raised:
        apply_manager_overrides(pool, {"cask": {"ignore_auto_updates": False}})
    assert AUTO_UPDATES_REPLACEMENT in str(raised.value)


def test_unknown_manager_with_override_operations_reads_as_typo():
    """A section whose operations only add arguments is a mistyped override.

    Not a definition missing its platforms.
    """
    with pytest.raises(ValidationError, match=r"unknown manager ID 'caks'"):
        apply_manager_overrides(
            pool,
            {"caks": {"operations": {"upgrade_all": {"extra_args": ["--greedy"]}}}},
        )


CONFIG_TEMPLATE = dedent("""\
    [mpm.overrides.{manager_id}]
    cli_search_path = ["/integration/test/path"]
    """)


def test_cli_loads_manager_overrides(invoke, create_config, reset_overrides):
    """End-to-end: `mpm --config <path>` applies `[mpm.overrides.<id>]` overrides."""
    conf_path = create_config(
        "conf.toml", CONFIG_TEMPLATE.format(manager_id=OVERRIDE_TARGET)
    )
    result = invoke("--config", str(conf_path), "managers")
    assert result.exit_code == 0
    assert pool[OVERRIDE_TARGET].cli_search_path == ("/integration/test/path",)


@skip_windows
def test_cli_warns_on_risky_override_from_untrusted_file(
    invoke, create_config, reset_overrides
):
    """The CLI warns about a risky override read from a file others can write to."""
    conf_path = create_config(
        "conf.toml", CONFIG_TEMPLATE.format(manager_id=OVERRIDE_TARGET)
    )
    conf_path.chmod(0o666)
    result = invoke("--config", str(conf_path), "managers")
    assert result.exit_code == 0
    assert "Override of cli_search_path on" in result.stderr
    assert "comes from untrusted file" in result.stderr


def test_cli_warns_on_stale_overrides_section(invoke, create_config, reset_overrides):
    """A table under `[mpm.managers]` is named in a warning and not applied.

    That was the old home of the overrides. The table is not dropped in silence.
    """
    conf_path = create_config(
        "conf.toml",
        dedent("""\
            [mpm.managers.pip]
            cli_search_path = ["/integration/test/path"]

            [mpm.managers.cask]
            timeout = 60
            """),
    )
    result = invoke("--config", str(conf_path), "managers")
    assert result.exit_code == 0
    assert "`[mpm.managers.<id>]` moved to `[mpm.overrides.<id>]`" in result.stderr
    assert "These sections are ignored: cask, pip." in result.stderr
    assert pool[OVERRIDE_TARGET].cli_search_path != ("/integration/test/path",)


def test_cli_fails_on_unknown_manager_in_config(invoke, create_config):
    """A typo'd manager ID in the config aborts the CLI with a precise dotted path.

    Permissive warn-and-skip behavior was removed: the same validator that powers
    `--validate-config` runs at normal load time.
    """
    conf_path = create_config(
        "conf.toml",
        dedent("""\
            [mpm.overrides.fictional-manager]
            cli_search_path = ["/x"]
            """),
    )
    result = invoke("--config", str(conf_path), "managers")
    assert result.exit_code != 0
    assert "mpm.overrides.fictional-manager" in result.stderr
    assert "unknown manager ID" in result.stderr


def test_cli_include_auto_updates_names_replacement(invoke):
    """The removed flag for auto-updating casks stops the run.

    It names the configuration that replaces it.
    """
    result = invoke("--include-auto-updates", "managers")
    assert result.exit_code == 2
    assert "--include-auto-updates was removed" in result.stderr
    assert AUTO_UPDATES_REPLACEMENT in result.stderr


def test_cli_ignore_auto_updates_warns(invoke):
    """The removed flag that asked for the default only warns."""
    result = invoke("--ignore-auto-updates", "managers")
    assert result.exit_code == 0
    assert "--ignore-auto-updates was removed and has no effect" in result.stderr


@pytest.mark.parametrize(
    ("value", "hint"),
    (
        pytest.param("false", AUTO_UPDATES_REPLACEMENT, id="included"),
        pytest.param("true", "stay out by default", id="default"),
    ),
)
def test_cli_removed_auto_updates_key_warns(invoke, create_config, value, hint):
    """click-extra drops the removed `[mpm]` key in silence, so mpm warns."""
    conf_path = create_config("conf.toml", f"[mpm]\nignore_auto_updates = {value}\n")
    result = invoke("--config", str(conf_path), "managers")
    assert result.exit_code == 0
    assert "`[mpm] ignore_auto_updates` is ignored" in result.stderr
    assert hint in result.stderr


# Contribution-hint feature.


def test_contribution_hint_fields_subset_of_overridable():
    """The hint allowlist must only name real overridable fields."""
    assert CONTRIBUTION_HINT_FIELDS.issubset(OVERRIDABLE_FIELDS)


def test_apply_returns_hint_for_detection_field(reset_overrides):
    hints = apply_manager_overrides(
        pool, {OVERRIDE_TARGET: {"cli_search_path": ["/no/such/path"]}}
    )
    assert len(hints) == 1
    hint = hints[0]
    assert hint.manager_id == OVERRIDE_TARGET
    assert hint.field == "cli_search_path"
    assert hint.user_value == ("/no/such/path",)


def test_apply_returns_no_hint_for_preference_field(reset_overrides):
    """Overriding a preference field (timeout) generates no hint.

    It is not a detection bug signal.
    """
    hints = apply_manager_overrides(pool, {OVERRIDE_TARGET: {"timeout": 42}})
    assert hints == []


def test_apply_returns_no_hint_when_overrides_empty():
    assert apply_manager_overrides(pool, None) == []
    assert apply_manager_overrides(pool, {}) == []


def test_apply_raises_on_unknown_manager_so_no_hint_emitted():
    """Apply aborts on unknown manager IDs via the validator, so no hints leak.

    The validator runs before any side effects, so the pool is unchanged.
    """
    with pytest.raises(ValidationError, match=r"unknown manager ID"):
        apply_manager_overrides(
            pool, {"definitely-not-a-manager": {"cli_search_path": ["/x"]}}
        )


def test_apply_returns_hints_for_each_detection_field(reset_overrides):
    """Several detection-related overrides on one manager make one hint each.

    One hint per field.
    """
    hints = apply_manager_overrides(
        pool,
        {
            OVERRIDE_TARGET: {
                "cli_search_path": ["/x"],
                "requirement": ">=20.0",
                "timeout": 42,
            }
        },
    )
    fields = {h.field for h in hints}
    # Two detection-related, one preference (timeout) excluded.
    assert fields == {"cli_search_path", "requirement"}


def test_build_issue_url_targets_bug_template():
    hint = ContributionHint(
        manager_id="winget",
        field="cli_search_path",
        user_value=("C:\\Users\\foo\\bin",),
        detected_cli_path=None,
    )
    url = _build_issue_url(hint)
    assert url.startswith(
        "https://github.com/kdeldycke/meta-package-manager/issues/new?"
    )
    # Pre-fills the bug-report template.
    assert "template=bug-report.yml" in url
    # Body field is named after the bug-report.yml `id: bug-description`.
    assert "bug-description=" in url
    # Stays under GitHub's URL length cap.
    assert len(url) <= MAX_ISSUE_URL_LENGTH


def test_build_issue_url_asserts_on_oversize_url():
    """A pathological override value trips the URL-length assertion.

    Rather than silently producing a URL that GitHub would truncate.
    """
    # 10 KiB of path entries is well past the 8 KiB cap.
    pathological_value = tuple(f"/very/long/path/{i:05d}" for i in range(500))
    hint = ContributionHint(
        manager_id="winget",
        field="cli_search_path",
        user_value=pathological_value,
        detected_cli_path=None,
    )
    with pytest.raises(AssertionError, match=r"exceeding the .*-character"):
        _build_issue_url(hint)


def test_build_issue_url_url_decodes_back_to_useful_body():
    """The URL-encoded body decodes back to text naming the override.

    Round-trip: it mentions the manager id, the field, and the user's value.
    """
    hint = ContributionHint(
        manager_id="winget",
        field="cli_names",
        user_value=("winget.exe",),
        detected_cli_path=None,
    )
    url = _build_issue_url(hint)
    qs = urllib.parse.urlparse(url).query
    params = dict(urllib.parse.parse_qsl(qs))
    body = params["bug-description"]
    assert "winget" in body
    assert "cli_names" in body
    assert "winget.exe" in body
    assert "not found" in body  # detected_cli_path was None


def test_build_issue_url_includes_detected_cli_path_when_available():
    hint = ContributionHint(
        manager_id="brew",
        field="cli_search_path",
        user_value=("/opt/custom",),
        detected_cli_path="/opt/homebrew/bin/brew",
    )
    url = _build_issue_url(hint)
    body = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))[
        "bug-description"
    ]
    assert "/opt/homebrew/bin/brew" in body


def test_format_contribution_hints_empty_returns_empty_string():
    assert format_contribution_hints([]) == ""


def test_format_contribution_hints_lists_each_with_url():
    hints = [
        ContributionHint(
            manager_id="winget",
            field="cli_search_path",
            user_value=("/x",),
            detected_cli_path=None,
        ),
        ContributionHint(
            manager_id="cargo",
            field="version_regexes",
            user_value=("foo",),
            detected_cli_path="/usr/bin/cargo",
        ),
    ]
    msg = format_contribution_hints(hints)
    assert "winget" in msg
    assert "cargo" in msg
    assert (
        msg.count("https://github.com/kdeldycke/meta-package-manager/issues/new") == 2
    )
    # Mentions the opt-out so the user knows how to silence.
    assert "--no-suggest-contribs" in msg


@pytest.mark.parametrize(
    ("config", "args", "hinted"),
    (
        # A detection-related override surfaces the hint.
        pytest.param(
            """\
            [mpm.overrides.pip]
            cli_search_path = ["/no/such/path/for/test"]
            """,
            (),
            True,
            id="detection-override",
        ),
        # Overriding only a preference field surfaces no hint.
        pytest.param(
            """\
            [mpm.overrides.pip]
            timeout = 42
            """,
            (),
            False,
            id="preference-override",
        ),
        # `--no-suggest-contribs` silences the hint.
        pytest.param(
            """\
            [mpm.overrides.pip]
            cli_search_path = ["/no/such/path"]
            """,
            ("--no-suggest-contribs",),
            False,
            id="opt-out-option",
        ),
        # The `[mpm] suggest_contribs = false` configuration silences it too.
        pytest.param(
            """\
            [mpm]
            suggest_contribs = false

            [mpm.overrides.pip]
            cli_search_path = ["/no/such/path"]
            """,
            (),
            False,
            id="opt-out-configuration",
        ),
    ),
)
def test_cli_contribution_hint(
    invoke, create_config, reset_overrides, config, args, hinted
):
    """The configuration decides whether the contribution hint is printed.

    End to end: the hint and the issue link it carries reach `<stderr>` or not.
    """
    conf_path = create_config("conf.toml", dedent(config))
    result = invoke("--config", str(conf_path), *args, "managers")
    assert result.exit_code == 0
    assert ("Detected user override" in result.stderr) is hinted
    assert ("issues/new" in result.stderr) is hinted
    if hinted:
        assert "cli_search_path" in result.stderr


# dump_manager_overrides + config-template subcommand.


def test_dump_manager_overrides_skips_none_values():
    """Attributes whose current value is `None` are omitted from the dump."""
    manager = pool[OVERRIDE_TARGET]
    # Force one overridable field to None to confirm it gets skipped.
    manager.__dict__["requirement"] = None
    try:
        dumped = dump_manager_overrides(manager)
        assert "requirement" not in dumped
    finally:
        manager.__dict__.pop("requirement", None)


def test_dump_manager_overrides_converts_tuples_to_lists():
    """Tuples are converted to lists so `tomli_w` can serialize them."""
    manager = pool[OVERRIDE_TARGET]
    dumped = dump_manager_overrides(manager)
    # cli_names is always set (the metaclass populates it from the manager ID).
    assert isinstance(dumped["cli_names"], list)
    assert all(not isinstance(v, tuple) for v in dumped.values())


def test_dump_manager_overrides_keys_are_alphabetical():
    """The output is canonical: dict insertion order matches sorted field names."""
    manager = pool[OVERRIDE_TARGET]
    dumped = dump_manager_overrides(manager)
    assert list(dumped) == sorted(dumped)


def test_dump_manager_overrides_lists_buildable_operations(reset_overrides):
    """The template names each operation an override can reach.

    With its current `extra_args`.
    """
    apply_manager_overrides(
        pool,
        {OVERRIDE_TARGET: {"operations": {"install": {"extra_args": ["--user"]}}}},
    )
    manager = pool[OVERRIDE_TARGET]
    operations = dump_manager_overrides(manager)["operations"]
    assert list(operations) == list(buildable_operations(manager))
    assert operations["install"] == {"extra_args": ["--user"]}
    assert operations["remove"] == {"extra_args": []}


@all_manager_ids
def test_config_template_round_trips(manager_id):
    """For every manager, dump → tomli_w → tomllib → converter yields the same value.

    Catches schema drift between
    {data}`~meta_package_manager.definitions.OVERRIDABLE_FIELDS` converters and the live
    attribute types.
    """
    manager = pool[manager_id]
    dumped = dump_manager_overrides(manager)
    serialized = tomli_w.dumps(dumped)
    parsed = tomllib.loads(serialized)
    for field, raw_value in parsed.items():
        if field == "operations":
            reparsed = parse_operation_overrides(manager_id, manager, raw_value)
            original = {
                op_name: manager.operation_extra_args.get(op_name, ())
                for op_name in buildable_operations(manager)
            }
        else:
            reparsed = OVERRIDABLE_FIELDS[field](raw_value)
            original = getattr(manager, field)
        assert reparsed == original, (
            f"{manager_id}.{field}: {reparsed!r} != {original!r}"
        )


def test_cli_config_template_one_manager(invoke):
    """`mpm config-template <id>` produces a single parseable manager section."""
    result = invoke("config-template", "winget")
    assert result.exit_code == 0
    parsed = tomllib.loads(result.stdout)
    assert list(parsed["mpm"][OVERRIDES_SECTION]) == ["winget"]
    winget = parsed["mpm"][OVERRIDES_SECTION]["winget"]
    # Every key present must be an overridable field or the operations table.
    assert set(winget).issubset({*OVERRIDABLE_FIELDS, "operations"})
    assert set(winget["operations"]) == set(buildable_operations(pool["winget"]))


def test_cli_config_template_multiple_managers(invoke):
    """`mpm config-template <id1> <id2>` dumps each requested manager."""
    result = invoke("config-template", "winget", "pip")
    assert result.exit_code == 0
    parsed = tomllib.loads(result.stdout)
    assert set(parsed["mpm"][OVERRIDES_SECTION]) == {"winget", "pip"}


def test_cli_config_template_no_args_dumps_all_maintained(invoke):
    """With no positional args, every maintained manager appears."""
    result = invoke("config-template")
    assert result.exit_code == 0
    parsed = tomllib.loads(result.stdout)
    assert set(parsed["mpm"][OVERRIDES_SECTION]) == set(pool.maintained_manager_ids)


def test_cli_config_template_unknown_manager_errors(invoke):
    result = invoke("config-template", "definitely-not-a-manager")
    assert result.exit_code != 0
    assert "definitely-not-a-manager" in result.stderr


def test_cli_config_template_output_is_applicable(invoke, reset_overrides):
    """A `config-template` output fed back through the overrides is a no-op.

    End-to-end: pipe `mpm config-template <id>` output back through
    `apply_manager_overrides` and confirm the pool is unchanged.
    """
    manager = pool[OVERRIDE_TARGET]
    before = {field: getattr(manager, field) for field in OVERRIDABLE_FIELDS}

    result = invoke("config-template", OVERRIDE_TARGET)
    assert result.exit_code == 0
    parsed = tomllib.loads(result.stdout)
    apply_manager_overrides(pool, parsed["mpm"][OVERRIDES_SECTION])

    for field, original in before.items():
        assert getattr(manager, field) == original, (
            f"{OVERRIDE_TARGET}.{field} changed after round-trip"
        )


def test_overrides_section_names_a_schema_field():
    """`OVERRIDES_SECTION` and the schema field declaring it opaque agree.

    click-extra derives a configuration path from the field name, so renaming one
    side alone leaves every reader of the constant looking at a sub-tree the
    schema no longer marks opaque, which the strict check then rejects key by key.
    """
    assert OVERRIDES_SECTION in {f.name for f in fields(MpmConfig)}
