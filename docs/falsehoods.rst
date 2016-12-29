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
1. A package has only one name (see #26).
1. A package name is unique.
1. Package `names are composed of ASCII characters
<https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/homebrew.py#L205-L206>`_.
1. A package name is the same as its ID (see #11).
1. There is only one way to install a package.
1. Only one version of a package is available on a system.
1. Package `upgrades can be automated
<https://en.wikipedia.org/wiki/Dependency_hell>`_.
1. All `packages have a version
<https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/mas.py#L71-L75>`_.
1. `Versionned packages are immutable
<https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/homebrew.py#L230-L231>`_.
1. Packages can't upgrade themselves.
1. A package can be reinstalled.


Package Managers
----------------

1. Package managers provides the latest version of packages.
1. Package managers provides clean packages.
1. Package managers provides stable softwares.
1. Only `one instance of a package manager exist on the system
<https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/gem.py#L47-L51>`_.
1. You can downgrade packages.
1. A package manager `can update itself
<https://twitter.com/kdeldycke/status/772832404960636928>`_.
1. A package is found under the same name in different package managers.
1. Package managers `can resolve dependencies
<https://github.com/pypa/pip/issues/988>`_.
1. All dependencies are provided by the package manager.
1. Package managers have a CLI.
1. Package managers behave the same accross OSes and distributions.
1. Package managers `tracks installed versions
<https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/homebrew.py#L219-L221>`_.
1. Package managers `can track removed packages
<https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/homebrew.py#L239-L242>`_.
1. Package managers are documented.
1. A package manager has a version.
1. A package manager check package integrity.
1. Package managers are secure.
1. Package managers can be unittested.
1. Package managers `can upgrade all outdated packages
<https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/pip.py#L94-L97>`_.
1. Package managers are forbidden to upgrade other package managers.
1. Packages are only managed by one package manager.
1. Installing a package doesn't require a reboot.
1. Package manager `output is consistent
<https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/mas.py#L42-L44>`_.
1. A package manager can upgrade a package installed by the user.
1. All `users on the system have access to the package manager
<https://github.com/kdeldycke/meta-package-manager/blob/v2.2.0/meta_package_manager/managers/gem.py#L95-L100>`_.
1. Package managers do not remove user data.
1. Package managers `can bootstrap themselves
<https://github.com/Homebrew/brew/blob/master/docs/Common-Issues.md#brew-complains-about-absence-of-command-line-tools>`_.
1. Package managers supports maultiple architectures.
1. You only need one package manager.


Meta
----

1. Implementing a meta package manager `is not a futile pursuit
<https://xkcd.com/1654/>`_.
