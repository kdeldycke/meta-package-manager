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

"""Tests for the per-manager override mechanism driven by the
``[mpm.managers.<id>]`` configuration section."""

from __future__ import annotations

from textwrap import dedent

import pytest

from meta_package_manager.config import (
    CONTRIBUTION_HINT_FIELDS,
    INVALIDATED_CACHED_PROPS,
    MAX_ISSUE_URL_LENGTH,
    OVERRIDABLE_FIELDS,
    ContributionHint,
    _build_issue_url,
    apply_manager_overrides,
    format_contribution_hints,
)
from meta_package_manager.pool import pool

OVERRIDE_TARGET = "pip"
"""Manager ID used as a fixture target for override tests.

``pip`` is portable across all test platforms and never deprecated, so its presence in
the pool is stable.
"""


@pytest.fixture
def reset_overrides():
    """Restore the override target's instance state after each test.

    The ``pool`` is a module-level singleton: any attribute we shadow on a manager
    instance via ``apply_manager_overrides()`` would leak to the next test. This
    fixture pops every overridable field and every cache-invalidated property from
    the instance ``__dict__``, and clears the pool's overridden-fields tracking dict
    so the next test starts from class defaults.
    """
    yield
    manager = pool[OVERRIDE_TARGET]
    for field in OVERRIDABLE_FIELDS:
        manager.__dict__.pop(field, None)
    for prop in INVALIDATED_CACHED_PROPS:
        manager.__dict__.pop(prop, None)
    pool.overridden_fields.pop(OVERRIDE_TARGET, None)


def test_overridable_fields_match_base_attributes():
    """Every overridable field must exist on the ``PackageManager`` base class.

    Drift between :data:`OVERRIDABLE_FIELDS` and the base class is silent at runtime
    (``setattr`` happily creates new attributes) so this test acts as the safety net.
    """
    from meta_package_manager.base import PackageManager

    for field in OVERRIDABLE_FIELDS:
        assert hasattr(PackageManager, field), (
            f"OVERRIDABLE_FIELDS lists {field!r} but PackageManager has no such attribute"
        )


def test_none_is_noop():
    apply_manager_overrides(pool, None)


def test_empty_is_noop():
    apply_manager_overrides(pool, {})


def test_non_dict_top_level_warns_and_skips(caplog):
    apply_manager_overrides(pool, "not a table")  # type: ignore[arg-type]
    assert any("expected a table" in rec.message for rec in caplog.records)


def test_unknown_manager_warns_and_skips(caplog):
    apply_manager_overrides(pool, {"definitely-not-a-manager": {"timeout": 99}})
    messages = [rec.message for rec in caplog.records]
    assert any("definitely-not-a-manager" in m for m in messages)
    assert any("unknown manager ID" in m for m in messages)


def test_non_dict_manager_section_warns_and_skips(caplog):
    apply_manager_overrides(pool, {OVERRIDE_TARGET: "not a table"})  # type: ignore[dict-item]
    assert any(
        f"[mpm.managers.{OVERRIDE_TARGET}]" in rec.message
        and "expected a table" in rec.message
        for rec in caplog.records
    )


def test_unknown_field_warns_and_skips(caplog, reset_overrides):
    apply_manager_overrides(pool, {OVERRIDE_TARGET: {"made_up_field": 99}})
    assert any(
        "made_up_field" in rec.message and "unknown field" in rec.message
        for rec in caplog.records
    )


def test_str_tuple_override_replaces_default(reset_overrides):
    new_path = ("/opt/custom/bin", "/usr/local/special")
    apply_manager_overrides(pool, {OVERRIDE_TARGET: {"cli_search_path": list(new_path)}})
    assert pool[OVERRIDE_TARGET].cli_search_path == new_path
    assert "cli_search_path" in pool[OVERRIDE_TARGET].__dict__


def test_str_tuple_override_coerces_list_to_tuple(reset_overrides):
    apply_manager_overrides(pool,
        {OVERRIDE_TARGET: {"cli_names": ["pip3", "pip", "pip2"]}}
    )
    assert pool[OVERRIDE_TARGET].cli_names == ("pip3", "pip", "pip2")
    assert isinstance(pool[OVERRIDE_TARGET].cli_names, tuple)


def test_str_tuple_override_rejects_bare_string(reset_overrides):
    with pytest.raises(ValueError, match=r"expected a list of strings"):
        apply_manager_overrides(pool,
            {OVERRIDE_TARGET: {"cli_search_path": "/single/path"}}
        )


