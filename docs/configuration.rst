Configuration
=============

``mpm`` can read defaults options from a `configuration file
<https://meta-package-manager.readthedocs.io/en/latest/meta_package_manager.html#meta_package_manager.config.default_conf_path>`_.

Here is a sample:

.. code-block:: toml

    # My default configuration file.

    [mpm]
    verbosity = "DEBUG"
    manager = ["brew", "cask"]

    [mpm.search]
    exact = True