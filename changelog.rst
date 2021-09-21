Changelog
=========


`4.2.0 (unreleased) <https://github.com/kdeldycke/meta-package-manager/compare/v4.1.0...develop>`_
--------------------------------------------------------------------------------------------------

.. note:: This version is not yet released and is under active development.

* [mpm] Add support for TOML configuration file. Closes #66.
* [mpm] Add ``-C`` / ``--config`` option to point to specific configuration file.
* [mpm] Upgrade to Click 8.x.
* [mpm] Add support for ``psql_unicode`` and ``minimal`` table format.
* [mpm] Set default table format to ``psql_unicode`` instead of ``fancy_grid`` to
  reduce visual noise.
* [mpm] Add support for environment variables for all parameters, prefixed with ``MPM_``.
* [mpm] Let Click produce default values in help screen.
* [mpm] Replace ``tomlkit`` dependency by ``tomli`` and ``tomli_w``.
* [xbar] Fix xbar plugin output format.
* [xbar] Rename ``VAR_SUBMENU_lAYOUT`` environment variable to ``VAR_SUBMENU_LAYOUT``.
* [mpm] Remove support for ``--cli-format bitbar`` option. Use ``xbar`` value instead.


`4.1.0 (2021-05-01) <https://github.com/kdeldycke/meta-package-manager/compare/v4.0.0...v4.1.0>`_
-------------------------------------------------------------------------------------------------

* [xbar] Add new ``Submenu layout`` boolean option in xbar plugin UI.
* [xbar] Rename ``XBAR_MPM_SUBMENU`` environment variable to ``VAR_SUBMENU_lAYOUT``.
* [mpm] Allow search of multiple CLI names for a package manager.
* [pip] Fix search of ``python3`` binary on macOS. Closes #247.


`4.0.0 (2021-04-27) <https://github.com/kdeldycke/meta-package-manager/compare/v3.6.0...v4.0.0>`_
-------------------------------------------------------------------------------------------------

* [xbar] Ugrade BitBar plugin to new xbar format.
* [xbar] Drop xbar plugin requirement on Python 2.x and bump it up to Python 3.7.3.
* [xbar] Update references of BitBar to xbar.
* [xbar] Rename ``BITBAR_MPM_SUBMENU`` environment variable to ``XBAR_MPM_SUBMENU``.
* [mpm] Rename ``--cli-format bitbar`` option to ``--cli-format xbar``.
* [mpm] Auto-generate API documentation via a GitHub action workflow.
* [mpm] Only trigger dependency graph update on tagging to reduce noise.
* [mpm] Re-introduce ``isort``.


`3.6.0 (2021-01-03) <https://github.com/kdeldycke/meta-package-manager/compare/v3.5.2...v3.6.0>`_
-------------------------------------------------------------------------------------------------

* [brew] Add support for ``brew`` on Linux.
* [brew,cask] Bump minimal requirement of ``brew`` to ``2.7.0``.
* [cask] Address deprecation of ``cask`` CLI subcommands.
* [pip] ``pip search`` has been disabled by maintainers because of server-side
  high-load.
* [mpm] Add test runs against new OSes and distributions: ``ubuntu-18.04`` and
  ``macos-11.0``.
* [mpm] Remove ``pycodestyle`` now that we rely on ``black``.
* [mpm] Add emoji to issue labels.


`3.5.2 (2020-10-29) <https://github.com/kdeldycke/meta-package-manager/compare/v3.5.1...v3.5.2>`_
-------------------------------------------------------------------------------------------------

* [mpm] Run tests on Python 3.9.
* [mpm] Upgrade to ``Poetry 1.1.0``.
* [mpm] Colorize version screen and add debug data.
* [mpm] Test publishing to PyPi in dry-run mode by the way of Poetry.
* [mpm] Make all keyword-based choice parameters (``--manager``, ``--exclude``,
  ``--output-format``, ``--sort-by`` and ``--cli-format``) case-insensitive.
