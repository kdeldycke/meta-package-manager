---
name: Bug report
about: Create a report to help us improve
title: ''
labels: "\U0001F41B bug"
assignees: ''

---

To help debugging the issue:

- Try running your command with `--verbosity DEBUG` option
- Provide details about identification of package managers with:
    ```
    mpm --verbosity DEBUG --all-managers managers
    ```
- Provide context with:
    ```
    mpm --version
    ```
- Try the bleeding edge [development version of `mpm`](https://kdeldycke.github.io/meta-package-manager/development.html#setup-environment)
