# {octicon}`command-palette` CLI parameters

The reference below walks the live command tree at build time, so every help screen matches the documented release. Each command section is anchored by its command path (like `#mpm-install`), the same scheme the readme and benchmark pages link to.

```{click:tree} mpm
from meta_package_manager.cli import mpm
```

## Man pages

Every command documented above also ships as a Unix manual page, generated from the same live command tree. The {doc}`/man` page indexes them and links each to its browser-viewable rendering.

## `meta_package_manager.cli` API

```{eval-rst}
.. automodule:: meta_package_manager.cli
   :members:
   :show-inheritance:
   :undoc-members:
```
