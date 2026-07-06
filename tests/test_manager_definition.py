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

"""Tests for brand-new package managers defined from the ``[mpm.managers.<id>]``
configuration section."""

from __future__ import annotations

import json
import os
import re

import pytest
from click_extra import ValidationError

from meta_package_manager.capabilities import Operations, implements
from meta_package_manager.config import (
    config_file_is_trusted,
    load_bundled_definitions,
    parse_manager_definition,
    register_config_managers,
    validate_manager_overrides_section,
)
from meta_package_manager.manager import (
    ConfigDrivenManager,
    ManagerDefinition,
    OperationSpec,
    build_manager_class,
)
from meta_package_manager.pool import pool

skip_windows = pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason="POSIX-only: needs a shell fake CLI and POSIX file ownership.",
)


def _clean_definitions() -> None:
    """Remove every config-defined manager from the singleton pool."""
    for manager_id in list(pool.config_defined_ids):
        pool.register.pop(manager_id, None)
    pool.config_defined_ids.clear()
    for cached_list in (
        "all_manager_ids",
        "default_manager_ids",
        "maintained_manager_ids",
        "unsupported_manager_ids",
    ):
        pool.__dict__.pop(cached_list, None)


@pytest.fixture
def reset_definitions():
    """Drop config-defined managers from the singleton pool before and after a test.

    The pool is a module-level singleton, so a manager registered by one test would
    otherwise leak into the next. Mirrors ``reset_overrides`` in
    :mod:`tests.test_manager_overrides`.
    """
    _clean_definitions()
    yield
    _clean_definitions()


@pytest.fixture
def fake_tool(tmp_path):
    """Write a minimal POSIX fake package-manager CLI and return its path."""
    tool = tmp_path / "mytool"
    tool.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  --version) echo "mytool 1.2.3";;\n'
        '  list) printf "foo@1.0.0\\nbar@2.3.4\\n";;\n'
        '  search) printf "foo@9.9.9\\n";;\n'
        '  install) echo "installed $2";;\n'
        "esac\n",
    )
    tool.chmod(0o755)
    return tool


# Parsing and validation.


def test_parse_definition_returns_dataclass():
    definition = parse_manager_definition(
        "deno",
        {
            "name": "Deno",
            "platforms": ["linux", "macos"],
            "homepage_url": "https://deno.land",
            "cli_names": ["deno"],
            "requirement": ">=1.40",
            "operations": {
                "installed": {
                    "args": ["list"],
                    "regex": r"^(?P<package_id>\S+)@(?P<installed_version>\S+)$",
                },
                "install": {"args": ["install", "{package_id}"]},
            },
        },
    )
    assert isinstance(definition, ManagerDefinition)
    assert definition.manager_id == "deno"
    assert definition.name == "Deno"
    assert definition.platforms == ("linux", "macos")
    assert definition.cli_fields["cli_names"] == ("deno",)
    assert set(definition.operations) == {"installed", "install"}
    assert definition.operations["installed"].parse_mode == "regex"
    assert definition.operations["install"].parse_mode == "none"


@pytest.mark.parametrize(
    ("section", "expected"),
    (
        pytest.param(
            {"platforms": ["narnia"], "operations": {"sync": {"args": ["s"]}}},
            "unknown platform",
            id="unknown-platform",
        ),
        pytest.param(
            {"platforms": ["linux"], "operations": {"frobnicate": {"args": ["s"]}}},
            "unknown operation",
            id="unknown-operation",
        ),
        pytest.param(
            {"platforms": ["linux"], "operations": {"install": {"args": ["install"]}}},
            "must reference the {package_id} placeholder",
            id="missing-package-id-placeholder",
        ),
        pytest.param(
            {"platforms": ["linux"], "operations": {"search": {"args": ["s"]}}},
            "must reference the {query} placeholder",
            id="missing-query-placeholder",
        ),
        pytest.param(
            {"platforms": ["linux"], "operations": {"installed": {"args": ["list"]}}},
            "needs a 'regex' or a JSON 'fields' parser",
            id="query-without-parser",
        ),
        pytest.param(
            {
                "platforms": ["linux"],
                "operations": {
                    "installed": {"args": ["list"], "regex": r"^(?P<package_id>\S+)$"},
                },
            },
            "missing required",
            id="regex-missing-installed-version",
        ),
        pytest.param(
            {
                "platforms": ["linux"],
                "operations": {"outdated": {"args": ["o"], "format": "json"}},
            },
            "JSON parsing requires a 'fields' mapping",
            id="json-without-fields",
        ),
        pytest.param(
            {
                "platforms": ["linux"],
                "operations": {
                    "installed": {
                        "args": ["list"],
                        "regex": r"(?P<package_id>\S+)(?P<installed_version>\S+)",
                        "fields": {"package_id": "n"},
                    },
                },
            },
            "not both",
            id="regex-and-json",
        ),
        pytest.param(
            {
                "platforms": ["linux"],
                "operations": {"sync": {"args": ["s"]}},
                "bogus": 1,
            },
            "unknown field",
            id="unknown-top-level-field",
        ),
        pytest.param(
            {"platforms": ["linux"]},
            "must declare 'operations'",
            id="missing-operations",
        ),
        pytest.param(
            {"operations": {"sync": {"args": ["s"]}}},
            "must declare 'platforms'",
            id="missing-platforms",
        ),
        pytest.param(
            {"platforms": ["linux"], "operations": {}},
            "non-empty table",
            id="empty-operations",
        ),
    ),
)
def test_parse_definition_rejects(section, expected):
    with pytest.raises(ValidationError) as raised:
        parse_manager_definition("mytool", section)
    assert expected in str(raised.value)


