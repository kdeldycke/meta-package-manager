Changelog
=========

`1.11.1 (unreleased) <https://github.com/kdeldycke/meta-package-manager/compare/v1.11.0...develop>`_
----------------------------------------------------------------------------------------------------

* Fix parsing of multiple versions of ``cask`` installed packages.
* Fix lexicographical sorting of ``brew`` and ``cask`` package versions.


`1.11.0 (2016-11-30) <https://github.com/kdeldycke/meta-package-manager/compare/v1.10.0...v1.11.1>`_
----------------------------------------------------------------------------------------------------

* Allow rendering of output data into ``json``.
* Sort list of outdated packages by lower-cased package IDs.
* Bump minimal requirement of ``brew`` to 1.0.0 and ``cask`` to 1.1.0.
* Fix fetching of outdated ``cask`` packages.
* Fix update of ``cask`` packages.


`1.10.0 (2016-10-04) <https://github.com/kdeldycke/meta-package-manager/compare/v1.9.0...develop>`_
---------------------------------------------------------------------------------------------------

* Add optionnal ``version`` property on package manager definitions.
* Allow each package manager to set requirement on its own version.
* Let ``mas`` report its own version.
* Bump minimal requirement of ``mas`` to 1.3.1.
* Fetch currently installed version from ``mas``. Closes #4.
* Fix parsing of ``mas`` package versions after the 1.3.1 release.
* Cache lazy properties to speed metadata computation.
* Shows detailed state of package managers in CLI.


`1.9.0 (2016-09-23) <https://github.com/kdeldycke/meta-package-manager/compare/v1.8.0...v1.9.0>`_
-------------------------------------------------------------------------------------------------

* Fix ``bumpversion`` configuration to target ``CHANGES.rst`` instead of
  ``README.rst``.
* Render list of detected managers in a table.
* Use ``conda`` in Travis tests to install specific versions of Python across
  the range of macOS workers.
* Drop support for PyPy while we search a way to install it on macOS with
  Travis.
* Let ``mpm`` auto-detect package manager definitions.
* Show package manager IDs in ``mpm managers`` CLI output.
* Rename ``package_manager.7h.py`` BitBar plugin to
  ``meta_package_manager.7h.py``.
* Give each package manager its own dedicated short string ID.
* Keep a cache of instanciated package manager.
* Add unittests around package manager definitions.
* Do not display location of inactive managers, even if hard-coded.
* Split-up CLI-producing methods and CLI running methods in ``PackageManager``
  base class.
* Add a new ``update`` CLI sub-command.
* Add a new ``sync`` CLI sub-command.
* Rename managers' ``active`` property to ``available``.
* Move all package manager definitions in a dedicated folder.
* Add simple CLI unittests. Closes #2.
* Implement ``outdated`` CLI sub-command.
* Allow selection of table rendering.
* Fix parsing of unversioned cask packages. Closes #6.


`1.8.0 (2016-08-22) <https://github.com/kdeldycke/meta-package-manager/compare/v1.7.0...v1.8.0>`_
-------------------------------------------------------------------------------------------------

* Move the plugin to its own repository.
* Rename ``package-manager`` project to ``meta-package-manager``.
* Add a ``README.rst`` file.
* License under GPLv2+.
* Add ``.gitignore`` config.
* Add Python package skeleton. Closes #1.
* Split ``CHANGES.rst`` out of ``README.rst``.
* Add Travis CI configuration.
* Use semver-like 3-components version number.
* Copy all BitBar plugin code to Python module.
* Give each supported package manager its own module file.
* Add minimal ``mpm`` meta CLI to list supported package managers.
* Add default ``bumpversion``, ``isort``, ``nosetests``, ``coverage``, ``pep8``
  and ``pylint`` default configuration.


`1.7.0 (2016-08-16) <https://github.com/kdeldycke/meta-package-manager/compare/v1.6.0...v1.7.0>`_
-------------------------------------------------------------------------------------------------

* Fix issues with ``$PATH`` not having Homebrew/Macports.
* New workaround for full ``pip`` upgrade command.
* Workaround for Homebrew Cask full upgrade command.
* Grammar fix when 0 packages need updated.


`1.6.0 (2016-08-10) <https://github.com/kdeldycke/meta-package-manager/compare/v1.5.0...v1.6.0>`_
-------------------------------------------------------------------------------------------------

* Work around the lacks of full ``pip`` upgrade command.
* Fix ``UnicodeDecodeError`` on parsing CLI output.


`1.5.0 (2016-07-25) <https://github.com/kdeldycke/meta-package-manager/compare/v1.4.0...v1.5.0>`_
-------------------------------------------------------------------------------------------------

* Add support for ``mas``.
* Don't show all ``stderr`` as ``err`` (check return code for error state).


`1.4.0 (2016-07-10) <https://github.com/kdeldycke/meta-package-manager/compare/v1.3.0...v1.4.0>`_
-------------------------------------------------------------------------------------------------

* Don't attempt to parse empty lines.
* Check for linked ``npm`` packages.
* Support system or Homebrew Ruby Gems (with proper ``sudo`` setup).


`1.3.0 (2016-07-09) <https://github.com/kdeldycke/meta-package-manager/compare/v1.2.0...v1.3.0>`_
-------------------------------------------------------------------------------------------------

* Add changelog.
* Add reference to package manager's issues.
* Force Cask update before evaluating available packages.
* Add sample of command output as version parsing can be tricky.


`1.2.0 (2016-07-08) <https://github.com/kdeldycke/meta-package-manager/compare/v1.1.0...v1.2.0>`_
-------------------------------------------------------------------------------------------------

* Add support for both ``pip2`` and ``pip3``, Node's ``npm``, Atom's ``apm``,
  Ruby's ``gem``.
* Fixup ``brew cask`` checking.
* Don't die on errors.


`1.1.0 (2016-07-07) <https://github.com/kdeldycke/meta-package-manager/compare/v1.0.0...v1.1.0>`_
-------------------------------------------------------------------------------------------------

* Add support for Python's ``pip``.


`1.0.0 (2016-07-05) <https://github.com/kdeldycke/meta-package-manager/commit/170ce9>`_
---------------------------------------------------------------------------------------

* Initial public release.
* Add support for Homebrew and Cask.
