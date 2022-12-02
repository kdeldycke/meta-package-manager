# Configuration

All `mpm` options can be set with a configuration file.

## Location

Location depends on OS (see
[`click-extra` doc](https://kdeldycke.github.io/click-extra/config.html#pattern-matching)):

- macOS:
  `~/Library/Application Support/mpm/*.{toml,yaml,yml,json,ini,xml}`
- Unix:
  `~/.config/mpm/*.{toml,yaml,yml,json,ini,xml}`
- Windows (roaming):
  `C:\Users\<user>\AppData\Roaming\mpm\*.{toml,yaml,yml,json,ini,xml}`

## TOML sample

```toml
# My default configuration file.

[mpm]
verbosity = "DEBUG"
manager = ["brew", "cask"]

[mpm.search]
exact = true
```

## Ignore a manager

A user [was looking](https://github.com/matryer/xbar/issues/777) to
always have it ignore `pip` to speed-up execution. That can be solved with the
following config file:

```toml
[mpm]
exclude = [ "pip",]
```

## Overlapping managers

MPM has support for some overlapping package managers. Take for instance `pacman` and its collection of AUR helpers like `paru` and `yay`. All of the alternative helpers have the same source of packages as `pacman` (except if someone added other repositories to them). So updates to a single package may show up multiple times, because AUR helpers depends on `pacman` (which is always installed on the system).

You can fine-tune this behaviour by simply excluding redundant managers depending on your preferrences.

For instance, if `yay` is your preferred helper and `pacman` is polluting your entries, you can setup a configuration file in `~/.config/mpm/config.toml` to exclude the other AUR helpers by default:

```toml
[mpm]
exclude = [ "pacman", "paru",]
```

## Troubleshooting

You can easely debug the way `mpm` source its configuration with the `--show-params`:

```{eval-rst}
.. click:run::
    from meta_package_manager.cli import mpm
    invoke(mpm, args=["--show-params"])
```
