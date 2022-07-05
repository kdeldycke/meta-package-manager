# Contribution guide

Good candidates for new package manager:

- [Wikipedia list of package managers](https://en.wikipedia.org/wiki/List_of_software_package_management_systems)
- [Awesome list of package managers](https://github.com/k4m4/terminals-are-sexy#package-managers)
- [GitHub list of package managers](https://github.com/showcases/package-managers)
- {doc}`/benchmark` of other similar tools

## Document a new package manager

Not a coder? No problem.

You can still provides invaluable information. Open a new issue and document
there a couple of CLI calls and its output to your manager. With this a contributor or maintainer
can attempt a blind implementation. From there we'll collectively iterate until we reach a useable level.

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
   - Read the {doc}`/falsehoods` to anticipate edge-cases.
   - Read the implementation of the {py:class}`meta_package_manager.base.PackageManager` base class from which all definitions derives.
1. Fix the code until the unittests passes. Most metadata, format
   constraints and structure for new managers are enforced in the unittest suite. See the
   {doc}`/development` page for more technical details.
1. Submit a PR.
