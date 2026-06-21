# {octicon}`command-palette` CLI parameters

## Help screen

```{click:run}
from meta_package_manager.cli import mpm
invoke(mpm, args=["--help"])
```

## Options

```{eval-rst}
.. click:: meta_package_manager.cli:mpm
    :prog: mpm
    :nested: full
```

## Man pages

The directive below renders a live index of every man page emitted by `click_extra.sphinx` from the `click_extra_manpages` config in `conf.py`. Each entry links to the browser-viewable HTML sibling produced when `mandoc` (preferred) or `groff` is on `PATH` during the docs build. The raw `.1` files sit next to the HTML siblings in `/man/` and are also bundled as `mpm-manpages.tar.gz` on every [GitHub release](https://github.com/kdeldycke/meta-package-manager/releases).

```{click-extra-manpages}
```

## `meta_package_manager.cli` API

```{eval-rst}
.. automodule:: meta_package_manager.cli
   :members:
   :show-inheritance:
   :undoc-members:
```
