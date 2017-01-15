BitBar Plugin
=============

A copy of the latest stable version of the BitBar plugin for ``mpm`` is always
`available on BitBar website
<https://getbitbar.com/plugins/Dev/MetaPackageManager/meta_package_manager.7h.py>`_
and `plugin repository
<https://github.com/matryer/bitbar-plugins/tree/master/Dev/MetaPackageManager>`_.

.. image:: https://raw.githubusercontent.com/kdeldycke/meta-package-manager/develop/screenshot.png
    :alt: Bitbar plugin screenshot.
    :align: left


Development workflow
--------------------

Active development of the plugin is happening here, as a side-project of
``mpm`` itself.

Releases of the plugin is synchronized with the package. Both share the exact
same version to simplify management. This explain why the plugin could appears
jumpimg ahead of a couple of major/minor version while providing tiny or no
changes at all.

A release is ready when both the package and the plugin reach a stable state.

If the plugin has been changed between releases, a `copy of the plugin is
pushed
<https://github.com/matryer/bitbar-plugins/pulls?q=is%3Apr%20%22Meta%20Package%20Manager%22>`_
to the `official BitBar plugin repository
<https://github.com/matryer/bitbar-plugins/tree/master/Dev/MetaPackageManager>`_.


Release process
---------------

1. `Fork <https://help.github.com/articles/fork-a-repo/>`_ the official `BitBar
   plugin repository <https://github.com/matryer/bitbar-plugins>`_.

2. Fetch a local copy of the fork:

   .. code-block:: shell-session

        $ git clone https://github.com/kdeldycke/bitbar-plugins
        $ cd bitbat-plugins

3. Create a new branch and switch to it:

   .. code-block:: shell-session

        $ git branch meta-package-manager-v230
        $ git checkout meta-package-manager-v230

4. Replace existing copy of the plugin with the latest tagged version:

   .. code-block:: shell-session

        $ wget https://raw.githubusercontent.com/kdeldycke/meta-package-manager/v2.3.0/meta_package_manager/bitbar/meta_package_manager.7h.py
        $ mv ./meta_package_manager.7h.py ./Dev/MetaPackageManager/
        $ chmod 755 ./Dev/MetaPackageManager/meta_package_manager.7h.py

5. Commit the new plugin:

   .. code-block:: shell-session

        $ git add ./Dev/MetaPackageManager/meta_package_manager.7h.py
        $ git commit -m 'Upgrade to Meta Package Manager plugin v2.3.0.'

6. Push new branch:

   .. code-block:: shell-session

        $ git push --set-upstream origin meta-package-manager-v230

7. `Create a pull-request
   <https://help.github.com/articles/creating-a-pull-request/>`_ in the
   original repository.
