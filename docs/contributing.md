# {octicon}`git-pull-request` Contribution guide

Good candidates for new package manager:

- [Awesome Package Manager](https://github.com/damon-kwok/awesome-package-manager)
- [Package managers from list of terminal CLIs](https://github.com/k4m4/terminals-are-sexy#package-managers)
- [Wikipedia list of package managers](https://en.wikipedia.org/wiki/List_of_software_package_management_systems)
- [GitHub list of package managers](https://github.com/showcases/package-managers)
- {doc}`/benchmark` of other similar tools

## Document a new package manager

Not a coder? No problem.

You can still provides invaluable information. [Open a new issue](https://github.com/kdeldycke/meta-package-manager/issues/new/choose) and fill in the form with raw output of CLI calls to your manager. Armed with this critical data, a contributor or maintainer can attempt a blind implementation. From there we'll collectively iterate until we reach a usable level.

This is often the best approach as it sometimes hard to create the same environment as the users.

## Code support for a new package manager

If you’re a Python developer, see the {doc}`/add-new-manager` guide for the full implementation checklist: module structure, registration, testing, and documentation updates.

## `claude.md` file

```{include} ../claude.md
---
start-line: 2
---
```
