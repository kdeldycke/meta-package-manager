{
  lib,
  python3Packages,
  fetchFromGitHub,
}:

python3Packages.buildPythonApplication (finalAttrs: {
  pname = "meta-package-manager";
  version = "7.3.0";
  pyproject = true;
  __structuredAttrs = true;

  src = fetchFromGitHub {
    owner = "kdeldycke";
    repo = "meta-package-manager";
    tag = "v${finalAttrs.version}";
    hash = "sha256-QyDUGwTSgYLe3EpUYre1KzvhnbH4i7vcpATS8wyeRYc=";
  };

  build-system = with python3Packages; [ uv-build ];

  dependencies = with python3Packages; [
    boltons
    click-extra
    extra-platforms
    packageurl-python
    tomli-w
    xmltodict
  ];

  nativeCheckInputs = with python3Packages; [
    pytestCheckHook
    # tests/test_docs.py parses the GitHub workflow YAML files and loads
    # docs/docs_update.py, which round-trips pyproject.toml with tomlkit.
    pyyaml
    tomlkit
    # The SBOM unit tests import the CycloneDX renderer and its JSON/XML
    # schema validators, the SPDX writers, and the mocked HTTP client of
    # the OSV adapter.
    cyclonedx-python-lib
    httpx
    jsonschema
    lxml
    platformdirs
    respx
    spdx-tools
  ];

  # The hermetic unit layer runs in full. The integration layer
  # (tests/test_manager_*.py, tests/test_cli*.py) spawns real package manager
  # binaries and auto-skips when ``$HOME`` is ``/homeless-shelter``, the
  # hermetic-builder convention shared by Guix and Nix. See the "Note for
  # downstream packagers" section of the project's CLAUDE.md.

  disabledTests = [
    # Asserts the committed issue template matches a regeneration from the
    # installed extra-platforms, whose platform groups evolve between
    # releases: a repo-maintenance sync guard, not a packaging invariant.
    "test_new_package_manager_issue_template"
  ];

  pythonImportsCheck = [ "meta_package_manager" ];

  meta = {
    description = "Package managers abstraction and unification tool";
    homepage = "https://kdeldycke.github.io/meta-package-manager/";
    changelog = "https://github.com/kdeldycke/meta-package-manager/blob/v${finalAttrs.version}/changelog.md";
    license = lib.licenses.gpl2Plus;
    # Add: maintainers = with lib.maintainers; [ kdeldycke ];
    mainProgram = "mpm";
  };
})