def test_parse_definition_rejects_bad_id():
    with pytest.raises(ValidationError, match="invalid manager ID"):
        parse_manager_definition(
            "MyTool", {"platforms": ["linux"], "operations": {"sync": {"args": ["s"]}}}
        )


# Section routing: built-in override vs new-manager definition.


def test_routing_builtin_is_override():
    # A bad override field on a built-in is reported as an unknown override field,
    # not treated as a definition.
    with pytest.raises(ValidationError, match="unknown field"):
        validate_manager_overrides_section({"pip": {"nope": 1}}, pool=pool)


def test_routing_typo_of_builtin_is_unknown_manager():
    with pytest.raises(ValidationError, match="unknown manager ID"):
        validate_manager_overrides_section({"bre": {"cli_names": ["brew"]}}, pool=pool)


def test_routing_definition_is_validated():
    # A non-built-in ID carrying operations is validated as a definition.
    validate_manager_overrides_section(
        {
            "mytool": {
                "platforms": ["linux"],
                "operations": {"sync": {"args": ["update"]}},
            },
        },
        pool=pool,
    )


# Factory.


def _definition(**operations):
    return ManagerDefinition(
        manager_id="mytool",
        name="My Tool",
        platforms=("all_platforms",),
        homepage_url=None,
        cli_fields={"cli_names": ("mytool",)},
        operations=operations,
    )


def test_build_class_identity():
    klass = build_manager_class(_definition(sync=OperationSpec(args=("update",))))
    manager = klass()
    assert manager.id == "mytool"
    assert manager.name == "My Tool"
    assert isinstance(manager, ConfigDrivenManager)
    assert manager.virtual is False


@pytest.mark.parametrize(
    ("operations", "implemented", "not_implemented"),
    (
        pytest.param(
            {
                "installed": OperationSpec(
                    args=("l",),
                    parse_mode="regex",
                    regex=r"(?P<package_id>\S+)\s+(?P<installed_version>\S+)",
                )
            },
            (Operations.installed,),
            (Operations.outdated, Operations.install, Operations.remove),
            id="installed-only",
        ),
        pytest.param(
            {
                "installed": OperationSpec(
                    args=("l",),
                    parse_mode="regex",
                    regex=r"(?P<package_id>\S+)\s+(?P<installed_version>\S+)",
                ),
                "upgrade_one": OperationSpec(args=("up", "{package_id}")),
            },
            (Operations.installed, Operations.upgrade),
            (Operations.upgrade_all, Operations.outdated),
            id="upgrade-needs-installed",
        ),
        pytest.param(
            {"upgrade_all": OperationSpec(args=("up",))},
            (Operations.upgrade_all,),
            (Operations.upgrade, Operations.installed),
            id="upgrade-all-only",
        ),
    ),
)
def test_build_class_implements(operations, implemented, not_implemented):
    manager = build_manager_class(_definition(**operations))()
    for operation in implemented:
        assert implements(manager, operation) is True
    for operation in not_implemented:
        assert implements(manager, operation) is False


def test_factory_regex_parsing():
    manager = build_manager_class(
        _definition(
            installed=OperationSpec(
                args=("list",),
                parse_mode="regex",
                regex=r"^(?P<package_id>\S+)@(?P<installed_version>\S+)$",
            ),
        ),
    )()
    manager.run_cli = lambda *args, **kwargs: "ruff@0.1.2\nblack@24.1.0"
    assert [(p.id, str(p.installed_version)) for p in manager.installed] == [
        ("ruff", "0.1.2"),
        ("black", "24.1.0"),
    ]


