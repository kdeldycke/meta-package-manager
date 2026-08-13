# {octicon}`file-submodule` Package managers

Each package manager `mpm` supports has a dedicated page detailing the platforms it runs on, the operations `mpm` implements for it, how its CLI is invoked and its version probed, and the ecosystem identifiers it responds to. Everything below renders live from the manager declarations at build time, so it never drifts from the code. The popularity and activity columns are the one exception, sampled weekly from each project's upstream repository and committed here, which is what lets the build report a hundred forges without touching a network.

Tools deliberately left out of this list are catalogued in [unsupported managers](unsupported.md), with the reason for each.

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
