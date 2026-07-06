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

"""Replay documented CLI output back through each manager's own parser.

Every query method documents a sample invocation and its output in a
``.. code-block:: shell-session`` block sitting right next to the regex (or JSON
parser) that consumes it. This module harvests those blocks straight from the
source and feeds each one back through the parser it illustrates, asserting the
documented example still yields well-formed packages.

It is a *Tier-1* guard: it proves the documented output **still parses** (which
catches a regex that silently stops matching after an upstream format change, or
a docstring that has drifted from the code beside it), not that every field is
captured correctly. It authors no fixtures of its own: the corpus is the
docstrings.

It covers ``installed``, ``outdated`` and ``--version`` blocks. ``installed`` and
``--version`` are single-source (one CLI call), fed straight through.
``outdated`` may cross-reference two commands (``list`` + ``latest``), so its
calls are routed to the right block by a command-dispatching stub. Blocks are
harvested from raw source, not the escape-processed ``__doc__``: ``cleandoc``
expands tabs and the compiler collapses ``\\``, either of which would rewrite a
tab-delimited or escaped-JSON fixture into something the parser rejects. A few
methods that neither of these mechanisms can reach are listed, with reasons, in
:data:`KNOWN_EXCEPTIONS`. See
https://github.com/kdeldycke/meta-package-manager/issues/1023.
"""

from __future__ import annotations

import ast
import inspect
import re
import shlex
import textwrap
from contextlib import suppress
from functools import cache
from pathlib import Path

import pytest

from meta_package_manager.pool import pool
from meta_package_manager.version import parse_version

DIRECTIVES = (
    ".. code-block:: shell-session",
    ".. code-block:: pwsh-session",
)
"""reStructuredText directives introducing a captured CLI session.

PowerShell sessions use ``> `` as their prompt, which the dissector already
recognizes, so both flavors share one extraction path.
"""

ELISION = re.compile(r"\(\.\.\.\)|\.\.\.|…")
"""Marks output a docstring abbreviated: an illustration, not a literal fixture."""

# Blocks that are not literal, single-call fixtures. Keyed by the parametrize id
# ``{manager_id}-{member}-{block_index}``. ``skip`` marks a block that can never
# round-trip here (an illustration, or a harness limitation); ``xfail`` marks a
# genuine documentation drift we still intend to fix, so repairing the docstring
# flips the test to XPASS and flags the stale marker for removal.
KNOWN_EXCEPTIONS = {
    "yarn-installed-1": pytest.mark.skip(
        reason="Second block illustrates the human-readable `yarn global list`, "
        "not the `--json` stream installed() parses.",
    ),
    "flatpak-outdated": pytest.mark.skip(
        reason="`remote-ls --ostree-verbose` appends branch/arch columns whose "
        "exact tab layout is unverified without a live capture.",
    ),
    "ports-upgrade_one_cli": pytest.mark.skip(
        reason="upgrade_one_cli resolves the package's port origin through a "
        "live pkg query the stubbed CLI cannot answer.",
    ),
    "scoop-sync": pytest.mark.skip(
        reason="sync's docstring is a narrative before/after transcript: the "
        "`scoop status` blocks illustrate the state around the one `scoop "
        "update` the method actually runs.",
    ),
    "sdkman-outdated": pytest.mark.skip(
        reason="`sdk` is a shell builtin driven via `echo n | sdk upgrade`; "
        "outdated never routes through `run_cli` and the sample is an interactive "
        "prompt.",
    ),
}


def extract_blocks(docstring: str | None) -> list[str]:
    """Return the dedented body of every ``shell-session`` block in a docstring."""
    if not docstring:
        return []
    lines = docstring.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() in DIRECTIVES:
            directive_indent = len(line) - len(line.lstrip())
            i += 1
            body = []
            while i < len(lines):
                candidate = lines[i]
                if candidate.strip() == "":
                    body.append("")
                    i += 1
                    continue
                indent = len(candidate) - len(candidate.lstrip())
                if indent > directive_indent:
                    body.append(candidate)
                    i += 1
                else:
                    break
            blocks.append(textwrap.dedent("\n".join(body)).strip("\n"))
        else:
            i += 1
    return blocks


