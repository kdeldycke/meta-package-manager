Meta Package Manager
====================

CLI providing unifying interface to all package managers.

Stable release: |release| |versions| |license| |dependencies|

Development: |build| |docs| |coverage| |quality|

.. |release| image:: https://img.shields.io/pypi/v/meta-package-manager.svg
    :target: https://pypi.python.org/pypi/meta-package-manager
    :alt: Last release
.. |versions| image:: https://img.shields.io/pypi/pyversions/meta-package-manager.svg
    :target: https://pypi.python.org/pypi/meta-package-manager
    :alt: Python versions
.. |license| image:: https://img.shields.io/pypi/l/meta-package-manager.svg
    :target: https://www.gnu.org/licenses/gpl-2.0.html
    :alt: Software license
.. |dependencies| image:: https://requires.io/github/kdeldycke/meta-package-manager/requirements.svg?branch=master
    :target: https://requires.io/github/kdeldycke/meta-package-manager/requirements/?branch=master
    :alt: Requirements freshness
.. |build| image:: https://github.com/kdeldycke/meta-package-manager/workflows/Unittests/badge.svg
    :target: https://github.com/kdeldycke/meta-package-manager/actions?query=workflow%3AUnittests
    :alt: Unittests status
.. |docs| image:: https://readthedocs.org/projects/meta-package-manager/badge/?version=develop
    :target: https://meta-package-manager.readthedocs.io/en/develop/
    :alt: Documentation Status
.. |coverage| image:: https://codecov.io/gh/kdeldycke/meta-package-manager/branch/develop/graph/badge.svg
    :target: https://codecov.io/github/kdeldycke/meta-package-manager?branch=develop
    :alt: Coverage Status
.. |quality| image:: https://scrutinizer-ci.com/g/kdeldycke/meta-package-manager/badges/quality-score.png?b=develop
    :target: https://scrutinizer-ci.com/g/kdeldycke/meta-package-manager/?branch=develop
    :alt: Code Quality

.. figure:: https://imgs.xkcd.com/comics/universal_install_script.png
    :alt: Obligatory XKCD.
    :align: right

    Source: `XKCD #1654 <https://xkcd.com/1654/>`_.


Features
---------

* Inventory and list all package managers available the system.
* Supports macOS, Linux and Windows.
* List installed packages.
* Search for packages.
* List outdated packages.
* Sync local package infos.
* Upgrade all outdated packages.
* Backup list of installed packages to TOML files.
* Pin-point commands to a subset of package managers (include/exclude
  selectors).
* Export results in JSON or user-friendly tables.
* Provides a `BitBar plugin
  <https://meta-package-manager.readthedocs.io/en/develop/bitbar.html>`_ for
  friendly macOS integration.


Supported package managers
--------------------------

================ =========== ====== ====== ======== ========= ============== =========== ============ ============= ============
Package manager  Version     macOS  Linux  Windows  ``sync``  ``installed``  ``search``  ``install``  ``outdated``  ``upgrade``
================ =========== ====== ====== ======== ========= ============== =========== ============ ============= ============
|brew|__          >= 1.7.4   ✓                      ✓         ✓              ✓                        ✓             ✓
|cask|__          >= 1.7.4   ✓                      ✓         ✓              ✓                        ✓             ✓
|pip2|__          >= 9.0.0   ✓      ✓      ✓                  ✓              ✓                        ✓             ✓
|pip3|__          >= 9.0.0   ✓      ✓      ✓                  ✓              ✓                        ✓             ✓
|npm|__           >= 4.0.*   ✓      ✓      ✓                  ✓              ✓                        ✓             ✓
|yarn|__          >= 1.21.*  ✓      ✓      ✓                  ✓              ✓                        ✓             ✓
|apm|__                      ✓      ✓      ✓                  ✓              ✓                        ✓             ✓
|gem|__                      ✓      ✓      ✓                  ✓              ✓                        ✓             ✓
|mas|__           >= 1.3.1   ✓                                ✓              ✓                        ✓             ✓
|apt|__           >= 1.0.0          ✓               ✓         ✓              ✓                        ✓             ✓
|composer|__      >= 1.4.0   ✓      ✓      ✓        ✓         ✓              ✓                        ✓             ✓
|flatpak|__       >= 1.2.*          ✓                         ✓              ✓                        ✓             ✓
|opkg|__          >= 0.2.0          ✓               ✓         ✓              ✓                        ✓             ✓
================ =========== ====== ====== ======== ========= ============== =========== ============ ============= ============

