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

"""Harvest the CLI-session samples documented in manager source docstrings.

Every query method (and the `version_regexes` attribute) documents a sample
invocation and its output in a MyST ` ```{code-block} shell-session ` fence
sitting right next to the regex (or JSON parser) that consumes it. This module
reads those blocks straight from the source and exposes them, with a shared
notion of which ones are literal, replayable fixtures.

It has two consumers:

- {mod}`tests.test_docstring_corpus` replays each literal block back through the
  parser it illustrates, asserting the documented example still yields
  well-formed packages.
- `docs/docs_update.py` renders the literal blocks as the *reference traces*
  of a class-based manager's documentation page, the config-defined twin of the
  `[samples]` fixtures shipped alongside {abbr}`TOML`-defined managers.

Blocks are harvested from **raw source**, not the escape-processed `__doc__`:
{func}`inspect.cleandoc` expands tabs and the compiler collapses `\\\\`, either
of which would rewrite a tab-delimited or escaped-{abbr}`JSON` fixture into
something the parser rejects. Everything here reads static source through
{mod}`ast`/{mod}`inspect`, so it is host-independent: safe to call at
documentation build time on any machine.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from functools import cache
from pathlib import Path

FENCE_OPENERS = (
    "```{code-block} shell-session",
    "```{code-block} pwsh-session",
)
"""MyST fence openers introducing a captured CLI session.

PowerShell sessions use `> ` as their prompt, which the dissector already
recognizes, so both flavors share one extraction path.

```{important}
These two openers are the *fixture* fences: every `installed` /
`outdated` / `orphans` / `version_regexes` block written under one is a
complete sample that must parse (the corpus round-trip enforces it) and is
rendered as a reference trace. An illustration that is not a literal fixture
(a human-readable variant, an interactive prompt, a narrative before/after
transcript) uses a non-harvested fence instead, ` ```{code-block} console `,
so it stays out of the corpus and the traces while still rendering in the
API docs.
```
"""


def extract_blocks(docstring: str | None) -> list[str]:
    """Return the dedented body of every `shell-session` fence in a docstring.

    A fence body runs from the opener to the first closing ` ``` ` line, and
    shares the fence's indentation. The blank line the MyST syntax puts between
    a `{code-block}` opener and its content is stripped along with the common
    indentation.
    """
    if not docstring:
        return []
    lines = docstring.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        if lines[i].strip() in FENCE_OPENERS:
            i += 1
            body = []
            while i < len(lines) and lines[i].strip() != "```":
                body.append(lines[i])
                i += 1
            blocks.append(textwrap.dedent("\n".join(body)).strip("\n"))
        i += 1
    return blocks


def dissect(block: str) -> tuple[list[str], str]:
    """Split a shell-session block into its command tokens and its output.

    `$` starts a command and `>` continues it (the shell's secondary prompt).
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
    return dissect(block)[1]


def block_commands(block: str) -> list[list[str]]:
    """Return each documented command of a block as its own token list.

    Unlike {func}`dissect`, which pools every command of a block, this keeps
    commands separate so a block documenting several invocations (an `apt`
    cleanup running `autoremove` then `autoclean`) yields one list each.
    Prompt flavor is per-block: `$`-primary with `>` continuations for
    shell sessions, `>`-primary for PowerShell sessions.
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


def block_language(block: str) -> str:
    """Return the fenced-code language matching a block's prompt flavor.

    A shell session opens on a `$` prompt, a PowerShell session on `>`. The
    documented reference traces are re-fenced with the flavor they were captured
    under so their prompts keep highlighting correctly.
    """
    for line in block.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("$ "):
            return "shell-session"
        if stripped.startswith("> "):
            return "pwsh-session"
    return "shell-session"


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

    Reading the raw segment instead of the compiled `__doc__` keeps tab
    delimiters and backslash escapes verbatim. `ast.get_docstring` routes
    through `inspect.cleandoc`, which expands tabs, and the compiler collapses
    `\\\\` to a single backslash: either silently rewrites a fixture into
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
    """Strip a docstring's common indentation like `cleandoc`, but keep tabs.

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


def _text(node: ast.Constant, source: str, compiled: bool) -> str:
    """Dedented docstring text, in the form the caller needs.

    `compiled` picks the compiled value `\\\\` collapses to `\\`, escapes
    resolve: the form a reader sees on their terminal. Otherwise the raw source
    segment is kept verbatim (see {func}`_raw_literal`), the form the corpus
    round-trip feeds the parser so a tab-delimited or escaped-{abbr}`JSON`
    fixture reaches it exactly as the CLI emits it.
    """
    if compiled:
        # Callers only pass string docstring constants (see _harvest).
        value = node.value
        assert isinstance(value, str)
        return _dedent_doc(value)
    raw = _raw_literal(node, source)
    return _dedent_doc(raw) if raw else ""


def _harvest(cls: type, compiled: bool) -> dict[str, list[str]]:
    """Walk a manager class body, mapping ``{member: [blocks]}``.

    Covers both method docstrings and attribute docstrings (the string literal
    that follows `version_regexes = (...)`), the latter being invisible at
    runtime and only reachable through the source AST. A config-defined manager
    (built by the factory, not a class body) has no source file to read and
    yields an empty mapping. `compiled` is forwarded to {func}`_text`.
    """
    source_file = inspect.getsourcefile(cls)
    if not source_file:
        return {}
    source = Path(source_file).read_text(encoding="UTF-8")
    tree = ast.parse(source)
    members: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == cls.__name__):
            continue
        prev_target: str | None = None
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                docstring = _string_node(child)
                text = _text(docstring, source, compiled) if docstring else ""
                blocks = extract_blocks(text)
                if blocks:
                    members[child.name] = blocks
                prev_target = None
            elif (
                isinstance(child, ast.Expr)
                and isinstance(child.value, ast.Constant)
                and isinstance(child.value.value, str)
                and prev_target
            ):
                blocks = extract_blocks(_text(child.value, source, compiled))
                if blocks:
                    members[prev_target] = blocks
                prev_target = None
            elif isinstance(child, ast.Assign) and len(child.targets) == 1:
                target = child.targets[0]
                prev_target = target.id if isinstance(target, ast.Name) else None
            else:
                prev_target = None
    return members


@cache
def class_blocks(cls: type) -> dict[str, list[str]]:
    """Map ``{member: [blocks]}`` kept in raw source form for the corpus.

    Escapes and tabs survive verbatim so the round-trip feeds each block to the
    parser exactly as the CLI emits it. Rendered documentation wants the
    terminal-facing form instead: see {func}`class_display_blocks`.
    """
    return _harvest(cls, compiled=False)


@cache
def class_display_blocks(cls: type) -> dict[str, list[str]]:
    """Map ``{member: [blocks]}`` in compiled form for rendered documentation.

    The reference-traces generator reads these so a transcript shows single
    backslashes and resolved escapes, matching what a reader would see running
    the command, rather than the doubled source escapes {func}`class_blocks`
    preserves for the parser.
    """
    return _harvest(cls, compiled=True)


def is_fixture(output: str) -> bool:
    """A block is a fixture when it carries sample output to parse.

    A `shell-session` block showing only a command (no output, an empty
    system) illustrates an invocation but has nothing for a parser to consume,
    so it is not a fixture.
    """
    return bool(output.strip())


def literal_blocks(cls: type, members: tuple[str, ...]) -> list[tuple[str, int, str]]:
    """Return `(member, index, block)` for a class's replayable fixture blocks.

    A block qualifies when it carries sample output ({func}`is_fixture`). The
    index is its position within the member's full block list. Blocks come in
    compiled, terminal-facing form ({func}`class_display_blocks`): the escape/tab
    differences from the raw corpus form never touch a directive, so the same
    blocks are selected either way.
    """
    results = []
    blocks_by_member = class_display_blocks(cls)
    for member in members:
        for index, block in enumerate(blocks_by_member.get(member, ())):
            if is_fixture(split_session(block)):
                results.append((member, index, block))
    return results


def version_trace(cls: type) -> str | None:
    """Return the raw `--version` output documented for a class, or `None`.

    The first `version_regexes` block's output, mirroring the version
    `[samples]` fixture a {abbr}`TOML`-defined manager ships.
    """
    blocks = literal_blocks(cls, ("version_regexes",))
    if not blocks:
        return None
    return split_session(blocks[0][2])
