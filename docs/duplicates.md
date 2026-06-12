# {octicon}`copy` Cross-manager duplicates

The same package name often shows up across multiple managers: a tool packaged simultaneously for Homebrew, Cargo, npm, and pipx, or installed by mistake through more than one route on the same machine. `mpm` treats this as a first-class concern, with one command to find the best source for a new install and another to surface installations that already overlap.

## Find the best source

Searching across every supported manager at once tells you where the latest version actually lives:

```shell-session
$ mpm search broot --exact
╭────────────┬──────┬─────────┬────────────────╮
│ Package ID │ Name │ Manager │ Latest version │
├────────────┼──────┼─────────┼────────────────┤
│ broot      │      │ brew    │ 1.16.2         │
│ broot      │      │ cargo   │ 0.13.6         │
╰────────────┴──────┴─────────┴────────────────╯
2 packages total (brew: 1, pip: 1, cask: 0, gem: 0, mas: 0, npm: 0).
```

Then choose your preferred package manager to install it:

```shell-session
$ mpm --brew install broot
Package manager order: brew
Install broot package from brew...
(...)
🍺  /usr/local/Cellar/broot/1.16.2: 8 files, 3.5MB
```

This pattern catches the common "I want the freshest version" decision without having to query each manager by hand.

## Audit existing installations

When the same package is already installed through more than one manager, list every duplicate with:

```shell-session
$ mpm list --duplicates
╭────────────┬──────┬─────────┬───────────────────╮
│ Package ID │ Name │ Manager │ Installed version │
├────────────┼──────┼─────────┼───────────────────┤
│ blah       │      │ cargo   │ 0.0.0             │
│ blah       │      │ gem     │ 0.0.2             │
│ blah       │      │ npm     │ 5.2.1             │
│ coverage   │      │ pip     │ 6.4.1             │
│ coverage   │      │ pipx    │ 6.4.1             │
│ six        │      │ brew    │ 1.16.0_2          │
│ six        │      │ pip     │ 1.16.0            │
╰────────────┴──────┴─────────┴───────────────────╯
7 packages total (pip: 2, brew: 1, cargo: 1, gem: 1, npm: 1, pipx: 1, cask: 0).
```

Removing every copy at once is a single command:

```shell-session
$ mpm remove blah
Remove blah with cargo, gem, npm
(...)
Successfully uninstalled blah-0.0.0
(...)
Successfully uninstalled blah-0.0.2
(...)
Successfully uninstalled blah-5.2.1
```

Or target a specific duplicate by routing through one manager:

```shell-session
$ mpm --pip uninstall six
(...)
```

```{todo}
Add arguments to `installed` command, or an `--installed` boolean flag to `search` so we can reduce the searched packages to those installed.
```

## See also

- {doc}`dump` &mdash; snapshot the resolved installation set after deduplication.
- {doc}`configuration` &mdash; pin a preferred manager order so duplicates resolve consistently across runs.
