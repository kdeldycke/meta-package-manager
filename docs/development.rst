Development
===========


Philosophy
----------

1. First create something that work (to provide business value).
2. Then something that's beautiful (to lower maintenance costs).
3. Finally works on performance (to avoid wasting time on premature
   optimizations).


Stability policy
----------------

This project follows `Semantic Versioning <https://semver.org/>`_.

Which boils down to the following rules of thumb regarding stability:

* **Patch releases** (``0.x.n`` → ``0.x.(n+1)`` upgrades) are bug-fix only.
  These releases must not break anything and keeps backward-compatibility with
  ``0.x.*`` and ``0.(x-1).*`` series.

* **Minor releases** (``0.n.*`` → ``0.(n+1).0`` upgrades) includes any
  non-bugfix changes. These releases must be backward-compatible with any
  ``0.n.*`` version but are allowed to drop compatibility with the
  ``0.(n-1).*`` series and below.

* **Major releases** (``n.*.*`` → ``(n+1).0.0`` upgrades) are not planned yet,
  unless we introduce huge changes to the project.


Build status
------------

==============  ==================  ===================
Branch          |master-branch|__   |develop-branch|__
==============  ==================  ===================
Unittests       |build-stable|      |build-dev|
Coverage        |coverage-stable|   |coverage-dev|
Quality         |quality-stable|    |quality-dev|
Dependencies    |deps-stable|       |deps-dev|
Documentation   |docs-stable|       |docs-dev|
==============  ==================  ===================

.. |master-branch| replace::
   ``master``
__ https://github.com/kdeldycke/meta-package-manager/tree/master
.. |develop-branch| replace::
   ``develop``
__ https://github.com/kdeldycke/meta-package-manager/tree/develop

.. |build-stable| image:: https://github.com/kdeldycke/meta-package-manager/workflows/Unittests/badge.svg?branch=master
    :target: https://github.com/kdeldycke/meta-package-manager/actions?query=workflow%3AUnittests+branch%3Amaster
    :alt: Unittests status
.. |build-dev| image:: https://github.com/kdeldycke/meta-package-manager/workflows/Unittests/badge.svg?branch=develop
    :target: https://github.com/kdeldycke/meta-package-manager/actions?query=workflow%3AUnittests+branch%3Adevelop
    :alt: Unittests status

.. |coverage-stable| image:: https://codecov.io/gh/kdeldycke/meta-package-manager/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/kdeldycke/meta-package-manager/branch/master
    :alt: Coverage Status
.. |coverage-dev| image:: https://codecov.io/gh/kdeldycke/meta-package-manager/branch/develop/graph/badge.svg
    :target: https://codecov.io/gh/kdeldycke/meta-package-manager/branch/develop
    :alt: Coverage Status

.. |quality-stable| image:: https://scrutinizer-ci.com/g/kdeldycke/meta-package-manager/badges/quality-score.png?b=master
    :target: https://scrutinizer-ci.com/g/kdeldycke/meta-package-manager/?branch=master
    :alt: Code Quality
.. |quality-dev| image:: https://scrutinizer-ci.com/g/kdeldycke/meta-package-manager/badges/quality-score.png?b=develop
    :target: https://scrutinizer-ci.com/g/kdeldycke/meta-package-manager/?branch=develop
    :alt: Code Quality

.. |deps-stable| image:: https://requires.io/github/kdeldycke/meta-package-manager/requirements.svg?branch=master
    :target: https://requires.io/github/kdeldycke/meta-package-manager/requirements/?branch=master
    :alt: Requirements freshness
.. |deps-dev| image:: https://requires.io/github/kdeldycke/meta-package-manager/requirements.svg?branch=develop
    :target: https://requires.io/github/kdeldycke/meta-package-manager/requirements/?branch=develop
    :alt: Requirements freshness

.. |docs-stable| image:: https://readthedocs.org/projects/meta-package-manager/badge/?version=stable
    :target: https://meta-package-manager.readthedocs.io/en/stable/
    :alt: Documentation Status