* [mpm] Pin versions of OSes and distributions in CI workflows to ``ubuntu-20.04``,
  ``macos-10.15`` and ``windows-2019``.
* [mpm] Always print errors in unittest's CLI calls.
* [mpm] Slow-down tests to prevent PyPi rate-limiting on live API.
* [mpm] Fix ``brew`` setup on macOS CI runners.
* [mpm] Fix ``npm`` setup in Ubuntu 18.04 and 20.04 CI runners.
* [mpm] Use latest ``Atom`` version in Ubuntu CI runners.


`3.5.1 (2020-10-03) <https://github.com/kdeldycke/meta-package-manager/compare/v3.5.0...v3.5.1>`_
-------------------------------------------------------------------------------------------------

* [mpm] Defaults to ``--continue-on-error`` instead of stopping.
* [mpm] Force checking of CLI being a file.
* [mpm] Auto-optimize images.
* [mpm] Auto-lock closed issues and PRs after a moment of inactivity.


`3.5.0 (2020-09-20) <https://github.com/kdeldycke/meta-package-manager/compare/v3.4.2...v3.5.0>`_
-------------------------------------------------------------------------------------------------

* [mpm] Fix ``--stop-on-error`` parameter: it was never taken into account.
* [brew,cask] Bump minimal requirement of ``brew`` to ``2.5.0``.
* [brew,cask] Fix warning to deprecated options.
* [npm] Always fix JSON parsing on error for any npm subcommand.


`3.4.2 (2020-09-13) <https://github.com/kdeldycke/meta-package-manager/compare/v3.4.1...v3.4.2>`_
-------------------------------------------------------------------------------------------------

* [brew,cask] Do not mix-up brew and cask upgrades.
* [npm] Skip parsing of JSON results on error.


`3.4.1 (2020-09-02) <https://github.com/kdeldycke/meta-package-manager/compare/v3.4.0...v3.4.1>`_
-------------------------------------------------------------------------------------------------

* [mpm] Rename ``master`` branch to ``main``.


`3.4.0 (2020-08-18) <https://github.com/kdeldycke/meta-package-manager/compare/v3.3.0...v3.4.0>`_
-------------------------------------------------------------------------------------------------

* [yarn] Set minimal requirement to 1.20.0.
* [yarn] Fix deprecated global arguments.
* [bitbar] Force refresh of local package databases before fetching outdated
  ones.
* [mpm] Add utilities to read a config TOML file. Refs #66.
* [mpm] Auto-format Python code with Black.
* [mpm] Move ``pytest`` config from ``setup.py`` to ``pyproject.toml``.
* [mpm] Removes ``isort``.
* [mpm] Auto-update Python's dependencies.
* [mpm] Auto-update GitHub actions.
* [mpm] Auto-update ``.gitignore`` file.
* [mpm] Auto-update ``.mailmap`` file.
* [mpm] Lint all YAML files. Add dependency on ``yamllint`` package.
* [mpm] Removes ``requires.io`` and Scrutinizer badges.
* [mpm] Revert to ``pipdeptree`` to produce package dependency graph.


`3.3.0 (2020-06-23) <https://github.com/kdeldycke/meta-package-manager/compare/v3.2.0...v3.3.0>`_
-------------------------------------------------------------------------------------------------

* [bitbar] Each entry in the drop-down menu can now be called into a terminal
  to track the execution by holding the ``Option`` key.
* [bitbar] Fix rendering of upgrade CLI in Bitbar dialect.
* [mpm] Hint for lack of ``sync`` and ``cleanup`` support by managers.
* [mpm] Do not print table headers if there is no row to print.
* [mpm] Always print non-fatal ``<stderr>`` output as warning mode.
* [mpm] Skip table rendering tests if no table is printed to stdout. Fixes
  flacky tests.