def test_factory_json_parsing():
    manager = build_manager_class(
        _definition(
            outdated=OperationSpec(
                args=("outdated", "--json"),
                parse_mode="json",
                list_path="packages",
                fields={
                    "package_id": "name",
                    "installed_version": "current",
                    "latest_version": "latest",
                },
            ),
        ),
    )()
    manager.run_cli = lambda *a, **k: json.dumps(
        {"packages": [{"name": "ruff", "current": "0.1.2", "latest": "0.2.0"}]},
    )
    outdated = list(manager.outdated)
    assert len(outdated) == 1
    assert outdated[0].id == "ruff"
    assert str(outdated[0].installed_version) == "0.1.2"
    assert str(outdated[0].latest_version) == "0.2.0"


def test_factory_command_substitution():
    manager = build_manager_class(
        _definition(
            install=OperationSpec(args=("install", "{package_id}")),
            upgrade_one=OperationSpec(args=("install", "--force", "{package_id}")),
        ),
    )()
    captured = {}
    manager.run_cli = lambda *args, **kwargs: captured.update(install=args) or ""
    manager.install("jq")
    assert captured["install"] == ("install", "jq")
    # upgrade_one_cli builds a command line off the resolved binary path.
    manager.build_cli = lambda *args, **kwargs: args
    assert manager.upgrade_one_cli("jq") == ("install", "--force", "jq")


# Trust gate.


@skip_windows
def test_config_file_is_trusted(tmp_path):
    good = tmp_path / "config.toml"
    good.write_text("")
    assert config_file_is_trusted(good) is True

    world_writable = tmp_path / "loose.toml"
    world_writable.write_text("")
    world_writable.chmod(0o666)
    assert config_file_is_trusted(world_writable) is False


@skip_windows
def test_register_refuses_untrusted_file(tmp_path, reset_definitions, caplog):
    loose = tmp_path / "loose.toml"
    loose.write_text("")
    loose.chmod(0o666)
    definition = _definition(sync=OperationSpec(args=("update",)))
    registered = register_config_managers(pool, {"mytool": definition}, source=loose)
    assert registered == []
    assert "mytool" not in pool.register
    assert "unsafe config file" in caplog.text


def test_register_refuses_url(reset_definitions, caplog):
    definition = _definition(sync=OperationSpec(args=("update",)))
    registered = register_config_managers(
        pool, {"mytool": definition}, source=None, source_is_url=True
    )
    assert registered == []
    assert "mytool" not in pool.register
    assert "remote config URL" in caplog.text


def test_register_rejects_builtin_collision(reset_definitions, caplog):
    definition = ManagerDefinition(
        manager_id="pip",
        name="Fake Pip",
        platforms=("all_platforms",),
        homepage_url=None,
        cli_fields={},
        operations={"sync": OperationSpec(args=("update",))},
    )
    registered = register_config_managers(pool, {"pip": definition}, source=None)
    assert registered == []
    assert "already uses this ID" in caplog.text


def test_register_is_idempotent(reset_definitions):
    definition = _definition(sync=OperationSpec(args=("update",)))
    assert register_config_managers(pool, {"mytool": definition}, source=None) == [
        "mytool",
    ]
    assert "mytool" in pool.register
    assert "mytool" in pool.config_defined_ids
    # A second pass is a no-op (already registered).
    assert register_config_managers(pool, {"mytool": definition}, source=None) == []


# End-to-end through the real subprocess and the CLI.


@skip_windows
def test_factory_functional(tmp_path, fake_tool, reset_definitions):
    definition = ManagerDefinition(
        manager_id="mytool",
        name="My Tool",
        platforms=("all_platforms",),
        homepage_url=None,
        cli_fields={
            "cli_names": ("mytool",),
            "cli_search_path": (str(tmp_path),),
            "requirement": ">=1.0",
            "version_regexes": (r"mytool (?P<version>\S+)",),
        },
        operations={
            "installed": OperationSpec(
                args=("list",),
                parse_mode="regex",
                regex=r"^(?P<package_id>\S+)@(?P<installed_version>\S+)$",
            ),
            "search": OperationSpec(
                args=("search", "{query}"),
                parse_mode="regex",
                regex=r"^(?P<package_id>\S+)@(?P<latest_version>\S+)$",
            ),
            "upgrade_one": OperationSpec(args=("install", "--force", "{package_id}")),
        },
    )
    manager = build_manager_class(definition)()
    assert manager.available is True
    assert {p.id for p in manager.installed} == {"foo", "bar"}
    assert [p.id for p in manager.search("foo", False, False)] == ["foo"]
    assert "--force" in manager.upgrade_one_cli("foo")


