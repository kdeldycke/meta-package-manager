# CLAUDE.md

Project-specific guidance for working in this repository. The generic coding conventions load from the maintainer's machine configuration and are deliberately not duplicated here: this file carries only what is specific to `mpm`, and only what has no closer home.

## Project overview

Meta Package Manager (`mpm`) is a CLI that wraps multiple package managers (Homebrew, apt, pip, npm, etc.) behind a unified interface. It can list, search, install, upgrade, and remove packages across all supported managers simultaneously, and snapshot the whole inventory to a single file that restores it on another machine.

## Upstream conventions

This repository uses reusable workflows from [`kdeldycke/repomatic`](https://github.com/kdeldycke/repomatic) and follows the conventions established there. Propose a gap or an improvement in those workflows at [`kdeldycke/repomatic`](https://github.com/kdeldycke/repomatic/issues).

## Where the rules live

Each rule sits beside the code or the page it governs: a docstring, a comment, a test or a docs page. Read the home of an area before an edit in that area. A new rule goes to its home, and this file gets one row at most.

| Area                                                                           | Home                                                                                       |
| :----------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------- |
| Development commands, stability policy                                         | `docs/contributing.md`                                                                     |
| New manager, declined tool, manager docstrings, argv conventions               | `.claude/skills/add-manager/SKILL.md`                                                      |
| Manager attributes, `unmaintained` policy                                      | `meta_package_manager/manager.py`                                                          |
| Docs generators, mirror regions, glyph scale, page layout (`MANAGER_SECTIONS`) | `meta_package_manager/_docs.py`                                                            |
| Docstring fixtures: `shell-session` against `console`                          | `meta_package_manager/docstring_corpus.py`                                                 |
| Fan-out, lock families (`SHARED_LOCK_FAMILIES`), `✓`/`✘` trail                 | `meta_package_manager/dispatch.py`                                                         |
| Spinner, live line, timeouts, `--plan` capture                                 | `meta_package_manager/execution.py`                                                        |
| Logging tiers, exit codes                                                      | `meta_package_manager/cli.py`                                                              |
| Cooldown vocabulary of the product                                             | `meta_package_manager/cooldown.py`, `docs/cooldown.md`                                     |
| Labels and labeller rules (`MANAGER_LABELS`)                                   | `meta_package_manager/labels.py`                                                           |
| Brewfile export                                                                | `meta_package_manager/brewfile.py`, `docs/dump.md`                                         |
| Benchmark data and cell evidence                                               | `docs/benchmark.toml`, `docs/benchmark.md`                                                 |
| Packaging channels, install tabs, distributor jobs                             | `docs/add-packaging-channel.md`, `.github/workflows/tests-install.yaml`                    |
| Brand assets, vendored logos                                                   | `docs/brand_update.py`, `docs/logos_update.py`                                             |
| Captured screenshots                                                           | `.github/workflows/docs-screenshots.yaml` and its two drivers in `docs/`                   |
| Test suite conventions                                                         | `tests/__init__.py`, `tests/conftest.py`, `tests/test_cli.py`, `tests/destructive_plan.py` |
| Manager member order (`CANONICAL_ATTRS`)                                       | `tests/test_managers.py`                                                                   |
| Test matrix, coverage floor                                                    | `pyproject.toml`                                                                           |

## Cooldown on every install

`mpm --cooldown` applies the same idea to a different subject, and the two are easy to conflate here. That flag is a user-facing feature, gating the packages `mpm` installs on the user's machine, and `docs/cooldown.md` is its documentation and its inventory of managers. This section covers what CI resolves onto a runner while building `mpm` itself. A comment or changelog entry naming one should not read as the other.

### Documented exemptions

Three installs deliberately bypass the window:

- **The upstream toolkit's own pin.** Every `uvx` call carrying the `repomatic` pin passes `--exclude-newer-package repomatic=P0D` beside it: the pin moves in lockstep with the `uses:` refs, so a release must install the minute it is published.
- **A fresh click-extra or extra-platforms, on the day it ships.** Both share a maintainer with `mpm`, and most `mpm` releases raise one of their floors. `[tool.uv] exclude-newer-package` names the package with the midnight following its upload, an absolute timestamp that covers that release and nothing after it. The entry is transient: repomatic's `sync-uv-lock` prunes it once the release ages past the window.
- **The `tests-install.yaml` workflow.** Its subject is the freshly published artifact. Its header comment holds the rationale.

## Documentation conventions

- **Example data.** Do not reach for software-engineering or packaging vocabulary for a placeholder, and never invent a plausible-looking package or manager name: this project's whole domain is package metadata, so a made-up `foo-lib 1.2.3` in a docstring is indistinguishable from a real fixture and will eventually be read as one. The `[samples]` fixtures and the harvested `shell-session` blocks are captured CLI output: those are data, not examples.
- **Changelog scope tags.** Every bullet of `changelog.md` opens with a `[scope]` tag that selects the pages it renders on. The docstring of `scope_changelog()` in `meta_package_manager/_docs.py` holds the rules to choose one.
- **`readme.md`.** Update the relevant section when a change reaches the public surface.
- **Generated content.** Never edit by hand a stub of `docs/managers/` or a `<!-- mirror -->` region: `docs/docs_update.py` and `click-extra refresh-directives` own them.
- **Manager IDs link to their pages.** A manager named as a code span in `docs/*.md` links to its own page, once per paragraph: a name repeated in the next sentence stays plain, and an enumeration is uniformly linked. Three places keep the bare span: a heading, where a link would rewrite the anchor other pages cross-reference; the column headers and competitor cells of the benchmark, which name rival tools; and the `docs/cooldown.md` cells that the manager pages reuse verbatim, where a relative target lands nowhere.

## Code conventions

- **Commit prefix.** A `[bracketed]` commit prefix is reserved for a mechanism that parses it back, and only `[changelog] …` qualifies, matched literally by repomatic's auto-tagging job. The `[scope]` tags of `changelog.md` are an unrelated vocabulary.
- **Workflow file naming.** Related workflows share a prefix for visual grouping in the file listing: `tests.yaml` and `tests-install.yaml`. Apply the same pattern to a new workflow file.
