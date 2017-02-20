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
.. |dependencies| image:: https://img.shields.io/requires/github/kdeldycke/meta-package-manager/master.svg
    :target: https://requires.io/github/kdeldycke/meta-package-manager/requirements/?branch=master
    :alt: Requirements freshness
.. |build| image:: https://img.shields.io/travis/kdeldycke/meta-package-manager/develop.svg
    :target: https://travis-ci.org/kdeldycke/meta-package-manager
    :alt: Unit-tests status
.. |docs| image:: https://readthedocs.org/projects/meta-package-manager/badge/?version=develop
    :target: https://meta-package-manager.readthedocs.io/en/develop/
    :alt: Documentation Status
.. |coverage| image:: https://codecov.io/github/kdeldycke/meta-package-manager/coverage.svg?branch=develop
    :target: https://codecov.io/github/kdeldycke/meta-package-manager?branch=develop
    :alt: Coverage Status
.. |quality| image:: https://img.shields.io/scrutinizer/g/kdeldycke/meta-package-manager.svg
    :target: https://scrutinizer-ci.com/g/kdeldycke/meta-package-manager/?branch=develop
    :alt: Code Quality

.. figure:: https://imgs.xkcd.com/comics/universal_install_script.png
    :alt: Obligatory XKCD.
    :align: right

    Source: `XKCD #1654 <https://xkcd.com/1654/>`_.


Features
---------

* Search and list all package managers on the system.
* Supports macOS and Linux.
* List installed packages.
* Search for packages.
* List outdated packages.
* Sync local package infos.
* Upgrade all outdated packages.
* Apply commands per-package manager or to all of them.
* Export results in JSON or user-friendly tables.
* Provides a `BitBar plugin
  <https://meta-package-manager.readthedocs.io/en/develop/bitbar.html>`_ for
  friendly macOS integration.


Supported package managers
--------------------------

================ ========== ====== ====== ======== ========= ============== =========== ============ ============= ============
Package manager  Version    macOS  Linux  Windows  ``sync``  ``installed``  ``search``  ``install``  ``outdated``  ``upgrade``
================ ========== ====== ====== ======== ========= ============== =========== ============ ============= ============
|brew|__          >= 1.0.*   ✅                     ✅          ✅              ✅                        ✅             ✅
|cask|__          >= 1.0.*   ✅                     ✅          ✅              ✅                        ✅             ✅
|pip2|__                     ✅     ✅                          ✅              ✅                        ✅             ✅
|pip3|__                     ✅     ✅                          ✅              ✅                        ✅             ✅
|npm|__           >= 4.0.*   ✅     ✅                          ✅              ✅                        ✅             ✅
|apm|__                      ✅     ✅                          ✅              ✅                        ✅             ✅
|gem|__                      ✅     ✅                          ✅              ✅                        ✅             ✅
|mas|__           >= 1.3.1   ✅                                 ✅              ✅                        ✅             ✅
================ ========== ====== ====== ======== ========= ============== =========== ============ ============= ============

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
.. |apm| replace::
   Atom's ``apm``
__ https://atom.io/packages
.. |gem| replace::
   Ruby's ``gem``
__ https://rubygems.org
.. |mas| replace::
   Mac AppStore via ``mas``
__ https://github.com/argon/mas

If you're bored, feel free to add support for new package manager. See the
`list of good candidates
<https://en.wikipedia.org/wiki/List_of_software_package_management_systems>`_.


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
      -m, --manager [npm|mas|pip3|pip2|cask|apm|brew|gem]
                                      Restrict sub-command to one package manager.
                                      Defaults to all.
      -o, --output-format [simple|plain|json|fancy]
                                      Rendering mode of the output. Defaults to
                                      fancy.
      --version                       Show the version and exit.
      --help                          Show this message and exit.

    Commands:
      managers  List supported package managers and their location.
      outdated  List outdated packages.
      sync      Sync local package info.
      upgrade   Upgrade all packages.

List all supported package managers and their status on current system:

.. code-block:: shell-session

    $ mpm managers
    ╒═══════════════════╤══════╤═════════════╤════════════════════════╤══════════════╤═════════════╕
    │ Package manager   │ ID   │ Supported   │ CLI                    │ Executable   │ Version     │
    ╞═══════════════════╪══════╪═════════════╪════════════════════════╪══════════════╪═════════════╡
    │ Atom's apm        │ apm  │ ✓           │ ✓  /usr/local/bin/apm  │ ✓            │ ✓  1.12.9   │
    ├───────────────────┼──────┼─────────────┼────────────────────────┼──────────────┼─────────────┤
    │ Homebrew          │ brew │ ✓           │ ✓  /usr/local/bin/brew │ ✓            │ ✓  1.1.7    │
    ├───────────────────┼──────┼─────────────┼────────────────────────┼──────────────┼─────────────┤
    │ Homebrew Cask     │ cask │ ✓           │ ✓  /usr/local/bin/brew │ ✓            │ ✓  1.1.7    │
    ├───────────────────┼──────┼─────────────┼────────────────────────┼──────────────┼─────────────┤
    │ Ruby Gems         │ gem  │ ✓           │ ✓  /usr/bin/gem        │ ✓            │ ✓  2.0.14.1 │
    ├───────────────────┼──────┼─────────────┼────────────────────────┼──────────────┼─────────────┤
    │ Mac AppStore      │ mas  │ ✓           │ ✓  /usr/local/bin/mas  │ ✓            │ ✓  1.3.1    │
    ├───────────────────┼──────┼─────────────┼────────────────────────┼──────────────┼─────────────┤
    │ Node's npm        │ npm  │ ✓           │ ✓  /usr/local/bin/npm  │ ✓            │ ✓  4.0.5    │
    ├───────────────────┼──────┼─────────────┼────────────────────────┼──────────────┼─────────────┤
    │ Python 2's Pip    │ pip2 │ ✓           │ ✓  /usr/local/bin/pip2 │ ✓            │ ✓  9.0.1    │
    ├───────────────────┼──────┼─────────────┼────────────────────────┼──────────────┼─────────────┤
    │ Python 3's Pip    │ pip3 │ ✓           │ ✓  /usr/local/bin/pip3 │ ✓            │ ✓  9.0.1    │
    ╘═══════════════════╧══════╧═════════════╧════════════════════════╧══════════════╧═════════════╛