@skip_windows
def test_cli_lists_config_defined_manager(
    invoke, create_config, tmp_path, fake_tool, reset_definitions
):
    conf_path = create_config(
        "conf.toml",
        f"""
        [mpm.managers.mytool]
        name = "My Tool"
        platforms = ["all_platforms"]
        cli_names = ["mytool"]
        cli_search_path = ["{tmp_path}"]
        requirement = ">=1.0"
        version_regexes = ['mytool (?P<version>\\S+)']

        [mpm.managers.mytool.operations.installed]
        args = ["list"]
        regex = '^(?P<package_id>\\S+)@(?P<installed_version>\\S+)$'
        """,
    )
    result = invoke("--config", str(conf_path), "managers")
    assert result.exit_code == 0
    assert "mytool" in result.stdout


def test_cli_rejects_bad_definition(invoke, create_config, reset_definitions):
    conf_path = create_config(
        "conf.toml",
        """
        [mpm.managers.mytool]
        platforms = ["narnia"]

        [mpm.managers.mytool.operations.sync]
        args = ["update"]
        """,
    )
    result = invoke("--config", str(conf_path), "managers")
    assert result.exit_code != 0
    assert "narnia" in result.output


# Bundled manager definitions shipped with mpm as package data.


def _fresh_gh_ext():
    """Build a throwaway gh-ext instance so parsing tests can monkeypatch ``run_cli``
    without mutating the shared pool singleton."""
    for definition, _ in load_bundled_definitions():
        if definition.manager_id == "gh-ext":
            return build_manager_class(definition)()
    raise AssertionError("gh-ext is not among the bundled definitions")


def test_bundled_definitions_are_valid():
    """Every shipped definition parses and reports a repo-relative TOML source."""
    bundled = load_bundled_definitions()
    assert bundled, "mpm ships at least one bundled manager definition"
    for definition, source in bundled:
        assert isinstance(definition, ManagerDefinition)
        assert source.startswith("meta_package_manager/managers/")
        assert source.endswith(".toml")


def test_bundled_ids_disjoint_from_builtins():
    assert pool.bundled_manager_ids
    assert pool.bundled_manager_ids.isdisjoint(pool.builtin_manager_ids)
    assert pool.known_manager_ids == pool.builtin_manager_ids | pool.bundled_manager_ids


def test_gh_ext_registered():
    """The bundled gh-ext manager is always present in the pool, config-defined."""
    assert "gh-ext" in pool.bundled_manager_ids
    manager = pool["gh-ext"]
    assert isinstance(manager, ConfigDrivenManager)
    assert manager.name == "GitHub CLI extensions"
    assert manager.homepage_url == "https://cli.github.com"
    assert manager.definition_source == "meta_package_manager/managers/gh_ext.toml"


@pytest.mark.parametrize(
    ("operation", "expected"),
    (
        (Operations.installed, True),
        (Operations.search, True),
        (Operations.install, True),
        (Operations.remove, True),
        (Operations.upgrade, True),
        (Operations.upgrade_all, True),
        (Operations.outdated, False),
        (Operations.sync, False),
        (Operations.cleanup, False),
    ),
)
def test_gh_ext_capabilities(operation, expected):
    assert implements(pool["gh-ext"], operation) is expected


def test_gh_ext_version_regex():
    match = re.search(
        pool["gh-ext"].version_regexes[0], "gh version 2.62.0 (2024-11-14)"
    )
    assert match is not None
    assert match.group("version") == "2.62.0"


def test_gh_ext_parses_installed():
    """Parse the headerless, tab-separated ``gh extension list`` piped output.

    Column 1 is ``gh <name>`` (the short name is the package id), column 2 the
    ``owner/repo`` slug, column 3 the free-form version (a tag or a commit SHA).
    """
    manager = _fresh_gh_ext()
    manager.run_cli = lambda *args, **kwargs: (
        "gh dash\tdlvhdr/gh-dash\tv4.7.0\ngh cockpit\tgithub/gh-cockpit\ta1b2c3d4"
    )
    assert [(p.id, str(p.installed_version)) for p in manager.installed] == [
        ("dash", "v4.7.0"),
        ("cockpit", "a1b2c3d4"),
    ]


def test_gh_ext_parses_search():
    """Extract the ``owner/repo`` slug from ``gh extension search`` output by content.

    Covers all three row shapes: the first row whose leading empty-state tab ``run_cli``
    strips off (slug in column 1), a row with an empty install-state column (slug in
    column 2), and a row whose install-state column is populated with ``installed``.
    """
    manager = _fresh_gh_ext()
    manager.run_cli = lambda *args, **kwargs: (
        "dlvhdr/gh-dash\tA rich terminal UI for GitHub\n"
        "\tvilmibm/gh-screensaver\tScreensavers for your terminal\n"
        "installed\tcli/gh-webhook\tForward webhooks to localhost"
    )
    assert [p.id for p in manager.search("gh", False, False)] == [
        "dlvhdr/gh-dash",
        "vilmibm/gh-screensaver",
        "cli/gh-webhook",
    ]