* [mpm] Replace internal helpers with upstreamed ``boltons 20.2.0`` utils.
* [mpm] Force test marked as ``xfail`` count as failure if they succeed.
* [mpm] Always check wheel content.
* [mpm] Automate creation of GitHub release.
* [mpm] Automate publishing of package to PyPi on tagging.
* [mpm] Save build artifacts on each CI runs.
* [mpm] Auto-sort module imports.
* [mpm] Auto-fix common typos.
* [mpm] Lint JSON files.
* [mpm] Automate GitHub label generation and synchronization.
* [mpm] Automaticcaly applies labels on PRs and issues depending on their
  changed files and content.
* [mpm] Check label rules against manager definitions. Adds development
  dependency on ``PyYAML``.


`3.2.0 (2020-05-31) <https://github.com/kdeldycke/meta-package-manager/compare/v3.1.0...v3.2.0>`_
-------------------------------------------------------------------------------------------------

* [snap] Add support for ``snap`` on Linux.
* [cask] Rely on JSON output to fetch outdated packages.
* [brew,cask] Bump minimal requirement to 2.2.15.
* [pip] Remove ``pip2``/``pip3`` distinctions, use system's python and call
  ``pip`` module.
* [windows] Allow blacklisting some table rendering on Windows.
* [mpm] Add ``--time`` / ``--no-time`` flag to show elapsed execution time.
  Closes #9.
* [mpm] Print table rendering, stats and timing in console output instead of
  logger to allow them to be greppable.
* [bitbar] Test plugin with Python 2.7.
* [mpm] Allow for manager-specific search path to help hunting down CLIs.
* [mpm] Highlight CLI and indent results in debug output.
* [mpm] Bump dependency to ``pylint 2.5`` and ``cli-helpers 2.0``.
* [mpm] Use local copy of ``boltons`` utils while we wait for upstream release.
* [mpm] Move pylint config from ``setup.cfg`` to ``pyproject.toml``.
* [mpm] Fail CI and QA checks if pylint score lower than 9.
* [mpm] Add more platform definition unittests.
* [mpm] Unittests all rendering modes in all subcommands.
* [mpm] Randomize unittests.
* [mpm] Drop support of Python 3.6.
* [mpm] Use group-tabs in Sphinx docs.


`3.1.0 (2020-04-02) <https://github.com/kdeldycke/meta-package-manager/compare/v3.0.0...v3.1.0>`_
-------------------------------------------------------------------------------------------------

* [mpm] Add new ``cleanup`` command. Closes #5.
* [mpm] Improve table sorting with new version-aware tokenizer.
* [mpm] Highlight manager IDs depending on their availability in ``managers``
  command.
* [gem] Ignore ``default:`` prefix on package version parsing.
* [mpm] Remove ``packaging`` dependency. Rely on internal version parsing.
* [mpm] Add new ``--exact`` and ``--extended`` parameters to ``search``
  command.
* [mpm] Highlight search matches in console output.
* [mas] Retrieve version in search results.
* [mas] Bump minimal version to ``1.6.1``.
* [mpm] Allow stats to be printed for ``backup`` command.
* [gem] Bump minimal requirement to ``2.5.0``.


`3.0.0 (2020-03-25) <https://github.com/kdeldycke/meta-package-manager/compare/v2.9.0...v3.0.0>`_
-------------------------------------------------------------------------------------------------

* [mpm] Add new ``backup`` and dummy ``restore`` commands to respectively dump
  and load up list of installed packages to/from a TOML file. Refs #38.
* [mpm] Add dependency on ``tomlkit``.
* [yarn] Add support for ``yarn`` package manager for Linux, macOS and Windows.
* [yarn] Install yarn on all unittest platforms.
* [mpm] Allow exclusion of a subset of package managers. Closes #45.
* [pip] Collect installer metadata on listing.
* [pip] Bump minimal requirement of ``pip`` to ``10.0.*``.
* [mpm] Prepend ``/usr/local/bin`` to cli search path.
* [npm] ``install package@version`` instead of ``update package``.
* [npm] Skip update notifier.
* [brew,cask] Allow independent search for each manager.
* [brew,cask] Bump minimal requirement of to ``2.2.9``.
* [mpm] Allow sorting restuls by packages, managers or version. Closes #35
  and #37.
