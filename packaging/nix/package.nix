{
  lib,
  stdenv,
  python3Packages,
  fetchFromGitHub,
  zsh,
}:

python3Packages.buildPythonApplication (finalAttrs: {
  pname = "meta-package-manager";
  version = "8.0.1";
  pyproject = true;
  __structuredAttrs = true;

  src = fetchFromGitHub {
    owner = "kdeldycke";
    repo = "meta-package-manager";
    tag = "v${finalAttrs.version}";
    hash = "sha256-GRtgU9mz6bYxixFy94eSvGE1/hyw0R/Rqg8BKgA/Hp8=";
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

  nativeCheckInputs =
    with python3Packages;
    [
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
    ++ lib.optionals stdenv.hostPlatform.isDarwin [ zsh ];

  # Temporary, and deletable at the first release carrying the `integration`
  # and `host_environment` markers: `tests/conftest.py` skips both inside a
  # hermetic build automatically, and `tests/test_sbom.py` now skips itself
  # when cyclonedx-python-lib is too old. Until then this builds the v8.0.1
  # tarball, whose suite predates all three, so the names stay listed here.
  disabledTests = [
    # Drive the CLI, which exits 2 on `No manager selected`: there are none.
    "test_cli_cooldown_config_table"
    "test_cli_cooldown_keyword_without_window_is_a_noop"
    "test_cli_cooldown_legacy_config_spelling"
    # `NameError: PredefinedLifecycle` against nixpkgs' cyclonedx-python-lib,
    # below the floor `[sbom-offline]` declares. Both spellings are needed:
    # these match parametrised ids, so each case's SPDX half keeps running.
    "cyclonedx"
    "CycloneDX"
    # Probe for a sudo binary and a policy the sandbox does not have.
    "test_prime_sudo"
  ];

  # Imports the environment of a login shell, which the build user has neither
  # a passwd entry nor a shell for.
  disabledTestPaths = [ "tests/test_shell_env.py" ];

  pythonImportsCheck = [ "meta_package_manager" ];

  meta = {
    description = "Package managers abstraction and unification tool";
    homepage = "https://mpm.run/";
    changelog = "https://github.com/kdeldycke/meta-package-manager/blob/v${finalAttrs.version}/changelog.md";
    license = lib.licenses.gpl2Plus;
    # Add: maintainers = with lib.maintainers; [ kdeldycke ];
    mainProgram = "mpm";
  };
})