def _dissect(block: str) -> tuple[list[str], str]:
    """Split a shell-session block into its command tokens and its output.

    ``$`` starts a command and ``>`` continues it (the shell's secondary prompt).
    A command may also continue onto unprefixed lines via a trailing backslash, so
    those are absorbed too. Every remaining line is output.
    """
    tokens, output, in_command = [], [], False
    for line in block.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("$ ", "> ")) or in_command:
            in_command = stripped.rstrip().endswith("\\")
            text = stripped[2:] if stripped.startswith(("$ ", "> ")) else stripped
            tokens.extend(text.rstrip(" \\").split())
        else:
            output.append(line)
    return tokens, "\n".join(output)


def split_session(block: str) -> str:
    """Return just the command output of a shell-session block."""
    return _dissect(block)[1]


def _block_commands(block: str) -> list[list[str]]:
    """Return each documented command of a block as its own token list.

    Unlike :func:`_dissect`, which pools every command of a block, this keeps
    commands separate so a block documenting several invocations (an ``apt``
    cleanup running ``autoremove`` then ``autoclean``) yields one list each.
    Prompt flavor is per-block: ``$``-primary with ``>`` continuations for
    shell sessions, ``>``-primary for PowerShell sessions.
    """
    lines = block.splitlines()
    primary = "$ " if any(line.lstrip().startswith("$ ") for line in lines) else "> "
    commands: list[list[str]] = []
    continuing = False
    for line in lines:
        stripped = line.lstrip()
        starts = stripped.startswith(primary)
        continues = continuing and (
            stripped.startswith("> ") or not stripped.startswith(("$ ", "> "))
        )
        if starts:
            commands.append([])
        elif not continues:
            continuing = False
            continue
        text = stripped[2:] if stripped.startswith(("$ ", "> ")) else stripped
        commands[-1].extend(text.rstrip(" \\").split())
        continuing = stripped.rstrip().endswith("\\")
    return commands


def _string_node(node: ast.AST) -> ast.Constant | None:
    """Return the leading docstring literal node of a class or function, if any."""
    body = getattr(node, "body", None)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[0].value
    return None


def _raw_literal(node: ast.Constant, source: str) -> str | None:
    """Inner text of a string literal read straight from source.

    Reading the raw segment instead of the compiled ``__doc__`` keeps tab
    delimiters and backslash escapes verbatim. ``ast.get_docstring`` routes
    through ``inspect.cleandoc``, which expands tabs, and the compiler collapses
    ``\\\\`` to a single backslash: either silently rewrites a fixture into
    something the manager's own parser then rejects (tab-delimited `cpan`,
    escaped-JSON `fwupd`).
    """
    segment = ast.get_source_segment(source, node)
    if segment is None:
        return None
    start = 0
    while start < len(segment) and segment[start] not in "\"'":
        start += 1  # Skip a string prefix (r, u, ...).
    body = segment[start:]
    for quote in ('"""', "'''", '"', "'"):
        if (
            len(body) >= 2 * len(quote)
            and body.startswith(quote)
            and body.endswith(quote)
        ):
            return body[len(quote) : -len(quote)]
    return None


def _dedent_doc(text: str) -> str:
    """Strip a docstring's common indentation like ``cleandoc``, but keep tabs.

    Only leading spaces count as indentation (source here is space-indented), so
    tabs inside the sample output survive to reach the parser.
    """
    lines = text.split("\n")
    margin = None
    for line in lines[1:]:
        stripped = line.lstrip(" ")
        if stripped:
            indent = len(line) - len(stripped)
            margin = indent if margin is None else min(margin, indent)
    cleaned = [lines[0].lstrip(" ")]
    cleaned += [line[margin:] if margin else line for line in lines[1:]]
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    return "\n".join(cleaned)


@cache
def _class_blocks(cls: type) -> dict[str, list[str]]:
    """Map ``{member: [blocks]}`` harvested from a manager class's own body.

    Covers both method docstrings and attribute docstrings (the string literal
    that follows ``version_regexes = (...)``), the latter being invisible at
    runtime and only reachable through the source AST.
    """
    source = Path(inspect.getsourcefile(cls)).read_text(encoding="UTF-8")  # type: ignore[arg-type]
    tree = ast.parse(source)
    members: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == cls.__name__):
            continue
        prev_target: str | None = None
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                docstring = _string_node(child)
                raw = _raw_literal(docstring, source) if docstring else None
                blocks = extract_blocks(_dedent_doc(raw)) if raw else []
                if blocks:
                    members[child.name] = blocks
                prev_target = None
            elif (
                isinstance(child, ast.Expr)
                and isinstance(child.value, ast.Constant)
                and isinstance(child.value.value, str)
                and prev_target
            ):
                raw = _raw_literal(child.value, source)
                blocks = extract_blocks(_dedent_doc(raw)) if raw else []
                if blocks:
                    members[prev_target] = blocks
                prev_target = None
            elif isinstance(child, ast.Assign) and len(child.targets) == 1:
                target = child.targets[0]
                prev_target = target.id if isinstance(target, ast.Name) else None
            else:
                prev_target = None
    return members


