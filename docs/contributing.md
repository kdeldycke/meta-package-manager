# {octicon}`git-pull-request` Contribution guide

Candidates for a new package manager come from `mpm`'s own coverage map. The {doc}`/benchmark` holds one row per tool any comparable wrapper drives, so a blank cell in its `mpm` column marks a tool nobody has assessed yet: that is the worklist. {doc}`/unsupported` is the other half of the map, recording each tool already declined and the reason, which is worth checking before proposing one.

## Document a new package manager

Not a coder? No problem.

You can still provide invaluable information. [Open a new issue](https://github.com/kdeldycke/meta-package-manager/issues/new/choose) and fill in the form with raw output of CLI calls to your manager. Armed with this critical data, a contributor or maintainer can attempt a blind implementation. From there we'll collectively iterate until we reach a usable level.

This is often the best approach, as it is sometimes hard to create the same environment as the users.

## Code support for a new package manager

If you’re a Python developer, see the {doc}`/add-new-manager` guide for the full implementation checklist: module structure, registration, testing, and documentation updates.

## `claude.md` file

```{include} ../claude.md
:start-line: 2
```
