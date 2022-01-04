# Configuration

All `mpm` options defaults can be specified with a configuration file.

## Location

Location depends on OS (see [`click-extra` doc](https://github.com/kdeldycke/click-extra/blob/v1.3.0/click_extra/config.py#L49-L63)):

    * macOS & Linux: `~/.mpm/config.toml`

    * Windows: `C:\Users\<user>\AppData\Roaming\mpm\config.toml`

## Sample

``` toml
# My default configuration file.

[mpm]
verbosity = "DEBUG"
manager = ["brew", "cask"]

[mpm.search]
exact = true
```

## Ignore a manager

A user of `mpm` [was looking](https://github.com/matryer/xbar/issues/777) to always have it ignore `pip` to speed-up execution. That can be solved with the following config file:

``` toml
[mpm]
manager = ["pip"]
```
