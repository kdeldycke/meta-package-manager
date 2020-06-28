Use-cases
=========

A collection of user's problems and how ``mpm`` solves them.


Keep system secure
------------------

A [recent study shows that 70% of vulnerabilities lies in outdated libraries](https://developers.slashdot.org/story/20/05/23/2330244/open-source-security-report-finds-library-induced-flaws-in-70-of-applications). One of the key habits of security professionnals to keep a system secure consist in having all software up to date.

``mpm`` helps you upgrade all packages from all managers of a system with one-liner:

.. code-block:: shell-session

    $ mpm upgrade
    Updating all outdated packages from brew...
    ==> Upgrading 4 outdated packages:
    gnu-getopt 2.35.1 -> 2.35.2
    rclone 1.51.0 -> 1.52.0
    fd 8.1.0 -> 8.1.1
    youtube-dl 2020.05.08 -> 2020.05.29
    (...)
    Updating all outdated packages from cask...
    ==> Upgrading 4 outdated packages:
    balenaetcher 1.5.89 -> 1.5.94, libreoffice 6.4.3 -> 6.4.4
    (...)
    Updating all outdated packages from gem...
    Updating openssl
    (...)
    Updating all outdated packages from npm...
    + npm@6.14.5
    (...)
    Updating all outdated packages from pip...
    Successfully installed dephell-argparse-0.1.3
    Successfully installed dephell-pythons-0.1.15

This is the primary use case of ``mpm`` and the first reason I built it.


Fills the gap between managers
------------------------------

Some package manager are missing features.

For instance, `pip doesn't can't upgrade all outdated package <https://github.com/pypa/pip/issues/4551>`_ with a single command. ``mpm`` adds that missing feature:

.. code-block:: shell-session

    $ mpm --manager pip upgrade
    Updating all outdated packages from pip...
    warning: pip doesn't seems to implement a full upgrade subcommand. Call
    single-package upgrade CLI one by one.

    Collecting boltons
      Using cached boltons-20.1.0-py2.py3-none-any.whl (169 kB)
    Installing collected packages: boltons
    Successfully installed boltons-20.1.0

    Collecting graphviz
      Using cached graphviz-0.14-py2.py3-none-any.whl (18 kB)
    Installing collected packages: graphviz
    Successfully installed graphviz-0.14

    Collecting tomlkit
      Using cached tomlkit-0.6.0-py2.py3-none-any.whl (31 kB)
    Installing collected packages: tomlkit
    Successfully installed tomlkit-0.6.0

    Collecting urllib3
      Using cached urllib3-1.25.9-py2.py3-none-any.whl (126 kB)
    Installing collected packages: urllib3
    Successfully installed urllib3-1.25.9

    Collecting zipp
      Using cached zipp-3.1.0-py3-none-any.whl (4.9 kB)
    Installing collected packages: zipp
    Successfully installed zipp-3.1.0


Explore repositories
--------------------

You just learned of a new CLI you did not known about (``broot``) from a friend. Back to your terminal, you can easely search for it across all package repositories, then choose your preferred package manager to install it:

.. code-block:: shell-session

    $ mpm search broot
    ╒════════════════╤═══════╤═══════════╤══════════════════╕
    │ Package name   │ ID    │ Manager   │ Latest version   │
    ╞════════════════╪═══════╪═══════════╪══════════════════╡
    │ broot          │ broot │ brew      │ 0.1.0            │
    ├────────────────┼───────┼───────────┼──────────────────┤
    │ broot          │ broot │ pip       │ 0.1.1            │
    ╘════════════════╧═══════╧═══════════╧══════════════════╛
    2 packages total (brew: 1, pip: 1, cask: 0, gem: 0, mas: 0, npm: 0).

    $ brew install broot
    (...)
    🍺  /usr/local/Cellar/broot/0.13.6: 8 files, 3.5MB

Thanks to ``mpm`` we were able to choose quickly the place from which we sourced ``broot`` to get the latest version. No need to track down the CLI on Github and read the documentation (if it even exists).

.. todo::

    Implement an ``install`` command so all step above can be performed in one go with ``mpm``.


Deduplicate packages
--------------------

Use the `search` command to hunt down packages that were installed via multiple managers.

One exemple I had on my machine, in which ``httpie`` was both installed by the way of ``brew`` and ``pip``:

.. code-block:: shell-session

    $ mpm installed | grep httpie
    │ httpie  │ httpie  │ brew  │ 2.1.0  │
    │ httpie  │ httpie  │ pip   │ 2.1.0  │

Now you can easely remove one of them, and no longer have to think hard about which is which.

.. code-block:: shell-session

    $ python -m pip uninstall httpie
    Found existing installation: httpie 2.1.0
    Uninstalling httpie-2.1.0:
      Would remove:
        /usr/local/bin/http
        /usr/local/bin/https
        /usr/local/lib/python3.7/site-packages/httpie-2.1.0.dist-info/*
        /usr/local/lib/python3.7/site-packages/httpie/*
    Proceed (y/n)? y
      Successfully uninstalled httpie-2.1.0

.. todo::

    Add arguments to ``installed`` command, or an ``--installed`` boolean flag to ``search`` so we can reduce the searched packages to those installed.


Backup installed packages
-------------------------

You maintain a repository of ``dotfiles``. This helps you spawn up a highly customized working environment in a couple of hours. New job? New machine? Easy: run your dotfiles, get a coffe, come back with everything perfectly in place to start an extremely productive hacking session. But maintaining ``dotfiles`` is a pain.

``mpm`` allows you to dump the whole list of packages installed on your machine:

.. code-block:: shell-session

    $ mpm backup ./packages.toml
    Backup package list to ./packages.toml
    Dumping packages from brew...
    Dumping packages from cask...
    Dumping packages from gem...
    Dumping packages from mas...
    Dumping packages from npm...
    Dumping packages from pip...
    1109 packages total (npm: 659, brew: 229, pip: 115, gem: 49, cask: 48, mas: 9).

    $ head ./packages.toml
    # Generated by mpm 3.2.0.
    # Timestamp: 2020-05-29T11:15:29.539863.

    [brew]
    ack = "^3.3.1"
    adns = "^1.5.1"
    aom = "^1.0.0"
    apr = "^1.7.0"
    apr-util = "^1.6.1_3"
    arss = "^0.2.3"
    (...)


Get rid of Docker for lambda ?
------------------------------

Some developers have a hard-time reproducing environment for lambda execution
onto their local machine. Most of devs use Docker to abstract their runtime
requirements. But Docker might be too big for some people.

``mpm`` can be a lightweigh alternative to Docker here to abstract the runtime
from their execution environment.

.. todo::

    Once the ``install`` and ``restore`` sub-commands are implemented, we can
    declare all dependencies into a ``.toml`` file and let ``mpm`` resolve
    dependencies.


Switch systems
--------------

You used to work on macOS. Now you'd like to move to Linux. To reduce friction
during your migration, you can invotory all your installed packages with
``mpm``, then reinstall them on your new, bare OS.

1. Inventory all installed packages on macOS:

.. code-block:: shell-session

    $ mpm backup ./packages.toml

1. On your brand new Linux install, restore all packages with:

.. code-block:: shell-session

    $ mpm restore ./packages.toml

.. todo::

    Implement a best matchig strategy, across package managers of different
    kinds.