* [mpm] Add shell completion for Bash, Zsh and Fish.
* [mpm] Do not force sync when calling outdated. Closes #36.
* [apt] Fallback on ``apt version apt`` when looking for version. Closes #57
  and #52.
* [mpm] Removes all copyright dates.
* [mpm] Replace unmaintained ``bumpversion`` by ``bump2version``.
* [mpm] Raise requirement to ``click 7.1``.
* [mpm] Raise requirement to ``boltons >= 20.0``.


`2.9.0 (2020-03-18) <https://github.com/kdeldycke/meta-package-manager/compare/v2.8.0...v2.9.0>`_
-------------------------------------------------------------------------------------------------

* [mpm] Drop support of Python 2.7, 3.4 and 3.5. Add support for Python 3.8.
* [windows] Add support for ``apm``, ``composer``, ``gem``, ``npm`` and
  ``pip2`` on Windows.
* [linux] Add support for ``Flatpak`` and ``opkg`` package managers on Linux.
* [gem] Force Ruby ``gem`` to install packages to user-install by default.
  Refs #58.
* [pip] Force Python ``pip`` upgrade to user-installed packages. Refs #58.
* [brew] Fix call to ``brew upgrade --cleanup``. Refs #50.
* [brew] Fix parsing of ``brew`` version. Closes #49 and #51.
* [mpm] Switch from Travis to GitHub actions.
* [composer] Install ``composer`` in all platforms CI runners.
* [linux] Install ``flatpak`` in Linux CI runner.
* [windows] Install ``apm`` in Windows CI runner.
* [mpm] Bump requirement to ``click-log >= 0.3``.
* [mpm] Add non-blocking Pylint code quality checks in CI.
* [mpm] Check for conflicting dependencies in CI.
* [mpm] Use Poetry for package and virtualenv management.
* [mpm] Replace ``pipdeptree`` by Poetry CLI output.
* [mpm] Remove ``backports.shutil_which`` dependency.
* [mpm] Update ``.gitignore``.
* [mpm] Drop all Python 3.0 ``__future__`` imports.
* [mpm] Add detailed usage CLI page in documentation.


`2.8.0 (2019-01-03) <https://github.com/kdeldycke/meta-package-manager/compare/v2.7.0...v2.8.0>`_
-------------------------------------------------------------------------------------------------

* [composer] Add support for PHP ``composer``.
* [cask] Remove ``cask``-specific ``version``, ``sync`` and ``search`` command.
  Closes #47.
* [brew] Vanilla brew and cask CLIs now shares the same version requirements.
* [brew] Bump minimal requirement of ``brew`` and ``cask`` to ``1.7.4``.
* [mpm] Activate unittests in Python 3.7.
* [mpm] Drop Travis unittests on deprecated Ubuntu Precise targets and vintage
  Mac OS X 10.10 and 10.11.
* [mpm] Use latest macOS 10.12 and 10.13 Travis images.


`2.7.0 (2018-04-02) <https://github.com/kdeldycke/meta-package-manager/compare/v2.6.1...v2.7.0>`_
-------------------------------------------------------------------------------------------------

* [mpm] Add new ``--ignore-auto-updates`` and ``--include-auto-updates``
  boolean flags.
* [mpm] Support even fancier table output rendering, including ``csv`` and
  ``html``.
* [mpm] Depends on ``cli-helpers`` package to render tables.
* [mpm] Removes direct dependency on ``tabulate``.
* [cask] Fix minimal version check for ``cask``. Closes #41 and #44.
* [bitbar] Do not run BitBar plugin unittests but on macOS.


`2.6.1 (2017-11-05) <https://github.com/kdeldycke/meta-package-manager/compare/v2.6.0...v2.6.1>`_
-------------------------------------------------------------------------------------------------

* [mpm] Fix Travis unittests.