def _is_fixture(output: str) -> bool:
    """A block is a literal fixture only if it carries non-elided sample output."""
    return bool(output.strip()) and not ELISION.search(output)


def _query_commands(cls: type, members: tuple[str, ...]) -> list[tuple[list[str], str]]:
    """Collect ``(command_tokens, output)`` for a class's literal query blocks."""
    pairs = []
    blocks_by_member = _class_blocks(cls)
    for member in members:
        for block in blocks_by_member.get(member, ()):
            tokens, output = _dissect(block)
            if tokens and _is_fixture(output):
                pairs.append((tokens, output))
    return pairs


def _member_output(cls: type, member: str) -> str:
    """First literal block output documented for a member, or empty string."""
    for block in _class_blocks(cls).get(member, ()):
        output = split_session(block)
        if _is_fixture(output):
            return output
    return ""


def _dispatch(command_map: list[tuple[list[str], str]], default: str = ""):
    """A ``run_cli`` stub returning the output whose documented command best
    matches the invocation.

    An ``outdated`` that cross-references two commands (`list` + `latest`) gets
    each call routed to its own block: the match is the documented command
    containing every invocation argument, preferring the most specific (fewest
    extra tokens). A call matching nothing (a whole-script argument, a per-item
    subcommand whose name differs from the example) falls back to ``default``.
    """

    def stub(*args, **kwargs) -> str:
        argv = [str(arg) for arg in args]
        best_output, best_extra = None, None
        for tokens, output in command_map:
            if all(arg in tokens for arg in argv):
                extra = len(tokens) - len(argv)
                if best_extra is None or extra < best_extra:
                    best_output, best_extra = output, extra
        return best_output if best_output is not None else default

    return stub


def _fixtures():
    """Yield a ``pytest.param`` per documented block worth replaying.

    ``installed`` and ``version_regexes`` are single-source: one param per literal
    block, fed straight through. ``outdated`` is one param per manager, driven by a
    command-dispatching stub so its (possibly two-command) path is exercised whole.
    """
    for manager in pool.values():
        # The pool yields untyped instances, and mypy cannot match type[Any]
        # against the cache wrapper's Hashable parameter.
        blocks_by_member = _class_blocks(type(manager))  # type: ignore[arg-type]
        for member in ("installed", "version_regexes"):
            for index, block in enumerate(blocks_by_member.get(member, ())):
                output = split_session(block)
                if not _is_fixture(output):
                    continue
                param_id = f"{manager.id}-{member}-{index}"
                yield pytest.param(
                    manager,
                    member,
                    output,
                    id=param_id,
                    marks=KNOWN_EXCEPTIONS.get(param_id, ()),
                )
        if any(
            _is_fixture(split_session(b)) for b in blocks_by_member.get("outdated", ())
        ):
            param_id = f"{manager.id}-outdated"
            yield pytest.param(
                manager,
                "outdated",
                None,
                id=param_id,
                marks=KNOWN_EXCEPTIONS.get(param_id, ()),
            )


def _parse_version_output(version_regexes: tuple[str, ...], output: str) -> str | None:
    """Extract a version from ``--version`` output, mirroring ``execution.py``."""
    for regex in version_regexes:
        match = re.compile(regex, re.MULTILINE).search(output)
        if match and match.groupdict().get("version"):
            return match["version"]
    return None