def test_str_tuple_override_rejects_non_string_entries(reset_overrides):
    with pytest.raises(ValueError, match=r"expected all entries to be strings"):
        apply_manager_overrides(pool,
            {OVERRIDE_TARGET: {"cli_search_path": ["/ok", 42]}}
        )


def test_bool_override(reset_overrides):
    apply_manager_overrides(pool, {OVERRIDE_TARGET: {"ignore_auto_updates": False}})
    assert pool[OVERRIDE_TARGET].ignore_auto_updates is False


def test_bool_override_rejects_int(reset_overrides):
    with pytest.raises(ValueError, match=r"expected a boolean"):
        apply_manager_overrides(pool, {OVERRIDE_TARGET: {"ignore_auto_updates": 1}})


def test_int_override(reset_overrides):
    apply_manager_overrides(pool, {OVERRIDE_TARGET: {"timeout": 42}})
    assert pool[OVERRIDE_TARGET].timeout == 42


def test_int_override_rejects_bool(reset_overrides):
    """A boolean is not an acceptable integer override even though ``bool`` subclasses
    ``int`` in Python."""
    with pytest.raises(ValueError, match=r"expected an integer"):
        apply_manager_overrides(pool, {OVERRIDE_TARGET: {"timeout": True}})


def test_int_override_rejects_string(reset_overrides):
    with pytest.raises(ValueError, match=r"expected an integer"):
        apply_manager_overrides(pool, {OVERRIDE_TARGET: {"timeout": "42"}})


def test_str_override(reset_overrides):
    apply_manager_overrides(pool, {OVERRIDE_TARGET: {"requirement": ">=20.0"}})
    assert pool[OVERRIDE_TARGET].requirement == ">=20.0"


def test_str_override_rejects_int(reset_overrides):
    with pytest.raises(ValueError, match=r"expected a string"):
        apply_manager_overrides(pool, {OVERRIDE_TARGET: {"requirement": 23}})


def test_dict_override(reset_overrides):
    apply_manager_overrides(pool,
        {OVERRIDE_TARGET: {"extra_env": {"PIP_INDEX_URL": "https://example.test"}}}
    )
    assert pool[OVERRIDE_TARGET].extra_env == {
        "PIP_INDEX_URL": "https://example.test"
    }


def test_dict_override_rejects_non_string_value(reset_overrides):
    with pytest.raises(ValueError, match=r"expected a table of string-to-string"):
        apply_manager_overrides(pool, {OVERRIDE_TARGET: {"extra_env": {"K": 1}}})


def test_multiple_fields_in_one_call(reset_overrides):
    apply_manager_overrides(pool,
        {
            OVERRIDE_TARGET: {
                "cli_search_path": ["/x"],
                "timeout": 60,
                "ignore_auto_updates": False,
            }
        }
    )
    manager = pool[OVERRIDE_TARGET]
    assert manager.cli_search_path == ("/x",)
    assert manager.timeout == 60
    assert manager.ignore_auto_updates is False


def test_cached_property_evicted_on_override(reset_overrides):
    """Force a cached_property to be computed, then verify the override evicts it."""
    manager = pool[OVERRIDE_TARGET]
    # Force computation; the value itself doesn't matter, only that it is now cached.
    _ = manager.cli_path
    # `cli_path` may or may not have been resolved on this host; what matters is that
    # if it WAS computed, the cache entry is cleared so a follow-up access recomputes.
    apply_manager_overrides(pool, {OVERRIDE_TARGET: {"cli_search_path": ["/elsewhere"]}})
    assert "cli_path" not in manager.__dict__


def test_per_manager_timeout_beats_global_default(reset_overrides):
    """A per-manager ``timeout`` override must survive the global ``setattr`` loop in
    ``_select_managers``: the most specific value wins."""
    apply_manager_overrides(pool, {OVERRIDE_TARGET: {"timeout": 42}})
    selected = list(
        pool._select_managers(
            keep=(OVERRIDE_TARGET,),
            drop_not_found=False,
            timeout=999,
        )
    )
    assert len(selected) == 1
    assert selected[0].timeout == 42


def test_per_manager_ignore_auto_updates_beats_global_default(reset_overrides):
    apply_manager_overrides(pool, {OVERRIDE_TARGET: {"ignore_auto_updates": False}})
    selected = list(
        pool._select_managers(
            keep=(OVERRIDE_TARGET,),
            drop_not_found=False,
            ignore_auto_updates=True,
        )
    )
    assert len(selected) == 1
    assert selected[0].ignore_auto_updates is False


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


