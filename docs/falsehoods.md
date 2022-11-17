# Falsehoods programmers believe about package managers

Implementing `mpm` exposed me to many edge-cases and pitfalls of package management. Here is a list of falsehoods programmers believe about them.

## Packages

1. A package has a name.
1. A package has only one name (see {issue}`26`).
1. A package name is unique.
1. Package
   {gh}`names are composed of ASCII characters <blob/v2.2.0/meta_package_manager/managers/homebrew.py#L205-L206>`.
1. A package name is the same as its ID (see {issue}`11`).
1. There is only one way to install a package.
1. Only one version of a package is available on a system.
1. Package
   [upgrades can be automated](https://en.wikipedia.org/wiki/Dependency_hell).
1. All
   {gh}`packages have a version <blob/v2.2.0/meta_package_manager/managers/mas.py#L71-L75>`.
1. {gh}`Versionned packages are immutable <blob/v2.2.0/meta_package_manager/managers/homebrew.py#L230-L231>`.
1. Packages can’t upgrade themselves.
1. A package can be reinstalled.

## Package managers

1. Package managers provides the latest version of packages.
1. Package managers provides clean packages.
1. Package managers provides stable software.
1. Only
   {gh}`one instance of a package manager exist on the system <blob/v2.2.0/meta_package_manager/managers/gem.py#L47-L51>`.
1. You can downgrade packages.
1. A package manager
   [can update itself](https://twitter.com/kdeldycke/status/772832404960636928).
1. A package is found under the same name in different package managers.
1. Package managers
   [can resolve dependencies](https://github.com/pypa/pip/issues/988).
1. All dependencies are provided by the package manager.
1. Package managers have a CLI.
1. Package managers behave the same across OSes and distributions.
1. Package managers
   {gh}`tracks installed versions <blob/v2.2.0/meta_package_manager/managers/homebrew.py#L219-L221>`.
1. Package managers
   {gh}`can track removed packages <blob/v2.2.0/meta_package_manager/managers/homebrew.py#L239-L242>`
   (see {issue}`17`).
1. Package managers are documented.
1. A package manager has a version.
1. A package manager check package integrity.
1. Package managers are secure.
1. Package managers can be unittested.
1. Package managers
   {gh}`can upgrade all outdated packages <blob/v2.2.0/meta_package_manager/managers/pip.py#L94-L97>`.
1. Package managers are forbidden to upgrade other package managers.
1. Packages are only managed by one package manager.
1. Installing a package doesn’t require a reboot.
1. Package manager
   {gh}`output is consistent <blob/v2.2.0/meta_package_manager/managers/mas.py#L42-L44>`.
1. A package manager can upgrade a package installed by the user.
1. All
   {gh}`users on the system have access to the package manager <blob/v2.2.0/meta_package_manager/managers/gem.py#L95-L100>`.
1. Package managers do not remove user data.
1. Package managers
   [can bootstrap themselves](https://github.com/Homebrew/brew/blob/master/docs/Common-Issues.md#brew-complains-about-absence-of-command-line-tools).
1. Package managers supports multiple architectures.
1. You
   [only need one package manager](https://utcc.utoronto.ca/~cks/space/blog/tech/PackageManagersTwoTypes).

## Meta

1. Implementing a meta package manager
   [is not a futile pursuit](https://xkcd.com/1654/).
1. [Package managers don't need their own conference](https://packaging-con.org).

## See also

- [Falsehoods About Versions](https://github.com/xenoterracide/falsehoods/blob/master/versions.md).
- And more generally, the
  [Awesome List of Falshoods](https://github.com/kdeldycke/awesome-falsehood).
