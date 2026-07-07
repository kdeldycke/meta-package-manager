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
from pathlib import Path

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
            {
                "platforms": ["linux"],
                "operations": {
                    "installed": {
                        "args": ["list"],
                        "regex": r"(?P<package_id>\S+) (?P<installed_version>\S+)",
                        "sudo": True,
                    },
                },
            },
            "unknown key",
            id="sudo-on-query-operation",
        ),
        pytest.param(
            {
                "platforms": ["linux"],
                "operations": {"sync": {"args": ["s"], "cli": ""}},
            },
            "must be a non-empty string",
            id="empty-operation-cli",
        ),
        pytest.param(
            {
                "platforms": ["linux"],
                "operations": {"sync": {"args": ["s"], "sudo": "yes"}},
            },
            "expected a boolean",
            id="non-boolean-sudo",
        ),
        pytest.param(
            {
                "platforms": ["linux"],
                "operations": {"sync": {"args": ["s"]}},
                "version_cli": 1,
            },
            "expected a string",
            id="non-string-version-cli",
        ),
        pytest.param(
            {
                "platforms": ["linux"],
                "operations": {"sync": {"args": ["s"]}},
                "default_sudo": "yes",
            },
            "expected a boolean",
            id="non-boolean-default-sudo",
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


def test_parse_definition_multi_binary_and_sudo():
    """A definition can span sibling binaries, mark privileged operations, and
    declare an alternate version probe."""
    definition = parse_manager_definition(
        "urpmi-like",
        {
            "platforms": ["linux"],
            "cli_names": ["urpmi"],
            "default_sudo": True,
            "version_cli": "uname",
            "operations": {
                "search": {
                    "args": ["--fuzzy", "{query}"],
                    "cli": "urpmq",
                    "regex": r"^(?P<package_id>\S+)$",
                },
                "install": {"args": ["--auto", "{package_id}"], "sudo": True},
                "remove": {
                    "args": ["--auto", "{package_id}"],
                    "cli": "urpme",
                    "sudo": True,
                },
            },
        },
    )
    assert definition.cli_fields["default_sudo"] is True
    assert definition.cli_fields["version_cli"] == "uname"
    assert definition.operations["search"].cli == "urpmq"
    assert definition.operations["search"].sudo is False
    assert definition.operations["install"].cli is None
    assert definition.operations["install"].sudo is True
    assert definition.operations["remove"].cli == "urpme"
    assert definition.operations["remove"].sudo is True


# Section routing: built-in override vs new-manager definition.


def test_routing_builtin_is_override():
    # A bad override field on a built-in is reported as an unknown override field,
    # not treated as a definition.
    with pytest.raises(ValidationError, match="unknown field"):
        validate_manager_overrides_section({"pip": {"nope": 1}}, pool=pool)


def test_routing_typo_of_builtin_is_unknown_manager():
    with pytest.raises(ValidationError, match="unknown manager ID"):
        validate_manager_overrides_section({"brw": {"cli_names": ["brew"]}}, pool=pool)


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


def test_factory_regex_parsing(monkeypatch):
    manager = build_manager_class(
        _definition(
            installed=OperationSpec(
                args=("list",),
                parse_mode="regex",
                regex=r"^(?P<package_id>\S+)@(?P<installed_version>\S+)$",
            ),
        ),
    )()
    monkeypatch.setattr(
        manager, "run_cli", lambda *args, **kwargs: "ruff@0.1.2\nblack@24.1.0"
    )
    assert [(p.id, str(p.installed_version)) for p in manager.installed] == [
        ("ruff", "0.1.2"),
        ("black", "24.1.0"),
    ]


def test_factory_json_parsing(monkeypatch):
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
    monkeypatch.setattr(
        manager,
        "run_cli",
        lambda *a, **k: json.dumps(
            {"packages": [{"name": "ruff", "current": "0.1.2", "latest": "0.2.0"}]},
        ),
    )
    outdated = list(manager.outdated)
    assert len(outdated) == 1
    assert outdated[0].id == "ruff"
    assert str(outdated[0].installed_version) == "0.1.2"
    assert str(outdated[0].latest_version) == "0.2.0"


def test_factory_command_substitution(monkeypatch):
    manager = build_manager_class(
        _definition(
            install=OperationSpec(args=("install", "{package_id}")),
            upgrade_one=OperationSpec(args=("install", "--force", "{package_id}")),
        ),
    )()
    captured: dict[str, tuple[str, ...]] = {}
    monkeypatch.setattr(
        manager,
        "run_cli",
        lambda *args, **kwargs: captured.update(install=args) or "",
    )
    manager.install("jq")
    assert captured["install"] == ("install", "jq")
    # upgrade_one_cli builds a command line off the resolved binary path.
    monkeypatch.setattr(manager, "build_cli", lambda *args, **kwargs: args)
    assert manager.upgrade_one_cli("jq") == ("install", "--force", "jq")


def test_factory_operation_cli(monkeypatch):
    """An operation carrying its own ``cli`` resolves the sibling binary and routes
    the call through it; a missing sibling is an error, not a silent fallback."""
    manager = build_manager_class(
        _definition(
            remove=OperationSpec(args=("--auto", "{package_id}"), cli="urpme"),
        ),
    )()
    sibling = Path("/fake/bin/urpme")
    captured: dict[str, object] = {}
    monkeypatch.setattr(manager, "which", lambda name: sibling)
    monkeypatch.setattr(
        manager,
        "run_cli",
        lambda *args, **kwargs: captured.update(args=args, **kwargs) or "",
    )
    manager.remove("jq")
    assert captured["args"] == ("--auto", "jq")
    assert captured["override_cli_path"] == sibling

    monkeypatch.setattr(manager, "which", lambda name: None)
    with pytest.raises(FileNotFoundError, match="urpme not found"):
        manager.remove("jq")


def test_factory_operation_sudo(monkeypatch):
    """A ``sudo = true`` operation is built privileged; unmarked ones are not."""
    manager = build_manager_class(
        _definition(
            install=OperationSpec(args=("--auto", "{package_id}"), sudo=True),
            sync=OperationSpec(args=("update",)),
            upgrade_all=OperationSpec(args=("--auto-select",), sudo=True),
        ),
    )()
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        manager,
        "run_cli",
        lambda *args, **kwargs: captured.update(kwargs) or "",
    )
    manager.install("jq")
    assert captured["sudo"] is True
    manager.sync()
    assert captured["sudo"] is False
    monkeypatch.setattr(
        manager,
        "build_cli",
        lambda *args, **kwargs: captured.update(kwargs) or args,
    )
    manager.upgrade_all_cli()
    assert captured["sudo"] is True


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
def test_factory_functional_version_cli(tmp_path, fake_tool, reset_definitions):
    """The version probe runs the ``version_cli`` binary instead of the main CLI,
    like OS-versioned tool suites exposing no version flag of their own."""
    probe = tmp_path / "myuname"
    probe.write_text("#!/bin/sh\necho '7.7'\n")
    probe.chmod(0o755)
    definition = ManagerDefinition(
        manager_id="mytool",
        name="My Tool",
        platforms=("all_platforms",),
        homepage_url=None,
        cli_fields={
            "cli_names": ("mytool",),
            "cli_search_path": (str(tmp_path),),
            "requirement": ">=7.0",
            "version_cli": "myuname",
            "version_cli_options": ("-r",),
            "version_regexes": (r"(?P<version>[\d.]+)",),
        },
        operations={
            "sync": OperationSpec(args=("update",)),
        },
    )
    manager = build_manager_class(definition)()
    assert str(manager.version) == "7.7"
    assert manager.available is True


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


