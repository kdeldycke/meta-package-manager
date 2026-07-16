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

import inspect
import json
import os
import re
from operator import attrgetter
from pathlib import Path

import pytest
from click_extra import ValidationError

import meta_package_manager
from meta_package_manager.capabilities import Operations, implements
from meta_package_manager.config import (
    config_file_is_trusted,
    register_config_managers,
    validate_manager_overrides_section,
)
from meta_package_manager.definitions import (
    ConfigDrivenManager,
    ManagerDefinition,
    OperationSpec,
    build_manager_class,
    load_bundled_definitions,
    parse_manager_definition,
)
from meta_package_manager.pool import pool

from .conftest import tomllib


skip_windows = pytest.mark.skipif(
    not hasattr(os, "getuid"),
    reason="POSIX-only: needs a shell fake CLI and POSIX file ownership.",
)


def _clean_definitions() -> None:
    """Remove every config-defined manager from the singleton pool."""
    for manager_id in list(pool.config_defined_ids):
        pool.register.pop(manager_id, None)
    pool.config_defined_ids.clear()
    pool._evict_id_caches()


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


def test_parse_definition_versionless_catalog_manager():
    """A tool with no per-package versions, no search command and a Brewfile mapping.

    Locks three schema affordances at once: an ``installed`` regex may capture only
    the package ID (Clear Linux bundles and Cygwin listings carry no version), a
    ``search`` may omit ``{query}`` to list the whole catalog and rely on
    client-side refiltering, and the Brewfile export fields land on the built class.
    """
    definition = parse_manager_definition(
        "bundletool",
        {
            "platforms": ["linux"],
            "brewfile_entry_type": "brew",
            "brewfile_skip_warning": "Skipping {count} bundle(s).",
            "operations": {
                "installed": {
                    "args": ["list"],
                    "regex": r"^(?P<package_id>\S+)$",
                },
                "search": {
                    "args": ["list", "--all"],
                    "regex": r"^(?P<package_id>\S+)$",
                },
            },
        },
    )
    klass = build_manager_class(definition)
    assert klass.brewfile_entry_type == "brew"
    assert klass.brewfile_skip_warning == "Skipping {count} bundle(s)."


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
            {
                "platforms": ["linux"],
                "operations": {
                    "search": {
                        "args": ["s", "{qeury}"],
                        "regex": r"^(?P<package_id>\S+)$",
                    },
                },
            },
            "unknown placeholder(s): {qeury}",
            id="typoed-placeholder",
        ),
        pytest.param(
            {
                "platforms": ["linux"],
                "operations": {"sync": {"args": ["s", "{package_id}"]}},
            },
            "sync args take no placeholder",
            id="placeholder-on-placeholderless-operation",
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
                    "outdated": {"args": ["o"], "regex": r"^(?P<package_id>\S+)$"},
                },
            },
            "missing required",
            id="regex-missing-latest-version",
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
            {
                "platforms": ["linux"],
                "operations": {"sync": {"args": ["s"]}},
                "internal_sudo": "yes",
            },
            "expected a boolean",
            id="non-boolean-internal-sudo",
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


def test_parse_definition_internal_sudo():
    """A definition can mark its tool as escalating internally (like fink), and
    the flag lands on the built class without touching the wrapping policy."""
    definition = parse_manager_definition(
        "finklike",
        {
            "platforms": ["macos"],
            "internal_sudo": True,
            "operations": {
                "install": {"args": ["install", "{package_id}"]},
            },
        },
    )
    assert definition.cli_fields["internal_sudo"] is True
    klass = build_manager_class(definition)
    assert klass.internal_sudo is True
    assert klass.default_sudo is False


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
    # Each phase clears the dict so its assert reads the state its own call
    # captured, and reads through a local: mypy narrows the ``captured["sudo"]``
    # subscript on each assert and cannot see the monkeypatched methods mutate
    # the dict, so re-asserting the same subscript with alternating values
    # would mark the later phases unreachable.
    manager.install("jq")
    install_sudo = captured["sudo"]
    assert install_sudo is True
    captured.clear()
    manager.sync()
    sync_sudo = captured["sudo"]
    assert sync_sudo is False
    monkeypatch.setattr(
        manager,
        "build_cli",
        lambda *args, **kwargs: captured.update(kwargs) or args,
    )
    captured.clear()
    manager.upgrade_all_cli()
    upgrade_all_sudo = captured["sudo"]
    assert upgrade_all_sudo is True


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

BUNDLED_DEFINITION_FILES = sorted(
    (Path(inspect.getfile(meta_package_manager)).parent / "managers").glob("*.toml"),
)
"""Every definition file mpm ships, discovered exactly like the runtime loader."""

BUNDLED_FILE_DATA = {
    toml_path: tomllib.loads(toml_path.read_text(encoding="UTF-8"))
    for toml_path in BUNDLED_DEFINITION_FILES
}
"""Parsed content of each shipped file: the definition and its ``[samples]``.

The samples are the source-derived output fixtures feeding
``test_bundled_version_regex`` and ``test_bundled_parsing``, so adding a bundled
manager (with its samples) extends those tests without touching this module.
"""


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