.. |docs-dev| image:: https://readthedocs.org/projects/meta-package-manager/badge/?version=develop
    :target: https://meta-package-manager.readthedocs.io/en/develop/
    :alt: Documentation Status


Setup a development environment
-------------------------------

This **step is required** for all the other sections from this page.

Check out latest development branch:

.. code-block:: shell-session

    $ git clone git@github.com:kdeldycke/meta-package-manager.git
    $ cd ./meta-package-manager
    $ git checkout develop

Install package in editable mode with all development dependencies:

.. code-block:: shell-session

    $ pip install poetry
    $ poetry install

Now you're ready to hack and abuse git!


Unit-tests
----------

Install test dependencies and run unit-tests:

.. code-block:: shell-session

    $ poetry run pytest


Coding style
------------

Run `isort <https://github.com/timothycrosley/isort>`_ utility to sort Python
imports:

.. code-block:: shell-session

    $ poetry run isort --apply


Then run `pycodestyle <https://pycodestyle.readthedocs.io>`_ and `Pylint
<https://docs.pylint.org>`_ code style checks:

.. code-block:: shell-session

    $ poetry run pycodestyle
    $ poetry run pylint meta_package_manager


Documentation
-------------

The documentation you're currently reading can be built locally with `Sphinx
<https://www.sphinx-doc.org>`_:

.. code-block:: shell-session

    $ poetry install --extras docs
    $ poetry run sphinx-build -b html ./docs ./docs/html

And once in a while, it's good to upgrade the `graph of package dependencies
<./install.html#python-dependencies>`_:

.. code-block:: shell-session

    $ poetry show --all --no-dev --tree


Screenshots
-----------

Once in a while, refresh screenshots found in the docs and the README file at
the root of project.

To produce clean and fancy terminals screenshots, use either:

* https://graphite-shot.now.sh
* https://github.com/carbon-app/carbon


Changelog
---------

From time to time, especially before a release, review and rewrite the changelog
to make it clean and readeable. The idea is to have it stays in the spirit of the
[Keep a changelog manifesto](https://keepachangelog.com).

Most (if not all) changes can be derived by simply comparing the last tagged
release with the `develop` branch:
``https://github.com/kdeldycke/meta-package-manager/compare/vX.X.X...develop``.
This direct link should be available at the top of the `changelog <changelog.html>`__ .


Release process
---------------

Check your starting from a clean ``develop`` branch:

.. code-block:: shell-session

    $ git checkout develop

Revision should already be set to the next version, so we just need to set the
released date in the changelog:

.. code-block:: shell-session

    $ vi ./CHANGES.rst

Create a release commit, tag it and merge it back to ``master`` branch:

.. code-block:: shell-session

    $ git add ./meta_package_manager/__init__.py ./CHANGES.rst
    $ git commit -m "Release vX.Y.Z"
    $ git tag "vX.Y.Z"
    $ git push
    $ git push --tags
    $ git checkout master
    $ git pull
    $ git merge "vX.Y.Z"
    $ git push

Build packages:

.. code-block:: shell-session

    $ poetry build

For a smooth release, you also need to `validate the rendering of package's
long description on PyPi
<https://packaging.python.org/guides/making-a-pypi-friendly-readme/#validating-restructuredtext-markup>`_,
as well as metadata:

.. code-block:: shell-session

    $ poetry check
    $ poetry run twine check ./dist/*

Publish packaging to `PyPi <https://pypi.python.org>`_:

.. code-block:: shell-session

    $ poetry publish

Update revision with `bump2version <https://github.com/c4urself/bump2version>`_
and set it back to development state by increasing the ``patch`` level.

.. code-block:: shell-session

    $ git checkout develop
    $ poetry run bumpversion --verbose patch
    $ git add ./meta_package_manager/__init__.py ./CHANGES.rst
    $ git commit -m "Post release version bump."
    $ git push

Now if the next revision is no longer bug-fix only, bump the ``minor``
revision level instead:

.. code-block:: shell-session

    $ poetry run bumpversion --verbose minor
    $ git add ./meta_package_manager/__init__.py ./CHANGES.rst
    $ git commit -m "Next release no longer bug-fix only. Bump revision."
    $ git push