def _fresh_bundled(manager_id):
    """Build a throwaway config-defined manager instance so parsing tests can
    monkeypatch ``run_cli`` without mutating the shared pool singleton."""
    for definition, _ in load_bundled_definitions():
        if definition.manager_id == manager_id:
            return build_manager_class(definition)()
    raise AssertionError(f"{manager_id} is not among the bundled definitions")


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


@pytest.mark.parametrize(
    ("manager_id", "name", "homepage_url", "definition_source"),
    (
        (
            "cave",
            "cave",
            "https://exherbo.org",
            "meta_package_manager/managers/cave.toml",
        ),
        (
            "chromebrew",
            "Chromebrew",
            "https://chromebrew.github.io",
            "meta_package_manager/managers/chromebrew.toml",
        ),
        (
            "fink",
            "Fink",
            "https://www.finkproject.org",
            "meta_package_manager/managers/fink.toml",
        ),
        (
            "gh-ext",
            "GitHub CLI extensions",
            "https://cli.github.com",
            "meta_package_manager/managers/gh_ext.toml",
        ),
        (
            "pkg-tools",
            "OpenBSD pkg tools",
            "https://man.openbsd.org/pkg_add",
            "meta_package_manager/managers/pkg_tools.toml",
        ),
        (
            "pkgin",
            "Pkgin",
            "https://pkgin.net",
            "meta_package_manager/managers/pkgin.toml",
        ),
        (
            "slapt-get",
            "slapt-get",
            "https://software.jaos.org/",
            "meta_package_manager/managers/slapt_get.toml",
        ),
        (
            "soar",
            "Soar",
            "https://github.com/pkgforge/soar",
            "meta_package_manager/managers/soar.toml",
        ),
        (
            "sorcery",
            "Sorcery",
            "https://sourcemage.org",
            "meta_package_manager/managers/sorcery.toml",
        ),
        (
            "tlmgr",
            "TeX Live Manager",
            "https://www.tug.org/texlive/",
            "meta_package_manager/managers/tlmgr.toml",
        ),
        (
            "topgrade",
            "Topgrade",
            "https://github.com/topgrade-rs/topgrade",
            "meta_package_manager/managers/topgrade.toml",
        ),
        (
            "urpmi",
            "urpmi",
            "https://wiki.mageia.org/en/URPMI",
            "meta_package_manager/managers/urpmi.toml",
        ),
    ),
)
def test_bundled_registered(manager_id, name, homepage_url, definition_source):
    """Each bundled manager is always present in the pool, config-defined."""
    assert manager_id in pool.bundled_manager_ids
    manager = pool[manager_id]
    assert isinstance(manager, ConfigDrivenManager)
    assert manager.name == name
    assert manager.homepage_url == homepage_url
    assert manager.definition_source == definition_source


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