CONFIG_TEMPLATE = dedent("""\
    [mpm.managers.{manager_id}]
    cli_search_path = ["/integration/test/path"]
    """)


def test_cli_loads_manager_overrides(invoke, create_config, reset_overrides):
    """End-to-end: ``mpm --config <path>`` applies overrides from
    ``[mpm.managers.<id>]``."""
    conf_path = create_config(
        "conf.toml", CONFIG_TEMPLATE.format(manager_id=OVERRIDE_TARGET)
    )
    result = invoke("--config", str(conf_path), "managers")
    assert result.exit_code == 0
    assert pool[OVERRIDE_TARGET].cli_search_path == ("/integration/test/path",)


def test_cli_warns_on_unknown_manager_in_config(invoke, create_config):
    conf_path = create_config(
        "conf.toml",
        dedent("""\
            [mpm.managers.fictional-manager]
            cli_search_path = ["/x"]
            """),
    )
    result = invoke("--config", str(conf_path), "managers")
    assert result.exit_code == 0
    assert "fictional-manager" in result.stderr


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
    """Overriding a preference field (timeout) must not generate a hint: it's not
    a detection bug signal."""
    hints = apply_manager_overrides(pool, {OVERRIDE_TARGET: {"timeout": 42}})
    assert hints == []


def test_apply_returns_no_hint_when_overrides_empty():
    assert apply_manager_overrides(pool, None) == []
    assert apply_manager_overrides(pool, {}) == []


def test_apply_returns_no_hint_when_unknown_manager():
    """Unknown manager IDs are skipped before any hint can be generated."""
    hints = apply_manager_overrides(
        pool, {"definitely-not-a-manager": {"cli_search_path": ["/x"]}}
    )
    assert hints == []


def test_apply_returns_hints_for_each_detection_field(reset_overrides):
    """Multiple detection-related overrides on the same manager produce one hint
    per field."""
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
    """A pathological override value must trip the URL-length assertion rather
    than silently producing a URL that GitHub would truncate."""
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
    """Round-trip: the URL-encoded body must decode back to text mentioning the
    manager id, the field, and the user's value."""
    import urllib.parse

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
    import urllib.parse

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
    assert msg.count("https://github.com/kdeldycke/meta-package-manager/issues/new") == 2
    # Mentions the opt-out so the user knows how to silence.
    assert "--no-suggest-contribs" in msg


def test_cli_prints_contribution_hint(invoke, create_config, reset_overrides):
    """End-to-end: a config with a detection-related override surfaces the hint."""
    conf_path = create_config(
        "conf.toml",
        dedent("""\
            [mpm.managers.pip]
            cli_search_path = ["/no/such/path/for/test"]
            """),
    )
    result = invoke("--config", str(conf_path), "managers")
    assert result.exit_code == 0
    assert "Detected user override" in result.stderr
    assert "cli_search_path" in result.stderr
    assert "issues/new" in result.stderr


def test_cli_no_hint_for_preference_override(invoke, create_config, reset_overrides):
    """Overriding only a preference field must not surface a hint."""
    conf_path = create_config(
        "conf.toml",
        dedent("""\
            [mpm.managers.pip]
            timeout = 42
            """),
    )
    result = invoke("--config", str(conf_path), "managers")
    assert result.exit_code == 0
    assert "Detected user override" not in result.stderr


def test_cli_opt_out_suppresses_hint(invoke, create_config, reset_overrides):
    """``--no-suggest-contribs`` silences the hint output."""
    conf_path = create_config(
        "conf.toml",
        dedent("""\
            [mpm.managers.pip]
            cli_search_path = ["/no/such/path"]
            """),
    )
    result = invoke(
        "--config",
        str(conf_path),
        "--no-suggest-contribs",
        "managers",
    )
    assert result.exit_code == 0
    assert "Detected user override" not in result.stderr
    assert "issues/new" not in result.stderr


def test_cli_opt_out_via_config(invoke, create_config, reset_overrides):
    """The ``[mpm] suggest_contribs = false`` config also silences
    the hint."""
    conf_path = create_config(
        "conf.toml",
        dedent("""\
            [mpm]
            suggest_contribs = false

            [mpm.managers.pip]
            cli_search_path = ["/no/such/path"]
            """),
    )
    result = invoke("--config", str(conf_path), "managers")
    assert result.exit_code == 0
    assert "Detected user override" not in result.stderr
    assert "issues/new" not in result.stderr
