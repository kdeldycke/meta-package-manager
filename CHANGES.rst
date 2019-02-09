Changelog
=========


`2.8.1 (unreleased) <https://github.com/kdeldycke/meta-package-manager/compare/v2.8.0...develop>`_
--------------------------------------------------------------------------------------------------

.. note:: This version is not yet released and is under active development.

* Fix homebrew version.


`2.8.0 (2019-01-03) <https://github.com/kdeldycke/meta-package-manager/compare/v2.7.0...v2.8.0>`_
-------------------------------------------------------------------------------------------------

* Add support for PHP ``composer``.
* Remove ``cask``-specific ``version``, ``sync`` and ``search`` command.
  Closes #47.
* Vanilla brew and cask CLIs now shares the same version requirements.
* Bump minimal requirement of ``brew`` and ``cask`` to ``1.7.4``.
* Activate unittests in Python 3.7.
* Drop Travis unittests on deprecated Ubuntu Precise targets and vintage Mac OS
  X 10.10 and 10.11.
* Use latest macOS 10.12 and 10.13 Travis images.


`2.7.0 (2018-04-02) <https://github.com/kdeldycke/meta-package-manager/compare/v2.6.1...v2.7.0>`_
-------------------------------------------------------------------------------------------------

* Add new ``--ignore-auto-updates`` and ``--include-auto-updates`` boolean
  flags.
* Support even fancier table output rendering, including ``csv`` and ``html``.
* Depends on ``cli-helpers`` package to render tables.
* Removes direct dependency on ``tabulate``.
* Fix minimal version check for ``cask``. Closes #41 and #44.
* Do not run BitBar plugin unittests but on macOS.


`2.6.1 (2017-11-05) <https://github.com/kdeldycke/meta-package-manager/compare/v2.6.0...v2.6.1>`_
-------------------------------------------------------------------------------------------------

* Fix Travis unittests.


`2.6.0 (2017-09-11) <https://github.com/kdeldycke/meta-package-manager/compare/v2.5.0...v2.6.0>`_
-------------------------------------------------------------------------------------------------

* Add support for ``apt`` on Linux systems.
* Use pip 9.0 JSON output. Closes #18.
* Bump minimal requirement of ``pip`` to ``9.0.*``.
* Use new ``brew cask outdated`` command.
* Remove usage of deprecated ``brew cask update`` command.
* Bump minimal requirement of ``cask`` to ``1.1.12``.
* Add dependency on ``simplejson``.
* Bump requirement to ``click_log >= 0.2.0``. Closes #39.
* Replace ``nose`` by ``pytest``.
* Only notify by mail of test failures.


`2.5.0 (2017-03-01) <https://github.com/kdeldycke/meta-package-manager/compare/v2.4.0...v2.5.0>`_
-------------------------------------------------------------------------------------------------

* Auto-detect location of manager CLI on the system.
* Add new ``search`` operation. Closes #22.
* Bump minimal requirement of ``npm`` to ``4.0.*``.
* Rename ``list`` operation to ``installed``.
* Allow use of ``gem``, ``npm`` and ``apm`` managers on Linux.
* Add new ``--stats``/``--no-stats`` boolean flags. Closes #8.
* Add new ``--stop-on-error``/``--continue-on-error`` parameters to make CLI
  errors either blocking or non-blocking.
* Allow reporting of several CLI errors by managers.
* Allow selection of a subset of managers.
* Do not force a ``sync`` before listing installed packages in CLI.
* Rework API documentation.
* Add unittest to cover unicode names for Cask packages. Closes #16.
* Add unittest to cover Cask packages with multiple names. Refs #26.
* Drop support of Python 3.3.


`2.4.0 (2017-01-28) <https://github.com/kdeldycke/meta-package-manager/compare/v2.3.0...v2.4.0>`_
-------------------------------------------------------------------------------------------------

* Add new ``list`` operation. Closes #20.
* Fix upgrade of ``mas`` packages. Closes #32.
* Document BitBar plugin release process.
* Colorize check-marks in CLI output.
* Decouple ``sync`` and ``outdated`` actions in all managers.
* Cache output of ``outdated`` command.
* Add global todo list in documentation.
* Bump requirement to ``boltons >= 17.0.0`` for Python 3.3 compatibility.


`2.3.0 (2017-01-15) <https://github.com/kdeldycke/meta-package-manager/compare/v2.2.0...v2.3.0>`_
-------------------------------------------------------------------------------------------------

* Add Sphinx documentation. Closes #24.
* Add installation instructions. Closes #19.
* Add a list of *Falsehoods Programmers Believe About Package Managers*.
* Add a `.mailmap` config file to consolidate contributor's identity.
* Make it easier to change the font, size and color of text in BitBar plugin.
* Move error icon in BitBar plugin to the front of manager name.
* Fix parsing of ``cask`` packages with multiple names. Closes #26.
* Move BitBar plugin documentation to dedicated page.
* Fix exceptions when commands gives no output. Closes #29 and #31.
* Fix ``cask update`` deprecation warning. Closes #28.
* Activate unittests in Python 3.6.
* Replace double by single-width characters in ``mpm`` output to fix table
  misalignement. Closes #30.