@pytest.mark.parametrize(
    ("manager_id", "version_output", "expected_version"),
    (
        ("cave", "cave 3.0.1", "3.0.1"),
        ("chromebrew", "1.75.0", "1.75.0"),
        ("fink", "Package manager version: 0.45.6", "0.45.6"),
        ("gh-ext", "gh version 2.62.0 (2024-11-14)", "2.62.0"),
        # pkg-tools probes `uname -r`, the suite shipping with the OS release.
        ("pkg-tools", "7.7", "7.7"),
        ("pkgin", "pkgin 26.4.0 (using SQLite 3.45.1)", "26.4.0"),
        ("slapt-get", "slapt-get version 0.11.12", "0.11.12"),
        ("soar", "soar 0.12.6", "0.12.6"),
        # Sorcery prints the bare content of /etc/sorcery/version, a datestamp.
        ("sorcery", "20240108", "20240108"),
        (
            "tlmgr",
            "tlmgr revision 66798 (2023-04-08 02:15:21 +0200)\n"
            "tlmgr using installation: /usr/local/texlive/2023\n"
            "TeX Live (https://tug.org/texlive) version 2023",
            "2023",
        ),
        ("topgrade", "topgrade 17.4.0", "17.4.0"),
        ("urpmi", "urpmi 8.121.7", "8.121.7"),
    ),
)
def test_bundled_version_regex(manager_id, version_output, expected_version):
    match = re.search(pool[manager_id].version_regexes[0], version_output)
    assert match is not None
    assert match.group("version") == expected_version