@pytest.mark.parametrize("manager, member, output", list(_fixtures()))
def test_documented_output_still_parses(manager, member, output, monkeypatch):
    """The output documented next to a parser must still parse through it."""
    # Neutralize the binary-resolution dependencies the parse path might touch.
    monkeypatch.setattr(manager, "which", lambda cli_name: Path("/usr/bin") / cli_name)
    monkeypatch.setattr(
        manager, "cli_path", Path("/usr/bin") / manager.cli_names[0], raising=False
    )

    if member == "version_regexes":
        version = _parse_version_output(manager.version_regexes, output)
        assert version, "version_regexes matched nothing in the documented output"
        assert parse_version(version), f"{version!r} is not a parseable version"
        return

    if member == "outdated":
        command_map = _query_commands(type(manager), ("installed", "outdated"))
        default = _member_output(type(manager), "outdated")
        monkeypatch.setattr(manager, "run_cli", _dispatch(command_map, default))
        packages = list(manager.outdated)
    else:  # installed.
        monkeypatch.setattr(manager, "run_cli", lambda *args, **kwargs: output)
        packages = list(manager.installed)

    assert packages, "documented output parsed to zero packages"
    for package in packages:
        assert package.id, "parsed a package with an empty id"
        # A genuinely version-less entry (a flatpak app with no version) is still
        # well-formed; only assert on versions the parser actually captured.
        for version in (package.installed_version, package.latest_version):
            if version:
                assert parse_version(str(version))


# --- Mutation commands: the documented invocation must be the constructed one. ---

MUTATION_MEMBERS = (
    "cleanup",
    "install",
    "remove",
    "sync",
    "upgrade_all_cli",
    "upgrade_one_cli",
)
"""Mutation methods whose docstrings document the exact CLI they run."""

PID_SENTINEL = "MPM-DOC-SENTINEL"
"""Stand-in package id; the documented command carries a real example id where
the constructed command carries this."""

BUILD_CLI_KWARGS = frozenset((
    "auto_post_args",
    "auto_pre_args",
    "auto_pre_cmds",
    "override_cli_path",
    "override_post_args",
    "override_pre_args",
    "override_pre_cmds",
))
"""``run_cli`` kwargs forwarded to ``build_cli`` when reconstructing the full
command. ``sudo`` is deliberately not forwarded: escalation depends on platform
and policy, so documented ``sudo`` prefixes are stripped on the other side."""


def _strip_sudo(tokens: list[str]) -> list[str]:
    """Drop a leading ``sudo`` (and its ``-n``) from a command."""
    if tokens and tokens[0] == "sudo":
        return tokens[2:] if tokens[1:2] == ["-n"] else tokens[1:]
    return tokens


