# CLAUDE.md

Project-specific guidance for working in this repository. The generic coding conventions load from the maintainer's machine configuration and are deliberately not duplicated here: this file carries only what is specific to `mpm`.

## Project overview

Meta Package Manager (`mpm`) is a CLI that wraps multiple package managers (Homebrew, apt, pip, npm, etc.) behind a unified interface. It can list, search, install, upgrade, and remove packages across all supported managers simultaneously, and snapshot the whole inventory to a single file that restores it on another machine.

## Upstream conventions

This repository uses reusable workflows from [`kdeldycke/repomatic`](https://github.com/kdeldycke/repomatic) and follows the conventions established there. The generic conventions used to be projected into this file by repomatic's retired `agent` component; they now live with the maintainer, and this file keeps only the `mpm`-specific half.

**Contributing upstream:** If you spot inefficiencies, improvements, or missing features in the reusable workflows, propose changes via a pull request or issue at [`kdeldycke/repomatic`](https://github.com/kdeldycke/repomatic/issues).

## Stability policy

This project more or less follows [Semantic Versioning](https://semver.org/).

Which boils down to the following these rules of thumb regarding stability:

- **Patch releases**: `0.x.n` → `0.x.(n+1)` upgrades

  Are bug-fix only. These releases must not break anything and keep
  backward-compatibility with `0.x.*` and `0.(x-1).*` series.

- **Minor releases**: `0.n.*` → `0.(n+1).0` upgrades

  Includes any non-bugfix changes. These releases must be backward-compatible
  with any `0.n.*` version but are allowed to drop compatibility with the
  `0.(n-1).*` series and below.

- **Major releases**: `n.*.*` → `(n+1).0.0` upgrades

  Make no promises about backwards-compatibility. Any API change requires a new
  major release.

- **Unmaintained managers**: managers whose `unmaintained` flag is set

  Are exempt from the rules above. A manager is flagged `unmaintained` when its upstream
  project is officially retired **or** we infer it is abandoned: archived on its forge,
  left without a release or commit for years (~3+), formally superseded by a successor,
  or part of a discontinued platform. A superseded-but-still-maintained tool (like a
  compatibility alias its upstream keeps shipping, such as `yum` fronting `dnf`) is
  *not* unmaintained.

  The commitment is to keep the wrapper for as long as that stays cheap: an unmaintained
  manager may still be removed, in part or in full, in any release and without notice,
  once keeping it working becomes too burdensome. Each flag is documented via the
  manager's `unmaintained_message` (a markdown block rendered into the docs), and
  unmaintained managers are hidden from default selection and kept out of the functional
  and integration test matrices to save CI resources. An upstream that is merely slowing
  down does not earn the flag: it carries an informational maintenance note instead. Both
  render on the manager's own page. See the `unmaintained` attribute in
  `meta_package_manager/manager.py` for the full policy.

  Being flagged is a different axis from being *unsupported*: an unmaintained manager is
  still wrapped and usable, whereas the tools in `docs/unsupported.md` were never wrapped
  at all.

## Cooldown on every install

**Every command that resolves a package from a live registry carries a cooldown, except where this section names otherwise.** A cooldown refuses any version published more recently than a fixed window, so a compromised release has to survive that window before it can enter a build. Most malicious releases (stolen publishing credentials, dependency confusion, account takeover) are caught and pulled within days of publication, which is what makes a window of days worth the delay it costs.

`mpm --cooldown` applies the same idea to a different subject, and the two are easy to conflate here. That flag is a user-facing feature, gating the packages `mpm` installs on the user's machine, and `docs/cooldown.md` is its documentation. This section covers what CI resolves onto a runner while building `mpm` itself. A comment or changelog entry naming one should not read as the other.

The product feature's vocabulary is settled; reuse it rather than coining near-synonyms. The gate has two axes: the **window** (the release age itself, `period` in configuration) and the **posture** (what happens to managers that cannot enforce it, `policy`), spelled by the single `--cooldown` union and the `[mpm.cooldown]` table. Managers are **gateable** or **ungateable** depending on whether they carry a native release-age mechanism. Never write "unsupported managers" in this sense: that phrase belongs to the tools `mpm` declined to wrap (`docs/unsupported.md`) and to platform support, and the collision is what the `8.0.0` rework removed. Strength words (`strict`, `soft`, `full`, `partial`) are kept out of the keyword set because they read as a weaker *window* rather than a narrower scope; the shipped keywords are `enforce` / `best-effort` / `off`, and the default posture is fail-closed by design.

The rule has no scratch exemption. It binds reusable workflows, one-off CI steps, test scripts, local reproduction commands and throwaway experiments equally: an uncooled `uvx` in a five-minute debugging step resolves the same tree from the same registry onto the same runner as a production job.

### Per-ecosystem knobs

| Ecosystem                                                                  | Cooldown                                                           | Per-package exemption                                   |
| :------------------------------------------------------------------------- | :----------------------------------------------------------------- | :------------------------------------------------------ |
| uv: `uvx`, `uv pip install`, `uv run --with`, `uv tool install`, `uv lock` | `--exclude-newer`, or `UV_EXCLUDE_NEWER`                           | `--exclude-newer-package pkg=YYYY-MM-DD`, CLI flag only |
| npm, `npx`                                                                 | `--min-release-age` in whole days, or `NPM_CONFIG_MIN_RELEASE_AGE` | `--min-release-age-exclude` taking a name or glob       |

uv accepts a friendly duration (`1 week`), an ISO 8601 span (`P7D`), or an absolute date; npm counts whole days and needs 11.10.0 or newer. Both knobs gate the whole resolved tree, transitive dependencies included, which is the point: the compromised package is rarely the one named on the command line.

For every other package manager, `docs/cooldown.md` is the inventory, and it is this project's own: which managers enforce a cooldown natively, which have support proposed upstream, which have none, and which are N/A because their archive already stages releases on its own.

### Documented exemptions

Three installs deliberately bypass the window. Two are per-package and never widen to the rest of the tree; the third is a whole workflow, and says why it has to be.

- **The upstream toolkit's own pin.** `repomatic` runs from a pin that moves in lockstep with the `uses:` refs pointing at it, so a release must be installable the minute it is published. Every `uvx` call carrying it passes `--exclude-newer-package repomatic=P0D` beside the pin.
- **A fresh click-extra, on the day it ships.** `mpm` and click-extra share a maintainer and evolve in lockstep: most `mpm` releases raise the floor to pick up what the CLI toolkit just shipped, so a week-long wait before the release can even resolve stalls the work rather than protecting it. `[tool.uv] exclude-newer-package` names click-extra with the midnight following its upload, an absolute timestamp covering that release and nothing published after it. The entry is transient, and repomatic's `sync-uv-lock` prunes it once that release ages past the window, which is what keeps the exemption from quietly becoming a standing one.
- **The `tests-install.yaml` workflow.** Its subject *is* the freshly published artifact, so a cooldown would make the question it exists to answer unanswerable. It declares `UV_EXCLUDE_NEWER: P0D` at workflow level rather than relying on uv's default, so the opt-out reads as a decision.

A fourth exemption is a bug until proven otherwise. Anything claiming one carries a comment naming what breaks without it, and the narrowest scope that still works: a package, not a job; a job, not a workflow.

## Build status

[`main` branch](https://github.com/kdeldycke/meta-package-manager/tree/main):
[![Unittests status](https://img.shields.io/github/actions/workflow/status/kdeldycke/meta-package-manager/tests.yaml?branch=main&label=%F0%9F%94%AC%20Tests)](https://github.com/kdeldycke/meta-package-manager/actions/workflows/tests.yaml?query=branch%3Amain)

## Commands

### Setup environment

Check out latest development branch:

```shell-session
$ git clone git@github.com:kdeldycke/meta-package-manager.git
$ cd ./meta-package-manager
$ git checkout main
```

Install package in editable mode with all development dependencies:

```shell-session
$ python -m pip install uv
$ uv venv
$ source .venv/bin/activate
$ uv sync --all-extras --all-groups
```

### Test `mpm` development version

After the steps above, you are free to play with the bleeding edge version of `mpm`:

```shell-session
$ uv run -- mpm --version
(...)
mpm, version 4.13.0
```

### Unit-tests

Run unit-tests with:

```shell-session
$ uv sync --group test
$ uv run -- pytest
```

Which should be the same as running non-destructive unit-tests in parallel with:

```shell-session
$ uv run pytest --numprocesses=auto --skip-destructive
```

Destructive tests mess with the package managers on your system. The safe local invocation runs them sequentially:

```shell-session
$ uv run pytest --numprocesses=0 --skip-non-destructive --run-destructive
```

CI parallelizes them instead, mirroring `mpm`'s own concurrency model: `tests/conftest.py` stamps every destructive test with an `xdist_group` derived from `SHARED_LOCK_FAMILIES` in `meta_package_manager/dispatch.py`, so `--dist=loadgroup` keeps managers contending for one backend lock serial on a single worker while independent families run at once. The cross-manager tests (`destructive_all_managers` marker) drive every available manager in one invocation, which no grouping can isolate, and keep a sequential CI step of their own. The sequential command stays the local recommendation: it cannot interleave `sudo` prompts and spares a workstation the parallel load.

### Note for downstream packagers

The canonical guidance for distribution packagers (test-suite layers, `/homeless-shelter` auto-skip, ignore-globs for writable-`$HOME` builders, dependency constraints, per-channel build instructions) lives in `docs/packaging.md`, published at [https://mpm.run/packaging/](https://mpm.run/packaging/). Packaging specs (`packaging/nix/`, `packaging/alpine/`, and their upstream submissions) must reference that URL, never this file.

Keep the comments in those specs tight. Their audience is each channel's own maintainers, who already know their build-sandbox conventions (the `/homeless-shelter` auto-skip, standard `make_check` / test-phase behavior): drop those, drop doc-link pointers, and collapse verbose per-dependency breakdowns to a single line. Keep only non-obvious, spec-specific rationale: a live workaround still needed, or why a particular test or dependency is excluded. When unsure, favor the tighter comment. This holds for both the in-repo `packaging/*` specs and their downstream branch copies.

### Type checking

```shell-session
$ uv run --group typing mypy meta_package_manager
```

### Documentation

Build Sphinx documentation locally:

```shell-session
$ uv sync --group docs
$ uv run -- sphinx-build -b html ./docs ./docs/html
```

The `docs` group declares `requires-python = ">= 3.14"` of its own, above the project's `3.10` floor, so a venv built on an older interpreter resolves the group to nothing and `sphinx-build` is simply absent rather than broken. Narrowing it is what lets the documentation dependencies carry flat version floors: see the comment on `dependency-groups.docs` in `[tool.uv]`.

The generation of API documentation is
[covered by a dedicated workflow](https://github.com/kdeldycke/meta-package-manager/blob/main/.github/workflows/docs.yaml).

## Documentation requirements

### Example data

Invented example data (docs, docstrings, comments, test fixtures) must be domain-neutral: cities, weather, fruits, animals, recipes. Do not reach for software-engineering or packaging vocabulary for a placeholder, and never invent a plausible-looking package or manager name: this project's whole domain is package metadata, so a made-up `foo-lib 1.2.3` in a docstring is indistinguishable from a real fixture and will eventually be read as one.

The exception is the material that must be real to be correct: the `[samples]` fixtures of the bundled TOML definitions and the `shell-session` blocks harvested into the docstring corpus are captured CLI output, held to byte-accuracy by `test_documented_output_still_parses`. Those are not examples, they are data.

### Changelog and readme updates

Always update documentation when making changes:

- **`changelog.md`**: Add a bullet point describing **what** changed (new features, bug fixes, behavior changes), not **why**. Keep entries concise and actionable. Justifications and rationale belong in documentation or code comments, not in the changelog.
- **`readme.md`**: Update relevant sections when adding/modifying public API, classes, or functions.

**Changelog scope tags.** Every bullet opens with a comma-separated `[scope]` tag, alphabetically sorted and deduplicated, drawn from the pool manager IDs plus the platform IDs and `mpm`, `bar-plugin`, `gnome-shell`. `test_changelog` enforces that vocabulary, and it is not cosmetic: `manager_changelog()` indexes the tags to build the release-history section of every manager page. Two consequences. A tag naming a manager must describe `mpm`'s *support* for that manager, so work on `mpm`'s own downstream package for a channel that shares a manager's name (Guix, Nix, MacPorts, Alpine) is scoped `[mpm]` like the rest of the packaging work, never to the manager whose page it would otherwise land on. And a new manager needs its changelog entry, since `test_manager_changelog_entries` asserts every pool manager has one.

### Benchmark page (`docs/benchmark.md`)

The benchmark compares `mpm` against related tools. It mixes one generated table with several hand-maintained ones, and its cells follow strict evidence rules.

**Generated vs hand-maintained.** Only the "Package manager support" table is generated: it renders live at Sphinx build time through the `{python:render}` block in `docs/benchmark.md`, which calls `benchmark_managers_table()` from `meta_package_manager/_docs.py`, fed by `docs/benchmark.toml`; its competitor set is the `BENCHMARK_COMPETITORS` tuple. Every other table (Features, Operations, OS, Distribution, Activity, Popularity, Metadata) is edited by hand. The block carries the `:mirror:` flag: a generated copy of the table is checked in right below the fence, between `<!-- mirror -->`/`<!-- mirror-end -->` markers, so it is reviewable in raw diffs and renders on GitHub. Never hand-edit the mirrored region: `click-extra refresh-directives` (run by repomatic's `update-docs` job, or by hand from the repository root) regenerates it. Sphinx builds keep rendering the live output in memory and never read the mirror, so the published table cannot drift even when the checked-in copy is stale; the mpm-column ✅ links (class source-line anchors) are computed at render time, so the mirror legitimately churns whenever manager source lines shift. `test_benchmark_table_renders` guards the generator against crashes and structural regressions.

**Cell glyphs.** ✅/❌ are shared by the docs' comparison and capability tables: the benchmark tables, the SBOM page's coverage matrix and tool-comparison table, the cooldown support table and the augmentations table. Never backtick-quote a glyph, in a table cell or in prose: a glyph is not an identifier, the backticks render as a code span around a pictograph, and in the benchmark's `mpm` column ✅ and ⚠️ are links, which a code span would flatten.

A dead upstream gets two glyphs, and the split is the point — it encodes whether `mpm` ships code for the tool:

- ⚠️ — **wrapped, but at risk.** The upstream is abandoned and the manager carries the `unmaintained` flag, yet it stays wrapped and usable. Marks the `Support` column of the manager index and the benchmark's `mpm` column alike, replacing the ✅ that manager would otherwise get, plus the same fact in `readme.md`'s operation matrix.
- ☠️ — **never wrapped.** The upstream is dead, so `mpm` declined to write the manager at all. Closes the section title of `docs/unsupported.md` and marks the manager index's `Support` column and the benchmark's `mpm` column alike (see the `unsupported` key below), alongside ❌ for a *live* tool declined on its own merits.

The benchmark's `mpm` column and the manager index's `Support` column are therefore both a five-state scale, and the two families never mix: ✅/⚠️ link to the implementing class, ☠️/❌ to the decision not to write one. Only the benchmark ever shows a blank cell, since the manager index lists nothing it has not assessed.

Never swap one for the other: a reader scanning for something they can still install today needs ⚠️ to mean "works, may go away" and ☠️ to mean "was never there". Two tables add glyphs that do not travel: the benchmark's 🟡 for coarse support a competitor cannot invoke in isolation, and the cooldown table's 🔜 (gate shipped upstream, not yet plugged into `mpm`), 🚧 (proposed upstream) and ➖ (not applicable). Only the dense per-manager operation grids keep plain `✓`: `readme.md`'s operation matrix and each manager page's own operations table. The bar plugin's ⚠️ is unrelated, counting runtime errors rather than upstream health. The evidence-link discipline below is benchmark-specific.

- ✅ — supported. The `mpm` ✅ is always a link: to the manager class's source line in the generated table, to the feature's user documentation in the Features table, where the row's label carries that same target so both halves of the row lead to the same page. A competitor's ✅ links to whatever proves the support — its documentation, config example, CLI declaration, or the source line implementing it — and stays a bare glyph only when the research turned up nothing citable.
- ❌ — not supported, **and only ever written with a link to explicit, verifiable evidence** that the project lacks or rejects the feature: an issue/PR closed not-planned, a maintainer "out of scope" / "won't add" comment, a still-open unaddressed feature request, or an official doc/man-page stating the limitation. **Absence of the feature is never sufficient** — if no citable source exists, leave the cell blank. Verify every URL (`gh issue view`, `gh api`, or WebFetch) and keep the exact supporting quote before committing the link; prefer a precise `#issuecomment-<id>` anchor when a maintainer states the position. This mirrors the "Concurrent multi-PM execution" row.
- 🟡 — coarse/bundled support the competitor cannot invoke in isolation (e.g., topgrade's `--only shell` running every shell-plugin manager at once), also with an evidence link.

**`docs/benchmark.toml`** has five alphabetically-sorted keys: `managers` (which competitor supports each manager), `homepages` (URLs for non-pool managers only), `coarse_support` (`{manager: {competitor: url}}`), `refused` (`{manager: {competitor: url}}` for competitors that explicitly declined a manager `mpm` wraps), and `unsupported` (`{manager: status}` for managers `mpm` itself declined). `test_benchmark_toml_well_formed` enforces the shape plus the no-orphan and no-conflict invariants (a `(manager, competitor)` pair cannot be in both `managers` and `refused`; an `unsupported` manager must have a `managers` row and must not be in the pool). TOML over YAML is a deliberate choice, not just a rename: `tomllib` rejects a duplicate manager-id row as a parse error, where `yaml.safe_load` used to silently keep the last one.

**The table is a coverage map, so a manager no tool wraps still earns a row.** A competitor's backend that `mpm` lacks is exactly what the table exists to surface: leaving it out hides the gap. By the same logic a retired tool is never dropped from the table — a competitor that still drives a dead tool is a fact about the competitor. The `mpm` column then distinguishes the two kinds of absence, which is what `unsupported` is for — ❌ links to the decision in `docs/unsupported.md`, while a blank cell means the tool was never assessed. Only settled decisions belong in `unsupported`: a tool framed as a *not yet* (the project-scoped ecosystems) keeps its blank cell, since ❌ would overstate it. The page lives once in `_docs.py`'s `UNSUPPORTED_DOCS_URL` and the section anchor comes from `unsupported_anchors()`, never repeated per manager in the TOML.

**`docs/unsupported.md` is the user-facing record, not the reasoning.** It carries one section per excluded tool and the reason for it, and nothing else. The title is the tool as a linked code span followed by its glyphs (`` [`paq`](https://github.com/savq/paq-nvim) ❌ 🛟 ``), which slugifies to the bare manager ID: that anchor is what the benchmark, the other pages, the code comments and the docstrings link to, so `https://mpm.run/unsupported/#paq` cites a decision from anywhere. Tools sharing a verdict word for word are grouped into one family section instead, titled after the family and naming its members in the paragraph that opens it, which is where `unsupported_sections()` reads them from when the title holds no ID. Sections are sorted by title, and `test_unsupported_page_matches_benchmark` holds the whole contract: the ordering, the coverage against `benchmark.toml`, and every member of a family agreeing on the glyphs their shared title shows. Every guideline behind it — why a dead upstream or a registry-less wrapper is disqualified, how to pick the live end of a lineage, the unattended-entry-point test, the three requirements enforced in code and their escape hatches — lives in the `add-manager` skill, where someone deciding whether to wrap a tool will actually read it. Keep it that way: the page is a record, and rationale added to it belongs in the skill instead.

**Two groups of benchmark rows are easy to misread**, and neither is a refusal. Competitors like `topgrade` also drive system updaters, dotfile managers and single-application updaters, which are outside `mpm`'s domain by definition. And `mpm` wraps `asdf`, `mise` and `volta` for what they install globally, so their rows say nothing about the per-project pinning that is the separate project-scope question.

**Scope and competitor set.** Feature/Operation rows cover only capabilities in `mpm`'s domain (cross-manager package operations, output, config, distribution). Do not add rows for a competitor's out-of-domain features (a runtime version manager's shims, task runner, env-var management, per-project version files). Columns are the wrapper peer group (`topgrade`, `pacaptr`, `pacapt`, `sysget`, `whohas`) plus `brew` (its Brewfile is a declarative multi-backend installer); `mise`/`asdf` were removed as out-of-scope version managers, kept only as managers `mpm` wraps in the generated table.

**Auditing competitor cells.** When (re)checking a column, research one competitor project at a time (parallel agents work well); each must verify every URL and quote and report "no evidence → blank" rather than infer a gap from absence.

### Manager augmentations page (`docs/augmentations.md`)

Documents capabilities `mpm` backfills on top of native tools. Two classes: *selective* — only some managers need it (full `upgrade --all`, the synthesized orphan sweep of `cleanup --orphans`, exact/extended search), shown in the per-manager table — and *universal* — every managed tool gains it (`--dry-run` simulation, cross-scheme version parsing, purl identifiers, uniform sudo). The per-manager table renders live at Sphinx build time through the `{python:render}` block calling `augmentations_table()` from `meta_package_manager/_docs.py`, derived from the capability declarations (`upgrade_all_is_synthesized()`, `cleanup_orphan_is_synthesized()` and the `search_capabilities` flags in `meta_package_manager/capabilities.py`), so the rendered page never drifts from the code. The block carries the `:mirror:` flag like the benchmark table: a generated copy sits below the fence between `<!-- mirror -->` markers, refreshed by `click-extra refresh-directives`, never hand-edited. `test_augmentations_table_renders` guards the generator.

### Concurrency page (`docs/concurrency.md`)

The user-facing half of what `dispatch.py` implements, and the only generic account of it: everything else on the subject is either a manager's own *Concurrency* section or the contributor-facing docstrings in `dispatch.py` and § *CLI output and logging* below. All three of its renderings are `{python:render}` blocks with the `:mirror:` flag, derived rather than restated, so a lock family or a subcommand added in `dispatch.py` reaches the page with no edit here.

- `concurrency_table()` glyphs every subcommand from `COMMAND_FAN_OUT`, whose ⇶⇶⇶/⇉⇶→/→→→ scale is local to this page. `test_fan_out_covers_every_subcommand` holds the catalog equal to the CLI's registered commands, which is what forces a new subcommand to declare its mode; the `FAN_OUT_NONE` entries record the decision for the commands that drive no manager, and are left out of the render. The catalog is the one thing here that *can* drift silently, since no test reads a fan-out mode back off its call site: a subcommand switching primitive, or gaining `report_state=True`, must be reflected in the same commit.
- `lock_families_sankey()` replaced the readme's flat `mpm` → manager fan-out, which had grown to a hundred-odd equal bands: a picture of the pool's size rather than of its structure, and slow to lay out for it. The diagram is rooted at the *serialized* managers and shows the families alone. Adding the managers that share no backend would spend most of the canvas on one band, so they are a sentence instead. Each family's `backend` label must stay clear of every manager ID, mermaid identifying a sankey node by its label alone: `test_lock_family_backends_are_distinct` enforces it.
- `lock_families_table()` reuses each family's `contention` fragment verbatim under a *Why?* heading, the same string the per-manager pages complete a sentence with. Do not recase it into a standalone sentence: one wording, one place to fix it.

### Snapshot page (`docs/dump.md`)

The canonical home of every Brewfile fact: which managers map to which entry keyword (a table generated from the pool's own `brewfile_entry_type` declarations), what the header warns about, how taps and entry order are emitted, and the per-manager caveats (VSCodium extensions skipped, `mas` entries keyed by App Store ID, the `uv`/`uvx` split, the flatpak remote). Everywhere else keeps a one-line contextual mention pointing here: manager class docstrings, the bundled TOML description comments, the `--brewfile` option help, `docs/configuration.md` and `docs/overrides.md`. Never re-enumerate the covered managers or entry types in prose: that list drifted twice already, still naming `uv` after the mapping had moved to `uvx`. Read it off `BUNDLE_ENTRY_TYPES` or the generated table instead.

### Per-manager pages (`docs/managers/`)

One documentation page per pool manager, plus the `docs/managers.md` hub. The invariants:

- **Stubs are generated — never hand-edit them.** Each `docs/managers/<id>.md` is written by `update_manager_stubs()` in `docs/docs_update.py` (run by repomatic's `update-docs` job), which owns the whole directory: it creates a stub per pool manager, rewrites drifted ones and deletes orphans. Adding or removing a manager needs no manual page work. `test_manager_stubs_in_sync` enforces byte-identity with the template.
- **A generator edit does not invalidate the Sphinx cache.** Incremental builds re-read a document only when its own source file changed, and editing `_docs.py` (or a manager docstring, or `changelog.md`) leaves every stub untouched: the pages then rebuild from cached doctrees carrying the *previous* output. Rebuild with `sphinx-build --fresh-env` after touching a generator, or the local `docs/_build` shows work that is already done. CI is immune, building from scratch every time.
- **A stub is one render block; the layout lives in `MANAGER_SECTIONS`.** Every stub is the same five lines calling `manager_page()`, which prints the page title, then walks that tuple: an untitled entry renders as the lede, a titled one as its heading followed by its `manager_*` generator's output. So a section added, renamed or dropped is a one-line edit in `meta_package_manager/_docs.py` instead of a rewrite of a hundred stubs (nine such bulk rewrites happened before the split, one per layout change). The individual generators still emit heading-free MyST, `manager_page()` being the only source of a heading, which `test_manager_page_sections_render` locks. Headings once had to be committed into each stub, `myst-parser` having dropped a heading generated inside a nested parse; it supports them now (`temp_root_node`). What it still cannot do is keep content emitted *above* the first heading of that parse in place: it builds the sections then appends the loose lead nodes after them, so a lede printed before the first `##` lands at the foot of the page. Printing the `#` title first is what avoids that, by leaving nothing loose, and it is why the title cannot go back into the stub. `test_manager_page_headings_survive_a_build` builds a page for real and asserts the title, the heading sequence and the infobox's position, all three regressions being silent and none visible to a test of the generators alone. A fact that fits on one line belongs in the infobox (`manager_card()`), not in a section: that is where the invocation plumbing went (CLI names and lookup paths, forced arguments and environment, formerly a *How `mpm` drives `<id>`* section), leaving only what a box cannot hold — the version probe with its transcript and regexes.
- **Generators read static declarations only** — class attributes, the bundled TOML files (description comment, operation specs, `[samples]` fixtures), the `shell-session` samples documented in class/attribute docstrings (harvested via `meta_package_manager.docstring_corpus`, shared with the corpus round-trip test, in terminal-facing `class_display_blocks` form for the reference traces) the hand-curated "Supported managers" table of `docs/cooldown.md`, whose per-manager row `manager_cooldown()` extracts (its id column partitions the pool, held by `test_cooldown_support_table_covers_the_pool`; a missing row degrades the rendered page to a "not yet assessed" line), `changelog.md`, whose `[scope]` tags `manager_changelog()` indexes into a per-manager release history, and `labels.py`, whose `MANAGER_LABELS` gives the card its tracker-search link (ecosystem siblings share one label, hence one search). Never touch host-probing properties (`cli_path`, `version`, `available`, installed packages): the pages must be identical on any build host, which is also why the card renders a path under the builder's home as `~`-prefixed (SDKMAN resolves its search path from `$SDKMAN_DIR`).
- **`shell-session` means fixture, `console` means illustration.** Every `installed`/`outdated`/`orphans`/`version_regexes` block written under a ```` ```{code-block} shell-session ```` (or `pwsh-session`) fence is a *complete* sample: it must parse through the manager's own parser (`test_documented_output_still_parses` enforces it) and it renders verbatim as a reference trace, so it carries no `(...)` truncation marker (`test_fixtures_carry_no_truncation_marker` guards this; bare `...` in genuine CLI output like apt's `Listing...` is fine) and no shell pipe: it shows the exact argv mpm runs, not a `| jq` prettified view or an `echo n |` prompt feed (`test_query_fixtures_run_verbatim` guards this). A block that is *not* a literal fixture — a human-readable variant, an interactive prompt (sdkman's `echo n | sdk upgrade`), a narrative before/after transcript — uses the non-harvested ```` ```{code-block} console ```` fence instead: it still renders in the API docs but never reaches the corpus or the traces. There is no central exception registry; the fence language is the whole signal.
- **Manager class docstrings render outside autodoc.** `manager_intro()` inlines the class docstring straight into the MyST page after a `{py:currentmodule}` directive, so cross-references in those docstrings must be fully-qualified or module-sibling (`` {class}`PKG` ``, `` {meth}`Yay.cooldown_env` ``) — a bare class-member short ref resolves in the API docs but breaks on the manager page. A malformed fence (unclosed, or a 3-backtick fence nested inside another 3-backtick fence) garbles both pages: when a code block must nest inside an admonition, the outer admonition uses a colon fence (`:::{note}`). TOML managers render their file's top description comment as the intro instead.
- **Brand marks are vendored, never hotlinked.** A manager's `logo` attribute (or TOML key) names an SVG under `docs/assets/managers/`, which `docs/logos_update.py` owns: it downloads them from a pinned [Simple Icons](https://simpleicons.org) release, normalizes each to a single unfilled line, and records title, brand color, source and license in `logos.yaml`. Run it by hand, never from CI or a docs build: committed artwork keeps builds hermetic and immune to an upstream icon removal. `manager_logo()` inlines the SVG into the page instead of referencing it as an image, which is what lets CSS recolor it: the marks carry no `fill`, so they follow `currentColor` on the dark theme and take their brand color on the light one, for every mark: `MIN_LOGO_CONTRAST` is measured and reported by `docs/logos_update.py` but never gates a render, since WCAG exempts logotypes and dropping pale marks back to `currentColor` repainted recognizable brands a flat black. Remote logo URLs were assessed and rejected: linkcheck resolves `nodes.image` URIs, so 75 hotlinked marks would each cost a request against a budget already throttled to about one per minute on github.com. A manager whose upstream polices its mark simply declares no `logo` and keeps the page's default package glyph: Microsoft's legal team had every Microsoft mark removed from the set in its `13.0.0` (https://github.com/simple-icons/simple-icons/issues/11236, which also auto-closes re-requests as duplicates), so `vscode`, `winget` and `pwsh-gallery` will never have one, and Oracle's went the same way (https://github.com/simple-icons/simple-icons/issues/11441), taking `sun-tools` with it. Do not re-request those, and do not vendor the marks by hand. Twelve marks carry an attribution-bearing license, so `manager_logo_credits()` renders their credits from the manifest into `docs/license.md`: crediting them is a license condition, not a courtesy.
- **Upstream readings are split between the card and its own section, never stated twice.** The weekly `sample-metrics` reading committed as `docs/assets/metrics.csv` gives the card two facts (stars, newest commit); everything else a forge knows about the project is the *Upstream project* section, where `manager_upstream()` renders live shields.io badges in the benchmark's own three families (Activity, Popularity, Metadata). Live rather than sampled, because a date written in at build time starts ageing immediately while a badge is fetched when the page is read, and shields renders it as the distance to today, coloured by age. `UPSTREAM_FORGES` maps each forge host to its badge family (a host missing there renders no section at all, which `test_upstream_badges_cover_every_forge` reports), and `UPSTREAM_BADGES` lists only the readings each family was *verified* to answer, since shields renders a red error image for an endpoint a forge cannot serve. That same red covers "no releases" and "repo not found" alike, so the release-only badges are gated on the sample's `release_source`: a project that tags without releasing (`pip`) shows its newest tag instead. All badge URLs are exempted from linkcheck in `conf.py`. This is not a licence to hotlink generally: brand marks stay vendored, per the rule above.
- **Manager IDs link to the pages.** The readme operation matrix (absolute `https://mpm.run/managers/<id>/` URLs built by `manager_page_url()`, exempted from linkcheck in `conf.py`), the benchmark first column (pool managers only), the augmentations table, the cooldown support table and the SBOM coverage matrix all link manager IDs to their page; home pages are listed on the pages themselves. The benchmark `mpm` ✅ keeps its source-line link. Prose follows the same rule: a manager named as a code span anywhere in `docs/*.md` links to its own page, once per paragraph, so a name repeated in the next sentence stays plain while an enumeration is uniformly linked. Three places keep the bare span: a heading, where a link would rewrite the anchor other pages cross-reference; the benchmark's own column headers and competitor cells, which name rival tools rather than wrapped managers; and the `cooldown.md` cells the manager-page generators reuse verbatim, where a relative target resolves from `docs/managers/` and lands nowhere.

### Installation and packaging pages (`docs/install.md`, `docs/packaging.md`)

`docs/install.md` is for end users installing `mpm`: every tab of its "Installation methods" tab-set opens with commands that work **today**, on the reader's machine, whatever the channel's upstream status. Everything aimed at distribution packagers lives in `docs/packaging.md`: the test-suite wiring, the dependency graph and `click-extra` compatibility matrix, and the per-channel catalog with its build walkthroughs and packaging rationale. A channel not yet released through its distro therefore carries the condensed build recipe from its `packaging.md` section, copied into the tab and trimmed to the commands, followed by a `{admonition}` naming the upstream pull request and inviting the reader to +1 it for native inclusion. Never demote such a tab to a status line plus a pointer: a one-liner the reader cannot run yet, sending them to another page for the one they can, is the shape this rule exists to forbid. The copy is the accepted cost of that: when a channel's build steps change, update both pages. Packaging specs and their upstream submissions cite the page URL `https://mpm.run/packaging/`, never `CLAUDE.md`. The end-to-end procedure for adding a channel is the playbook at `docs/add-packaging-channel.md`; the three-file sync it enforces is the *Distributor sync* rule below.

### Captured screenshots (`docs/assets/*bar-*.png`, `docs/assets/gnome-shell-*.png`)

Both frontends illustrate themselves from real sessions, driven by `docs/bar_screenshots_update.py` and `docs/gnome_screenshots_update.py` through the `docs-screenshots.yaml` workflow. Everything in an image is genuine: a real host renders a real menu, and only the package payload is held still, by a stand-in `mpm` serving `docs/outdated-sample.json`.

**A committed capture must be byte-reproducible, and the proof is a pair of runs.** Dispatch the workflow twice on the same commit: if `pr-sync` commits nothing the second time, the set has converged. Anything else rewrites all sixteen images on every push and the pull request stops carrying information. Reaching that took pinning six independent things a live desktop moves on its own, each recorded against the run that exposed it in the driver's own comments: the menu bar clock, the drawn clock's repaint, SwiftBar's relative *Updated* footer, an unanswered automation alert, the order of Control Center's menu bar modules, and the light-to-dark crossfade. Read those before adding anything to a frame.

**Measure a difference before explaining it.** When a capture moves, the rectangle and the count of pixels past a threshold say whether an element moved or a tint shifted, and the two have nothing in common. Guessing cost this project several 30-minute round trips; the window census (`report_windows`) and the whole-screen photograph behind the `capture_screens` dispatch input exist because measuring is cheaper. Leave that input off by default: each extra `screencapture` gives macOS another chance to raise the consent sheet the diagnostic is looking for.

### Brand assets (`docs/assets/`)

The mark is **flat and unoutlined**: an isometric solid reconstructed from the three shades its planes catch, which is what the ANSI rendition in `--version` had always been and the SVG only became once the outline came off. So the palette is **two purples and their midpoint**: the ink `#2d2364` on every left-facing face and on the lettering, the wash `#d3d3f6` on every lit face, and `#807bad` on the right-facing ones. That third value is computed, never chosen — the per-channel average of the other two — so the palette stays two colors and a derivation. Everything else a source shows is one of the three at reduced opacity (the tagline is the ink at 80%, the social banner's veins the ink at 12%), the single exception being that banner's opaque background, the wash at 45% over white.

**The open box shows its interior, and the interior mirrors the planes.** Two walls fill the rim behind the floating cube, and each carries the tone of the plane it *faces* rather than the one it sits behind: the far-left wall is lit as a right-facing face, so the interior's left half is the midpoint where the exterior's is the ink. That mirroring is not decoration — it is what keeps each face of the floating cube landing on the opposite tone, so the cube stays legible at every size. The geometry is derived, not eyeballed: both walls are drawn full height and clipped to the rim quadrilateral, so they meet on the vertical through the back corner without any intersection maths, and the same rim test fills the interior cells of the ANSI grid.

`docs/brand_update.py` owns every raster under `docs/assets/`: the light and dark PNGs of the square logo, the banner and the social card, plus the `.png`/`.ico`/`.icns` bundle Nuitka ships. Run it by hand after editing an SVG, never from CI, and `--check-palette` reports any color that strayed. The mark also exists outside that directory, in the GNOME Shell extension's `icons/mpm-logo.svg`, and moves with it.

**A dark export moves the lettering and nothing else.** The mark is one artwork on every surface, which is what going flat bought: a face carries its own value, where an ink *outline* on a dark background had nothing to stand against and dissolved. So `DARK_THEME` swaps `.word`/`.sub` onto the wash, repaints the social card's background and veins, and leaves the mark alone. Its keys are whole CSS rules rather than bare colors, deliberately: `.mpm-left` names the same ink the wordmark does, and a color-keyed swap would repaint every shadowed plane. That also lets `favicon.svg` and the app icons ship a single rendering, a browser tab and a dock being surfaces the script cannot know the color of.

The terminal rendition in `meta_package_manager/logo.py` repeats the two colors as literals, runtime code having no access to the SVG sources, and shades its isometric faces with the closest xterm-256 entries to them. `test_ansi_logo_tracks_the_brand_palette` holds the constants and the artwork together.

### Legal notices (`docs/license.md`)

The project's single legal sink: license and copyright, the blanket trademark notice covering every manager name and mark the docs display, credits for third-party artwork (the vendored brand marks, Open Clipart mascots, Octicons, the XKCD strip), and a pointer to where dependency licenses live. Legalese goes here and nowhere else, so a credit is never stranded next to the artwork it covers, where nobody looks for it. The file keeps its `license.md` name (and `license.html` URL) to stay aligned with the upstream repomatic docs tree, even though the page now covers more than the license; its `index.md` entry stays last in the `Development` toctree. A new third-party asset means a new entry here, and an attribution-bearing license means the entry is mandatory.

## Code style

### Version formatting

The version string is always bare (e.g., `1.2.3`). The `v` prefix is a **tag namespace** — it only appears when the reference is to a git tag or something derived from a tag (action ref, comparison URL, commit message). This aligns with PEP 440, PyPI, and semver conventions.

| Context                                | Format            | Example                                        | Rationale                         |
| :------------------------------------- | :---------------- | :--------------------------------------------- | :-------------------------------- |
| Python `__version__`, `pyproject.toml` | `1.2.3`           | `version = "6.1.2"`                            | PEP 440 bare version.             |
| Git tags                               | `` `v1.2.3` ``    | `` `v6.1.2` ``                                 | Tag namespace convention.         |
| GitHub comparison URLs                 | `v1.2.3...v1.2.4` | `compare/v6.1.1...v6.1.2`                      | References tags.                  |
| GitHub action/workflow refs            | `` `@v1.2.3` ``   | `actions/checkout@v6.0.2`                      | References tags.                  |
| Commit messages                        | `v1.2.3`          | `[changelog] Release v6.1.2`                   | References the tag being created. |
| CLI `--version` output                 | `1.2.3`           | `mpm, version 6.1.2`                           | Package version, not a tag.       |
| Changelog headings                     | `` `1.2.3` ``     | `` ## [`6.1.2` (2026-03-04)] ``                | Package version, code-formatted.  |
| PyPI URLs                              | `1.2.3`           | `pypi.org/project/meta-package-manager/6.1.2/` | PyPI uses bare versions.          |

**Rules:**

1. **No `v` prefix on package versions.** Anywhere the version identifies the *package* (PyPI, changelog heading, CLI output, `pyproject.toml`), use the bare version: `1.2.3`.
2. **`v` prefix on tag references.** Anywhere the version identifies a *git tag* (comparison URLs, action refs, commit messages, PR titles), use `v1.2.3`.
3. **Always backtick-escape versions in prose.** Both `v1.2.3` (tag) and `1.2.3` (package) are identifiers, not natural language. In markdown and in MyST docstrings alike, wrap them in single backticks: `` `v1.2.3` ``, `` `1.2.3` ``.
4. **Development versions** follow PEP 440: `1.2.3.dev0` with optional `+{short_sha}` local identifier.

### Commit messages

Default to a subject line and nothing else. A commit message is a log entry, not a design document. It gives a quick summary of what the commit holds, and points at context that lives elsewhere.

- **Subject.** One line under 72 characters, imperative mood, capitalized, no trailing period, every identifier backticked. Name what changed, not the category it falls in: `` Sync `uv.lock` ``, `` Fix `yay` cooldown overlay on Arch ``. Avoid the bare one-word subject (`Typo`, `Lint`, `Fix`): it costs the next reader a `git show` to learn anything. Say what the typo was in, what the lint fixed.
- **No decorative prefixes.** This is not [Conventional Commits](https://www.conventionalcommits.org): no `feat:`, `chore:`, `fix:`. A `[bracketed]` prefix is reserved for a mechanism that parses it back, and only `[changelog] …` qualifies, matched literally by repomatic's auto-tagging job. Do not confuse it with the `[scope]` tags that open every `changelog.md` bullet: those name a manager or platform, live in the changelog file rather than in git, and are indexed by `manager_changelog()`. The two vocabularies are unrelated. Never write a GitHub skip token (`[skip ci]` and its aliases) in any message, including a body: they match anywhere and leave a required check "Pending" rather than failing.
- **Body: three cases, and nothing else.** Omit the body by default, even when the *why* is not obvious from the diff. A body is not the place to explain the change, defend the approach, or restate what the diff already shows. Write one only when the commit meets one of these cases, and write no more than the case needs:
  - **It bundles orthogonal work.** The commit carries several unrelated tasks, or spans different domains, and one subject cannot name them all. Give one short line per strand.
  - **A public record holds the context.** Link it: the upstream manager's issue tracker, the distro packaging PR, the spec page that forced the behavior, the discussion thread. Forges render commit messages as HTML, so the link is the cheapest route from `git log` to the full story. Format every cross-repository reference as `[owner/repo#N](https://github.com/owner/repo/issues/N)`.
  - **It resolves or references a tracked item.** Use `Closes #N` when merging the commit into the default branch must close the issue, and `Related to #N` when it must not.

Never narrate the work in sequence, enumerate the files touched, or summarize the diff in prose: `git log --stat` lists the files and the diff shows the rest. Rationale belongs somewhere durable instead: a code comment, a docstring, `docs/`, or the PR body.

### Comments and docstrings

- All comments in Python files must end with a period.
- Docstrings are written in MyST markdown: single-backtick code spans, `{role}` cross-references in the unprefixed form (`{class}`, `{meth}`, `{func}`, `{attr}`, `{data}`, `{mod}`, `{exc}`), markdown links, and backtick-fenced directives. click-extra's `myst_docstrings` Sphinx extension converts them back to reST at build time, so autodoc is unaffected. Field lists (`:param x:`, `:return:`) keep their reST syntax, which passes through the conversion. A brace-bearing literal keeps reST double backticks (like ` `{count}` `) so the converter cannot misread it as a role. The `click-extra convert-to-myst` command migrates legacy reST docstrings idempotently.
- **Every URL in a docstring is a link.** MyST's `linkify` extension is off, so a bare `https://…` renders as dead plain text on the manager pages and in the API docs alike. Write a titled markdown link (`` [`emerge(1)` man page](url) ``), keeping `]` and `(` on the same source line — a line break between them silently kills the link. A list of one reference is not a list: inline it as `Documentation: [title](url).` and keep the bullets for two or more. Bare URLs inside a fenced block are captured CLI output and stay untouched. The bundled TOML definitions need none of this: `_toml_definition_intro()` autolinks their description comments.
- Documentation in `./docs/` uses MyST markdown format where possible. Fallback to reStructuredText if necessary.
- Keep lines within 88 characters in Python files, including docstrings and comments (ruff default). Markdown files have no line-length limit — do not hard-wrap prose in markdown. Each sentence or logical clause should flow as a single long line; let the renderer handle wrapping.
- Titles in markdown use sentence case.
- **Heading anchors:** use the natural auto-generated anchor for cross-references; add explicit MyST anchors (`(my-anchor)=`) only when the natural one is unavailable (duplicate headings, non-heading targets).
- **Dataclass field docs:** In dataclasses, document fields with attribute docstrings (a string literal immediately after the field declaration), not `:param:` entries in the class docstring. Attribute docstrings are co-located with the field they describe, recognized by Sphinx, and stay in sync when fields are added or reordered. The class docstring should contain only a summary of the class purpose.

### Named constants

Do not inline a named constant during a refactor. It exists for readability and grep-ability, and in this codebase the grep is usually the point: `SHARED_LOCK_FAMILIES`, `CANONICAL_ATTRS`, `MANAGER_SECTIONS` and `MANAGER_LABELS` are each the single place a reader can enumerate a rule that is otherwise scattered across managers. When moving code between modules, carry the constant with it rather than replacing it with a literal at the call site.

### Workflow file naming

Related workflows share a prefix for visual grouping in the file listing: `tests.yaml` (unit/integration test suite) and `tests-install.yaml` (distributor installability tests). Apply the same pattern when adding new workflow files.

### Workflow source URLs

Each job that tests a third-party distributor must have a comment above it with the precise URL(s) to verify the package's status on that platform. Use the public-facing package page first (e.g., `formulae.brew.sh`), followed by the source definition (e.g., the GitHub-hosted formula `.rb` or manifest `.json`).

### Distributor sync

`docs/install.md` (the "Installation methods" tab-set), `docs/packaging.md` (the per-channel catalog and build instructions) and `.github/workflows/tests-install.yaml` must stay in sync. All three carry cross-reference comments. When adding or removing a distributor, update them together: every channel gets a full install tab, whose commands are the released one-liner once the channel ships and the condensed build recipe until then.

### Schedule-only workflows

Jobs that test *released* artifacts from external distributors (PyPI, Homebrew, Scoop, etc.) must not run on every push. They test the published version, not the code being pushed, so they belong on a schedule or manual dispatch only.

### Command-line options

Always prefer long-form options over short-form for readability when invoking commands in workflow files and scripts:

- Use `--output` instead of `-o`.
- Use `--verbose` instead of `-v`.
- Use `--recursive` instead of `-r`.

The same rule applies to every argv `mpm` constructs at runtime: the manager commands built by the manager classes and definitions, and the `sudo` invocations in `meta_package_manager/sudo.py` (`sudo --non-interactive --validate`, not `sudo -n -v`). Long forms make the `--verbosity INFO` command disclosure self-documenting.

## CLI output and logging

`mpm` keeps two output channels distinct: the **state** of an operation (printed with `echo`) and **log messages** (`logging`, gated by `--verbosity`).

### Verbosity tiers

The CLI defaults to `WARNING` (inherited from click-extra's `--verbosity` default). Classify every `logging` call into one tier:

- **`WARNING` (default view):** genuine problems only, such as failures with no other on-screen signal, the diagnosis tail of a failed command (its captured `<stderr>`, or `<stdout>` when that is empty; version probes and `doctor` exempt, see `_DIAGNOSIS_EXEMPT_OPERATIONS`), safety notices (cooldown safeguard skipped, a file about to be overwritten, a silent CLI call that may be hiding a `sudo` password prompt), the end-of-run "N managers reported errors" summary, and timeouts. Plus `critical` for fatal conditions. Keep it sparse.
- **`INFO` (narration):** the operational story, like the selection summary, install/dispatch priority, per-manager announcements, discovery (`X has been installed with Y`), capability skips (`X does not implement Y`), "ignoring option ..." no-ops, and every CLI invocation run on the system (the reproducible `$`-prompt line with forced environment variables, so the user can replay by hand what mpm does). Version-detection probes are the exception and stay at `DEBUG`: they are discovery, fired for every candidate manager, and would drown the narration.
- **`DEBUG` (technical):** raw CLI output (streamed live, line by line, the manager ID glued into the level prefix as `debug:<manager_id>:`), version-detection probes, result refiltering, manager-selection parsing, internal data dumps. Raw output stays at `DEBUG` even for mutating operations, deliberately: streaming it at `INFO` was assessed and dropped when issue 1938 closed satisfied without it, since line-pumped output cannot faithfully reproduce raw passthrough (each `\r` progress redraw becomes its own prefixed line) and would swamp the narration tier. A *failed* run is the exception: the tail of its captured output promotes to `WARNING` at the failure gate (issue 1968), because a failure's stderr is its diagnosis while a success's stderr is chatter, and a failed mutating operation cannot be re-run at `DEBUG` to regenerate it. If demand appears for watching live output *with* concurrency (`DEBUG` serializes to one worker via `serial_at_debug`), the lever is ready: `run_cli` takes a per-call `output_level`, gated on `_active_operation` in `CLIExecutor.run`.

Heuristic for a new line: if it narrates a decision, a step, or a command run on the system it is `INFO`; a raw mechanism or a command's output is `DEBUG`; something genuinely wrong **and** not already shown by the ✓/✗ trail is `WARNING`. "Your option had no effect here" is `INFO`, not `WARNING`.

A manager-scoped line passes `extra={"label": manager.id}` instead of naming the manager in the message: click-extra's formatter renders the ID glued into the level prefix (`warning:gem: Could not list installed packages.`), matching the streamed CLI output lines and making logs grep-able by manager. Keep the ID in prose only where it is the object of the sentence (`X has been installed with Y`) or names a config artifact (`No [gem] section found.`).

An enum surfaced in any message must render as its bare member name: give it `__str__`/`__format__` returning `self.name`. A functional `Enum("Operations", (...))` otherwise leaks the `Operations.outdated` repr where the message wanted `outdated`.

### Operation state: the ✓/✗ trail

Fan-out operations report state with a per-item `✓`/`✗` trail plus a persistent finisher, printed via `echo` to stderr, never `logging`. `echo` survives the `WARNING` default and is instead gated on an interactive terminal plus `--progress`, so pipes, CI and serialized runs stay clean.

Concurrency is decided by cross-manager *ordering*, not by whether a command mutates state. Three fan-out primitives, all bounded by `--jobs`:

- **Per manager, concurrent** (`meta_package_manager.dispatch.collect_from_managers`, one result per manager): commands whose work is independent and reported per manager. The read-only queries (`installed`/`outdated`/`search`), the maintenance commands (`sync`/`cleanup`/`upgrade --all`, which pass `report_state=True` since the trail is their only output), and the inventory exporters (`dump`/`backup`, `sbom`, which collect concurrently then assemble in manager order).
- **Per package, concurrent across managers and serial within each** (`meta_package_manager.dispatch.collect_per_package`, one result per (package, manager)): the ordering-free state changers `remove`, `upgrade <packages>`, `restore`, and the manager-tied specs of `install`. Managers run in parallel; one manager's own packages run one at a time, since a manager cannot safely run two of its own invocations at once (see `SHARED_LOCK_FAMILIES`).
- **Sequential** (`OperationTrail` in `dispatch.py`): only `install` when a package is left untied to a manager. Such a package needs a priority search (install with the first manager that has it, skip the rest), which is genuinely cross-manager-sequential. `warn_jobs_ignored` notes at `INFO` when an explicit `--jobs` is therefore ignored.

The shared-lock families that make within-family concurrency unsafe (`brew`/`cask` over Homebrew's update lock, `apt`/`apt-mint`/`deb-get` over dpkg, plus the RPM and pacman families) are catalogued in `dispatch.py`'s `SHARED_LOCK_FAMILIES`. The mutating fan-outs enforce them: `merge_into_lock_lanes` collapses each family into one `dispatch` lane, so its members run serially (one shared backend lock, never raced) while distinct families still run in parallel. The read-only queries take no backend lock and keep one lane per manager. A family lane also shares a command cache (`CLIExecutor.run_cache`), so members resolving to a byte-identical invocation (`brew`/`cask` both running `brew update` for `sync`) run the subprocess once. Adding a newly-conflicting set is a one-line edit: append a `frozenset` of ids to `SHARED_LOCK_FAMILIES`.

Trail conventions:

- Two shapes: **package-keyed** (`✓ foo installed with brew`, for `install`/`remove`/`upgrade <packages>`/`restore`) and **manager-keyed** (`✓ brew`, `✓ Synced N/M managers`, for `sync`/`cleanup`/`upgrade --all`). `cleanup` suffixes each manager line with the categories dispatched to it (`✓ brew (cache)`), since the per-manager subsets differ.
- The finisher counts **per (package, manager) attempt**, matching the trail lines: a package acted on by two managers is `2/2`, not `1/1`.
- A `✗` line is TTY-only, so failures also emit a `critical: Could not ...` (shown everywhere) as the durable record and the non-zero-exit rationale. Keep both despite the overlap on a TTY.

### Exit codes

Action commands (`install`, `remove`, `upgrade <packages>`, `restore`) collect per-package failures and exit non-zero with a `critical:` summary. `-0`/`--zero-exit` opts out of that gate (see `exit_on_failures` in `cli.py`): the summary still prints but the exit stays `0`; usage and configuration errors keep exiting `2` regardless. Maintenance commands (`sync`, `cleanup`, `upgrade --all`) are best-effort: they mark a failed manager `✗` but stay exit-`0`. `doctor` is the third contract: read-only, it relays each manager's native diagnosis verbatim to stdout (the one deliberate exception to the raw-output-at-`DEBUG` rule, as the report is the product and cannot be parsed), reads health from the diagnostic command's exit code alone, and exits `1` when any manager reports problems (`-0` opts out).

## Testing guidelines

- Use `@pytest.mark.parametrize` when testing the same logic for multiple inputs. Prefer parametrize over copy-pasted test functions that differ only in their data — it deduplicates test logic, improves readability, and makes it trivial to add new cases.
- Keep test logic simple with straightforward asserts.
- Tests should be sorted logically and alphabetically where applicable.
- Test coverage is measured with `pytest-cov` and gated by the `[tool.coverage] report.fail_under` ratchet, which the parallel non-destructive run of `tests.yaml` is the one slice expected to clear. Declare the floor there and nowhere else: a `--cov-fail-under` flag outranks the config, so the partial slices opt out with an explicit `--cov-fail-under=0` rather than the full run passing a value. Coverage is off by default locally, since `--cov` is passed by the workflow rather than sitting in `addopts`: a focused local `pytest` never trips the floor, and only a deliberate local `--cov` does.
- Do not use classes for grouping tests. Write test functions as top-level module functions. Only use test classes when they provide shared fixtures, setup/teardown methods, or class-level state.
- **A test class earns its place by sharing tests, never by grouping them.** `tests/test_cli.py` keeps exactly two template classes, `CLITableTests` and `CLIQueryTests`: each hands its subclasses a battery of inherited behavior tests (`--columns` projection, serialization across every format, query filtering) for the price of a `subcmd` fixture and a little per-command data (`columns_registry`, `columns_test_pair`). That much is the deliberate exception to the no-classes rule, kept by decision: dissolving it into a command×behavior parametrize was assessed and rejected, since it would pull each command's specifics out of the command's own file into a central cross-product harder to read and extend. Everything else is a function. A module inheriting no template writes plain module-level tests, the file being the grouping; shared assertion logic is a module-level helper (`check_packages_payload`, `check_filtered_ids`), and per-command parametrize data stays in the subcommand's own file.
- **The manager-selection strategy is an argument, not a base class.** `check_manager_selection()` takes the per-subcommand `signals` callable answering *"did this manager show up?"*, which each `test_cli_*.py` defines as a module-level `evaluate_signals()` and binds once with `check_selection = partial(check_manager_selection, signals=evaluate_signals)`, keeping call sites free of plumbing. It used to arrive through an `InspectCLIOutput`/`CLISubCommandTests` pair that shared no test at all: two `@staticmethod` helpers and an abstract strategy, delivered by inheritance and resolved through the MRO. The tell was `managers_table_signals()`, already a module-level function so two hierarchies could share it, wrapped by subclasses in a `@staticmethod` that forwarded to it. Selection itself is still exercised once, on a single subcommand, since the logic is shared, and a subcommand with no specific behavior needs no `test_cli_*.py` file at all.
- **`@pytest.mark.once` for run-once tests.** The `once` marker (declared in `[tool.pytest].markers`) tags tests that only need to run once, not across the full CI matrix. The matrix `tests` job filters them out with `pytest -m "not once"`, and the `once-tests` job of `tests.yaml` runs them on a single runner. Two modules carry it today, both via a module-level `pytestmark`: `tests/test_metadata.py` (which reads `pyproject.toml` and the generated matrix) and `tests/test_gnome_extension.py` (which asserts on checked-in extension sources). The admission test is coverage, not just OS-independence: a `once` module must import no package code beyond `__version__`, so moving it off the matrix cannot lower the slice that holds the coverage floor. A test that both covers `meta_package_manager` and reads only static files stays on the matrix.
- **Every destructive test declares its scheduling group.** The destructive CI step runs `--dist=loadgroup`, so a destructive test must resolve to an `xdist_group` in one of three ways: parametrize it with `manager_id` (the collection hook in `tests/conftest.py` then derives the group through `destructive_group()`, collapsing `SHARED_LOCK_FAMILIES` members onto one worker), mark it with an explicit `xdist_group` when its manager is hardcoded, or mark it `destructive_all_managers` when it drives every available manager at once, which routes it to the sequential cross-manager step. Collection fails on a destructive test with none of the three. `tests/destructive_plan.py` holds the whole plan those tests read (the per-manager package, the per-host blockers, the groups), keeping `conftest.py` to what the rest of the suite shares; its `DESTRUCTIVE_TEST_FAMILIES` records the suite-level conflicts the lock catalog cannot know about: managers whose round-trips install the same package into the same target.
- **The inherited battery runs on the fake pool, and both halves of that are enforced.** A CLI test gets the host's real managers by *omitting* `fake_pool`, so the expensive, host-dependent path is the one an author lands on by accident, multiplied by however many subclasses inherit it. That is how a fifty-format rendering test became three hundred real-pool invocations, two hundred and fifty of them byte-identical, with nothing in the run reporting it: duplicate work looks like coverage. So a template test whose subject is the *rendering* (table formats, serializers, column projection) takes `fake_pool`, which also makes it deterministic on a runner carrying nothing, while one whose subject is the *inventory* keeps the real pool and is named in `REAL_POOL_TEMPLATE_TESTS` (exactly one per format family, `test_json_output`, not one per format). `test_template_tests_read_their_subcommand` and `test_template_tests_default_to_the_fake_pool` hold both rules against every inherited test: a method that names its own subcommand belongs at module level, where it is collected once.
- **Write conformance tests when fixing a class of bugs.** For a bug that is a *category* rather than a one-off, add a generic test locking in the invariant: enumerate every member of the set (pool managers, generators, bundled TOML files, docstring corpus entries) and assert the property uniformly, failing with the violator's name. This is why `test_content_order`, `test_manager_changelog_entries` and `test_documented_output_still_parses` exist. Applies when the bug stems from a shared convention checkable from the codebase alone, with no fixtures or mocks.
- **CI-only pytest flags belong in workflow steps, not `[tool.pytest].addopts`.** Flags that emit CI-only artifacts (`--cov-report=xml`, `--junitxml=junit.xml`) pollute local runs when placed in `addopts`: keep `addopts` for flags that apply everywhere and pass CI-specific ones in the workflow `run:` step. Coverage settings (`run.branch`, `run.source`, `report.precision`) belong in `[tool.coverage]`, not in `--cov-*` flags.
- **Pass `encoding="UTF-8"` to `subprocess.run(..., text=True)` when output may contain non-ASCII bytes** (emoji in a workflow `name:`, accented author names, translated strings). `text=True` alone decodes with the platform default (`cp1252` on Windows), so such output raises `UnicodeDecodeError` only in Windows CI while passing on macOS and Linux. Test helpers shelling out to package managers or `git` are the usual offenders.
- **Pass an explicit encoding to every text-mode `open()`, `read_text()` and `write_text()` in tests, same as production.** The same Windows `cp1252` default applies to file I/O, and the failure stays hidden until the content grows its first non-ASCII character, which manager output and docstring samples do constantly. When a change touches file I/O, run the suite once with `PYTHONWARNDEFAULTENCODING=1` ([PEP 597](https://peps.python.org/pep-0597/)) to surface every bare call at runtime, on any platform: a linter misses the unannotated `Path` locals.
- **TTY-gated output needs a pseudo-terminal to test.** The `✓`/`✗` trail, finishers and spinners only render on an interactive terminal, so click-extra's `CliRunner` (non-TTY) never emits them — drive the CLI under `pty.openpty()` to exercise them. Most CLI tests instead assert on the stdout table, exit code, or an explicit `--verbosity`, none of which are TTY-gated.
- **`--dry-run` simulates read CLIs too.** It dry-runs *every* manager invocation, including the installed-package lookup that `remove`/`upgrade` use to find their source managers — so a dry-run of those reports "not recognized" and cannot exercise their multi-manager path. Reach for purls (which carry the manager and bypass the lookup) or unit fixtures instead.
- **`--plan` runs reads but captures writes.** The complement of `--dry-run`: plan mode executes the read-only queries (so `install`/`remove`/`upgrade --all` resolve their real source managers and targets), then records only the state-changing commands (`_MUTATING_OPERATIONS`) into `execution.PLAN_RECORDER` and prints them to stdout at context close, without running them. `force_exec` reads (version probes, `yarn global dir`) patch `plan` off and run for real. Test it against real reads or purls, and assert on stdout: the plan is plain `echo`, not the TTY-gated trail.
- **The suite is hermetic with respect to the host `mpm` config.** click-extra's default `--config` search resolves to the host config folder (`~/Library/Application Support/mpm` on macOS, `~/.config/mpm` on Unix). Any `config.toml` there would otherwise leak into every in-process CLI invocation: a local `cpan = false` drops the manager, so `check_manager_selection` assertions expecting the full default set fail locally while passing in CI. The `isolate_user_config` autouse fixture in `tests/conftest.py` repoints config discovery at an empty temp directory, so host config never reaches the suite. Tests that exercise config loading pass `--config <path>` explicitly, which overrides the default and is left unaffected.

### Choosing test-matrix targets

`repomatic metadata` builds the full and PR matrices from `[tool.repomatic.test-matrix.*]`, whose every deviation from the defaults is commented in `pyproject.toml`. `tests/test_metadata.py` turns a matrix that drifts from `requires-python` into a failing check. The selection conventions:

- **Spread the OS axis, not the Python one: they answer different questions.** Every OS and architecture keeps a cell, since `mpm` drives a different set of managers on each and that spread is the product. Python version is interpreter compatibility, which is OS-independent, so the floor (`3.10`), the prerelease (`3.15`) and the free-threaded build (`3.14t`) each run on the single fastest runner (`ubuntu-26.04-arm`) while every other OS runs the ceiling alone. Linux hosts the floor because Linux is where a floor interpreter is actually used: distribution packagers build against whatever their channel ships, where macOS and Windows users install a Nuitka binary carrying a pinned one. The full cross-product was measured before being cut: across the 40 most recent `tests.yaml` runs, of the eleven with a failing cell, none failed on an OS whose *other* Python version passed, so the per-OS pairs cost 158 runner-minutes a push and caught nothing their survivor would have missed. Re-measure with the same question before widening it again, and note the one thing the pairs did give away for free: a single-cell failure no longer has a same-OS twin to tell a real bug from a host artifact, so diagnose one by re-running rather than by assuming.
- **Pin the dependency floor, and any release a workaround targets.** The floor of a supported range belongs in the matrix as an explicit value, along with any mid-range release a shim works around: that is the version that catches the shim regressing.
- **Select runners by measured speed and workload, not architecture.** Where one fast runner suffices, `ubuntu-26.04-arm` is the fastest and cheapest tier (upstream measured ARM Linux 2-3x faster than the retired lean x86 image) and hosted macOS bills about ten times Linux, so macOS and Windows cells are reserved for the manager coverage only they add. `remove.os` drops the slower twin of an OS pair. Every runner literal stays within repomatic's curated axes (`KNOWN_RUNNERS`): `lint-repo` flags anything outside them, and actionlint validates the labels themselves against repomatic's bundled `actionlint.yaml`, which declares the Ubuntu 26.04 preview pair that actionlint `1.7.12` predates. Declaring a `[tool.actionlint]` section here would *replace* that file rather than extend it, so a local label means restating every label repomatic ships and forfeiting the ones it adds later. The one deliberate exception is `check-void-deps.yaml` on `ubuntu-22.04`, pinned by its apparmor comment.

## Design principles

### Keep logic in Python, not workflow YAML

Push anything beyond trivial wiring out of workflow YAML and into the package or its tests. Rather than duplicating an `if:` condition across steps, compute it once and reference the result. Rather than asserting a project invariant with `grep` in a `run:` block, write the test: `tests/test_docs.py` and `tests/test_metadata.py` hold contracts that a shell one-liner would have expressed worse and silently stopped checking. A tested generator that fails loudly beats a static artifact that can drift.

The corollary bounds how much a workflow may know: `tests-install.yaml` is long because each distribution channel genuinely needs its own install incantation, not because logic accumulated there.

### Defensive workflow design

GitHub Actions workflows face race conditions, eventual consistency and partial failures, and this project adds a second layer of flakiness on top: every job drives real package managers against live third-party feeds. Prefer belt-and-suspenders, several independent correctness mechanisms over one guarantee. When a step depends on external state (a CDN, an upstream release, a snap store), add a retry or a graceful default and say in a comment what transient failure it absorbs. The `choco upgrade all` and `snap install code` steps of `tests.yaml` are the models.

Distinguish absorbing a flake from hiding a failure: a forced `exit 0` belongs on setup that is best-effort by nature, never on the assertion the job exists to make.

### Single source of truth for defaults

Every configurable default lives in exactly one place, and all other code derives it rather than repeating the literal. When adding one, grep for the value and point every other occurrence at the source. The cases already carrying this weight are worth knowing, since each has a test holding it: the coverage floor in `[tool.coverage] report.fail_under`, the cooldown window in `[tool.repomatic] minimum-release-age`, the manager pool in `meta_package_manager/pool.py`, and the page layout in `MANAGER_SECTIONS`.

### Ordering conventions

Keep definitions sorted for readability and to minimize merge conflicts:

- **Workflow jobs**: Ordered by execution dependency (upstream jobs first), then alphabetically within the same dependency level.
- **Python module-level constants and variables**: Alphabetically, unless there is a logical grouping or dependency order. Hard-coded domain constants should be placed at the top of the file, immediately after imports. These constants encode domain assertions and business rules — surfacing them early gives readers an immediate sense of the assumptions the module operates under.
- **Manager class members**: The canonical declaration order (identity, escalation policy, requirement, CLI plumbing, version probe, toggles, then methods in base-class order) is the `CANONICAL_ATTRS` tuple in `tests/test_managers.py`, enforced by `test_content_order`. Manager-specific constants (the `_*_REGEXP` parsers) conventionally sit between the attributes and the operations.
- **YAML configuration keys**: Alphabetically within each mapping level.
- **Documentation lists and tables**: Alphabetically, unless a logical order (e.g., chronological in changelog) takes precedence.

### Issue and PR labelling

The content and file rules generated into `pyproject.toml` from `meta_package_manager/labels.py` only *pre-label* a freshly filed issue or PR: they save the maintainer a first pass, never replace the manual review and classification, and nothing downstream treats them as authoritative. Tune for **precision, not recall** — encode a rule only when the signal is unambiguous, and none when it is not (that manager is then labelled by hand).

- **Content rules** come only from `MANAGER_CONTENT_KEYWORDS`: ecosystem, distro, language or brand names that unambiguously name the manager *and* never appear in mpm's own output. Never the manager ID or a CLI name — mpm prints those for every installed manager (the `✓ <id>` trail, the `<id>: <count>` summary, the `managers` table), so a pasted trace would tag the issue with every manager on the user's system. A manager whose only name is its ID gets no content rule.
- **File rules** map each manager's own module and test paths to its label; keep them narrow enough that only that manager's files match.

The `generate_content_rules` docstring covers the regex mechanics (anchoring, case-folding, why a label's keywords are OR-joined into one pattern). This is the local instance of the labeller principle in repomatic's `claude.md`.

### Common maintenance pitfalls

- **Documentation drift** is the most frequent issue. CLI output, version references, and workflow job descriptions in `readme.md` go stale after every release or refactor. Always verify docs against actual output after changes.
- **Module refactors strand fully-qualified docstring cross-refs.** Moving an attribute between classes or modules (like the `7.3.0` split that moved `cli_path` and `version` onto `execution.CLIExecutor`) silently breaks every `` {attr}`x <old.path>` `` pointing at the old home, and the docs build only warns, never fails. After a move, grep the whole tree for the old dotted path. The same sweep rule applies when docstrings gain a new rendering surface (like the manager pages): one malformed fence, glued bullet list, or stale ref found means the whole corpus needs a sweep for that defect class, not a spot fix.
- **CI debugging starts from the URL.** When a workflow fails, fetch the run logs first (`gh run view --log-failed`). Do not guess at the cause; when the user points to a specific failure, diagnose that exact one.
- **Trace to root cause before coding a fix.** Audit a bug's scope before writing the patch. If the same pattern appears in multiple places, fix it at the shared layer; if only one call site is affected, check whether the data is on the wrong code path before handling it where it lands.
- **Never reformat a hand-maintained table with an ad-hoc `mdformat`.** Several tables are parsed back by tests and generators against the exact row shape checked in, so a reformat that re-pads every cell reports as a content failure rather than a formatting complaint: `test_unsupported_page_matches_benchmark` used to match `docs/unsupported.md` rows with a padding-sensitive regex and answered "no manager rows found" when the table was realigned. That page is sections now, but `docs/cooldown.md` still feeds the per-manager pages through `_cooldown_table()`. The repository pins no `mdformat` configuration of its own (the `format-markdown` job upstream owns it), so a local run resolves different defaults and different plugins than CI. Edit a table row by copying the padding of the row above it, and leave the rest of the file untouched: the diff stays three lines instead of a hundred and fifty, and nothing downstream breaks.
- **Angle-bracket placeholders in bash code blocks.** `mdformat-shfmt` runs `shfmt` on fenced ```` ```bash ```` blocks, and `shfmt` parses `<foo>`/`>foo` as redirection and reorders the command. Use curly braces (`{foo}`) for placeholders in bash examples.
- **Type-checking divergence.** Code that passes `mypy` locally may fail in CI where `--python-version 3.10` is used. Always consider the minimum supported Python version.
- **`[[tool.repomatic.labels.extra]]` must stay the last array-of-tables of `[tool.repomatic]`.** `docs_update.update_labels()` drops the labels subtree and re-appends it at the end of the section, and `test_pyproject_updates_are_pyproject_fmt_fixpoint` fails on any array-of-tables sitting after it. A config wanting an array-of-tables shape goes in as an inline array value instead: `[tool.repomatic.metrics] charts` is one.
- **Simplify before adding.** When asked to improve something, first ask whether existing code or tools already cover the case. Remove dead code and unused abstractions before introducing new ones.
- **Route through existing infrastructure, don't bypass it.** Before writing a new helper or merge function, check whether the codebase already handles the operation. A bug from data on the wrong code path is better fixed by routing it correctly than by duplicating logic at the wrong site.
- **click-extra extension validators only see dict sub-trees.** The opaque `[mpm]` extension sections (`MpmConfig`'s mapping-typed fields: `managers`, `cooldown`) are forwarded to their `ConfigValidator` only when the value is a table; a string-shaped legacy value never reaches the validator, while the runtime path reading `CONF_FULL` sees every shape. Anything handling a deprecated or non-table spelling, a migration warning in particular, therefore belongs at runtime (the `mpm` group body is where the cooldown one lives), not in the validator.