def test_gh_ext_parses_installed():
    """Parse the headerless, tab-separated ``gh extension list`` piped output.

    Column 1 is ``gh <name>`` (the short name is the package id), column 2 the
    ``owner/repo`` slug, column 3 the free-form version (a tag or a commit SHA).
    """
    manager = _fresh_bundled("gh-ext")
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
    manager = _fresh_bundled("gh-ext")
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


@pytest.mark.parametrize(
    ("operation", "expected"),
    (
        (Operations.installed, True),
        (Operations.search, True),
        (Operations.install, True),
        (Operations.remove, True),
        (Operations.upgrade, True),
        (Operations.upgrade_all, True),
        (Operations.sync, True),
        (Operations.cleanup, True),
        (Operations.outdated, False),
    ),
)
def test_soar_capabilities(operation, expected):
    assert implements(pool["soar"], operation) is expected


def test_soar_parses_installed():
    """Parse ``soar list-installed``: split "name-version:repo" at the last "-" before a
    digit-led version, so multi-hyphen names stay intact."""
    manager = _fresh_bundled("soar")
    manager.run_cli = lambda *args, **kwargs: (
        "bat-0.24.0:soarpkgs (2025-01-15) (1.8 MB)\n"
        "google-chrome-131.0:soarpkgs (2025-01-14) (95.2 MB)\n"
        "7-zip-24.09:soarpkgs (2025-01-10) (1.5 MB) [Broken]"
    )
    assert [(p.id, str(p.installed_version)) for p in manager.installed] == [
        ("bat", "0.24.0"),
        ("google-chrome", "131.0"),
        ("7-zip", "24.09"),
    ]


def test_soar_parses_search():
    """Extract the package name (before "#") from each ``soar search`` line, tolerating
    both the installed (✓/+) and available (○/-) state icons."""
    manager = _fresh_bundled("soar")
    manager.run_cli = lambda *args, **kwargs: (
        "[+] bat#official:soarpkgs | 0.24.0 | archive - A cat clone (1.8 MB)\n"
        "[✓] ripgrep#official:soarpkgs | 14.1.0 | archive - Fast search (4.2 MB)"
    )
    assert [p.id for p in manager.search("bat", False, False)] == ["bat", "ripgrep"]


