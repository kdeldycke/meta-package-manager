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


Shell completion
----------------

Completion for popular shell `rely on Click feature
<https://click.palletsprojects.com/en/7.x/bashcomplete/>`_.

Bash
^^^^

Add this to ``~/.bashrc``:

.. code-block:: bash

    eval "$(_MPM_COMPLETE=source_bash mpm)"

Alternatively, export the generated completion code as a static script to be
executed:

.. code-block:: shell-session

    $ _MPM_COMPLETE=source_bash mpm > mpm-complete.sh

Then source it from ``~/.bashrc``:

.. code-block:: bash

   . /path/to/mpm-complete.sh

Zsh
^^^

Add this to ``~/.zshrc``:

.. code-block:: zsh

    eval "$(_MPM_COMPLETE=source_zsh mpm)"

Alternatively, export the generated completion code as a static script to be
executed:

.. code-block:: shell-session

    $ _MPM_COMPLETE=source_zsh mpm > mpm-complete.sh

Then source it from ``~/.zshrc``:

.. code-block:: zsh

   . /path/to/mpm-complete.sh

Fish
^^^^

Add this to ``~/.config/fish/completions/mpm.fish``:

.. code-block:: fish

    eval (env _MPM_COMPLETE=source_fish mpm)

Alternatively, export the generated completion code as a static script to be
executed:

.. code-block:: fish

   _MPM_COMPLETE=source_fish mpm > ~/.config/fish/completions/mpm-complete.fish


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
