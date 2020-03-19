Installation
============

This package is `available on PyPi
<https://pypi.python.org/pypi/meta-package-manager>`_, so you can install the
latest stable release and its dependencies with a simple ``pip`` call:

.. code-block:: shell-session

    $ pip install meta-package-manager

See also `pip installation instructions
<https://pip.pypa.io/en/stable/installing/>`_.

.. warning::

    ``mpm``, `the Python module <https://pypi.python.org/pypi/mpm>`_, is not
    the same as ``meta-package-manager``. Only the later provides the
    :command:`mpm` CLI *per-se*. The former has nothing to do with the
    current project.


Python dependencies
-------------------

FYI, here is a graph of Python package dependencies:

.. code-block:: shell-session

    $ poetry show --all --no-dev --tree
    boltons 17.2.0 When they're not builtins, they're boltons.
    cli-helpers 1.2.1 Helpers for building command-line apps
    ├── backports.csv >=1.0.0
    ├── configobj >=5.0.5
    │   └── six *
    ├── tabulate >=0.8.2
    │   └── wcwidth *
    └── terminaltables >=3.0.0
    click 5.1 A simple wrapper around optparse for powerful command line utilities.
    click-log 0.2.1 Logging integration for Click
    └── click *
    packaging 20.3 Core utilities for Python packages
    ├── pyparsing >=2.0.2
    └── six *
    simplejson 3.17.0 Simple, fast, extensible JSON encoder/decoder for Python

.. todo

    Have the CLI above run automatticaly and update documentation.
