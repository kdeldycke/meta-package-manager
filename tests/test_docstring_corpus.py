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

Scope is single-source ``installed`` and ``--version`` blocks. ``outdated``
routinely cross-references two commands (``list`` + ``latest``), which a single
stubbed CLI call cannot feed, and JSON blocks carrying backslash escapes need
raw-source harvesting rather than the escape-processed ``__doc__``; both are left
to a follow-up. See
https://github.com/kdeldycke/meta-package-manager/issues/1023.
"""

from __future__ import annotations

import ast
import inspect
import re
import textwrap
from functools import cache
from pathlib import Path

import pytest

from meta_package_manager.pool import pool
from meta_package_manager.version import parse_version

DIRECTIVE = ".. code-block:: shell-session"
"""reStructuredText directive introducing a captured CLI session."""

ELISION = re.compile(r"\(\.\.\.\)|\.\.\.|…")
"""Marks output a docstring abbreviated: an illustration, not a literal fixture."""

FIXTURE_MEMBERS = ("installed", "version_regexes")
"""Single-source members whose whole output comes from one CLI call."""

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
    "fwupd-installed-0": pytest.mark.skip(
        reason="JSON block carries backslash escapes that `__doc__` processing "
        "corrupts; needs raw-source harvesting. See issue 1023.",
    ),
    "flatpak-installed-0": pytest.mark.xfail(
        strict=True,
        reason="Documented output omits the `--ostree-verbose` columns the "
        "command requests and `_LIST_REGEXP` expects. Doc drift, see issue 1023.",
    ),
    "cpan-installed-0": pytest.mark.xfail(
        strict=True,
        reason="Documented `cpan -l` output parses to zero packages. See "
        "issue 1023.",
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
        if line.strip() == DIRECTIVE:
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


def split_session(block: str) -> str:
    """Return just the command output of a shell-session block.

    ``$`` starts a command and ``>`` continues it (the shell's secondary prompt).
    A command may also continue onto unprefixed lines via a trailing backslash,
    so those are absorbed too. Every remaining line is output.
    """
    output = []
    in_command = False
    for line in block.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("$ ", "> ")) or in_command:
            in_command = stripped.rstrip().endswith("\\")
            continue
        output.append(line)
    return "\n".join(output)


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
                blocks = extract_blocks(ast.get_docstring(child))
                if blocks:
                    members[child.name] = blocks
                prev_target = None
            elif (
                isinstance(child, ast.Expr)
                and isinstance(child.value, ast.Constant)
                and isinstance(child.value.value, str)
                and prev_target
            ):
                blocks = extract_blocks(textwrap.dedent(child.value.value))
                if blocks:
                    members[prev_target] = blocks
                prev_target = None
            elif isinstance(child, ast.Assign) and len(child.targets) == 1:
                target = child.targets[0]
                prev_target = target.id if isinstance(target, ast.Name) else None
            else:
                prev_target = None
    return members


def _fixtures():
    """Yield a ``pytest.param`` per literal, single-source documented block."""
    for manager in pool.values():
        blocks_by_member = _class_blocks(type(manager))
        for member in FIXTURE_MEMBERS:
            for index, block in enumerate(blocks_by_member.get(member, ())):
                output = split_session(block)
                # An elided or output-less block is an illustration, not a fixture.
                if not output.strip() or ELISION.search(output):
                    continue
                param_id = f"{manager.id}-{member}-{index}"
                yield pytest.param(
                    manager,
                    member,
                    output,
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
    # Neutralize every external dependency the parse path might touch, so the
    # stubbed output is the sole input.
    monkeypatch.setattr(manager, "run_cli", lambda *args, **kwargs: output)
    monkeypatch.setattr(manager, "which", lambda cli_name: Path("/usr/bin") / cli_name)
    monkeypatch.setattr(
        manager, "cli_path", Path("/usr/bin") / manager.cli_names[0], raising=False
    )

    if member == "version_regexes":
        version = _parse_version_output(manager.version_regexes, output)
        assert version, "version_regexes matched nothing in the documented output"
        assert parse_version(version), f"{version!r} is not a parseable version"
        return

    packages = list(manager.installed)
    assert packages, "documented output parsed to zero packages"
    for package in packages:
        assert package.id, "parsed a package with an empty id"
        if package.installed_version is not None:
            assert parse_version(str(package.installed_version))
