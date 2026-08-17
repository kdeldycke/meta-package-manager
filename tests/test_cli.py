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

from __future__ import annotations

import dataclasses
import inspect
import json
import re
import subprocess
import sys
from collections.abc import Callable, Collection, Iterable, Iterator
from functools import partial
from textwrap import dedent
from types import SimpleNamespace

import pytest
from boltons.iterutils import same
from boltons.strutils import strip_ansi
from click_extra.table import SERIALIZATION_FORMATS, TableFormat

from meta_package_manager import __version__
from meta_package_manager.cli import _debug_rerun_command
from meta_package_manager.package import Package
from meta_package_manager.pool import pool

from .conftest import default_manager_ids

""" Common tests for all CLI basic features and templates for subcommands. """


TEST_CONF_FILE = """\
# Comment

top_level_param = "to_ignore"

[mpm]
verbosity = "DEBUG"
blahblah = 234
manager = ["uv", "npm", "gem"]

[garbage]

[mpm.search]
exact = true
dummy_parameter = 3
"""


def check_manager_selection(
    result,
    selected: Iterable[str] = pool.default_manager_ids,
    reference_set: Collection[str] = pool.default_manager_ids,
    strict_selection_match: bool = True,
    *,
    signals: Callable[[str, str, str], Iterator[bool]],
):
    """Check that user-selected managers are found in CLI's output.

    To establish that `mpm` CLI is properly selecting managers, we search for
    signals in CLI logs, by matching regular expressions against `<stdout>` and
    `<stderr>`. This strategy close the gap of testing internal code testing and
    end user experience.

    `signals` is the per-subcommand strategy answering *"did this manager show
    up?"*, taking `(manager_id, stdout, stderr)` and yielding booleans roughly
    sorted from most specific to more forgiving. Each test module defines its
    own and binds it here once, conventionally as
    ``check_selection = partial(check_manager_selection, signals=...)``, so the
    call sites read as assertions rather than as plumbing.

    `strict_selection_match` check that all selected managers are properly
    reported in CLI output and none are missing.

    ```{caution}

    At this stage of the CLI execution, the order in which the managers are
    reported doesn't matter because:

    - `<stdout>` and `<stderr>` gets mangled
    - [paging is async](https://github.com/kdeldycke/meta-package-manager/issues/528)
    - we may introduce [parallel execution of managers in the future](https://github.com/kdeldycke/meta-package-manager/issues/529)

    This explain the use of `set()` everywhere in this method.
    ```
    """
    found_managers = set()
    skipped_managers = set()

    # Strip colors to simplify checks.
    stdout = strip_ansi(result.stdout)
    stderr = strip_ansi(result.stderr)

    for mid in reference_set:
        signals_eval = signals(mid, stdout, stderr)
        if True in signals_eval:
            found_managers.add(mid)
        else:
            skipped_managers.add(mid)

    # Check consistency of reported findings.
    assert len(found_managers) + len(skipped_managers) == len(reference_set)
    assert found_managers.union(skipped_managers) == set(reference_set)

    # Compare managers reported by the CLI and those expected.
    if strict_selection_match:
        assert found_managers == set(selected)
    # Partial reporting of found manager is allowed in certain cases like install
    # command, which is only picking one manager among the user's selection.
    else:
        assert set(found_managers).issubset(selected)


def assert_no_manager_selected(result) -> None:
    """Assert the run stopped on the `No manager selected.` exit-`2` guard.

    Shared by every subcommand test that deselects all managers (or selects
    only managers lacking the operation) and expects the run to refuse to
    proceed.
    """
    assert result.exit_code == 2
    assert not result.stdout
    assert "critical: No manager selected.\n" in result.stderr


def check_filtered_ids(result, expected_ids: set[str]) -> None:
    """Assert the serialized payload reports exactly `expected_ids`."""
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    package_ids = {pkg["id"] for info in data.values() for pkg in info["packages"]}
    assert package_ids == expected_ids