`2.6.0 (2017-09-11) <https://github.com/kdeldycke/meta-package-manager/compare/v2.5.0...v2.6.0>`_
-------------------------------------------------------------------------------------------------

* [apt] Add support for ``apt`` on Linux systems.
* [pip] Use pip 9.0 JSON output. Closes #18.
* [pip] Bump minimal requirement of ``pip`` to ``9.0.*``.
* [cask] Use new ``brew cask outdated`` command.
* [cask] Remove usage of deprecated ``brew cask update`` command.
* [cask] Bump minimal requirement of ``cask`` to ``1.1.12``.
* [mpm] Add dependency on ``simplejson``.
* [mpm] Bump requirement to ``click_log >= 0.2.0``. Closes #39.
* [mpm] Replace ``nose`` by ``pytest``.
* [mpm] Only notify by mail of test failures.


`2.5.0 (2017-03-01) <https://github.com/kdeldycke/meta-package-manager/compare/v2.4.0...v2.5.0>`_
-------------------------------------------------------------------------------------------------

* [mpm] Auto-detect location of manager CLI on the system.
* [mpm] Add new ``search`` operation. Closes #22.
* [npm] Bump minimal requirement of ``npm`` to ``4.0.*``.
* [mpm] Rename ``list`` operation to ``installed``.
* [gem,npm,apm,linux] Allow use of ``gem``, ``npm`` and ``apm`` managers on
  Linux.
* [mpm] Add new ``--stats``/``--no-stats`` boolean flags. Closes #8.
* [mpm] Add new ``--stop-on-error``/``--continue-on-error`` parameters to make
  CLI errors either blocking or non-blocking.
* [mpm] Allow reporting of several CLI errors by managers.
* [mpm] Allow selection of a subset of managers.
* [mpm] Do not force a ``sync`` before listing installed packages in CLI.
* [mpm] Rework API documentation.
* [cask] Add unittest to cover unicode names for Cask packages. Closes #16.
* [cask] Add unittest to cover Cask packages with multiple names. Refs #26.
* [mpm] Drop support of Python 3.3.


`2.4.0 (2017-01-28) <https://github.com/kdeldycke/meta-package-manager/compare/v2.3.0...v2.4.0>`_
-------------------------------------------------------------------------------------------------

* [mpm] Add new ``list`` operation. Closes #20.
* [mas] Fix upgrade of ``mas`` packages. Closes #32.
* [bitbar] Document BitBar plugin release process.
* [mpm] Colorize check-marks in CLI output.
* [mpm] Decouple ``sync`` and ``outdated`` actions in all managers.
* [mpm] Cache output of ``outdated`` command.
* [mpm] Add global todo list in documentation.
* [mpm] Bump requirement to ``boltons >= 17.0.0`` for Python 3.3 compatibility.


`2.3.0 (2017-01-15) <https://github.com/kdeldycke/meta-package-manager/compare/v2.2.0...v2.3.0>`_
-------------------------------------------------------------------------------------------------

* [mpm] Add Sphinx documentation. Closes #24.
* [mpm] Add installation instructions. Closes #19.
* [mpm] Add a list of *Falsehoods Programmers Believe About Package Managers*.
* [mpm] Add a ``.mailmap`` config file to consolidate contributor's identity.
* [bitbar] Make it easier to change the font, size and color of text in BitBar
  plugin.
* [bitbar] Move error icon in BitBar plugin to the front of manager name.
* [cask] Fix parsing of ``cask`` packages with multiple names. Closes #26.
* [bitbar] Move BitBar plugin documentation to dedicated page.
* [mpm] Fix exceptions when commands gives no output. Closes #29 and #31.
* [cask] Fix ``cask update`` deprecation warning. Closes #28.
* [mpm] Activate unittests in Python 3.6.
* [mpm] Replace double by single-width characters in ``mpm`` output to fix
  table misalignement. Closes #30.


`2.2.0 (2016-12-25) <https://github.com/kdeldycke/meta-package-manager/compare/v2.1.1...v2.2.0>`_
-------------------------------------------------------------------------------------------------