@pytest.mark.parametrize(
    ("manager_id", "operation", "output", "expected"),
    (
        pytest.param(
            "cave",
            "installed",
            "app-arch/gzip 1.14\nsys-apps/sed 4.9",
            [("app-arch/gzip", "1.14"), ("sys-apps/sed", "4.9")],
            id="cave-installed",
        ),
        pytest.param(
            "chromebrew",
            "installed",
            "Package        Version\n=======\nless           643\nnano           8.2",
            [("less", "643"), ("nano", "8.2")],
            id="chromebrew-installed",
        ),
        pytest.param(
            "chromebrew",
            "search",
            "less: GNU less is a paginator\nlesspipe: Filters for less",
            [("less", None), ("lesspipe", None)],
            id="chromebrew-search",
        ),
        pytest.param(
            "fink",
            "installed",
            " i \tfiglet\t2.2.5-1\tPrints text as ASCII art\n"
            "(i)\tnano\t6.2-1\tSmall editor\n"
            "   \tlynx\t2.9.0-1\tText browser is not installed",
            [("figlet", "2.2.5-1"), ("nano", "6.2-1")],
            id="fink-installed",
        ),
        pytest.param(
            "pkg-tools",
            "installed",
            "unzip-6.0p17        Extract files from ZIP archives\n"
            "lunzip-1.14p0       Lzip decompressor",
            [("unzip", "6.0p17"), ("lunzip", "1.14p0")],
            id="pkg-tools-installed",
        ),
        pytest.param(
            "pkg-tools",
            "search",
            "lunzip-1.14p0\nunzip-6.0p17 (installed)\nunzip-6.0p17-iconv",
            [
                ("lunzip", "1.14p0"),
                ("unzip", "6.0p17"),
                ("unzip", "6.0p17-iconv"),
            ],
            id="pkg-tools-search",
        ),
        pytest.param(
            "pkgin",
            "installed",
            "lbdb-0.48.1nb1;The little brother's database\n"
            "mutt-1.14.5;Text-based MIME mail client",
            [("lbdb", "0.48.1nb1"), ("mutt", "1.14.5")],
            id="pkgin-installed",
        ),
        pytest.param(
            "pkgin",
            "outdated",
            "abook-0.6.2;<;Text-based addressbook program",
            [("abook", "0.6.2")],
            id="pkgin-outdated",
        ),
        pytest.param(
            "pkgin",
            "search",
            "abook-0.6.1          Text-based addressbook program\n"
            "mutt-1.14.5 =        Text-based MIME mail client\n"
            "=: package is installed and up-to-date\n"
            "<: package is installed but newer version is available\n"
            ">: installed package has a greater version than available package",
            [("abook", "0.6.1"), ("mutt", "1.14.5")],
            id="pkgin-search",
        ),
        pytest.param(
            "slapt-get",
            "installed",
            "tree-2.3.2-x86_64-1 [inst=yes]: display directory tree\n"
            "util-linux-2.39-x86_64-1 [inst=yes]: collection of utilities",
            [("tree", "2.3.2"), ("util-linux", "2.39")],
            id="slapt-get-installed",
        ),
        pytest.param(
            "slapt-get",
            "search",
            "tree-2.3.2-x86_64-1 [inst=no]: display directory tree",
            [("tree", "2.3.2")],
            id="slapt-get-search",
        ),
        pytest.param(
            "sorcery",
            "installed",
            "cowsay:20240108:installed:3.03\nvim:20230101:held:9.0",
            [("cowsay", "3.03"), ("vim", "9.0")],
            id="sorcery-installed",
        ),
        pytest.param(
            "sorcery",
            "search",
            "cowsay 3.03 @test\ntree 2.1.1 @stable",
            [("cowsay", "3.03"), ("tree", "2.1.1")],
            id="sorcery-search",
        ),
        pytest.param(
            "tlmgr",
            "installed",
            "tlmgr: package repository https://mirror.ctan.org (verified)\n"
            "sansmath,15878\ntitlesec,68677",
            [("sansmath", "15878"), ("titlesec", "68677")],
            id="tlmgr-installed",
        ),
        pytest.param(
            "tlmgr",
            "outdated",
            "location-url\thttps://mirror.ctan.org\n"
            "total-bytes\t323544\n"
            "end-of-header\n"
            "adjmulticol\tu\t62935\t63073\t316000\t-\t-\t-\t-\t-\n"
            "end-of-updates\n"
            "running mktexlsr ...",
            [("adjmulticol", "63073")],
            id="tlmgr-outdated",
        ),
        pytest.param(
            "urpmi",
            "installed",
            "sgml-skel 0.7-24.mga9\ndesktop-file-utils 0.26-5.mga9",
            [("sgml-skel", "0.7-24.mga9"), ("desktop-file-utils", "0.26-5.mga9")],
            id="urpmi-installed",
        ),
        pytest.param(
            "urpmi",
            "outdated",
            "kernel-desktop-6.6.0-1.mga9\nfvwm3-1.0.2-1.1.mga8",
            [("kernel-desktop", "6.6.0-1.mga9"), ("fvwm3", "1.0.2-1.1.mga8")],
            id="urpmi-outdated",
        ),
    ),
)
def test_bundled_parsing(manager_id, operation, output, expected):
    """Lock each bundled definition's regexes to output samples derived from the
    upstream tools' own source code or documentation.

    Versions are compared as raw captured strings (``None`` when the regex has no
    version group). ``which`` is stubbed so operations declaring a sibling ``cli``
    resolve without the real binary installed.
    """
    manager = _fresh_bundled(manager_id)
    manager.which = lambda name: Path("/fake/bin") / name
    manager.run_cli = lambda *args, **kwargs: output
    if operation == "search":
        packages = manager.search("query", False, False)
    else:
        packages = getattr(manager, operation)
    role = "installed_version" if operation == "installed" else "latest_version"
    results = [
        (p.id, str(version) if (version := getattr(p, role)) else None)
        for p in packages
    ]
    assert results == expected
