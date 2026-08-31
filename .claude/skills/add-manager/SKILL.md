---
name: add-manager
description: Implement support for a new package manager in mpm, or complete a partial integration. Covers vetting the candidate, choosing between a Python class and a declarative definition, mapping operations, the cross-file checklist, and validation. Use when wrapping a new tool, finishing a half-wired manager, or recording why a tool was declined.
compatibility: 'Designed for Claude Code. Recommended model: Opus.'
allowed-tools: Bash Read Write Edit Grep Glob WebFetch WebSearch Agent
argument-hint: '[manager name or GitHub issue URL]'
---

# Add a new package manager

`$ARGUMENTS` names the manager to wrap, or the GitHub issue requesting it.

Implement support for a new package manager in `mpm`, or complete an incomplete integration. If adding a manager requested via a GitHub issue, extract CLI output samples from the issue body to guide the implementation.

## Confirm the tool is a candidate

Not everything that installs software is one. Two grounds disqualify a tool outright, whatever its popularity, and neither is a judgement about effort:

- **A dead upstream.** The stability policy flags an abandoned manager `unmaintained`, hides it from default selection, drops it from the test matrices and eventually removes it altogether. A wrapper written for an already-retired tool starts at the end of that lifecycle, so it is not written.
  **Almost no project announces its own death, so measure the silence instead of waiting for a statement.** Requiring an explicit discontinuation notice leaves a tool unassessed forever: of six checked this way, none published one and five were plainly retired. Read the newest artifact the project actually produces, and dig past the front page into the repository, its issues and its pull requests. Enthought Canopy's newest release note is dated 23 April 2018, `apt-rpm` last released in 2006, and `openpkg.org` now answers with an expired TLS certificate. Any of those settles it where a notice never comes.

  **Measure before believing a record that calls something dead.** Re-checking one list of "long dead" tools found five alive, including two live distribution package managers, `netpkg` and `upkg`, whose distributions had shipped releases within the year. A verdict inherited from a catalogue or an earlier pass is a lead, not a fact.

- **No registry of its own.** A tool that merely unifies syntax or declarations across other package managers reaches no package `mpm` cannot already reach through the backend it wraps directly, so wrapping it buys a translation or reconciliation layer and not one extra package. This is what rules out the declarative multi-backend managers (`metapac`, `decman`, `declaro`) and the syntax shims (`upt`) — several of them actively developed. Such a tool may still deserve a *benchmark column* as a peer of `mpm`; that is a separate question from wrapping it.

Target the live end of a lineage rather than whichever name is most familiar. Shougo's Vim managers ran `neobundle` → `dein` → `dpp.vim` before Neovim absorbed the job into core, and `mpm` wraps `vim-pack` alongside `lazy`; on the Zsh side `antibody` gave way to `antidote`, which `mpm` wraps next to `zinit`. Siblings are not a lineage: two live tools serving one ecosystem are each judged on their own, and wrapping one says nothing about the other. A lineage can also fork, and then each successor is judged separately: packer.nvim's unmaintained notice names both lazy.nvim and pckr.nvim.