* [mpm] Rename ``supported`` property of managers to ``fresh``.
* [mpm] Allow restriction of package managers to a platform. Closes #7.
* [mpm] Include ``supported`` property in ``mpm managers`` sub-command.
* [bitbar] Add optional submenu rendering for BitBar plugin. Closes #23.
* [bitbar] Move ``Upgrade all`` menu entry to the bottom of each section in
  BitBar plugin.
* [pip] Allow destructive unittests in Travis CI jobs.
* [pip] Allow usage of ``pip2`` and ``pip3`` managers on Linux.
* [mpm] Print current platform in debug messages.
* [mpm] Unittest detection of managers on each platform.


`2.1.1 (2016-12-17) <https://github.com/kdeldycke/meta-package-manager/compare/v2.1.0...v2.1.1>`_
-------------------------------------------------------------------------------------------------

* [brew,cask] Fix parsing of non-point releases of ``brew`` and ``cask``
  versions. Closes #15.
* [bitbar] Do not render emoji in BitBar plugin menu entries.
* [bitbar] Do not trim error messages rendered in BitBar plugin.
* [mpm] Do not strip CLI output. Keep original format.
* [mpm] Fix full changelog link.


`2.1.0 (2016-12-14) <https://github.com/kdeldycke/meta-package-manager/compare/v2.0.0...v2.1.0>`_
-------------------------------------------------------------------------------------------------

* [bitbar] Adjust rendering of BitBar plugin errors.
* [mpm] Fix fetching of log level names in Python 3.4+.
* [mpm] Print CLI output in unittests.
* [mpm] Print more debug info in unittests when CLI produce tracebacks.
* [macos] Drop support and unittests on Mac OS X 10.9.
* [macos] Add new macOS 10.12 target for Travis CI builds.
* [bitbar] Move BitBar plugin within the Python module.
* [mpm] Show unmet version requirements in table output for ``mpm managers``
  sub-command.
* [mpm] Fix duplicates in outdated packages by indexing them by ID.
* [bitbar] Unittest simple call of BitBar plugin.
* [mpm] Always print the raw, un-normalized version of managers, as reported by
  themselves.
* [mpm] Fetch version of all managers.
* [mpm] Make manager version mandatory.
* [mpm] Bump requirement to ``readme_renderer >= 16.0``.
* [mpm] Always remove ANSI codes from CLI output.
* [mpm] Fix rendering of unicode logs.
* [mpm] Bump requirement to ``click_log >= 0.1.5``.
* [bitbar] Force ``LANG`` environment variable to ``en_US.UTF-8``.
* [mpm,bitbar] Share same code path for CLI execution between ``mpm`` and
  BitBar plugin.
* [mpm] Add a ``-d/--dry-run`` option to ``mpm upgrade`` sub-command.
* [macos] Remove hard-requirement on ``macOS`` platform. Refs #7.
* [mpm,macos] Fix upgrade of ``setuptools`` in ``macOS`` + Python 3.3 Travis
  jobs.


`2.0.0 (2016-12-04) <https://github.com/kdeldycke/meta-package-manager/compare/v1.12.0...v2.0.0>`_
--------------------------------------------------------------------------------------------------

* [bitbar] Rewrite BitBar plugin based on ``mpm``. Closes #13.
* [bitbar] Render errors with a monospaced font in BitBar plugin.
* [mpm] Add missing ``CHANGES.rst`` in ``MANIFEST.in``.
* [mpm] Make wheels generated under Python 2 environnment available for Python
  3 too.
* [mpm] Only show latest changes in the long description of the package instead
  of the full changelog.
* [mpm] Add link to full changelog in package's long description.
* [mpm] Bump trove classifiers status out of beta.
* [mpm] Fix package keywords.
* [mpm] Bump minimal ``pycodestyle`` requirement to 2.1.0.
* [mpm] Always check for package metadata in Travis CI jobs.
* [mpm] Add ``upgrade_all_cli`` field for each package manager in JSON output
  of ``mpm outdated`` command.


