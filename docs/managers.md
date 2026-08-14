# {octicon}`file-submodule` Package managers

```{python:render}
from meta_package_manager._docs import manager_population_stats

print(manager_population_stats())
```

`Support` uses the same glyph scale as the benchmark's [`mpm` column](benchmark.md#package-manager-support):

| Glyph | Meaning                                                                                                               |
| :---- | :---------------------------------------------------------------------------------------------------------------------- |
| ✅    | Wrapped by `mpm`, linking to the class implementing it.                                                              |
| ⚠️    | Wrapped by `mpm` and usable, but its upstream is gone.                                                               |
| 🛟    | Not wrapped, yet still reachable through [`mpm upgrade --topgrade`](unsupported.md), which upgrades whatever it detects on the host. |
| ☠️    | Never wrapped, and its [upstream is retired](unsupported.md).                                                        |
| ❌    | Never wrapped: a live tool [declined on its own merits](unsupported.md).                                             |

```{python:render}
from meta_package_manager._docs import managers_index_table

print(managers_index_table())
```

```{toctree}
:glob:
:hidden:
:maxdepth: 1
managers/*
```

The full reason behind each declined tool lives in [unsupported managers](unsupported.md).