def _documented_commands(
    cls: type, member: str, extra_env: dict[str, str] | None
) -> list[list[str]]:
    """Every literal command documented for a mutation member, normalized.

    A command piped into another program or elided with ``...`` is an
    illustration. A leading ``sudo`` (and its ``-n``) is dropped on both the
    documented and constructed sides: escalation depends on platform and
    per-manager policy, not on the command's shape. Tokens restating the
    manager's ``extra_env`` (``BATCH=yes`` for Ports) document environment
    variables, not argv, and are dropped too.
    """
    env_tokens = {f"{key}={value}" for key, value in (extra_env or {}).items()}
    commands = []
    for block in _class_blocks(cls).get(member, ()):
        for raw_tokens in _block_commands(block):
            # Re-tokenize with shell quoting rules so a quoted argument (a
            # PowerShell ``-Command "..."`` payload) stays one token, matching
            # the constructed argv. Unbalanced quotes mean the command is an
            # illustration, like a pipe or an elision.
            try:
                tokens = shlex.split(" ".join(raw_tokens))
            except ValueError:
                continue
            if (
                not tokens
                or "|" in tokens
                or "&&" in tokens
                or any(ELISION.search(t) for t in tokens)
            ):
                continue
            tokens = [token for token in tokens if token not in env_tokens]
            # A leading VAR=VALUE is a shell environment prefix, not argv
            # (``IGNORE_OSVERSION=yes pkg update``).
            while tokens and re.match(r"[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
                tokens.pop(0)
            commands.append(_strip_sudo(tokens))
    return commands


def _normalize_constructed(command: tuple, cli_names: tuple[str, ...]) -> list[str]:
    """Shape a constructed command like its documented counterpart.

    Drops the ``sudo -n`` escalation prefix, unwraps the ``bash -c "source ...
    && <command>"`` indirection used for shell-function managers (sdkman), and
    reduces the absolute binary path to its basename.
    """
    tokens = _strip_sudo([str(token) for token in command])
    if tokens[:2] == ["bash", "-c"] and len(tokens) == 3 and " && " in tokens[2]:
        tokens = shlex.split(tokens[2].rsplit(" && ", 1)[1])
    if tokens:
        tokens[0] = Path(tokens[0]).name
    return tokens


def _matches(
    documented: list[str], constructed: list[str], cli_names: tuple[str, ...]
) -> bool:
    """Positional token compare, tolerating the sentinel and binary aliases.

    Wherever the constructed command carries the sentinel, the documented one
    may carry any non-flag token (the example package id, possibly with a
    pinned version). The leading binary may be documented under any of the
    manager's CLI names (``python`` for a ``python3`` binary).
    """
    if len(documented) != len(constructed):
        return False
    for position, (doc_token, built_token) in enumerate(zip(documented, constructed)):
        if PID_SENTINEL in built_token:
            if doc_token.startswith("-"):
                return False
        elif doc_token != built_token and not (
            position == 0 and doc_token in cli_names
        ):
            return False
    return True


def _mutation_fixtures():
    """Yield one ``pytest.param`` per manager mutation member with literal
    documented commands."""
    for manager in pool.values():
        for member in MUTATION_MEMBERS:
            documented = _documented_commands(
                type(manager), member, getattr(manager, "extra_env", None)
            )
            if documented:
                param_id = f"{manager.id}-{member}"
                yield pytest.param(
                    manager,
                    member,
                    documented,
                    id=param_id,
                    marks=KNOWN_EXCEPTIONS.get(param_id, ()),
                )


@pytest.mark.parametrize("manager, member, documented", list(_mutation_fixtures()))
def test_documented_command_matches_construction(
    manager, member, documented, monkeypatch
):
    """The command a mutation docstring shows must be the one the method builds."""
    monkeypatch.setattr(manager, "which", lambda cli_name: Path("/usr/bin") / cli_name)
    monkeypatch.setattr(
        manager, "cli_path", Path("/usr/bin") / manager.cli_names[0], raising=False
    )

    constructed = []

    def record_run_cli(*args, **kwargs) -> str:
        build_kwargs = {k: v for k, v in kwargs.items() if k in BUILD_CLI_KWARGS}
        constructed.append(manager.build_cli(*args, **build_kwargs))
        return ""

    def record_run(*args, **kwargs) -> str:
        # ``run`` takes the full, already-built command as a nested structure
        # (emerge's cleanup calls ``self.upgrade()``, which executes
        # ``upgrade_all_cli()`` through ``run``): flatten it like ``run`` does.
        def flatten(items):
            for item in items:
                if isinstance(item, (list, tuple)):
                    yield from flatten(item)
                elif item is not None:
                    yield item

        command = tuple(flatten(args))
        if command:
            constructed.append(command)
        return ""

    monkeypatch.setattr(manager, "run_cli", record_run_cli)
    monkeypatch.setattr(manager, "run", record_run)
    # A method may consult the inventory first (sdkman's remove looks up the
    # installed version to pass to ``uninstall``): feed it one sentinel package.
    monkeypatch.setattr(
        type(manager),
        "installed",
        property(
            lambda self: iter([
                self.package(id=PID_SENTINEL, installed_version=PID_SENTINEL)
            ])
        ),
    )

    if member == "install":
        manager.install(PID_SENTINEL)
        # A second, version-pinned invocation covers docstrings whose example
        # pins a version (``asdf install nodejs 20.10.0``). Managers without
        # version support may balk: the unpinned record is enough for them.
        with suppress(Exception):
            manager.install(PID_SENTINEL, version=PID_SENTINEL)
    elif member == "remove":
        manager.remove(PID_SENTINEL)
    elif member in ("sync", "cleanup"):
        getattr(manager, member)()
    elif member == "upgrade_all_cli":
        constructed.append(manager.upgrade_all_cli())
    else:  # upgrade_one_cli.
        constructed.append(manager.upgrade_one_cli(PID_SENTINEL))
        # Same version-pinned second pass as ``install`` above.
        with suppress(Exception):
            constructed.append(
                manager.upgrade_one_cli(PID_SENTINEL, version=PID_SENTINEL)
            )

    normalized = [
        _normalize_constructed(command, manager.cli_names)
        for command in constructed
        if command
    ]
    for doc_command in documented:
        assert any(
            _matches(doc_command, built, manager.cli_names) for built in normalized
        ), (
            f"documented command {doc_command} is not constructed by {member}(); "
            f"constructed: {normalized}"
        )
