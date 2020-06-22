Falsehoods Programmers Believe About Package Managers
=====================================================

Pre-required reads:

* `Falsehoods About Versions
  <https://github.com/xenoterracide/falsehoods/blob/master/versions.md>`_.

* And more generally, this `Awesome List of Falshoods
  <https://github.com/kdeldycke/awesome-falsehood>`_.


Packages
--------

1. A package has a name.
2. A package has only one name (see #26).
3. A package name is unique.
4. Package `names are composed of ASCII characters
   <https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/homebrew.py#L205-L206>`_.
5. A package name is the same as its ID (see #11).
6. There is only one way to install a package.
7. Only one version of a package is available on a system.
8. Package `upgrades can be automated
   <https://en.wikipedia.org/wiki/Dependency_hell>`_.
9. All `packages have a version
   <https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/mas.py#L71-L75>`_.
10. `Versionned packages are immutable
    <https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/homebrew.py#L230-L231>`_.
11. Packages can't upgrade themselves.
12. A package can be reinstalled.


Package Managers
----------------

13. Package managers provides the latest version of packages.
14. Package managers provides clean packages.
15. Package managers provides stable softwares.
16. Only `one instance of a package manager exist on the system
    <https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/gem.py#L47-L51>`_.
17. You can downgrade packages.
18. A package manager `can update itself
    <https://twitter.com/kdeldycke/status/772832404960636928>`_.
19. A package is found under the same name in different package managers.
20. Package managers `can resolve dependencies
    <https://github.com/pypa/pip/issues/988>`_.
21. All dependencies are provided by the package manager.
22. Package managers have a CLI.
23. Package managers behave the same across OSes and distributions.
24. Package managers `tracks installed versions
    <https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/homebrew.py#L219-L221>`_.
25. Package managers `can track removed packages
    <https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/homebrew.py#L239-L242>`_
    (see #17).
26. Package managers are documented.
27. A package manager has a version.
28. A package manager check package integrity.
29. Package managers are secure.
30. Package managers can be unittested.
31. Package managers `can upgrade all outdated packages
    <https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/pip.py#L94-L97>`_.
32. Package managers are forbidden to upgrade other package managers.
33. Packages are only managed by one package manager.
34. Installing a package doesn't require a reboot.
35. Package manager `output is consistent
    <https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/mas.py#L42-L44>`_.
36. A package manager can upgrade a package installed by the user.
37. All `users on the system have access to the package manager
    <https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/gem.py#L95-L100>`_.
38. Package managers do not remove user data.
39. Package managers `can bootstrap themselves
    <https://github.com/Homebrew/brew/blob/master/docs/Common-Issues.md#brew-complains-about-absence-of-command-line-tools>`_.
40. Package managers supports maultiple architectures.
41. You only need one package manager.


Meta
----

42. Implementing a meta package manager `is not a futile pursuit
    <https://xkcd.com/1654/>`_.
