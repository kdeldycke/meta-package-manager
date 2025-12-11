# {octicon}`sliders` Configuration

All `mpm` options can be set with a configuration file.

## Location

Location depends on OS (see [`click-extra` doc](https://kdeldycke.github.io/click-extra/config.html#default-folder)):

| Platform | Folder                                    |
| :------- | :---------------------------------------- |
| macOS    | `~/Library/Application Support/mpm/`   |
| Unix     | `~/.config/mpm/`                       |
| Windows  | `C:\Users\<user>\AppData\Roaming\mpm\` |

## TOML sample

Here is an example of a typical configuration file:

```toml
# My default configuration file.

[mpm]
verbosity = "INFO"
flatpak = true
pipx = true

[mpm.search]
exact = true
```

## Selecting managers

### Default managers

As you can see in the example above, you can select which package managers you want `mpm` to consider by default.

So the following configuration:

```toml
[mpm]
verbosity = "INFO"
flatpak = true
pipx = true
```

Is equivalent to always running any commands with the `--verbosity INFO`, `--flatpak` and `--pipx` parameters.

So if we call `mpm managers` with the above configuration, we will get the following output:

```shell-session
$ mpm managers
info: User selection of managers by priority: > flatpak > pipx
info: Managers dropped by user: None
╭────────────┬─────────┬────────────────────┬──────────────────────────┬────────────┬─────────╮
│ Manager ID │ Name    │ Supported          │ CLI                      │ Executable │ Version │
├────────────┼─────────┼────────────────────┼──────────────────────────┼────────────┼─────────┤
│ flatpak    │ Flatpak │ ✘ BSD, Linux, Unix │ ✘ flatpak not found      │            │         │
│ pipx       │ Pipx    │ ✓                  │ ✓ /opt/homebrew/bin/pipx │ ✓          │ ✓ 1.7.1 │
╰────────────┴─────────┴────────────────────┴──────────────────────────┴────────────┴─────────╯
```

````{hint}
There is an alternative syntax to specify default managers, which is to use the `manager` key:
```toml
[mpm]
manager = ["flatpak", "pipx"]
```

It calls `mpm` with the `--manager flatpak` and `--manager pipx` parameters instead of `--flatpak` and `--pipx`.

It is equivalent to the previous example, but call the hidden `--manager` parameter. This parameter is not shown in the help message as it is less user-friendly.

You can still mix both syntax in the same configuration file, as well as on the command line.
````

### Ignore a manager

Same as selecting managers, you can exclude some of them.

See [for example this user](https://github.com/matryer/xbar/issues/777), who was looking to always have `mpm` ignore `pip` to speed-up execution. This can That can be solved with the following config file:

```toml
[mpm]
pip = false
```

````{hint}
Again as for manager selection detailed in the previous sections, there is this alternative syntax to ignore managers:
```toml
[mpm]
exclude = ["pip", "pipx"]
```

It calls `mpm` with the `--exclude pip` and `--exclude pipx` parameters, which is the equivalent of `--no-pip` and `--no-pipx` options.

The `--exclude` parameter is advertised in the help message as it is less user-friendly than single `--no-<manager>` flags.

You can still mix both syntax in the same configuration file, as well as on the command line.
````

### Overlapping managers

`mpm` supports some overlapping package managers. Take for instance `pacman` and its collection of AUR helpers like `paru` and `yay`. All of these alternatives have the same source of packages as `pacman`. So updates to a single package may show up multiple times, because AUR helpers depends on `pacman` (which is always installed on the system).

You can fine-tune this behaviour by simply excluding redundant managers depending on your preferences.

For instance, if `yay` is your preferred helper and `pacman` and `paru` are polluting your entries, you can setup a configuration file in `~/.config/mpm/config.toml` to exclude the other AUR helpers by default:

```toml
[mpm]
pacman = false
paru = false
```

## Troubleshooting

You can easily debug the way `mpm` source its configuration with the `--show-params`:

```{click:run}
from meta_package_manager.cli import mpm
invoke(mpm, args=["--table-format", "vertical", "--show-params"])
```