.. |brew| replace::
   Homebrew
__ https://brew.sh
.. |cask| replace::
   Homebrew Cask
__ https://caskroom.github.io
.. |pip2| replace::
   Python 2 ``pip``
__ https://pypi.org
.. |pip3| replace::
   Python 3 ``pip``
__ https://pypi.org
.. |npm| replace::
   Node's ``npm``
__ https://www.npmjs.com
.. |yarn| replace::
   Node's ``yarn``
__ https://yarnpkg.com
.. |apm| replace::
   Atom's ``apm``
__ https://atom.io/packages
.. |gem| replace::
   Ruby's ``gem``
__ https://rubygems.org
.. |mas| replace::
   Mac AppStore via ``mas``
__ https://github.com/argon/mas
.. |apt| replace::
   ``apt``
__ https://wiki.debian.org/Apt
.. |composer| replace::
   ``composer``
__ https://getcomposer.org
.. |flatpak| replace::
   Flatpak
__ https://flatpak.org
.. |opkg| replace::
   opkg
__ https://git.yoctoproject.org/cgit/cgit.cgi/opkg/


If you're bored, feel free to add support for new package manager. See
good candidates at:

* `Wikipedia list of package managers
  <https://en.wikipedia.org/wiki/List_of_software_package_management_systems>`_
* `Awesome list of package managers
  <https://github.com/k4m4/terminals-are-sexy#package-managers>`_
* `GitHub list of package managers
  <https://github.com/showcases/package-managers>`_


Installation
------------

This package is `available on PyPi
<https://pypi.python.org/pypi/meta-package-manager>`_, so you can install the
latest stable release and its dependencies with a simple ``pip`` call:

.. code-block:: shell-session

    $ pip install meta-package-manager


Documentation
-------------

Docs are `hosted on Read the Docs
<https://meta-package-manager.readthedocs.io>`_.


Usage
-----

Examples of the package's ``mpm`` CLI.

List global options and commands:

.. code-block:: shell-session

    $ mpm
    Usage: mpm [OPTIONS] COMMAND [ARGS]...

      CLI for multi-package manager upgrades.

    Options:
      -v, --verbosity LEVEL           Either CRITICAL, ERROR, WARNING, INFO or
                                      DEBUG. Defaults to INFO.
      -m, --manager [apm|apt|brew|cask|composer|flatpak|gem|mas|npm|opkg|pip2|pip3]
                                      Restrict sub-command to a subset of package
                                      managers. Repeat to select multiple
                                      managers. Defaults to all.
      --ignore-auto-updates / --include-auto-updates
                                      Report all outdated packages, including
                                      those tagged as auto-updating. Defaults to
                                      include all packages. Only applies for
                                      'outdated' and 'upgrade' commands.
      -o, --output-format [ascii|csv|csv-tab|double|fancy_grid|github|grid|html|jira|json|latex|latex_booktabs|mediawiki|moinmoin|orgtbl|pipe|plain|psql|rst|simple|textile|tsv|vertical]
                                      Rendering mode of the output. Defaults to
                                      fancy-grid.
      --stats / --no-stats            Print statistics or not at the end of
                                      output. Active by default.
      --stop-on-error / --continue-on-error
                                      Stop right away or continue operations on
                                      manager CLI error. Defaults to stop.
      --version                       Show the version and exit.
      --help                          Show this message and exit.

    Commands:
      installed  List installed packages.
      managers   List supported package managers and their location.
      outdated   List outdated packages.
      search     Search packages.
      sync       Sync local package info.
      upgrade    Upgrade all packages.

