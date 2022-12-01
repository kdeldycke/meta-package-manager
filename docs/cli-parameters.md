# CLI parameters

## Help screen

```{eval-rst}
.. click:run::
    from meta_package_manager.cli import mpm
    invoke(mpm, args=["--help"])
```

## Options

```{eval-rst}
.. click:: meta_package_manager.cli:mpm
    :prog: mpm
    :nested: full
```