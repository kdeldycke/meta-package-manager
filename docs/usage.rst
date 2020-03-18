Usage
=====

.. todo

    Have the CLIs below run automatticaly and update documentation.


``mpm``
-------

List global options and commands:

.. code-block:: shell-session

    $ mpm --help
    Usage: mpm [OPTIONS] COMMAND [ARGS]...

      CLI for multi-package manager upgrades.

    Options:
      -v, --verbosity LEVEL           Either CRITICAL, ERROR, WARNING, INFO or
                                      DEBUG. Defaults to INFO.
      -m, --manager [apm|apt|brew|cask|composer|gem|mas|npm|pip2|pip3]
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


``mpm installed``
-----------------

.. code-block:: shell-session

    $ mpm installed --help
    Usage: mpm installed [OPTIONS]

      List all packages installed on the system from all managers.

    Options:
      --help  Show this message and exit.


``mpm managers``
----------------

.. code-block:: shell-session

    $ mpm managers --help
    Usage: mpm managers [OPTIONS]

      List all supported package managers and their presence on the system.

    Options:
      --help  Show this message and exit.


``mpm outdated``
----------------

.. code-block:: shell-session

    $ mpm outdated --help
    Usage: mpm outdated [OPTIONS]

      List available package upgrades and their versions for each manager.

    Options:
      -c, --cli-format [plain|fragments|bitbar]
                                      Format of CLI fields in JSON output.
                                      Defaults to plain.
      --help                          Show this message and exit.


``mpm search``
--------------

.. code-block:: shell-session

    $ mpm search --help
    Usage: mpm search [OPTIONS] QUERY

      Search packages from all managers.

    Options:
      --help  Show this message and exit.


``mpm sync``
------------

.. code-block:: shell-session

    $ mpm sync --help
    Usage: mpm sync [OPTIONS]

      Sync local package metadata and info from external sources.

    Options:
      --help  Show this message and exit.


``mpm upgrade``
---------------

.. code-block:: shell-session

    $ mpm upgrade --help
    Usage: mpm upgrade [OPTIONS]

      Perform a full package upgrade on all available managers.

    Options:
      -d, --dry-run  Do not actually perform any upgrade, just simulate CLI calls.
      --help         Show this message and exit.

