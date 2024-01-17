# Contribution guide

Good candidates for new package manager:

- [Awesome Package Manager](https://github.com/damon-kwok/awesome-package-manager)
- [Package managers from list of terminal CLIs](https://github.com/k4m4/terminals-are-sexy#package-managers)
- [Wikipedia list of package managers](https://en.wikipedia.org/wiki/List_of_software_package_management_systems)
- [GitHub list of package managers](https://github.com/showcases/package-managers)
- {doc}`/benchmark` of other similar tools

## Document a new package manager

Not a coder? No problem.

You can still provides invaluable information. [Open a new issue](https://github.com/kdeldycke/meta-package-manager/issues/new/choose) and fill in the form
with raw output of CLI calls to your manager. Armed with this critical data, a contributor or maintainer
can attempt a blind implementation. From there we'll collectively iterate until we reach a usable level.

This is often the best approach as it sometimes hard to create the same environment as the users.

## Code support for a new package manager

If you're a Python developer, for now the easiest way to have new package managers supported is to:

1. Fork the project.
1. Identify an already implemented package manager that is similar to the new
   one you’d like to add.
1. Duplicate its definition file from the
   {gh}`/managers subfolder <tree/main/meta_package_manager/managers>`.
1. Adapt the new file to the particularities of the new package manager:
   - Always use `--long-form-option` wherever you can to have self-documenting CLIs.
   - Add at least one capture of the CLI output in the docstring to help future maintainers.
   - Reduce verbosity of CLI output to its essential data.
   - Use no-colors and/or non-emoji options if possible to not pollute output.
   - Force the manager to output machine-readable format like JSON, XML or CSV.
   - If you cannot, you'll have to rely on less robust parsing with regular expressions. In which case try to make the output as predictable as possible.
   - Read the {doc}`/falsehoods` to anticipate edge-cases.
   - Read the implementation of the {py:class}`meta_package_manager.base.PackageManager` base class from which all definitions derives.
1. Fix the code until the unittests and type checking passes. Most metadata, format
   constraints and structure for new managers are enforced in the unittest suite. See the
   {doc}`/development` page for more technical details.
1. Submit a PR.