That fork is the worked example of the criterion that decides an editor or shell plugin manager, since neither ships a package database `mpm` can query directly. Ask whether the tool can be driven to completion with nobody at the keyboard. lazy.nvim can, through a headless Neovim plus a JSON lockfile listing installed plugins without starting the editor, which is why it is wrapped. pckr.nvim cannot, and the way it lost the ability is the lesson: packer.nvim documented a headless recipe closing on a `User PackerComplete` autocommand, and the rewrite emits no autocommand at all, so nothing signals completion, while removal blocks on an `OK to remove? [y/N]` prompt and the lockfile is opt-in, Lua rather than JSON, and keyed by URL. A request for a synchronous entry point was closed with a redirect to `config` and dependencies ([lewis6991/pckr.nvim#12](https://github.com/lewis6991/pckr.nvim/issues/12)). `dpp.vim` cannot either: its work runs in a Deno process the editor starts, with no headless entry point documented at all. Design that entry point in from the start when proposing a manager upstream; retrofitting one meets resistance.

**Ask whether the headless path is a stated contract or an accident of the current implementation, and re-check it after any upstream rewrite.** packer.nvim's was as deliberate as they come, a recipe in its own readme, and it still did not survive the rewrite that replaced it, so a successor inherits nothing here and has to be assessed from zero. `micro` is the shape to look for: its help states the plugin manager is invoked "with the `> plugin ...` command, or in the shell with `micro -plugin ...`", so the shell path is something upstream committed to rather than a flag that happens to be handled before the screen initializes. Where a wrap has to rest on incidental behavior instead, say so in the class docstring, so that the next failure is read as an upstream change rather than a parser bug.

**A candidate is not required to support every operation.** Inventorying and updating are enough on their own, and a missing `install` disqualifies nothing. That pair already beats what the competing wrappers do for the same tools, which is a coarse upgrade of a whole category with no listing at all, so wrapping at that level turns an opaque bulk update into something a user can inspect. `topgrade` is wrapped on `upgrade_all` alone, and `lazy` on inventory plus update: lazy.nvim materializes only the plugin set the user's own Lua configuration names, so an `install` would mean `mpm` editing configuration it does not own. Declare the operations the tool genuinely supports, let `mpm` auto-skip the rest, and record in the class docstring why each absent one is absent. Never fake an operation with a mutating command.

**There is a floor under that, and `topgrade` is where everything below it goes.** `topgrade` sits in the pool precisely as the catch-all for tools too thin to wrap on their own: it auto-detects and upgrades whatever it finds on the host, so every tool it drives is already reachable through `mpm upgrade --topgrade` without `mpm` learning any of them. That makes it the sinkhole, and it changes what a marginal candidate has to prove.

Apply the test in this order:

1. **Does the candidate offer an inventory?** If it can list what it has installed, wrap it. That is the one thing `topgrade` categorically cannot do for any tool, having no listing at all, so the inventory is the whole gain and a missing `install`/`remove`/`outdated` does not diminish it. This is why [`lazy`](managers/lazy.md), [`vim-pack`](managers/vim-pack.md), [`zim`](managers/zim.md) and [`zplug`](managers/zplug.md) are wrapped on inventory plus update.
2. **If not, does it offer any per-package operation?** A tool with no listing but real `install` or `remove` verbs still reaches packages one at a time, which `topgrade` cannot. [`steamcmd`](managers/steamcmd.md) is wrapped on `install` alone on those grounds, and [`sheldon`](managers/sheldon.md) on `remove` plus update.
3. **If neither, and `topgrade` already drives it, decline.** A wrapper whose entire honest surface is `upgrade_all` buys one more way to run an upgrade `mpm` already reaches, at the cost of a full manager's checklist and its ongoing maintenance. `zr` is the worked example: plugins are the arguments you hand it, so it owns no inventory, and `zr --update` is already inside `topgrade`'s catalog.

Check `docs/benchmark.toml` before leaning on step 3: it is only an argument for tools `topgrade` actually covers. A thin tool `topgrade` does *not* drive reaches nobody, and is judged on its own merits.

Three further requirements are enforced in code. They are not preferences: a tool that cannot clear them cannot be wrapped in the current architecture, however much work is thrown at it.

| Requirement          | Enforced by              | What it rules out                                                                                                      |
| :------------------- | :----------------------- | :--------------------------------------------------------------------------------------------------------------------- |
| An executable CLI    | `CLIExecutor.executable` | A tool shipped only as a file meant to be *sourced*, with no binary anywhere and no interpreter to key the manager on. |
| A reportable version | `PackageManager.fresh`   | A tool that reports no version through any binary: without one the manager is never considered available.              |
| System scope         | `ManagerScope.SYSTEM`    | A tool whose packages live inside one project tree rather than on the machine.                                         |

The first two have escape hatches worth trying before declaring a tool impossible. A shell-function manager can key on the interpreter that runs it instead of on its own sources: `zinit` and `antidote` are both wrapped that way, with Zsh as their CLI and their version probe doubling as the presence check. Check the file mode before assuming otherwise, since a shebang is not an executable bit: `antidote` ships its CLI mode `644` and Homebrew installs it as package data under `share/`, never linking it into `bin`. A manager whose own binaries expose no version can name a companion binary through `CLIExecutor.version_cli`.

Keying on a shared interpreter raises a second problem, which that same probe solves. Two managers may legitimately want the same binary: `vim-pack` and `lazy` both run `nvim`. What separates them is that each probe reports a version only once its own tool is found, `lazy` by testing for the lazy.nvim checkout before putting it on the runtime path, so a host with a bare editor leaves it unavailable rather than shadowing every machine that has one. Guard the probe so an absent tool exits cleanly and prints nothing, instead of raising.

dein.vim is the worked example of both hatches failing, and the shape to compare a candidate against. It is Vimscript with no binary anywhere, and nothing to test for that would make an `nvim` or `vim` probe conclusive the way `lazy`'s is. It reports no version either: `g:dein#_cache_version` is an internal state-format counter, and its releases are Git tags on a checkout the user places freely.

When a tool is rejected, record the decision rather than leaving it implicit: add a section to `docs/unsupported.md` and an entry to the `unsupported` table of `docs/benchmark.toml`. Title the section with the tool as a linked code span followed by its glyphs (`` [`paq`](https://github.com/savq/paq-nvim) ❌ 🛟 ``), and keep the page sorted by title. Sort the key against the whole list rather than eyeballing the line above it: the `unsupported` table of `docs/benchmark.toml` sorts by manager id while the sections of `docs/unsupported.md` sort by *title*, so `topgrade` precedes `tpack` on the page while `toolbx` precedes `tpack` in the table, and a family section titled after its family sorts under that title rather than under any member. Both orderings are asserted by `tests/test_docs.py`. Where an existing section already carries that verdict word for word, add the tool to its member list instead of copying the paragraph. The benchmark then renders a `❌` linking straight to that section instead of a blank cell. That changes the rendered table, so run `click-extra refresh-directives readme.md docs` afterwards or `test_mirror_blocks_in_sync` fails: a decline is never a docs-only edit.

**Every tool assessed gets one of the two outcomes, always.** Wrapped, or written down as unsupported with a rationale. Nothing is left in between, including a tool waved off in passing during a discussion: that is still a decision, and an unrecorded one is indistinguishable from an unexamined one. The target is total coverage of everything that installs software, so a blank benchmark cell is a gap to close rather than a neutral state, and "not worth wrapping" is a rationale to write out, not a reason to skip the row.

Ground the reason upstream whenever the blocking behavior has been raised there. Search the tool's tracker for the missing capability and link what you find: a feature request closed not-planned, a maintainer stating the position, or an open request left unaddressed for years. Quote the deciding sentence and anchor the link on the exact `#issuecomment-<id>` when a comment is what settles it, exactly as the benchmark's `❌` cells do. `zgenom` is the worked example: its decline rests on reporting no version, and the request to tag releases was closed on the maintainer's own "*I consider everything merged into main as a stable release*". That turns a verdict a reader has to trust into one they can audit, and it dates the decision, so a tool whose upstream later changes course can be reassessed against the same link. When no such discussion exists, say so rather than implying one: an absence that is deliberate design (`zr` treats plugins as arguments and so owns no inventory) is itself the reason.

## Drive the tool before writing it

Install the candidate, run every verb, capture the output. This is the step that pays: `bob`'s catalogue omission, `spack`'s environment scoping and `getnf`'s colour handling were each invisible from the documentation, and each would have shipped a broken definition. Documentation is a starting point, never the authority.

**Read the argument parser, not the readme.** Where a tool ships its parser in one readable file, that file is what settles the verdict. `pkgit`'s readme lists neither `--version` nor `--list` while `src/parse_args.c` handles both, so a readme-only reading would have declined a genuine candidate twice over. `choosenim` and `gup` are the same shape: `gup update <name>` runs although its own usage line documents `gup update [flags]` alone.

**Check what the competitor actually drives before trusting a home page.** A benchmark row's URL can name a different project entirely: the `voom` row linked a Vim outliner that installs nothing, while `topgrade`'s `run_voom` requires a `voom` binary and runs `voom update`, which is [airblade/voom](https://github.com/airblade/voom). Reading the competitor's own step source settles it in one call.

Run the candidate under a **repointed `HOME`** so its state never lands on the real machine, and know what that does and does not buy:

- **Not every tool honours it.** `bob` resolved its data directory to the real `~/.local/share/bob` regardless, and `roswell` reads and writes `~/.roswell` whatever `$HOME` says: 37 MB and 248 MB respectively, on the actual machine. Check where a tool reports installing before assuming the sandbox held, and check `PATH` too, since `0install` wrote its launcher into the first writable `bin` it found.
- **A repointed `HOME` silently disables the cooldown safeguard.** A host config setting `cooldown` fail-closes managers that cannot enforce it natively; under a scratch `HOME` no config is found, so an install succeeds where a real user would be refused. Verify both ways, or at least know which one produced the green.
- **A long scratch path breaks tools with a socket under `$HOME`.** `0install` failed on `can't connect to the keyboxd: File name too long`, which is the path overflowing the Unix socket limit rather than anything about the tool. Drive from a short path such as `/tmp/mpm-drive`.
- **A GPG-verifying tool needs the command sandbox off.** Past the path limit, the same tool failed on `IPC connect call failed`, because the sandbox blocks the socket `keyboxd` listens on, leaving every feed signature unverifiable. The symptom names the daemon, never the sandbox.
- **A downloaded release binary cannot be made executable** where `chmod` is denied, so that route dead-ends at a `644` file. Prefer a channel that sets the bit itself: `pkgx <tool>` runs anything in its pantry, and `go install <module>@latest` writes an executable binary, which is how `zvm` was wrapped after being abandoned once on exactly this. Check whether a blocked candidate is written in Go before recording it as undrivable.

**Fixtures come from that driving and nowhere else.** Never invent a sample and never trim one: a `shell-session` block is a complete capture that has to parse through the manager's own parser. Where a needed state is missing, create it for real. `getnf`'s `unknown version` row came from deleting a release marker, `elan`'s orphan report from clearing `default_toolchain` out of elan's own settings, and `gup`'s outdated fixture from downgrading a binary to an older tag.

**A tab-indented fixture cannot survive in a docstring.** `ruff format` rewrites a docstring's indentation, so a leading tab reaches the corpus as spaces and a parser keyed on `\t` at line start fails only *after* the formatter runs. `go`'s listing hit this: its parser now ignores leading whitespace and keys on the field separator instead. Run the formatter before trusting a green corpus test, and prefer a parser that does not depend on how a line is indented. A bundled TOML definition is immune, its samples living in the TOML file rather than in Python.

## Choose an implementation strategy: class-based or config-based

Before writing anything, decide how the manager will be implemented. `mpm` supports two paths:

- **Class-based:** a Python module in `meta_package_manager/managers/`. Full power: multi-line or stateful output parsing, version pinning, per-operation search flags, conditional `sudo`, delegation, arbitrary logic. It is the most capable path, and what the rest of this document describes.
- **Config-based:** a declarative `[mpm.managers.<id>]` block that `mpm` turns into a live manager at startup, with no Python (documented in {doc}`/overrides`, "Define a new manager"). Quick to write, but constrained: each operation is a fixed argument list, and listings must parse either line-by-line with a single regex or as one flat top-level JSON array. The DSL covers sibling binaries (a per-operation `cli` key), unconditionally privileged operations (a per-operation `sudo = true` key plus a manager-level `default_sudo`), and version probes on a companion binary (`version_cli`, for suites versioned with the OS). A definition can live two places: in a user's own trusted configuration file (a private, per-machine manager), or bundled with `mpm` as read-only package data (a manager shipped to every user, like a built-in). The bundled path is how `mpm` distributes a simple manager as data instead of code.

Reach for config-based **only when every one of these holds**. If any fails, the manager needs a class:

| Requirement                                                                                                                | Rules out config-based when                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| :------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A version command prints a regex-extractable version string, on the manager's own CLI or a `version_cli` companion binary. | No binary reports a usable version at all (like macOS `msupdate`).                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `installed`, `outdated` and `search` each emit one package per line, or one flat top-level JSON array.                     | Records span multiple lines (`pacman -Ss`, `cabal list`, Solaris `pkginfo -x`) or the JSON is an object keyed by package or environment name (`mise`, `pixi`, `pnpm`).                                                                                                                                                                                                                                                                                                                    |
| One command per operation fully populates each package record.                                                             | A record needs enriching through a second, per-package call (`pacstall --cache-info` to fetch a version the listing omits): one operation is one command, so the DSL cannot chain the follow-up. A name-only listing is fine on its own (`apt-cyg list`, `swupd bundle-list`): `installed_version` is optional, so `mpm` yields those packages without a version.                                                                                                                         |
| Every mutating operation is one argument list with `{package_id}` or `{query}` substituted in.                             | An operation needs *conditional* `sudo` (static `sudo = true` is fine), delegation, or output post-processing. Query operations never escalate, so a listing that needs root (`deb-get`'s outdated piggybacks on `sudo deb-get update`) also rules the DSL out.                                                                                                                                                                                                                           |
| Every declared operation reports through stdout on a zero exit.                                                            | An operation signals its result through a *non-zero* exit or writes its payload to stderr. A definition parses stdout on a zero exit and can express neither, so one such operation pulls the whole manager into a class: `bin`'s `update --dry-run` exits `3` with the report on stderr, and `gext`'s exits `17` with it on stdout. Check the exit code of every "what would change" command before assuming it is declarable, since both of these look like ordinary queries until run. |
| The manager installs globally.                                                                                             | Packages are scoped to an activated project or environment (`flox`; `cabal outdated` is project-only).                                                                                                                                                                                                                                                                                                                                                                                    |
| Version pinning and native exact/extended search filtering are both unnecessary.                                           | The manager's whole point is selecting versions, or search must be resolved exactly server-side.                                                                                                                                                                                                                                                                                                                                                                                          |
| No cooldown machinery is wanted.                                                                                           | The tool ships a native release-age knob (`cooldown_env_var` is class-only) or qualifies for the per-package probe of `release_date()`: the DSL's one cooldown key is `cooldown_policy`, so a config-based manager is always ungated under `--cooldown`.                                                                                                                                                                                                                                  |

Config-based skips the class machinery: no Python module, no `pool.py` registration, no version pinning or delegation. A private definition needs nothing beyond your own config file; shipping one bundled adds only a short metadata checklist (see below). Reach for a class when the manager needs power the DSL cannot express, and upstream it if it would help others: {doc}`/overrides` and {doc}`/security` explain why a reviewed, shipped manager beats executable configuration.

Whatever the path, identify the tool's escalation model before mapping operations — each demands a different treatment:

- **Plain root-requiring** (most system managers): mark mutating operations privileged (`sudo = true` in a definition; `run_cli(..., sudo=True)` plus `default_sudo = True` in a class).
- **Self-escalating** (fink re-execs itself under `/usr/bin/sudo` and no-ops when already root): never mark operations privileged, or sudo stacks on sudo.
- **Broker-based** (pkcon hands transactions to a polkit-authorized daemon): no escalation at all; note that unattended runs depend on the broker's policy.
- **Root-refusing** (chromebrew hard-aborts as root): no escalation, and never wrap in sudo manually.

Also check whether the `platforms` tokens exist in extra-platforms (`VALID_PLATFORM_TOKENS` accepts any platform or group ID). A missing distro detection is an upstream extra-platforms addition (same author): land it there, track git main via `[tool.uv.sources]` until the release, then relax to the PyPI floor. The new-manager issue template's platform checklist derives from `MAIN_PLATFORMS` and is enforced by `test_new_package_manager_issue_template`, so regenerate it when platforms land.

## Config-based managers

The declarative schema (required keys, every operation, the regex and JSON parsers, placeholders, worked examples) is the "Define a new manager" section of {doc}`/overrides`, which is the source of truth. This section adds only the authoring workflow and the pitfalls that decide success.

1. **Capture real output first.** For each operation you plan to declare, run the actual CLI and paste its output. Confirm a single per-line regex or one flat JSON array can extract `package_id` (plus `installed_version` for `installed`, `latest_version` for `outdated`). Never assume a format.

   A tool that does not belong on this host is usually still runnable, and reading its source is the *last* resort rather than the first. Try these in order before falling back to it:

   - **Run it in a throwaway sandbox.** Most managers root everything they touch at `$XDG_*` or one environment variable, so repointing those at a scratch directory gets a real install, a real listing and a real removal without touching the user's machine. Fetch the release binary rather than installing the tool for real. Miss one variable and the tool reaches for the real home, which the sandbox refuses: read that refusal as the hint it is (`yazi` needed `XDG_CACHE_HOME` on top of the other three).
   - **Feed the real tool synthetic state.** When the inventory is read off disk, fabricate the on-disk shape and let the tool parse it: a `mason` receipt, a `bin` config naming deliberately stale binaries, a `metadata.json` per GNOME extension. The parser under test is the tool's own, so the output is genuine even though the packages are not.
   - **Drive the tool's own code with the host-specific call stubbed.** For a manager written in an interpreted language, import its command handler and replace only what needs the absent platform, leaving its formatter and command flow real. `gext`'s listing was captured on macOS this way, stubbing the one call that shells out to `gsettings`; its search and dry-run needed no stub at all, hitting the live registry.

   Only when all three fail, derive the format from upstream: read the exact `printf`/`echo`/`print` statements that emit each line in the tool's source, cite them, and mark reconstructed samples as source-derived in comments. **Never invent output.**

   Whatever the route, ask what the default listing *omits* before trusting it. `gext list` shows only enabled extensions until `--all`, and micro's shows only loaded plugins. A listing that silently drops half the inventory is worse than one that errors.

2. **Write the block.** Add `[mpm.managers.<id>]` with an `<id>` that no built-in uses. Set `platforms`, the `operations` table, and the identity fields (`cli_names`, `requirement`, `version_regexes`, ...). Silence color and interactivity via `pre_args`, `post_args` or `extra_env` (like `NO_COLOR = "1"`) so the parser sees clean text. `mpm config-template` prints the built-ins' overridable fields as a formatting reference.

3. **Declare only expressible operations.** A manager with no non-mutating "list upgradable" command (common: `soar`, `appman`, `gh extension`) omits `outdated`; `mpm` auto-skips it and `upgrade --all` still works. Never fake an operation with a mutating command.

4. **Validate against the real CLI.** `mpm` checks the definition at load and reports the first problem with a precise path:

   ```shell-session
   $ mpm --config ./my-managers.toml managers
   $ mpm --config ./my-managers.toml --<id> installed
   ```

5. **Add tests.** For a private definition, mirror `tests/test_manager_definition.py`: `parse_manager_definition` for validation cases, `build_manager_class(...)` with a monkeypatched `run_cli` for parsing, and the `fake_tool` fixture for an end-to-end run through a real subprocess. For a bundled definition, ship the `[samples]` fixtures in the TOML file itself instead (see the checklist below): the suite globs the shipped files and derives its checks from them.

Design around the DSL's fixed limits (all detailed in {doc}`/overrides`): no version pinning (`install` and `upgrade` always take the latest, `{version}` is never substituted); listings are line-by-line regex or a single flat JSON array, with no multi-line records, pagination, or value transforms; `search` cannot declare native exact or extended filtering, so `mpm` refilters the results itself. If any of these is load-bearing for the manager, stop and write a class instead.

### Where a config-based definition lives

A definition has two homes:

- **Private (a user's config).** Drop the `[mpm.managers.<id>]` block into your own configuration file. `mpm` picks it up on the next run: nothing else to touch, and it never leaves your machine.
- **Bundled (shipped with `mpm`).** Put the block in its own `meta_package_manager/managers/<id>.toml` file. `mpm` loads every shipped `*.toml` at startup and registers it like a built-in, so every user gets its `--<id>` flag. Bundled files are read-only package data, so they load without the config-file trust gate that guards a user's own definitions (see {doc}`/security`). `meta_package_manager/managers/gh_ext.toml` is the worked example.

Shipping a bundled definition is far lighter than the class-based checklist below, with no module:

| File                                      | Change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| :---------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `meta_package_manager/managers/<id>.toml` | The definition (one `[mpm.managers.<id>]` section) plus a top-level `[samples]` table: a `[samples.version]` fixture locking the version probe, and one `[[samples.<operation>]]` block per declared query operation, locking each parser to a source-derived output sample. Auto-discovered: the loader and the sample-derived tests glob the file up.                                                                                                                                                                    |
| `meta_package_manager/labels.py`          | Optional: a `MANAGER_LABEL_GROUPS` entry if the manager joins an ecosystem group, plus an *unambiguous* ecosystem keyword in `MANAGER_CONTENT_KEYWORDS` (a distro/language/brand name mpm never prints, never the ID or a CLI name). The label and its file rule derive from the pool; the content rule comes only from the keyword you add, and a manager with none gets no content rule.                                                                                                                                 |
| `docs/docs_update.py`                     | Optional: a well-known ecosystem alias in `KEYWORDS_EXTRAS` when it differs from the manager ID (like `gh-ext` and `github cli`). The ID lands in the PyPI keywords automatically.                                                                                                                                                                                                                                                                                                                                         |
| `tests/conftest.py`                       | Add a `PACKAGE_IDS` entry: the destructive install/remove round-trip covers bundled managers too, and the import-time assertion requires every shipped manager to carry one.                                                                                                                                                                                                                                                                                                                                               |
| `tests/test_pool.py`                      | Increment the `len(pool)` assertion in `test_manager_count`; `len(manager_classes)` stays.                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `changelog.md`                            | A `- [<id>] Add ...` entry.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `docs/benchmark.toml`                     | If the manager already had a competitor row, delete its `homepages` entry: the homepage now comes from the definition (`test_benchmark_homepages_cover_non_pool_managers` enforces).                                                                                                                                                                                                                                                                                                                                       |
| `pyproject.toml`                          | Add the manager's upstream repository to `[tool.repomatic.metrics] subjects`, keyed by its ID, or its reason for having none to `NO_UPSTREAM` in `meta_package_manager/_docs.py`. `test_manager_upstreams_cover_the_pool` requires every wrapped manager to sit in exactly one of the two, since the pair feeds the stars and commit facts of the manager card.                                                                                                                                                            |
| `docs/cooldown.md`                        | Two hand-maintained tables, each needing a row. The *Supported managers* table takes the manager's cooldown status, a three-way call settled during vetting (see *Gating the manager under `--cooldown`*): ✅ native knob, ✅ `mpm` per-package probe, or ❌/➖. `manager_cooldown()` reuses that row on the manager's own page, and `test_cooldown_support_table_covers_the_pool` fails until the row is there (`pikaur`, `trizen` and `dkp-pacman` all shipped without one back when the page just degraded silently). The *Retraction paths by registry* table takes the manager's id in whichever registry row its packages come from, and its *Publish date* cell is worth filling while the registry research is fresh, a server-set date there being exactly what qualifies the probe; `test_retraction_table_well_formed` fails until the id is there, since the mapping must partition the pool. |

Then regenerate the pool-derived blocks, both run by repomatic's `update-docs` job (a manual run is just a pre-check): `docs/docs_update.py` writes the PyPI keywords and labeller rules in `pyproject.toml`, the readme's operation-matrix platform footnotes and the manager's `docs/managers/<id>.md` page stub; `click-extra refresh-directives readme.md` refreshes the readme's Sankey diagram and operation matrix, which are `<!-- mirror-src -->` blocks. The benchmark, augmentations and per-manager pages need no content regeneration: their tables and sections render live at Sphinx build time. A bundled config manager needs **no** `pool.py` import or `docs/meta_package_manager.managers.md` automodule: those are class-only.

## Completing an incomplete integration

External contributors often submit a working manager module (`managers/<name>.py`, `pool.py`, `conftest.py`) but skip the documentation and metadata files. See [kdeldycke/meta-package-manager#1758](https://github.com/kdeldycke/meta-package-manager/pull/1758) for a typical example: the PR added code and tests but was missing 10+ files.

When asked to "integrate further", "fill gaps", or "finish" a manager that already has code:

1. Read the existing manager module to understand supported operations and platforms.
2. Walk the **file checklist** below and check **every** file for the manager's presence. The most commonly missed files are: `docs/meta_package_manager.managers.md`, `labels.py` (group and synonyms), `test_pool.py` (manager count), and `changelog.md`. Also regenerate the pool-derived blocks: `docs/docs_update.py` (keywords, labeller rules, readme footnotes, manager page stubs) and `click-extra refresh-directives readme.md` (the readme's Sankey and operation-matrix mirror-src blocks).
3. Verify the `requirement` version specifier by fetching the upstream release history. Check when the features the code depends on (like `--json` output) were actually introduced. Contributors often default to `>=1.0.0` without checking.
4. If the manager wraps or complements another (like sfsu wraps Scoop), merge them under a single `📦 manager:` label by grouping them in `labels.py`. Use the `-based` suffix convention for the group name (like `scoop-based`) to avoid colliding with the manager ID itself; the label and its rules regenerate from the group.
5. Fetch the upstream repository (README, releases, changelog) to verify CLI output formats match the parsing code.
6. Check class attribute ordering against the base class. The `test_content_order` test enforces that class-level attributes and methods follow the canonical order defined in `PackageManager`. Common mistakes: `version_regexes` before `post_args`, or `name` after `homepage_url`.
7. If the manager delegates operations to another manager's CLI, use the `Delegate` descriptor from `capabilities.py` instead of repeating `override_cli_path` boilerplate. See the **Delegating operations** section below.

## Choose a template

Pick an existing manager with a similar CLI as your starting point. Read the template file in full before starting.

| Pattern                      | Example                          | When to use                                                                                                                          |
| ---------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Simple regex parsing         | `snap.py`, `flatpak.py`          | CLI outputs fixed-width or whitespace-delimited text                                                                                 |
| JSON output                  | `npm.py`, `homebrew.py`          | CLI supports `--json` or structured output                                                                                           |
| Multiple compiled regexes    | `gem.py`, `dnf.py`               | Complex text output requiring several capture patterns                                                                               |
| Shell function wrapper       | `sdkman.py`                      | Manager is a shell function, not a standalone binary                                                                                 |
| Sibling binaries             | `nix.py`                         | Different operations use different CLI binaries in the same directory                                                                |
| Subclass of existing manager | `yay.py`, `paru.py`, `pacaur.py` | Manager is a drop-in replacement or wrapper for another manager already implemented                                                  |
| Delegate to another manager  | `sfsu.py`                        | Manager has its own CLI for read operations but delegates mutating operations (install, upgrade, remove) to another manager's binary |

Subclassing is the lightest option: `yay.py` is only 39 lines because it inherits almost everything from `pacman.py`. If the new manager shares the same CLI interface as an existing one, subclass it and override only what differs.

Delegation via `Delegate` is for managers that share the same package ecosystem but have different CLI interfaces. Unlike subclassing, the read operations (list, search, outdated) have completely different implementations, but mutating operations reuse the other manager's methods verbatim.

Typical manager modules range from 140 to 260 lines. Larger implementations (350-570 lines) tend to involve managers with unusual output formats or many edge cases like `fwupd.py`, `winget.py`, or `pkg.py`.

## Implementation

Create `meta_package_manager/managers/<name>.py`. Follow the import pattern, class structure, and `TYPE_CHECKING` block from your template exactly.

Class-level attributes and methods must follow the canonical order defined in `PackageManager` (enforced by `test_content_order`). The order is: `homepage_url`, `logo`, `platforms`, `requirement`, `cli_names`, `cli_search_path`, `extra_env`, `pre_cmds`, `pre_args`, `post_args`, `version_cli_options`, `version_regexes`, then operations (`installed`, `outdated`, `release_date`, `search`, `install`, `upgrade_all_cli`, `upgrade_one_cli`, `upgrade_all_cli_excluding`, `remove`, `sync`, `cleanup`).

### Class attributes

Required:

- `homepage_url`: official project URL.
- `platforms`: use constants from `extra_platforms` (`ALL_PLATFORMS`, `LINUX_LIKE`, `MACOS`, `WINDOWS`, `UNIX_WITHOUT_MACOS`, etc.). Combine with tuples: `platforms = LINUX_LIKE, MACOS`.

Common optional:

- `logo`: slug of the brand mark shown atop the manager's documentation page, naming an SVG vendored under `docs/assets/managers/`. Run `uv run -- python docs/logos_update.py --scan-gaps` to see whether Simple Icons carries one; if it does, declare the slug and re-run the tool without the flag to vendor the file and refresh `logos.yaml`. Leave it unset when there is none, which is the right outcome for roughly a quarter of the pool: the page keeps its generic package glyph, and no placeholder is invented. Managers wrapping the same upstream share one slug (`brew` and `cask` are both `homebrew`), declared once on their virtual base when they have one. A tool with no mark of its own takes its ecosystem's (`apt` under Debian's, `cargo` under Rust's). Never hand-vendor a mark whose brand had its icons pulled from Simple Icons after a legal request: see the comments in `winget.py` and `sun_tools.py`.

- `requirement`: minimum version specifier (e.g., `">=2.0.0"`). Set this to the earliest version that supports all features the implementation depends on. If the code parses `--json` output, check the upstream release history to find when that flag was introduced. Do not default to `>=1.0.0` without verification.

  A floor on the *tool* is not a floor on the *data it wrote*. Anything a manager records on disk carries the shape of whichever release created it, so a current tool keeps serving records written years ago and a parser reading only the newest shape drops those packages silently rather than failing. `mason` is the worked example: its receipts carry their own `schema_version`, the source sits under `source` from `2.0` and under `primary_source` before it, and mason's own reader branches on exactly that. Read every shape the tool still reads, whatever the floor says.

- `cli_names`: tuple of binary names to search for. Defaults to `(lowercase_class_name,)`. Set explicitly when the binary name differs from the class name (e.g., `cli_names = ("nix-env",)` for class `Nix`).

- `version_regexes`: tuple of regex strings with a `(?P<version>...)` named group.

- `version_cli_options`: tuple of args to get version. Defaults to `("--version",)`.

- `pre_args`, `post_args`: global arguments prepended/appended to every CLI call. Use these for flags like `--no-color` or `--quiet` that apply to all operations.

- `extra_env`: dict of environment variables to suppress colors, pagers, interactive prompts, etc.

- `cli_search_path`: extra directories to find the binary (e.g., `("~/.sdkman/bin",)`).

### Operations

Each operation maps to one of these methods. Implement as many as the manager supports. Unimplemented operations are automatically skipped by `mpm`.

| Operation   | Method signature                            | Returns             | Notes                                                                                                                                       |
| ----------- | ------------------------------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Installed   | `installed` (property)                      | `Iterator[Package]` | Yield packages with `id` and `installed_version`.                                                                                           |
| Outdated    | `outdated` (property)                       | `Iterator[Package]` | Yield packages with `id`, `installed_version`, and `latest_version`.                                                                        |
| Search      | `search(query, extended, exact)`            | `Iterator[Package]` | Decorate with `@search_capabilities(extended_support=..., exact_support=...)`. Yield with `id`, `latest_version`, optionally `description`. |
| Install     | `install(package_id, version=None)`         | `str`               | Decorate with `@version_not_implemented` if version pinning is unsupported.                                                                 |
| Upgrade all | `upgrade_all_cli()`                         | `tuple[str, ...]`   | Return `self.build_cli(...)`, not `self.run_cli(...)`.                                                                                      |
| Upgrade one | `upgrade_one_cli(package_id, version=None)` | `tuple[str, ...]`   | Same as above. Decorate with `@version_not_implemented` if needed.                                                                          |
| Remove      | `remove(package_id)`                        | `str`               | Optional.                                                                                                                                   |
| Sync        | `sync()`                                    | `None`              | Optional. For refreshing package metadata from remote sources.                                                                              |
| Cleanup     | `cleanup()`                                 | `None`              | Optional. For garbage collection, cache clearing, orphan removal.                                                                           |

Key helpers from the base class:

- `self.run_cli(*args, **kwargs)` executes the manager CLI and returns stdout.
- `self.build_cli(*args)` builds a command tuple without executing it (used by `upgrade_all_cli` and `upgrade_one_cli`).
- `self.package(id=..., ...)` creates a `Package` with `manager_id` pre-filled.
- `self.cli_path` resolves to the discovered binary path. Use `.parent` to find sibling binaries for operations that use a different CLI (see `nix.py` for `sync` and `cleanup`).

### Traps that recur across managers

Each of these cost a wrong implementation once. Ask them of every candidate:

- **Does a whole-system upgrader read its positionals?** `pamac upgrade <package>` parses its options and calls `run_sysupgrade()` without ever reading them, so it silently upgrades everything; single-package upgrades route through `install --no-upgrade` instead. `haxelib` is the same shape and is safe, but only because its argument count is enforced upstream, which is a fact to verify rather than assume.
- **Does the tool update itself as a side effect?** `rustup` replaces its own binary on every mutating branch unless `--no-self-update` is passed. Worse, several tools name their self-update the same as a package upgrade: bare `pi update`, `pearl update`, `zvm upgrade` and `choosenim update self` each replace the tool rather than anything it installed, so an `upgrade_all` mapped to them upgrades the wrong thing.
- **What does the output depend on besides the packages installed?** `nala` needs `LC_ALL=C` to pin its runtime-translated strings and glyphs, and `vcpkg` needs `--classic` to pin its inventory to the machine rather than to whichever project the working directory sits in.
- **Does a project-local mode exist?** `haxelib` walks up the whole tree for a `.haxelib` directory and switches to that repository the moment it finds one, so every call forces `--global`. `vagrant` and `pyenv` need the same audit before either can be called system-scoped.
- **What does a read do when its server is down?** `ollama`'s listing needs a daemon, and where none runs the client starts one, launching the desktop application on macOS. It was wrapped anyway, the daemon being one the user installed deliberately, but the behaviour is documented on its page.
- **Is there a projection flag hiding under a table?** `gcloud` renders a bordered table by default, yet `--format=value(...)` prints tab-separated fields with no heading. Check for a machine-readable mode before concluding a listing needs a Python class.
- **Does the listing repeat an identifier?** `vagrant` reports one row per name, provider and version, so a package appears several times and has to be reduced to one entry per id. That is the case `parse_regex_lines` names as its own exit, and `luarocks` and `roswell` share it.
- **Which object do the verbs agree on?** For a runtime manager, that question decides what counts as a package: `rustup` narrowed to toolchains because a component listing answers for whichever toolchain is active, while `ghcup` widened to every tool kind because its listing is flat and self-describing. An inventory that depends on ambient state rather than on the machine is the defect that forced `--global` on haxelib.
- **Does a failure look like an empty result?** `roswell` exits `0` with empty stdout and its diagnosis on stderr alone when the implementation it resolves is absent, so a parser would report an empty inventory and never know. Pass `must_succeed=True` on any call whose output is parsed, and remember it keys on the exit code: a zero exit with a non-empty stderr slips through, which is why that candidate is still queued.

### Delegating operations to another manager

When a manager uses its own CLI for read operations but delegates mutating operations to another manager's binary, use the `Delegate` descriptor from `capabilities.py`:

```python
from ..capabilities import Delegate
from .scoop import Scoop


class SFSU(PackageManager):
    _scoop = Delegate(Scoop)

    # Read operations use sfsu's own CLI with JSON output.
    @property
    def installed(self) -> Iterator[Package]:
        output = self.run_cli("list", "--json")
        ...

    # Mutating operations delegate to scoop.
    install = _scoop.install
    upgrade_all_cli = _scoop.upgrade_all_cli
    upgrade_one_cli = _scoop.upgrade_one_cli
    remove = _scoop.remove
```

The `Delegate` factory resolves the target manager's CLI binary via `self.which()` and temporarily sets `_delegate_cli_path` on the instance so that `build_cli` routes the command through the target binary. The host manager's `post_args` are automatically suppressed during delegation.

Place `_scoop = Delegate(Scoop)` at the top of the class body (before `homepage_url`). Place individual delegation assignments (`install = _scoop.install`) in the canonical operation order, interspersed with the other operations.

Do **not** subclass when the two managers have completely different output formats for read operations. Subclassing is for managers that share the same CLI interface. Delegation is for managers that share the same package ecosystem but have different CLIs.

### Gating the manager under `--cooldown`

Settle the release-age axis while the real tool is being driven, since the answer costs one extra capture then and a second assessment pass later. Three outcomes, in order of preference:

1. **A native release-age knob.** Declare `cooldown_env_var` (plus a `cooldown_env_value` override when the format is not an RFC 3339 cutoff: npm counts days, pnpm minutes). The manager is ✅ in the support table of {doc}`/cooldown`.
2. **No knob, but the per-package probe qualifies.** Implement `release_date(package_id)` when both admission rules hold: a **server-set** publication date is reachable through the manager's own CLI, and the install unit is self-contained, or the whole transaction is enumerable behind a native exclusion flag (then also implement `upgrade_all_cli_excluding()`, `paru`'s `--ignore` being the worked example). The trust contract is in the `release_date` docstring and {doc}`/cooldown`: an author-settable date (a git commit, embedded package metadata, an optional manifest field like winget's `ReleaseDate`) never qualifies, and install-time dependency resolution disqualifies the probe outright, `choco` and `pwsh-gallery` being the recorded declines. Return `COOLDOWN_EXEMPT` for the out-of-scope half of a hybrid manager (`paru` exempts official-repository packages, whose archive stages releases on its own).
3. **Neither.** The manager stays ungated: ❌ in the support table, or ➖ where the ecosystem's own staging makes the concept inapplicable.

Probe traps, each hit in the first three implementations (`flatpak`, `mas`, `paru`):

- Field labels are localized and timestamps may render in local time: force `LC_ALL=C.UTF-8` (plus `TZ=UTC` where needed, as for `paru`) through `override_extra_env` on the probe calls only, never through `extra_env`.
- Verify the exact timestamp rendering from the tool's *source*, the same way listing formats are verified: `flatpak` hardcodes a literal `+0000`, `paru` formats `%a, %e %b %Y %T` after converting to local time. A probe docstring whose sample was reconstructed from source uses a `console` fence, not `shell-session`.
- Design the probe so its expected path never fails: a failing CLI call lands in `cli_errors` and flips the manager's trail to `✗`, so resolve the right remote or scope *before* the call that could miss (`flatpak` reads the installed app's origin first, and only falls back to trying every remote for an app not installed yet).

### CLI output guidelines

- Use `--long-form-options` for self-documenting CLIs.
- Suppress colors and emoji (`--no-color`, `--color=never`, etc.) via `post_args` or `extra_env`. Some tools cannot be talked out of it: `bob` writes SGR escapes whether or not it holds a terminal and honors neither `NO_COLOR` nor `TERM=dumb`. That is not a blocker, because listings are matched with `re.search` rather than anchored to the start of the line, so a pattern can simply step over the escapes instead of fighting them. Prove the tool ignores every lever before adding one that does nothing. Where it *is* the terminal that varies the bytes rather than the packages, pin it: `getnf` colors through `tput`, which ignores redirection entirely, so it forces `TERM=dumb`.
- A fixture carrying those escapes needs them written as a `\u001B` unicode escape in a TOML basic string, since TOML rejects a raw control character outright and the file will not parse. Stripping them instead is the wrong fix: it leaves a sample that no longer proves the pattern survives what the tool actually emits.
- Prefer a format string with **no space in it** when a tool offers an output projection. `mpm` discloses the command it runs so a user can replay it by hand, and it does not shell-quote, so `--format {name} {version}` prints a line that no longer works when pasted back. `spack` uses `{name}@{version}` for exactly this, which is its own spec syntax besides.
- Prefer machine-readable output (JSON, XML, CSV) over text parsing. When parsing text, use class-level compiled regexes with named groups.
- Include at least one CLI output sample in each method's docstring as a `.. code-block:: shell-session` block. This helps future maintainers verify parsing without access to the actual manager.
- Read {doc}`/falsehoods` to anticipate edge cases in package naming and versioning.

## Choosing the destructive-test package (`PACKAGE_IDS`)

The destructive suite runs `mpm --<id> install <pkg>` then `mpm --<id> remove <pkg>` against the real host, so `PACKAGE_IDS[<id>]` in `tests/conftest.py` must name a package that installs and uninstalls cleanly:

- **Tiny and fast**: no dependency tree, no services/daemons, no `/etc` config, a single self-contained binary.
- **Not relied upon**: avoid ubiquitous tools (`wget`, `curl`, `git`, `jq`, `openssl`). They are usually already installed (so the install step is a no-op) and removing them can break the host or the test runner.
- **Self-contained**, ideally a Rust or Go binary.
- **Verified to exist** in that manager's repo/registry, with the exact ID format the manager expects (a bare name, `category/name`, `bucket/name`, `Publisher.Package`, a numeric ID, ...). Check the real index before committing the choice: do not guess.
- **Findable through the manager's own `search`**, which is a stricter test than existing. `mpm install` resolves a package it was handed no manager for by searching first, so a name the tool installs happily but its catalog never lists cannot be installed through `mpm` at all, and the round-trip fails on the install step. Naming the manager does not help: the lookup is what supplies the candidate. `bob` is the worked example, where `nightly` installs fine but appears in no `list-remote` output, so the entry names a released tag instead. Run `mpm --<id> search <pkg>` before settling on a pick, and where the gap is real, say so on the manager's page: it is a user-visible limitation, not just a test-fixture detail.

Reuse the established picks for consistency instead of inventing new ones:

| Ecosystem                                                           | Package                                         | Notes                                                                                 |
| ------------------------------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------- |
| Linux distros, Homebrew, FreeBSD (apt, dnf, pacman, apk, brew, ...) | `nyancat`                                       | Single-file C binary in nearly every distro, Homebrew and FreeBSD; zero reverse-deps. |
| Distros lacking `nyancat`                                           | `sl` (Solus, Void), `hello`, `lolcat` (OpenWrt) | Fall back only where `nyancat` is absent.                                             |
| Source-compiling managers (emerge, FreeBSD ports)                   | `games-misc/nyancat`, `net/nyancat`             | Compiles in seconds from one C file; use the `category/name` atom.                    |
| Functional managers (Guix, Nix)                                     | `hello`                                         | The canonical GNU demo package.                                                       |
| Windows binary stores (choco, scoop, sfsu, winget) and `stew`       | `hyperfine`                                     | One self-contained Rust binary; use the manager's ID format.                          |
| npm, Yarn                                                           | `ms`                                            | Zero-dependency, ~7 KB.                                                               |
| pip, uv                                                             | `pytz`                                          | Pure-Python, zero-dependency.                                                         |
| pipx, uvx                                                           | `pycowsay`                                      | Must expose a console-script entry point (a library like `pytz` fails here).          |
| gem, cpan, composer                                                 | `paint`, `Try::Tiny`, `ralouphie/getallheaders` | Smallest inert zero-dependency package native to the language.                        |

Special cases: managers that only ship large artifacts use their lightest option (`sdkman` → `jbang`); managers with no real per-package install reference themselves (`deb-get`, `topgrade`); `fwupd` must never use an ID that flashes firmware on real hardware. Add a short inline comment for any non-obvious ID (numeric App Store/Steam IDs, firmware GUIDs).

## File checklist

Every new manager touches the same set of files. This list is derived from all 30 manager-addition commits in the project history.

### Always required

| File                                      | Change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `meta_package_manager/managers/<name>.py` | The new manager implementation.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `meta_package_manager/pool.py`            | Add import (sorted by module name) and class to `manager_classes` tuple (sorted case-insensitively by class name).                                                                                                                                                                                                                                                                                                                                                                                                         |
| `tests/conftest.py`                       | Add `"<manager_id>": "<package_id>"` to `PACKAGE_IDS`. See [Choosing the destructive-test package](#choosing-the-destructive-test-package-package-ids) for the selection criteria and the canonical per-ecosystem picks. A missing entry aborts collection of the whole suite (`PACKAGE_IDS` is asserted against the pool at import time).                                                                                                                                                                                 |
| `tests/test_pool.py`                      | Increment both count assertions in `test_manager_count()`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `changelog.md`                            | Add `- [<manager_id>] Add <Name> package manager with <operations> support.` under the current unreleased version.                                                                                                                                                                                                                                                                                                                                                                                                         |
| `readme.md`                               | Sankey + matrix: `mirror-src` blocks via `refresh-directives`. Footnotes: `docs_update.py`.                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `docs/managers/<manager_id>.md`           | Regenerated by `docs/docs_update.py`: one page stub per pool manager, its sections rendering live at Sphinx build time. Nothing to hand-edit (`test_manager_stubs_in_sync` enforces byte-identity).                                                                                                                                                                                                                                                                                                                        |
| `docs/meta_package_manager.managers.md`   | Add `automodule` section for `meta_package_manager.managers.<name>` in alphabetical order.                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `pyproject.toml`                          | Add the manager's upstream repository to `[tool.repomatic.metrics] subjects`, keyed by its ID, or its reason for having none to `NO_UPSTREAM` in `meta_package_manager/_docs.py`. `test_manager_upstreams_cover_the_pool` requires every wrapped manager to sit in exactly one of the two, since the pair feeds the stars and commit facts of the manager card.                                                                                                                                                            |
| `docs/cooldown.md`                        | Two hand-maintained tables, each needing a row. The *Supported managers* table takes the manager's cooldown status, a three-way call settled during vetting (see *Gating the manager under `--cooldown`*): ✅ native knob, ✅ `mpm` per-package probe, or ❌/➖. `manager_cooldown()` reuses that row on the manager's own page, and `test_cooldown_support_table_covers_the_pool` fails until the row is there (`pikaur`, `trizen` and `dkp-pacman` all shipped without one back when the page just degraded silently). The *Retraction paths by registry* table takes the manager's id in whichever registry row its packages come from, and its *Publish date* cell is worth filling while the registry research is fresh, a server-set date there being exactly what qualifies the probe; `test_retraction_table_well_formed` fails until the id is there, since the mapping must partition the pool. |
| `meta_package_manager/specifier.py`       | Claim the manager's registry in `PURL_MAP` when a matching purl type exists (`"nuget": {"dotnet"}`). A type left mapped to `None` is worse than an absent key: `parse_purl` tests membership before falling back to the manager ID, so a present-but-`None` type makes `pkg:<type>/...` raise instead of resolving. The claim also feeds the `purl types` line of the manager's page, which otherwise contradicts the registry named in `docs/cooldown.md`. Leave it alone when no type fits.                              |
| `pyproject.toml`                          | Regenerated by `docs/docs_update.py`: the `keywords`, the label registry and the labeller rules. The keywords, registry and file rules derive from the pool; the content rules come only from the hand-curated `MANAGER_CONTENT_KEYWORDS`. Nothing to hand-edit here.                                                                                                                                                                                                                                                      |
| `meta_package_manager/labels.py`          | If the manager belongs to an ecosystem group, add it to the appropriate frozenset in `MANAGER_LABEL_GROUPS`. If the manager creates a new group (standalone manager now gaining a wrapper), add a new group entry. Add an ecosystem keyword to `MANAGER_CONTENT_KEYWORDS` only if it unambiguously names the manager and mpm never prints it (not the ID or a CLI name); otherwise add none and let the maintainer label by hand.                                                                                          |
| `docs/docs_update.py`                     | Add a well-known ecosystem alias to `KEYWORDS_EXTRAS` when it differs from the manager ID; the ID itself lands in the PyPI keywords automatically.                                                                                                                                                                                                                                                                                                                                                                         |

### When applicable

| File                                                       | When                                                                                                           | Change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.github/workflows/tests.yaml`                             | Manager can be installed on CI runners.                                                                        | Add an install step for every matrix OS the manager's `platforms` covers, near related managers. Availability stops being the test once a `requirement` floor is set: check the *version* each channel ships, and never stop at the distro package, which is the stalest channel there is. Ubuntu 26.04 has Neovim 0.11.6, under `vim-pack`'s `>=0.12.0`, while the `nvim` snap, Chocolatey and Scoop all track 0.12.x: reading apt alone is what left `vim-pack` tested on macOS only, for a manager declaring `ALL_PLATFORMS`. A platform left out is silent, never red — mpm reports the manager unavailable and its destructive test skips. |
| `docs/benchmark.toml`                                      | Manager already appears in the comparison table.                                                               | Delete its `homepages` entry: the homepage now comes from the class (a sync test enforces the set).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `docs/assets/managers/`                                    | Manager declares a `logo` whose slug is not vendored yet.                                                      | Run `python docs/logos_update.py` to fetch the mark and refresh `logos.yaml`. Never hand-edit either: the SVG is normalized and the manifest feeds the credits block of {doc}`/license`. **Commit the SVG itself**, not just the manifest: it arrives as a brand-new file, so it is the one artifact a `git commit -- <paths>` silently leaves behind, and a manifest naming artwork that is not in the tree renders nothing on a fresh checkout while passing every check locally.                                                                                                                                                             |
| `.github/workflows/tests-install.yaml` + `docs/install.md` | Manager is a *distributor of mpm itself* (like Homebrew, Scoop, Nix, or an AUR helper). Most managers are not. | Add a CI job testing `mpm` installation via the new channel, and a matching tab in the install docs.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |

## Validate

Regenerate first, then test: several checks compare a generated artifact against the tree, so testing before regenerating reports drift that the regeneration would have settled.

```shell-session
$ uv run --frozen -- python docs/docs_update.py
$ uv run --frozen -- click-extra refresh-directives readme.md docs
$ uv run --frozen -- pytest tests/test_pool.py tests/test_managers.py tests/test_manager_definition.py tests/test_docstring_corpus.py tests/test_docs.py -q --numprocesses=auto
$ uv run --group typing mypy meta_package_manager/managers/<name>.py
```

That selection covers everything a manager touches and runs in about fifteen seconds. `docs/logos_update.py` is run by hand and only when a `logo` is declared: it re-downloads every mark, and the manifest records which managers each is credited to, so a new manager reusing an existing mark fails `test_manager_logos_resolve` until it is re-run.

A broader slice is worth one pass before a batch of work leaves the machine, `pytest tests/ --skip-destructive --ignore=tests/test_cli_sbom.py`, which takes about seven minutes. The full non-destructive suite is a different matter and has stalled around 91-94% with no summary on more than one machine, so treat that as a local-environment issue rather than a signal and rely on the targeted selection plus CI.

The test suite enforces: valid ID format, homepage URL, platform declarations, version regexes, no duplicate IDs, correct pool count, canonical attribute ordering (`test_content_order`), and label group disjointness.

Common validation failures after adding a manager:

- **`test_manager_count`**: forgot to increment the count in `test_pool.py`.
- **`test_content_order`**: class attributes are not in the canonical order (like `version_regexes` before `post_args`).
- **`test_manager_logos_resolve`** (in `tests/test_docs.py`, so the `Validate` command above does not catch it): a declared `logo` slug with no vendored SVG, or a vendored mark no manager claims. Run `docs/logos_update.py`.
- **Label group collision**: the group name in `labels.py` collides with a manager ID. Use the `-based` suffix (like `scoop-based`, `pypi-based`).
- **A content rule silently disappearing**: `MANAGER_CONTENT_KEYWORDS` is keyed by the ID a label *derives* from, so folding a manager into a group (or renaming one) orphans its entry, which then generates nothing. No test catches it. Re-key it to the group and diff `pyproject.toml` for a dropped `patterns =` line.
- **Whole-suite collection abort**: `tests/conftest.py` asserts `PACKAGE_IDS` covers exactly the class managers at import time; a missing class entry (or a stray bundled one) kills every test, not one.
- **`test_docstring_corpus`**: the `$ ...` shell-session samples in operation docstrings are checked against the real CLI construction. Write them in build order: binary, `pre_args`, the declared arguments with the package ID exactly where the code puts it, `post_args` last (`pkcon install --noninteractive hello --plain`, not `pkcon install hello --noninteractive --plain`).
- **`test_new_package_manager_issue_template`**: the issue template's platform checklist is generated from `MAIN_PLATFORMS`; it goes stale when an extra-platforms release adds detections.
