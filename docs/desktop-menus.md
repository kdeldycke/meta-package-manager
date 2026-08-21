# {octicon}`device-desktop` Desktop menus

`mpm` puts the same menu on two desktops. On macOS it is a plugin for the menu bar, running under {doc}`Xbar or SwiftBar <bar-plugin>`. On Linux it is a {doc}`GNOME Shell extension <gnome-shell>` in the top bar. Both list the outdated packages `mpm outdated` reports across every package manager on the system, and upgrade them one by one or per manager.

|                | {doc}`Menu bar plugin <bar-plugin>`              | {doc}`GNOME Shell extension <gnome-shell>`  |
| :------------- | :----------------------------------------------- | :------------------------------------------ |
| Desktop        | macOS, under Xbar or SwiftBar                    | GNOME Shell `46` to `50`                    |
| Written in     | Python, one file shipped inside `mpm`            | GJS                                         |
| Installed by   | symlinking that file into the host's plugin folder | an extension zip, or a source checkout    |
| Configured by  | environment variables, edited in the host's UI   | GSettings, edited in the preferences window |
| States drawn as | emoji                                            | named icons from the desktop icon theme     |
| `mpm` required | `5.0.0` or newer                                 | `6.4.0` or newer                            |

Both are frontends to the `mpm` CLI, which is installed separately: see {doc}`install`.

```{toctree}
:maxdepth: 2
bar-plugin
gnome-shell
```

## What a click runs

Clicking a package runs `mpm --<manager-id> upgrade <package-id>`, and a section's *Upgrade all* entry runs `mpm --<manager-id> upgrade --all`. Neither invokes the package manager directly, so a click is subject to the same policy as the `mpm` run that rendered the menu: manager selection, {doc}`sudo` escalation, per-manager {doc}`overrides` and the release-age {doc}`cooldown` all apply.

That last one is the visible consequence: with a `cooldown` set, clicking a package of a manager that cannot enforce it natively skips it with a warning instead of upgrading it ungated. Set `policy = "best-effort"` in the `[mpm.cooldown]` table to let those managers run anyway, without the safeguard.

*How* the command is run is each frontend's own business, and both pages cover their terminal handling.

## Settings drive the layout, `mpm` drives the rest

A frontend's own settings only decide the menu layout and the check cadence. Everything else comes from `mpm`'s configuration file: neither frontend passes an option beyond the ones it decides itself, so the file found at its default location on the system applies to every run either of them triggers. See {doc}`configuration` for the search paths and the full schema.

## Version diffs

Each outdated package has its version diff colored with the same convention as `mpm outdated`: unchanged prefix in gray, installed-version suffix in red, latest-version suffix in green. Both frontends split a version at the same point, so a package listed in both reads the same way on either desktop.

## When no `mpm` is found

The menu then carries a bootstrap pair in place of the package list: an *Install mpm with uv* entry running `uv tool install --upgrade meta-package-manager`, and an *Open mpm installation instructions* entry opening {doc}`install` for the systems `uv` does not answer for. The menu bar plugin shows the same pair for an `mpm` older than it requires.

## The states a menu reports

Both frontends report the same states, and only the vocabulary differs. The plugin spells each one as an emoji, which Xbar and SwiftBar render as text wherever it appears. The extension names a stock symbolic icon instead, which the shell resolves against whichever icon theme is in force: an emoji is a font glyph a desktop theme cannot restyle, and the GNOME reviewers ask for icons. The [panel icons table](gnome-shell.md#panel-icons) puts the two vocabularies side by side.
