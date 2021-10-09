# Installation

## With `pip`

This package is [available on
PyPi](https://pypi.python.org/pypi/meta-package-manager), so you can install
the latest stable release and its dependencies with a simple `pip` call:

``` shell-session
$ pip install meta-package-manager
```

See also [pip installation
instructions](https://pip.pypa.io/en/stable/installing/).

```{admonition} Danger: **Misleading package names**
:class: danger
[*`mpm`*, the Python module](https://pypi.python.org/pypi/mpm), is not the same
as **`meta-package-manager`**. Only the later provides the {command}`mpm` CLI
*per-se*. The former has nothing to do with the current project.
```

## Shell completion

Completion for popular shell [rely on Click feature](https://click.palletsprojects.com/en/8.0.x/shell-completion/).

```{eval-rst}
.. tabs::

  .. group-tab:: Bash

    Add this to ``~/.bashrc``:

    .. code-block:: bash

        eval "$(_MPM_COMPLETE=bash_source mpm)"

  .. group-tab:: Zsh

    Add this to ``~/.zshrc``:

    .. code-block:: zsh

        eval "$(_MPM_COMPLETE=zsh_source mpm)"

  .. group-tab:: Fish

    Add this to ``~/.config/fish/completions/mpm.fish``:

    .. code-block:: fish

        eval (env _MPM_COMPLETE=fish_source mpm)
```

Alternatively, export the generated completion code as a static script to be
executed:

``` {eval-rst}
.. tabs::

  .. group-tab:: Bash

    .. code-block:: shell-session

        $ _MPM_COMPLETE=bash_source mpm > ~/.mpm-complete.bash

    Then source it from ``~/.bashrc``:

    .. code-block:: bash

        . ~/.mpm-complete.bash

  .. group-tab:: Zsh

    .. code-block:: shell-session

        $ _MPM_COMPLETE=zsh_source mpm > ~/.mpm-complete.zsh

    Then source it from ``~/.zshrc``:

    .. code-block:: zsh

        . ~/.mpm.zsh

  .. group-tab:: Fish

    .. code-block:: fish

       _MPM_COMPLETE=fish_source mpm > ~/.config/fish/completions/mpm.fish
```

``` {todo}
Replace [`sphinx_tabs`](https://github.com/executablebooks/sphinx-tabs) by
[`sphinx-inline-tabs`](https://github.com/pradyunsg/sphinx-inline-tabs#readme) once the latter
[supports Python < 3.8](https://github.com/pradyunsg/sphinx-inline-tabs/issues/24).
```

## Python dependencies

FYI, here is a graph of Python package dependencies:

```{image} dependencies.png
:alt: Meta Package Manager dependency graph
:align: center
```