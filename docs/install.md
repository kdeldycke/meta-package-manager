# Installation

````{admonition} Danger: **Misleading package name**
---
class: danger
---
```{eval-rst}
.. figure:: images/angry-paper-box.png
    :align: right
    :figwidth: 50px
```

There is a *`mpm`* Python module on PyPi that has nothing to do with this project. Avoid it!

The **real package is named `meta-package-manager`**. Only the latter provides the {command}`mpm` CLI
you're looking for.
````

## `pip` install

You can install the latest stable release and its dependencies with a simple `pip`
call:

```shell-session
$ python -m pip install meta-package-manager
```

On some system, due to the Python 2.x to 3.x migration, you'll have to call `python3` directly:

```shell-session
$ python3 -m pip install meta-package-manager
```

Other variations includes:

```shell-session
$ pip install meta-package-manager
```

```shell-session
$ pip3 install meta-package-manager
```

If you have difficulties to use `pip`, see
[`pip`'s own installation instructions](https://pip.pypa.io/en/stable/installing/).

## Run `mpm`

Meta package manager should now be available system-wide:

```shell-session
$ mpm --version
mpm, version 4.13.0
(...)
```

If not, you can directly execute the module from Python:

```shell-session
$ python -m meta_package_manager --version
mpm, version 4.13.0
(...)
```

Or on some systems:

```shell-session
$ python3 -m meta_package_manager --version
mpm, version 4.13.0
(...)
```

## Shell completion

Completion for popular shell
[rely on Click feature](https://click.palletsprojects.com/en/8.0.x/shell-completion/).

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

```{eval-rst}
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

```{todo}
Replace [`sphinx_tabs`](https://github.com/executablebooks/sphinx-tabs) by
[`sphinx-inline-tabs`](https://github.com/pradyunsg/sphinx-inline-tabs#readme) once the latter
[supports Python < 3.8](https://github.com/pradyunsg/sphinx-inline-tabs/issues/24).
```

## Python dependencies

FYI, here is a graph of Python package dependencies:

```{image} images/dependencies.png
---
alt: Meta Package Manager dependency graph
align: center
---
```