def test_bundled_inventory():
    """The pool registers exactly one bundled manager per shipped TOML file.

    Catches a loader-side skip: a malformed file is logged and dropped at load
    time, so the pool silently missing an ID would be the only trace.
    """
    assert BUNDLED_DEFINITION_FILES
    file_ids = set()
    for toml_path, data in BUNDLED_FILE_DATA.items():
        sections = data["mpm"]["managers"]
        assert len(sections) == 1, f"{toml_path.name} must define a single manager"
        file_ids.update(sections)
    assert file_ids == set(pool.bundled_manager_ids)


@pytest.mark.parametrize("toml_path", BUNDLED_DEFINITION_FILES, ids=attrgetter("stem"))
def test_bundled_registered(toml_path):
    """Each shipped definition file lands in the pool as a config-defined manager.

    Every expectation derives from the file itself, so a new bundled manager is
    covered without extending any hardcoded list here. The file must carry
    nothing but its definition and the test samples locking its parsers.
    """
    data = BUNDLED_FILE_DATA[toml_path]
    assert set(data) <= {"mpm", "samples"}, (
        f"unexpected top-level keys in {toml_path.name}"
    )

    manager_id = next(iter(data["mpm"]["managers"]))
    assert toml_path.stem == manager_id.replace("-", "_")
    assert manager_id in pool.bundled_manager_ids
    manager = pool[manager_id]
    assert isinstance(manager, ConfigDrivenManager)
    assert (
        manager.definition_source == f"meta_package_manager/managers/{toml_path.name}"
    )
    assert manager.name
    assert manager.homepage_url

    # Validate the shape of the sample fixtures consumed by the tests below.
    samples = data.get("samples", {})
    assert set(samples) <= {"version", "installed", "outdated", "search"}
    assert "version" in samples, (
        f"{toml_path.name} must ship a [samples.version] fixture"
    )
    assert set(samples["version"]) == {"output", "expected"}
    for operation in ("installed", "outdated", "search"):
        for sample in samples.get(operation, ()):
            assert set(sample) == {"output", "packages"}
            assert sample["packages"], "a sample must expect at least one package"
            for package in sample["packages"]:
                assert set(package) <= {"id", "version"}
                assert package["id"]


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


def _version_sample_params():
    """One param per shipped definition file, from its ``[samples.version]`` fixture."""
    params = []
    for data in BUNDLED_FILE_DATA.values():
        manager_id = next(iter(data["mpm"]["managers"]))
        sample = data.get("samples", {}).get("version")
        if sample:
            params.append(
                pytest.param(
                    manager_id, sample["output"], sample["expected"], id=manager_id
                ),
            )
    return params


@pytest.mark.parametrize(("manager_id", "output", "expected"), _version_sample_params())
def test_bundled_version_regex(manager_id, output, expected):
    """Lock each bundled definition's version probe to the output sample shipped in
    its TOML file, derived from the upstream tool's own source or documentation."""
    match = re.search(pool[manager_id].version_regexes[0], output)
    assert match is not None
    assert match.group("version") == expected


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


@pytest.mark.parametrize(
    ("operation", "expected"),
    (
        (Operations.install, True),
        (Operations.installed, False),
        (Operations.outdated, False),
        (Operations.search, False),
        (Operations.remove, False),
        (Operations.sync, False),
        (Operations.cleanup, False),
        # The declared upgrade_one command is not enough: single-package upgrade
        # also needs an `installed` listing to resolve which manager owns the
        # package, and SteamCMD cannot provide one. Same verdict as the former
        # Python class.
        (Operations.upgrade, False),
        (Operations.upgrade_all, False),
    ),
)
def test_steamcmd_capabilities(operation, expected):
    """SteamCMD exposes no inventory: only install and per-title upgrade exist,
    both mapping to the same idempotent ``+app_update`` command."""
    assert implements(pool["steamcmd"], operation) is expected


def _parsing_sample_params():
    """One param per query-operation sample shipped in the definition files."""
    params = []
    for data in BUNDLED_FILE_DATA.values():
        manager_id = next(iter(data["mpm"]["managers"]))
        samples = data.get("samples", {})
        for operation in ("installed", "outdated", "search"):
            op_samples = samples.get(operation, ())
            for index, sample in enumerate(op_samples):
                expected = [
                    (package["id"], package.get("version"))
                    for package in sample["packages"]
                ]
                param_id = f"{manager_id}-{operation}"
                if len(op_samples) > 1:
                    param_id += f"-{index}"
                params.append(
                    pytest.param(
                        manager_id, operation, sample["output"], expected, id=param_id
                    ),
                )
    return params


@pytest.mark.parametrize(
    ("manager_id", "operation", "output", "expected"),
    _parsing_sample_params(),
)
def test_bundled_parsing(manager_id, operation, output, expected):
    """Lock each bundled definition's parsers to the output samples shipped in its
    TOML file, derived from the upstream tools' own source code or documentation.

    Versions are compared as raw captured strings (omitted from the sample when
    the regex captures no version group). ``which`` is stubbed so operations
    declaring a sibling ``cli`` resolve without the real binary installed.
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