`1.12.0 (2016-12-03) <https://github.com/kdeldycke/meta-package-manager/compare/v1.11.0...v1.12.0>`_
----------------------------------------------------------------------------------------------------

* [mpm] Rename ``mpm update`` command to ``mpm upgrade``.
* [mpm] Allow restriction to only one package manager for each sub-command.
  Closes #12.
* [mpm] Differentiate packages names and IDs. Closes #11.
* [mpm] Sort list of outdated packages by lower-cased package names first.
* [mpm] Add ``upgrade_cli`` field for each outdated packages in JSON output.
* [mpm,bitbar] Allow user to choose rendering of ``upgrade_cli`` field to
  either one-liner, fragments or BitBar format. Closes #14.
* [mpm] Include errors reported by each manager in JSON output of
  ``mpm outdated`` command.
* [cask] Fix parsing of multiple versions of ``cask`` installed packages.
* [brew,cask] Fix lexicographical sorting of ``brew`` and ``cask`` package
  versions.
* [mpm] Fix fall-back to iterative full upgrade command.
* [mpm] Fix computation of outdated packages statistics.


`1.11.0 (2016-11-30) <https://github.com/kdeldycke/meta-package-manager/compare/v1.10.0...v1.11.0>`_
----------------------------------------------------------------------------------------------------

* [mpm] Allow rendering of output data into ``json``.
* [mpm] Sort list of outdated packages by lower-cased package IDs.
* [brew,cask] Bump minimal requirement of ``brew`` to 1.0.0 and ``cask`` to
  1.1.0.
* [cask] Fix fetching of outdated ``cask`` packages.
* [cask] Fix upgrade of ``cask`` packages.


`1.10.0 (2016-10-04) <https://github.com/kdeldycke/meta-package-manager/compare/v1.9.0...v1.10.0>`_
---------------------------------------------------------------------------------------------------

* [mpm] Add optionnal ``version`` property on package manager definitions.
* [mpm] Allow each package manager to set requirement on its own version.
* [mas] Let ``mas`` report its own version.
* [mas] Bump minimal requirement of ``mas`` to 1.3.1.
* [mas] Fetch currently installed version from ``mas``. Closes #4.
* [mas] Fix parsing of ``mas`` package versions after the 1.3.1 release.
* [mpm] Cache lazy properties to speed metadata computation.
* [mpm] Shows detailed state of package managers in CLI.


`1.9.0 (2016-09-23) <https://github.com/kdeldycke/meta-package-manager/compare/v1.8.0...v1.9.0>`_
-------------------------------------------------------------------------------------------------

* [mpm] Fix ``bumpversion`` configuration to target ``CHANGES.rst`` instead of
  ``README.rst``.
* [mpm] Render list of detected managers in a table.
* [macos] Use ``conda`` in Travis tests to install specific versions of Python
  across the range of macOS workers.
* [macos] Drop support for PyPy while we search a way to install it on macOS
  with Travis.
* [mpm] Let ``mpm`` auto-detect package manager definitions.
* [mpm] Show package manager IDs in ``mpm managers`` CLI output.
* [mpm] Rename ``package_manager.7h.py`` BitBar plugin to
  ``meta_package_manager.7h.py``.
* [mpm] Give each package manager its own dedicated short string ID.
* [mpm] Keep a cache of instanciated package manager.
* [mpm] Add unittests around package manager definitions.
* [mpm] Do not display location of inactive managers, even if hard-coded.
* [mpm] Split-up CLI-producing methods and CLI running methods in
  ``PackageManager`` base class.
* [mpm] Add a new ``update`` CLI sub-command.
* [mpm] Add a new ``sync`` CLI sub-command.
* [mpm] Rename managers' ``active`` property to ``available``.
* [mpm] Move all package manager definitions in a dedicated folder.
* [mpm] Add simple CLI unittests. Closes #2.
* [mpm] Implement ``outdated`` CLI sub-command.
* [mpm] Allow selection of table rendering.
* [cask] Fix parsing of unversioned cask packages. Closes #6.


