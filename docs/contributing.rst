Contribution guide
==================

Good candidates for new package manager:

* `Wikipedia list of package managers
  <https://en.wikipedia.org/wiki/List_of_software_package_management_systems>`_
* `Awesome list of package managers
  <https://github.com/k4m4/terminals-are-sexy#package-managers>`_
* `GitHub list of package managers
  <https://github.com/showcases/package-managers>`_


How-to add a new package manager
--------------------------------

For now the easiest way to have new package managers supported is to:

1. Fork the project.
2. Identify an already implemented package manager that is similar to the new one you'd like to add.
3. Duplicate its already existing definition file in the ``/managers`` subfolder.
4. Adapt the new file to the particularities of the new package manager. Read the
   `Falsehoods Programmers Believe About Package Managers
   <https://meta-package-manager.readthedocs.io/en/latest/falsehoods.html>`_ to anticipate edge-cases.
5. Fix the code until the unittests passes. Most of all metadata and format constraints for
   new managers are enforced in the unittest suite. See the `development page
   <https://meta-package-manager.readthedocs.io/en/latest/development.html>`_ for more technical details.
6. Send a PR.


Code of conduct
---------------

.. include:: ../.github/code-of-conduct.md
   :literal:
