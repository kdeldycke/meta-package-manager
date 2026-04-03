---
name: repomatic-deps
description: Generate dependency graphs, audit pyproject.toml declarations against version policy, and explore unused dependency APIs that could simplify code.
model: opus
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob, Agent
argument-hint: '[graph [--level N]|review [all|runtime|dev|policy]|explore [<package>]]'
---

## Context

!`[ -f uv.lock ] && echo "uv.lock exists" || echo "No uv.lock found"`
!`[ -f pyproject.toml ] && head -5 pyproject.toml || echo "No pyproject.toml found"`
!`grep -c '".*>=\|".*~=\|".*<\|".*==' pyproject.toml 2>/dev/null || echo "0"`
!`[ -f repomatic/__init__.py ] && echo "CANONICAL_REPO" || echo "DOWNSTREAM"`

## Instructions

You help users understand and maintain their project's dependencies. This skill has three modes: **graph** (visualize the resolved dependency tree), **review** (audit `pyproject.toml` declarations against version policy), and **explore** (find unused dependency APIs that could simplify existing code).

### Determine invocation method

- If the context above shows `CANONICAL_REPO`, use `uv run repomatic`.
- Otherwise, use `uvx -- repomatic`.

### Mode selection

- No arguments: Run both `graph` and `review all`.
- `graph`: Generate and analyze the dependency graph only.
- `review [all|runtime|dev|policy]`: Audit `pyproject.toml` declarations only.
- `explore [<package>]`: Search for unused dependency APIs that could simplify existing code.
- If `$ARGUMENTS` starts with `--level` or a number, treat it as `graph` mode with those arguments.

---

## Graph mode

### Mechanical layer

The `autofix.yaml` workflow's `update-deps-graph` job already regenerates the dependency graph on every push to `main`. This mode is useful for **interactive analysis** — understanding the graph, spotting concerns, or generating it before pushing.

### Argument handling

- Pass remaining arguments through to `<cmd> update-deps-graph`.
- If no extra arguments, run `<cmd> update-deps-graph` with no arguments.

### After running

- Display the Mermaid output.
- Analyze the graph: count total dependencies, flag deep dependency chains, identify packages with high fan-in (many dependents) or fan-out (many dependencies).
- Highlight any notable patterns or potential concerns (e.g., single points of failure, overly deep transitive chains).

---

## Review mode

This is purely analytical work with no mechanical equivalent in CI.

### Scope selection

- `all` (default when no sub-argument): Run all checks below.
- `runtime`: Review `[project].dependencies` only.
- `dev`: Review `[dependency-groups]` and `[project.optional-dependencies]` only.
- `policy`: Print the policy summary without auditing.

### Version specifier policy

These conventions are derived from the `pyproject.toml` files across all `kdeldycke/*` repositories.

#### Runtime dependencies (`[project].dependencies`)

1. **Use `>=` (not `~=` or `==`).** Relaxed lower bounds give packagers freedom to release security hotfixes without waiting for an upstream bump. Upper bounds are forbidden per <https://iscinumpy.dev/post/bound-version-constraints/>.
2. **Every version bound needs a comment tying the floor to a concrete code dependency.** The comment goes on the line above the dependency and states which feature, method, or API from that version the project actually uses. Prefer referencing the call site or module that depends on it:
   ```toml
   # wcmatch 10.0 changed globbing semantics; our sync_gitignore() relies on
   # the new symlink-aware matching behavior.
   "wcmatch>=10",
   ```
   A good floor comment answers: "if someone installed an older version, what would break and where?" If you cannot point to a concrete usage, the floor may be unnecessarily high.
   **Security fixes are also a valid floor bump reason.** A CVE or advisory in an older version justifies raising the floor even when the API is unchanged. The comment should cite the CVE or advisory:
   ```toml
   # requests 2.32.0 fixes CVE-2024-35195 (session credential leak on redirects).
   "requests>=2.32",
   ```
3. **Python version support is not a valid reason to bump a floor.** The dependency resolver already picks the right version via `requires-python` metadata. If `boltons>=20` works and boltons 25 merely adds Python 3.13 support, keep `>=20` — the resolver handles it. **Exception:** when a dependency *drops* a Python version your project still supports (or your project drops one, aligning minimum `requires-python`), that alignment is a valid floor bump reason. The comment should state the version range alignment, not the Python support:
   ```toml
   # boltons 25.0.0 dropped Python 3.9, matching our requires-python >= 3.10.
   "boltons>=25",
   ```
4. **Use conditional markers for Python-version-gated deps.** Example: `"tomli>=2; python_version<'3.11'"`. When a dep has a version marker, the floor rationale must make sense for the Python versions where the dep is actually installed — not for versions excluded by the marker.
5. **Alphabetical order** within the list.

#### Development dependencies (`[dependency-groups]`)

06. **Prefer `[dependency-groups]`** (uv standard) over `[project.optional-dependencies]` for test, typing, and docs groups.
07. **`>=` is preferred for dev deps too**, but `~=` is acceptable when stricter pinning reduces CI randomness. If a package also appears in runtime deps, the dev entry must use the same specifier style. The relaxation is about specifier *style* (`~=` allowed), not about floor *accuracy* — dev dep floors still need to be grounded in actual API or compatibility requirements, not adoption timestamps.
08. **Standard group names:** `test`, `typing`, `docs` (lowercase, alphabetical).
09. **Type stubs** go in the `typing` group with stub-specific versions: `"types-boltons>=25.0.0.20250822"`.
10. **Alphabetical order** within each group.

#### General rules

11. **No upper bounds** (`<`, `<=`, `!=`, `~=` that implies an upper bound). The only exception is conditional markers like `python_version<'3.11'`.
12. **Extras syntax** is fine: `"coverage[toml]>=7.11"`.
13. **One dependency per line** for readable diffs. Short groups that fit on one line are acceptable — the `format-json` workflow normalizes layout automatically.

### Audit procedure

Read the full `pyproject.toml`. For each dependency entry, check:

| Check                     | What to flag                                                                                                                                                    |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Specifier style           | `~=`, `==`, or upper bounds on runtime deps                                                                                                                     |
| Missing comment           | No comment above the entry explaining the version floor                                                                                                         |
| Weak comment              | Comment cites Python version support instead of a concrete code dependency. Flag unless it documents a `requires-python` alignment or a Python version drop     |
| Stale comment             | Comment references a reason that no longer applies (e.g., the cited method was replaced, or the Python version was dropped from the support matrix)             |
| Inflated floor            | Floor higher than the oldest version providing the APIs actually used (see [floor verification](#floor-verification) below)                                     |
| Marker/rationale mismatch | Floor rationale contradicts the conditional marker (e.g., "Python 3.14 wheels" on a dep gated by `python_version<'3.11'` — that dep is never installed on 3.14) |
| Ordering                  | Dependencies not in alphabetical order                                                                                                                          |
| Group placement           | Type stubs outside `typing` group, test deps outside `test` group                                                                                               |
| Section style             | `[project.optional-dependencies]` used where `[dependency-groups]` would be appropriate                                                                         |
| Bare dependency           | No version specifier at all (e.g., `"requests"`)                                                                                                                |
| Conditional markers       | Missing Python version marker for backport packages                                                                                                             |
| Stale cooldown exceptions | `exclude-newer-package` entries in `[tool.uv]` for packages that no longer need them (see below)                                                                |

### Floor verification

Comments and changelogs can lie; the codebase is the source of truth. For each dependency with a weak or suspicious comment, verify the floor against actual usage:

1. **Grep for imports.** Search the source tree for all imports from the package. List the specific APIs used (functions, classes, constants).
2. **Determine the oldest version providing those APIs.** Check when the API was introduced — changelogs, release notes, or `pip index versions <pkg>` to see what exists on PyPI.
3. **Lower the floor** when it exceeds the oldest compatible version. Prefer conservative minimums (e.g., the major version that introduced the API) over aggressive ones. Update both the version specifier and the comment.
4. **Run `uv lock`** after any floor change to verify the lock still resolves.

#### Special cases

- **Backport packages** (e.g., `backports-strenum`, `tomli`, `exceptiongroup`) exist solely to provide a stdlib class to older Python versions. Their entire API is the backported class itself, available in all versions. The floor is typically `>=1` (or the first release) unless a specific bug fix is needed for the Python versions where the dep is actually installed.
- **Conditional deps with stale bug-fix floors.** A dep gated by `python_version<'3.11'` that has a floor set for a bug affecting Python \<3.8.6 — if the project's `requires-python` is `>=3.10`, that bug is irrelevant and the floor can be lowered.
- **pytest plugins** with no special API beyond auto-registration (e.g., `pytest-randomly`, `pytest-github-actions-annotate-failures`) have low effective floors — their basic functionality has been stable across major versions. Set the floor at the major version introducing the current plugin interface, not at the latest release.

#### Floor bumps to adopt new APIs

A floor bump is justified when a newer version of an existing dependency provides an API that **replaces hand-rolled code** in the project. This is the flip side of floor verification: instead of checking whether the floor is too high, check whether it could be raised to unlock a simplification.

A valid simplification bump must:

1. **Replace existing code**, not add new features. The goal is less code, not more capability.
2. **Be a net reduction** in complexity. Swapping a one-line comprehension for a library call is not a win.
3. **Use the public API** of the dependency. Private/undocumented attributes do not count.
4. **Update the floor comment** to reference the new API and the code it replaces.

When `explore` mode identifies a candidate, the review output should include it as an **Info**-level suggestion with the current code, the replacement, and the version that introduced the API.

#### Red flag patterns in comments

These comment patterns typically signal a floor set at adoption or auto-bump time, not at an API boundary:

- "First version we used" / "first version when we last changed the requirement" — the floor is an artifact of when the dep was added or last bumped by Renovate/Dependabot, not a deliberate API minimum.
- "First version to support Python 3.X" — unless it documents a `requires-python` drop alignment or a concrete build failure (e.g., missing wheels that cause install failures on that Python version), this is not a valid floor reason.
- **The `~= → >=` conversion pipeline.** A common inflation path: (a) dep added as `~=X.Y` (latest at time), (b) Renovate bumps to `~=X.Z`, (c) a bulk "relax requirements" commit converts all `~=` to `>=`. Each step inflates the floor without API validation. Check `git log` for this pattern when a floor looks suspiciously high.

### `exclude-newer-package` cooldown audit

The `[tool.uv]` section may contain `exclude-newer-package` entries that exempt specific packages from the global `exclude-newer` cooldown window (e.g., `exclude-newer-package = { "repomatic" = "0 day" }`). These exceptions exist for a reason (typically: the package is developed in-repo or needs immediate updates), but they accumulate over time and may outlive their purpose.

For each `exclude-newer-package` entry, check:

1. **Is the package still a dependency?** If it was removed from `[project].dependencies` and all `[dependency-groups]`, the exception is dead weight.
2. **Is the exception still justified?** A `"0 day"` override for an in-repo package makes sense. A `"0 day"` override for an external package that was temporarily pinned during a migration may no longer be needed.
3. **Does the comment explain the reason?** Like version floors, cooldown exceptions should have a comment explaining why the package is exempted.

Flag stale or unjustified entries as warnings.

### Cross-repo reference

When the context shows `DOWNSTREAM`, also compare the dependency list against the canonical `repomatic` `pyproject.toml` (fetch with `gh api repos/kdeldycke/repomatic/contents/pyproject.toml --jq '.content' | base64 -d`) to identify:

- Shared dependencies where the downstream floor is lower than upstream (may be missing a needed bump).
- Shared dev dependencies where upstream has moved to a newer group structure.

### Output format

Produce:

1. **Policy compliance summary**: A table with one row per dependency: name, specifier, has comment (yes/no), issues found.
2. **Grouped findings** by severity:
   - **Errors**: Wrong specifier style, missing version, upper bounds.
   - **Warnings**: Missing or stale comments, ordering issues, inflated floors, marker/rationale mismatches.
   - **Info**: Suggestions for floor adjustments based on API verification or cross-repo data.
3. **Suggested fixes**: For each error/warning, show the current line and the recommended replacement. For inflated floors, include the verified API minimum and a rewritten comment.

---

## Explore mode

Search for unused APIs in existing dependencies that could replace hand-rolled code. This is purely analytical: it produces recommendations, not changes.

### Scope selection

- No argument: explore all runtime dependencies.
- `<package>`: explore a single dependency (e.g., `explore boltons`).

### Procedure

For each dependency in scope:

1. **Catalog current usage.** Grep the source tree (not tests) for all imports from the package. List every function, class, and constant actually used, with file locations.

2. **Catalog available APIs.** Using your knowledge of the library (and its docs if needed via `WebFetch`), list the public APIs the project does NOT currently use. Focus on utilities, helpers, and data structures: the kind of thing that replaces 3-10 lines of hand-rolled code.

3. **Search for replacement candidates.** For each unused API, grep the source tree for code patterns it could replace. Be specific about what constitutes a match:

   | Library API                                      | Pattern to search for                                                                                             |
   | ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
   | `boltons.iterutils.partition`                    | Two complementary list comprehensions filtering the same iterable                                                 |
   | `boltons.iterutils.first`                        | `next(iter(...), None)` or `seq[0] if seq else None` on non-generator sequences                                   |
   | `boltons.iterutils.bucketize`                    | Loops building a `dict[K, list[V]]` via `setdefault(k, []).append(v)`                                             |
   | `boltons.iterutils.chunked`                      | Manual slice loops (`for i in range(0, len(seq), n)`)                                                             |
   | `boltons.dictutils.subdict`                      | `{k: v for k, v in d.items() if k in keys}` or `if k not in exclude`                                              |
   | `boltons.fileutils.atomic_save`                  | `Path.write_text()` on files where partial writes would corrupt state                                             |
   | `packaging.specifiers.SpecifierSet`              | Manual version-range checks with `<`/`>`/`in` loops over `Version` objects                                        |
   | `packaging.requirements.Requirement`             | Regex parsing of PEP 508 requirement strings                                                                      |
   | `packaging.markers.Marker`                       | Regex parsing of PEP 508 environment markers (only when the public API exposes the needed structure)              |
   | `wcmatch.fnmatch` / `wcmatch.pathlib`            | stdlib `fnmatch` or `pathlib.Path.glob()` that would benefit from brace expansion, negation, or extended patterns |
   | `pyproject_metadata.StandardMetadata` properties | Manual `toml_dict.get("project", {}).get("field")` when a `StandardMetadata` instance is already available        |

4. **Verify each candidate.** Read the actual code at each location. Discard false positives:

   - A one-line comprehension is not worth replacing with a function call.
   - `next()` on a generator is idiomatic Python; `first()` adds a dependency import for no clarity gain.
   - `Path.write_text()` is fine when the file is immediately committed by CI or when partial writes are harmless.
   - `TableFormat.GITHUB` hardcoded in functions that generate markdown for PR bodies is correct: the `--table-format` CLI option is for terminal output only.
   - Stdlib `glob.glob()` with `recursive=True` is fine when no extended glob features (brace expansion, negation) are needed.
   - `packaging.markers.Marker` only helps if the public API exposes the structure you need. Its primary public method is `evaluate()`, not AST inspection.

5. **Check version requirements.** For each surviving candidate, determine which version of the dependency introduced the API. Compare against the current floor. If a bump is needed, it must satisfy the [floor bump criteria](#floor-bumps-to-adopt-new-apis).

### Output format

Produce a table of findings:

| Dependency         | Unused API                  | Location           | Current code (summary)                    | Replacement                   | Version needed             | Verdict                                    |
| ------------------ | --------------------------- | ------------------ | ----------------------------------------- | ----------------------------- | -------------------------- | ------------------------------------------ |
| boltons            | `subdict`                   | `metadata.py:2232` | dict comprehension filtering by key set   | `subdict(metadata, keys)`     | any (available since 16.x) | Skip: one-liner, no clarity gain           |
| pyproject-metadata | `StandardMetadata.keywords` | `cli.py:2733`      | `toml.get("project", {}).get("keywords")` | `metadata.pyproject.keywords` | current floor sufficient   | **Adopt**: parsed object already available |

Only recommend changes where the replacement is a genuine simplification: fewer lines, better error handling, or elimination of a manual reimplementation.

### Filtering noise

Most dependencies are already well-used. Expect the majority of candidates to be discarded during verification. A run that produces zero recommendations is a valid outcome: it means the codebase is already leveraging its dependencies effectively.

Common false-positive patterns to reject early:

- **Swapping idioms for library calls.** `next(iter(x))` → `first(x)` adds an import for no clarity gain.
- **Adding atomicity where none is needed.** `atomic_save` on files that are immediately git-committed or overwritten by CI.
- **Unifying glob implementations.** stdlib `glob` and `wcmatch.glob` serve different purposes; not every `glob.glob()` call needs extended syntax.
- **Replacing regex with structured parsing** when the regex is simpler. `re.match(r"extra\s*==\s*'([^']+)'", marker)` is more direct than navigating a `Marker` object's internal structure.

---

### Next steps

Suggest the user run:

- `/repomatic-deps review all` to audit version floors and specifier policy.
- `/repomatic-lint` to check repository metadata for issues.
- `/repomatic-audit` for a comprehensive alignment check beyond dependencies.
