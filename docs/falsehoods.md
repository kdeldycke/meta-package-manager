# {octicon}`unverified` Falsehoods programmers believe about package managers

Implementing `mpm` exposed me to many edge-cases and pitfalls of package management. Here is a list of falsehoods programmers believe about them.

## Packages

01. A package has a name.
02. A package has only one name (see {issue}`26`).
03. A package name is unique.
04. Package
    [names are composed of ASCII characters](https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/homebrew.py#L205-L206).
05. A package name is the same as its ID (see {issue}`11`).
06. There is only one way to install a package.
07. Only one version of a package is available on a system.
08. Shared [dependencies are always compatible](https://en.wikipedia.org/wiki/Dependency_hell).
09. [Version selection is guaranteed to run fast](https://research.swtch.com/version-sat).
10. All
    [packages have a version](https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/mas.py#L71-L75).
11. [Versioned packages are immutable](https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/homebrew.py#L230-L231).
12. Packages can’t upgrade themselves.
13. A package can be reinstalled.

## Package managers

01. Package managers provides the latest version of packages.
02. Package managers provides clean packages.
03. Package managers provides stable software.
04. Only
    [one instance of a package manager exist on the system](https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/gem.py#L47-L51).
05. You can downgrade packages.
06. A package manager
    [can update itself](https://twitter.com/kdeldycke/status/772832404960636928).
07. A package is found under the same name in different package managers.
08. Package managers
    [can resolve dependencies](https://github.com/pypa/pip/issues/988).
09. Package managers [resolve dependencies the same way](https://github.com/ecosyste-ms/package-manager-resolvers).
10. Package managers [solvers are correct and complete](https://arxiv.org/abs/2011.07851).
11. All dependencies are provided by the package manager.
12. Package managers have a CLI.
13. Package managers behave the same across OSes and distributions.
14. Package managers
    [tracks installed versions](https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/homebrew.py#L219-L221).
15. Package managers
    [can track removed packages](https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/homebrew.py#L239-L242)
    (see {issue}`17`).
16. Package managers are documented.
17. A package manager has a version.
18. A package manager check package integrity.
19. Package managers are secure.
20. Package managers can be unittested.
21. Package managers
    [can upgrade all outdated packages](https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/pip.py#L94-L97).
22. Package managers are forbidden to upgrade other package managers.
23. Packages are only managed by one package manager.
24. Installing a package doesn’t require a reboot.
25. Package manager
    [output is consistent](https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/mas.py#L42-L44).
26. A package manager can upgrade a package installed by the user.
27. All
    [users on the system have access to the package manager](https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/gem.py#L95-L100).
28. Package managers do not remove user data.
29. Package managers
    [can bootstrap themselves](https://github.com/Homebrew/brew/blob/master/docs/Common-Issues.md#brew-complains-about-absence-of-command-line-tools).
30. Package managers supports multiple architectures.
31. You
    [only need one package manager](https://utcc.utoronto.ca/~cks/space/blog/tech/PackageManagersTwoTypes).

## Meta

1. Implementing a meta package manager
   [is not a futile pursuit](https://xkcd.com/1654/).
2. [Package managers don't need their own conference](https://packaging-con.org).

## See also

- [So you want to write a package manager](https://medium.com/@sdboyer/so-you-want-to-write-a-package-manager-4ae9c17d9527).
- [Nine Circles of Dependency Hell](https://matt-rickard.com/nine-circles-of-dependency-hell).
- [Falsehoods About Versions](https://github.com/xenoterracide/falsehoods/blob/master/versions.md).
- And more generally, the
  [Awesome List of Falsehoods](https://github.com/kdeldycke/awesome-falsehood).