`2.2.0 (2016-12-25) <https://github.com/kdeldycke/meta-package-manager/compare/v2.1.1...v2.2.0>`_
-------------------------------------------------------------------------------------------------

* Rename ``supported`` property of managers to ``fresh``.
* Allow restriction of package managers to a platform. Closes #7.
* Include ``supported`` property in ``mpm managers`` sub-command.
* Add optional submenu rendering for BitBar plugin. Closes #23.
* Move ``Upgrade all`` menu entry to the bottom of earch section in BitBar
  plugin.
* Allow destructive unittests in Travis CI jobs.
* Allow usage of ``pip2`` and ``pip3`` managers on Linux.
* Print current platform in debug messages.
* Unittest detection of managers on each platform.


`2.1.1 (2016-12-17) <https://github.com/kdeldycke/meta-package-manager/compare/v2.1.0...v2.1.1>`_
-------------------------------------------------------------------------------------------------

* Fix parsing of non-point releases of ``brew`` and ``cask`` versions.
  Closes #15.
* Do not render emoji in BitBar plugin menu entries.
* Do not trim error messages rendered in BitBar plugin.
* Do not strip CLI output. Keep original format.
* Fix full changelog link.


`2.1.0 (2016-12-14) <https://github.com/kdeldycke/meta-package-manager/compare/v2.0.0...v2.1.0>`_
-------------------------------------------------------------------------------------------------

* Adjust rendering of BitBar plugin errors.
* Fix fetching of log level names in Python 3.4+.
* Print CLI output in unittests.
* Print more debug info in unittests when CLI produce tracebacks.
* Drop support and unittests on Mac OS X 10.9.
* Add new macOS 10.12 target for Travis CI builds.
* Move BitBar plugin within the Python module.
* Show unmet version requirements in table output for ``mpm managers``
  sub-command.
* Fix duplicates in outdated packages by indexing them by ID.
* Unittest simple call of BitBar plugin.
* Always print the raw, un-normalized version of managers, as reported by
  themselves.
* Fetch version of all managers.
* Make manager version mandatory.
* Bump requirement to ``readme_renderer >= 16.0``.
* Always remove ANSI codes from CLI output.
* Fix rendering of unicode logs.
* Bump requirement to ``click_log >= 0.1.5``.
* Force ``LANG`` environment variable to ``en_US.UTF-8``.
* Share same code path for CLI execution between ``mpm`` and BitBar plugin.
* Add a ``-d/--dry-run`` option to ``mpm upgrade`` sub-command.
* Remove hard-requirement on ``macOS`` platform. Refs #7.
* Fix upgrade of ``setuptools`` in ``macOS`` + Python 3.3 Travis jobs.


`2.0.0 (2016-12-04) <https://github.com/kdeldycke/meta-package-manager/compare/v1.12.0...v2.0.0>`_
--------------------------------------------------------------------------------------------------

* Rewrite BitBar plugin based on ``mpm``. Closes #13.
* Render errors with a monospaced font in BitBar plugin.
* Add missing ``CHANGES.rst`` in ``MANIFEST.in``.
* Make wheels generated under Python 2 environnment available for Python 3 too.
* Only show latest changes in the long description of the package instead of
  the full changelog.
* Add link to full changelog in package's long description.
* Bump trove classifiers status out of beta.
* Fix package keywords.
* Bump minimal ``pycodestyle`` requirement to 2.1.0.
* Always check for package metadata in Travis CI jobs.
* Add ``upgrade_all_cli`` field for each package manager in JSON output of
  ``mpm outdated`` command.


`1.12.0 (2016-12-03) <https://github.com/kdeldycke/meta-package-manager/compare/v1.11.0...v1.12.0>`_
----------------------------------------------------------------------------------------------------

* Rename ``mpm update`` command to ``mpm upgrade``.
* Allow restriction to only one package manager for each sub-command.
  Closes #12.
* Differentiate packages names and IDs. Closes #11.
* Sort list of outdated packages by lower-cased package names first.
* Add ``upgrade_cli`` field for each outdated packages in JSON output.
* Allow user to choose rendering of ``upgrade_cli`` field to either one-liner,
  fragments or BitBar format. Closes #14.
* Include errors reported by each manager in JSON output of ``mpm outdated``
  command.
* Fix parsing of multiple versions of ``cask`` installed packages.
* Fix lexicographical sorting of ``brew`` and ``cask`` package versions.
* Fix fall-back to iterative full upgrade command.
* Fix computation of outdated packages statistics.


`1.11.0 (2016-11-30) <https://github.com/kdeldycke/meta-package-manager/compare/v1.10.0...v1.11.0>`_
----------------------------------------------------------------------------------------------------

* Allow rendering of output data into ``json``.
* Sort list of outdated packages by lower-cased package IDs.
* Bump minimal requirement of ``brew`` to 1.0.0 and ``cask`` to 1.1.0.
* Fix fetching of outdated ``cask`` packages.
* Fix upgrade of ``cask`` packages.


`1.10.0 (2016-10-04) <https://github.com/kdeldycke/meta-package-manager/compare/v1.9.0...v1.10.0>`_
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
* Grammar fix when 0 packages need to be upgraded.


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