# CLI behavior shared by all subcommands is exercised once, on a single
# non-destructive subcommand (like `mpm installed` or `mpm managers`): the
# selection logic and code path is the same for all of them, so repeating the
# test per subcommand would only slow the suite down.


def test_executable_module():
    """Try running the CLI as a Python module.

    Use the current Python executable so we don't have to worry about missing
    dependencies.
    """
    process = subprocess.run(
        (sys.executable, "-m", "meta_package_manager", "--version"),
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert process.returncode == 0
    assert not process.stderr
    # click_extra appends `+<git_short_hash>` to `.dev` versions at
    # runtime, so accept the optional local version identifier suffix.
    # Newer versions of click_extra also append a Python version/platform
    # line, so match that optional trailing line too.
    assert re.fullmatch(
        # click-extra 8.0's --color defaults to the tri-state `auto`, which
        # strips ANSI codes for non-interactive output. subprocess.run captures
        # via pipes (non-TTY), so the version screen comes through uncolored.
        rf"mpm, version {re.escape(__version__)}(\+[0-9a-f]+)?\n"
        rf"(Python [^\n]+\n)?",
        process.stdout,
    )


@pytest.mark.parametrize(
    ("argv", "expected"),
    (
        (
            ("mpm", "--apt", "upgrade", "papers"),
            "mpm --verbosity DEBUG --apt upgrade papers",
        ),
        # An explicit verbosity is dropped, not duplicated: Click keeps the last
        # value of a repeated option, which sits after the one we insert.
        (
            ("mpm", "--verbosity", "WARNING", "upgrade", "--all"),
            "mpm --verbosity DEBUG upgrade --all",
        ),
        (("mpm", "--verbosity=INFO", "sync"), "mpm --verbosity DEBUG sync"),
        # Copy-pasteable: an argument needing quotes keeps them.
        (
            ("mpm", "install", "my package"),
            "mpm --verbosity DEBUG install 'my package'",
        ),
    ),
)
def test_debug_rerun_command(monkeypatch, argv, expected):
    """The re-run hint of the error summary reproduces the current invocation."""
    ctx = SimpleNamespace(find_root=lambda: SimpleNamespace(info_name="mpm"))
    monkeypatch.setattr(sys, "argv", list(argv))
    assert _debug_rerun_command(ctx) == expected  # type: ignore[arg-type]


def test_timeout(invoke, slow_fake_pool):
    """Check that timeout is handled gracefully: command exits 0 and logs a warning."""
    result = invoke("--timeout", "1", "outdated")
    assert result.exit_code == 0
    assert result.exception is None
    assert "Timed out after 1s." in result.stderr


@pytest.mark.parametrize(
    ("summary_arg", "active_summary"),
    (("--summary", True), ("--no-summary", False), (None, True)),
)
def test_summary(invoke, fake_pool, summary_arg, active_summary):
    """Test the result on all combinations of optional summary options."""
    result = invoke(summary_arg, "installed")
    assert result.exit_code == 0
    # With --no-summary at the default WARNING verbosity stderr can be empty, so
    # guard the last-line lookup instead of indexing into a possibly-empty list.
    lines = result.stderr.splitlines()
    summary_match = lines and re.match(
        r"\d+ packages total \((\w+: \d+(, )?)+\)\.",
        # Last line of stderr.
        lines[-1],
    )
    assert active_summary is bool(summary_match)


def managers_table_signals(mid: str, stdout: str, stderr: str) -> Iterator[bool]:
    """Signals telling whether `mid` shows up in the `mpm managers` table.

    Lives at module level so both the selection tests below and the dedicated
    `managers` subcommand suite (`tests.test_cli_managers`) share it through
    downward imports, instead of one test module importing the other sideways.
    """
    yield from (
        # Search in manager table.
        bool(
            re.search(
                rf"│\s+{mid}\s+│.+│\s+(✓|✘).+│\s+(✓|✘)",
                stdout,
            ),
        ),
    )


# Selection of the package managers to use, exercised on the `mpm managers`
# subcommand: a safe read-only operation that works on every platform. The
# selection logic and code path is shared by all subcommands, so there is no
# need to repeat these against each one. See the implementation in
# `meta_package_manager.pool.ManagerPool.select_managers()`.

check_managers_table_selection = partial(
    check_manager_selection, signals=managers_table_signals
)
"""Selection assertions reading the `mpm managers` table."""


@pytest.mark.parametrize("selector", ("--manager", "--exclude"))
def test_invalid_manager_selector(invoke, selector):
    result = invoke(selector, "unknown", "managers")
    assert result.exit_code == 2
    assert not result.stdout
    assert "Error: Invalid value for " in result.stderr
    assert selector in result.stderr


def test_default_all_managers(invoke):
    """Test all available managers are selected by default.

    With no selector to answer about, `managers` reports its default
    `detected` view, so the platform defaults whose CLI is missing are left
    out. The wider views are covered in `tests.test_cli_managers`.
    """
    result = invoke("managers")
    assert result.exit_code == 0
    check_managers_table_selection(
        result,
        {mid for mid in pool.default_manager_ids if pool[mid].available},
    )


@default_manager_ids
def test_manager_shortcuts(invoke, manager_id):
    """Test each manager selection shortcut."""
    result = invoke(f"--{manager_id}", "managers")
    assert result.exit_code == 0
    check_managers_table_selection(result, {manager_id})


def test_conf_file_overrides_defaults(invoke, create_config):
    conf_path = create_config("conf.toml", TEST_CONF_FILE)
    result = invoke("--config", str(conf_path), "managers", color=False)
    assert result.exit_code == 0
    check_managers_table_selection(result, ("uv", "npm", "gem"))
    assert "debug: " in result.stderr


def test_conf_file_cli_override(invoke, create_config):
    conf_path = create_config("conf.toml", TEST_CONF_FILE)
    result = invoke(
        "--config",
        str(conf_path),
        "--verbosity",
        "CRITICAL",
        "managers",
        color=False,
    )
    assert result.exit_code == 0
    check_managers_table_selection(result, ("uv", "npm", "gem"))
    assert "error: " not in result.stderr
    assert "warning: " not in result.stderr
    assert "info: " not in result.stderr
    assert "debug: " not in result.stderr


def test_conf_and_parameter_mix_keep_order(invoke, create_config):
    conf_path = create_config(
        "conf.toml",
        dedent("""\
            [mpm]
            npm = true
            flatpak = false
            manager = ["gem"]
            cargo = false
            pipx = true
            """),
    )
    result = invoke(
        "--uv", "--no-pip", "--config", str(conf_path), "managers", color=False
    )
    assert result.exit_code == 0
    check_managers_table_selection(result, ("uv", "npm", "gem", "pipx"))


# How `-m`/`--<id>` (keep) and `-x`/`--no-<id>` (drop) compose and override each
# other for operational subcommands. `installed --dry-run` is the stub: it is
# read-only, fast (the per-manager list invocation is replaced by a printed
# command line), works on every platform, and crucially still honors both keep
# and drop selectors. The `managers` subcommand intentionally ignores drops for
# its diagnostic inventory view, so it cannot stand in for general
# selection-precedence tests anymore.


def reached_manager_signals(mid: str, stdout: str, stderr: str) -> Iterator[bool]:
    """Detect whether `mpm` reached a manager during the invocation.

    Available managers appear in the `N package total (brew: 0, ...)`
    stats line; the manager id is matched by its `<mid>: <count>` slice
    instead of by tailing the stream because at `--verbosity DEBUG` a
    few `Reset <logger> to WARNING` lines trail the stats line.
    Unavailable ones surface as `Skipped: ...` lines tagged with the
    manager ID in their level prefix (`debug:<mid>:`): that message is
    demoted to DEBUG for implicit selection, so test invocations pass
    `--verbosity DEBUG` to keep both signals visible.
    """
    yield from (
        bool(re.search(rf"\b{re.escape(mid)}: \d+", stderr)),
        f":{mid}: Skipped:" in stderr,
        f":{mid}: Does not implement " in stderr,
    )


check_reached_selection = partial(
    check_manager_selection, signals=reached_manager_signals
)
"""Selection assertions reading the per-manager stats and skip lines."""


@pytest.mark.parametrize(
    ("args", "expected"),
    (
        pytest.param(("--manager", "uv"), {"uv"}, id="single_selector"),
        pytest.param(("--uv",), {"uv"}, id="single_flag_selector"),
        pytest.param(("--manager", "uv") * 2, {"uv"}, id="duplicate_selectors"),
        pytest.param(("--uv",) * 2, {"uv"}, id="duplicate_flag_selectors"),
        pytest.param(
            ("--manager", "uv", "--uv"),
            {"uv"},
            id="duplicate_mixed_selectors",
        ),
        pytest.param(
            ("--manager", "uv", "--manager", "gem"),
            {"uv", "gem"},
            id="multiple_selectors",
        ),
        pytest.param(
            ("--manager", "uv", "--gem"),
            {"uv", "gem"},
            id="multiple_mixed_selectors",
        ),
        pytest.param(
            ("--gem", "--uv"),
            {"uv", "gem"},
            id="ordered_selectors",
        ),
        pytest.param(
            ("--gem", "--manager", "uv"),
            {"uv", "gem"},
            id="ordered_mixed_selectors",
        ),
        pytest.param(
            ("--no-uv",),
            set(pool.default_manager_ids) - {"uv"},
            id="single_exclusion",
        ),
        pytest.param(
            ("--no-uv",) * 2,
            set(pool.default_manager_ids) - {"uv"},
            id="duplicate_exclusions",
        ),
        pytest.param(
            ("--no-uv", "--no-gem"),
            set(pool.default_manager_ids) - {"uv", "gem"},
            id="multiple_exclusions",
        ),
        pytest.param(
            ("--uv", "--no-gem"),
            {"uv"},
            id="selector_priority_ordered",
        ),
        pytest.param(
            ("--no-gem", "--uv"),
            {"uv"},
            id="selector_priority_reversed",
        ),
        pytest.param(
            ("--uv", "--no-uv"),
            None,
            id="exclusion_precedence_ordered",
        ),
        pytest.param(
            ("--no-uv", "--uv"),
            None,
            id="exclusion_precedence_reversed",
        ),
    ),
)
def test_selector_precedence(invoke, args, expected):
    result = invoke("--verbosity", "DEBUG", *args, "--dry-run", "installed")
    if expected is None:
        assert result.exit_code == 2
        assert not result.stdout
        # `critical: No manager selected.` is checked anywhere in the
        # stream, not at the end: `--verbosity DEBUG` makes click_extra
        # append a couple of `Reset <logger>` trailing lines. ANSI codes
        # are stripped because color presence depends on the runner.
        assert "critical: No manager selected." in strip_ansi(result.stderr)
    else:
        assert result.exit_code == 0
        check_reached_selection(result, expected)


def check_packages_payload(
    result,
    optional_keys: frozenset[str] = frozenset(),
    reference_set: Collection[str] = pool.default_manager_ids,
) -> None:
    """Validate the serialized ``{manager: {id, name, errors, packages}}`` payload.

    The shared shape check of the package-reporting subcommands (`installed`,
    `outdated`, `search`) in `--table-format json` mode: every manager entry
    carries the standard keys (plus the subcommand's `optional_keys`, like
    `outdated`'s `upgrade_all_cli`), and every package serializes a subset of
    the {class}`~meta_package_manager.package.Package` fields as strings.

    `reference_set` defaults to the platform's real default managers, but a
    caller pinned to `fake_pool` (like `orphans`, with no implementing
    manager on every platform) overrides it to match.
    """
    assert result.exit_code == 0
    data = json.loads(result.stdout)

    assert data
    assert isinstance(data, dict)
    assert set(data).issubset(reference_set)

    for manager_id, info in data.items():
        assert isinstance(manager_id, str)
        assert isinstance(info, dict)

        keys = {"errors", "id", "name", "packages"}
        for key in optional_keys:
            if key in info:
                assert isinstance(info[key], str)
                keys.add(key)
        assert set(info) == keys

        assert isinstance(info["errors"], list)
        if info["errors"]:
            assert same(map(type, info["errors"]), str)
        assert isinstance(info["id"], str)
        assert isinstance(info["name"], str)

        assert info["id"] == manager_id

        assert isinstance(info["packages"], list)
        for pkg in info["packages"]:
            assert isinstance(pkg, dict)

            fields = {f.name for f in dataclasses.fields(Package)}
            assert set(pkg).issubset(fields)

            for f in pkg:
                assert isinstance(pkg[f], str) or pkg[f] is None


class CLITableTests:
    """Test subcommands whose output is a configurable table.

    Any table output is also allowed to be rendered in all serialization formats.
    """

    columns_registry: tuple = ()
    """The subcommand's column registry (a `tables.py` `*_COLUMNS` constant).

    Set by each subclass so the generic `--columns` tests below resolve column
    IDs to their header labels from the same source of truth the CLI uses.
    """

    columns_test_pair: tuple[str, str] = ("manager_id", "package_id")
    """Two column IDs, guaranteed by the subcommand's registry, that the generic
    projection test selects in this order. Overridden by subclasses whose
    registry has no package columns."""

    def test_columns_projection(self, invoke, subcmd, fake_pool):
        """`--columns` restricts and reorders the table, SQL-SELECT-style."""
        first, second = self.columns_test_pair
        labels = {spec.id: spec.label for spec, _ in self.columns_registry}
        result = invoke(subcmd, "--columns", f"{first},{second}", color=False)
        assert result.exit_code == 0
        header = next(line for line in result.stdout.splitlines() if "│" in line)
        # Two columns only, in the selection's order.
        assert header.count("│") == 3
        assert 0 < header.index(labels[first]) < header.index(labels[second])

    def test_columns_unknown_id(self, invoke, subcmd, fake_pool):
        """An unknown column ID fails fast, listing the accepted ones."""
        result = invoke(subcmd, "--columns", "bogus")
        assert result.exit_code == 2
        assert "Unknown value(s): 'bogus'" in result.stderr
        assert self.columns_test_pair[0] in result.stderr

    def test_json_output(self, invoke, subcmd):
        """JSON output is expected to be parseable if read from `<stdout>`.

        Debug level messages are redirected to <stderr> and are not supposed to interfere
        with this behavior.

        The one serialization case kept on the real pool, deliberately: it is
        what proves a live inventory survives serialization, whatever package
        names, versions and encodings the host's managers report. The format
        matrix below runs on the fake pool, that property being a fact about
        the data rather than about each format.
        """
        result = invoke("--table-format", "json", "--verbosity", "DEBUG", subcmd)
        assert result.exit_code == 0
        assert "debug" in result.stderr
        json.loads(result.stdout)
        with pytest.raises(json.decoder.JSONDecodeError):
            json.loads(result.stderr)

    @pytest.mark.parametrize(
        "fmt",
        sorted(
            [f for f in SERIALIZATION_FORMATS if f != TableFormat.JSON],
            key=lambda f: f.value,  # type: ignore[attr-defined]
        ),
        ids=lambda f: f.value,
    )
    def test_serialized_output(self, invoke, subcmd, fake_pool, fmt):
        """All serialization formats produce parseable output on `<stdout>`.

        Debug messages go to `<stderr>` and must not leak into the structured output.
        Formats whose optional dependency is not installed are skipped.

        Runs on the fake pool: the subject is the serializer, not the inventory
        feeding it, and re-querying every installed manager once per format made
        this the most expensive block in the suite (`outdated` alone spent
        sixteen minutes of one Windows runner's time across its seven cases).
        {meth}`test_json_output` keeps the live inventory covered.
        """
        result = invoke("--table-format", fmt, "--verbosity", "DEBUG", subcmd)
        if result.exit_code == 1 and "requires an optional dependency" in str(
            result.exception
        ):
            pytest.skip(f"{fmt.value} extra not installed")
        assert result.exit_code == 0
        assert "debug" in result.stderr


@pytest.mark.parametrize("mode", TableFormat)
def test_all_table_rendering(invoke, fake_pool, mode):
    """Every table format renders an inventory without crashing.

    A module-level test rather than a {class}`CLITableTests` method, because it
    names its own subcommand instead of reading the `subcmd` fixture: inherited,
    it ran the *same* invocation once per subclass, so fifty formats became
    three hundred cases of which two hundred and fifty were byte-identical.

    The fake pool is what makes it an assertion rather than a coincidence. The
    real pool reports whatever the host happens to carry, so on a runner with an
    empty inventory every format rendered an empty table and the test proved
    nothing about formatting; the fake pool guarantees rows to render, on any
    host, at the price of no subprocess at all.
    """
    result = invoke("--table-format", mode, "installed")
    assert result.exit_code == 0


# The per-table resolution of --sort-by (field-to-column mapping, skipped
# absent fields, original order when none is carried) is covered upstream by
# click-extra's column_sort_key() test suite.


class CLIQueryTests:
    """Template for inventory subcommands taking an optional positional `QUERY`.

    Runs against the deterministic `fake_pool` package set. Subclasses keep
    their own `test_query_filter` parametrize — the case data *is* the
    per-command filtering semantics — and delegate each case's assertions to
    {func}`check_filtered_ids`.
    """

    def test_query_highlight(self, invoke, subcmd, fake_pool):
        """The matched substring is wrapped in the theme's green search style."""
        result = invoke("--color", subcmd, "alpha")
        assert result.exit_code == 0
        assert "\x1b[32malpha\x1b[0m" in result.stdout


REAL_POOL_TEMPLATE_TESTS = frozenset({"test_json_output"})
"""Template tests deliberately driving the host's own managers.

One per format family is the whole budget: proving a live inventory survives
serialization is a fact about the *data*, so it needs one serializer rather
than one case per serializer per subcommand. Everything else inherited runs on
`fake_pool`.
"""

TEMPLATE_TEST_METHODS = tuple(
    pytest.param(method, id=f"{template.__name__}.{name}")
    for template in (CLITableTests, CLIQueryTests)
    for name, method in vars(template).items()
    if name.startswith("test_")
)
"""Every test a subcommand inherits by subclassing a template."""

# An empty tuple would make the guards below vacuous rather than failing.
assert len(TEMPLATE_TEST_METHODS) >= 5


@pytest.mark.parametrize("method", TEMPLATE_TEST_METHODS)
def test_template_tests_read_their_subcommand(method):
    """A template test must take `subcmd`, or it is the same test N times.

    A method naming its own subcommand still gets inherited by every subclass,
    which runs the identical invocation once per subclass with nothing to tell
    the copies apart. `test_all_table_rendering` did exactly that: fifty
    formats collected as three hundred cases, two hundred and fifty of them
    byte-identical, each driving the real manager pool. Nothing in the run
    reported it, since duplicate work looks like coverage. A test that names
    its own subcommand belongs at module level, where it is collected once.
    """
    assert "subcmd" in inspect.signature(method).parameters, (
        f"{method.__qualname__} does not read the `subcmd` fixture, so every "
        "subclass would re-run the same invocation: move it to module level."
    )


@pytest.mark.parametrize("method", TEMPLATE_TEST_METHODS)
def test_template_tests_default_to_the_fake_pool(method):
    """A template test must take `fake_pool` unless it is a listed exception.

    Omitting the fixture is how a test silently acquires the host's real
    managers, and a template multiplies that by its subclasses. The exceptions
    are named in {data}`REAL_POOL_TEMPLATE_TESTS` so adding one is a decision
    rather than an oversight.
    """
    if method.__name__ in REAL_POOL_TEMPLATE_TESTS:
        return
    assert "fake_pool" in inspect.signature(method).parameters, (
        f"{method.__qualname__} drives the host's real managers for every "
        "subclass inheriting it: take `fake_pool`, or add it to "
        "REAL_POOL_TEMPLATE_TESTS with the reason it must stay live."
    )
