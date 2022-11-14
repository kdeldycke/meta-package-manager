---
name: Bug report
about: Create a report to help us improve
title: ''
labels: 🐛 bug
assignees: ''
---

To help debugging the issue:

- Try running your command with `--verbosity DEBUG` option and inspect the output to look for unexpected execution traces.
- Provide details about identification of package managers with:
  ```
  mpm --verbosity DEBUG --all-managers managers
  ```
- Provide context with:
  ```
  mpm --version
  ```
- Provide the current configuration with:
  ```
  mpm --show-params
  ```
- Try the bleeding edge [development version of `mpm`](https://kdeldycke.github.io/meta-package-manager/development.html#setup-environment)