`1.8.0 (2016-08-22) <https://github.com/kdeldycke/meta-package-manager/compare/v1.7.0...v1.8.0>`_
-------------------------------------------------------------------------------------------------

* [mpm] Move the plugin to its own repository.
* [mpm] Rename ``package-manager`` project to ``meta-package-manager``.
* [mpm] Add a ``README.rst`` file.
* [mpm] License under GPLv2+.
* [mpm] Add ``.gitignore`` config.
* [mpm] Add Python package skeleton. Closes #1.
* [mpm] Split ``CHANGES.rst`` out of ``README.rst``.
* [mpm] Add Travis CI configuration.
* [mpm] Use semver-like 3-components version number.
* [bitbar] Copy all BitBar plugin code to Python module.
* [mpm] Give each supported package manager its own module file.
* [mpm] Add minimal ``mpm`` meta CLI to list supported package managers.
* [mpm] Add default ``bumpversion``, ``isort``, ``nosetests``, ``coverage``,
  ``pep8`` and ``pylint`` default configuration.


`1.7.0 (2016-08-16) <https://github.com/kdeldycke/meta-package-manager/compare/v1.6.0...v1.7.0>`_
-------------------------------------------------------------------------------------------------

* [brew] Fix issues with ``$PATH`` not having Homebrew/Macports.
* [pip] New workaround for full ``pip`` upgrade command.
* [cask] Workaround for Homebrew Cask full upgrade command.
* [mpm] Grammar fix when 0 packages need to be upgraded.


`1.6.0 (2016-08-10) <https://github.com/kdeldycke/meta-package-manager/compare/v1.5.0...v1.6.0>`_
-------------------------------------------------------------------------------------------------

* [pip] Work around the lacks of full ``pip`` upgrade command.
* [mpm] Fix ``UnicodeDecodeError`` on parsing CLI output.


`1.5.0 (2016-07-25) <https://github.com/kdeldycke/meta-package-manager/compare/v1.4.0...v1.5.0>`_
-------------------------------------------------------------------------------------------------

* [mas] Add support for ``mas``.
* [mpm] Don't show all ``stderr`` as ``err`` (check return code for error
  state).


`1.4.0 (2016-07-10) <https://github.com/kdeldycke/meta-package-manager/compare/v1.3.0...v1.4.0>`_
-------------------------------------------------------------------------------------------------

* [mpm] Don't attempt to parse empty lines.
* [npm] Check for linked ``npm`` packages.
* [gem] Support system or Homebrew Ruby Gems (with proper ``sudo`` setup).


`1.3.0 (2016-07-09) <https://github.com/kdeldycke/meta-package-manager/compare/v1.2.0...v1.3.0>`_
-------------------------------------------------------------------------------------------------

* [mpm] Add changelog.
* [mpm] Add reference to package manager's issues.
* [cask] Force Cask update before evaluating available packages.
* [mpm] Add sample of command output as version parsing can be tricky.


`1.2.0 (2016-07-08) <https://github.com/kdeldycke/meta-package-manager/compare/v1.1.0...v1.2.0>`_
-------------------------------------------------------------------------------------------------

* [pip,npm,apm,gem] Add support for both ``pip2`` and ``pip3``, Node's ``npm``,
  Atom's ``apm``, Ruby's ``gem``.
* [cask] Fixup ``brew cask`` checking.
* [mpm] Don't die on errors.


`1.1.0 (2016-07-07) <https://github.com/kdeldycke/meta-package-manager/compare/v1.0.0...v1.1.0>`_
-------------------------------------------------------------------------------------------------

* [pip] Add support for Python's ``pip``.


`1.0.0 (2016-07-05) <https://github.com/kdeldycke/meta-package-manager/commit/170ce9>`_
---------------------------------------------------------------------------------------

* [mpm] Initial public release.
* [brew,cask] Add support for Homebrew and Cask.
