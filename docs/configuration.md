# Configuration

`mpm` can read defaults options from a [configuration file](meta_package_manager.config.default_conf_path).

Here is a sample:

```toml
# My default configuration file.

[mpm]
verbosity = "DEBUG"
manager = ["brew", "cask"]

[mpm.search]
exact = True
```