List all supported package managers and their status on current system (macOS):

.. code-block:: shell-session

    $ mpm managers
    ╒═══════════════════╤══════════╤═══════════════╤════════════════════════════╤══════════════╤═══════════╕
    │ Package manager   │ ID       │ Supported     │ CLI                        │ Executable   │ Version   │
    ╞═══════════════════╪══════════╪═══════════════╪════════════════════════════╪══════════════╪═══════════╡
    │ Atom's apm        │ apm      │ ✓             │ ✘  apm CLI not found.      │              │           │
    ├───────────────────┼──────────┼───────────────┼────────────────────────────┼──────────────┼───────────┤
    │ APT               │ apt      │ ✘  Linux only │ ✓  /usr/bin/apt            │ ✓            │ ✘         │
    ├───────────────────┼──────────┼───────────────┼────────────────────────────┼──────────────┼───────────┤
    │ Homebrew          │ brew     │ ✓             │ ✓  /usr/local/bin/brew     │ ✓            │ ✓  2.2.10 │
    ├───────────────────┼──────────┼───────────────┼────────────────────────────┼──────────────┼───────────┤
    │ Homebrew Cask     │ cask     │ ✓             │ ✓  /usr/local/bin/brew     │ ✓            │ ✓  2.2.10 │
    ├───────────────────┼──────────┼───────────────┼────────────────────────────┼──────────────┼───────────┤
    │ PHP's Composer    │ composer │ ✓             │ ✘  composer CLI not found. │              │           │
    ├───────────────────┼──────────┼───────────────┼────────────────────────────┼──────────────┼───────────┤
    │ Flatpak           │ flatpak  │ ✘  Linux only │ ✘  flatpak CLI not found.  │              │           │
    ├───────────────────┼──────────┼───────────────┼────────────────────────────┼──────────────┼───────────┤
    │ Ruby Gems         │ gem      │ ✓             │ ✓  /usr/bin/gem            │ ✓            │ ✓  3.0.3  │
    ├───────────────────┼──────────┼───────────────┼────────────────────────────┼──────────────┼───────────┤
    │ Mac AppStore      │ mas      │ ✓             │ ✓  /usr/local/bin/mas      │ ✓            │ ✓  1.6.3  │
    ├───────────────────┼──────────┼───────────────┼────────────────────────────┼──────────────┼───────────┤
    │ Node's npm        │ npm      │ ✓             │ ✓  /usr/local/bin/npm      │ ✓            │ ✓  6.13.7 │
    ├───────────────────┼──────────┼───────────────┼────────────────────────────┼──────────────┼───────────┤
    │ Node's yarn       │ yarn     │ ✓             │ ✓  /usr/local/bin/yarn     │ ✓            │ ✓  1.21.0 │
    ├───────────────────┼──────────┼───────────────┼────────────────────────────┼──────────────┼───────────┤
    │ OPKG              │ opkg     │ ✘  Linux only │ ✘  opkg CLI not found.     │              │           │
    ├───────────────────┼──────────┼───────────────┼────────────────────────────┼──────────────┼───────────┤
    │ Python 2's Pip    │ pip2     │ ✓             │ ✘  pip2 CLI not found.     │              │           │
    ├───────────────────┼──────────┼───────────────┼────────────────────────────┼──────────────┼───────────┤
    │ Python 3's Pip    │ pip3     │ ✓             │ ✓  /usr/local/bin/pip3     │ ✓            │ ✓  20.0.2 │
    ╘═══════════════════╧══════════╧═══════════════╧════════════════════════════╧══════════════╧═══════════╛
