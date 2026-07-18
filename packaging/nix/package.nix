{
  lib,
  python3Packages,
  fetchFromGitHub,
  zsh,
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

  patches = [
    # Backport the bar-plugin fix for the UnboundLocalError crash when a
    # probed binary does not exist, merged upstream after 7.3.0:
    # https://github.com/kdeldycke/meta-package-manager/commit/6e21daa3
    ./check-mpm-missing-binary.patch
  ];

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
  ]
  # The Xbar/SwiftBar plugin tests only run on macOS and drive the plugin
  # through the login shells it targets.
  ++ lib.optionals python3Packages.python.stdenv.hostPlatform.isDarwin [ zsh ];

  # The hermetic unit layer runs in full. The integration layer
  # (tests/test_manager_*.py, tests/test_cli*.py) spawns real package manager
  # binaries and auto-skips when ``$HOME`` is ``/homeless-shelter``, the
  # hermetic-builder convention shared by Guix and Nix. See
  # https://kdeldycke.github.io/meta-package-manager/packaging.html

  disabledTests = [
    # Asserts the committed issue template matches a regeneration from the
    # installed extra-platforms, whose platform groups evolve between
    # releases: a repo-maintenance sync guard, not a packaging invariant.
    "test_new_package_manager_issue_template"
    # Drives the Xbar/SwiftBar plugin end-to-end through mpm, which needs at
    # least one live package manager on the host: the build sandbox has none,
    # so mpm exits with "critical: No manager selected."
    "test_rendering"
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
