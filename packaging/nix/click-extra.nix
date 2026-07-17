{
  lib,
  buildPythonPackage,
  fetchFromGitHub,
  gitMinimal,
  pytestCheckHook,
  hjson,
  jsonschema,
  myst-parser,
  pygments,
  pytest-httpserver,
  pyyaml,
  requests,
  sphinx,
  tomlkit,
  xmltodict,
  uv-build,
  boltons,
  click,
  cloup,
  deepmerge,
  extra-platforms,
  tabulate,
  wcmatch,
  wcwidth,
}:

buildPythonPackage (finalAttrs: {
  pname = "click-extra";
  version = "8.4.0";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "kdeldycke";
    repo = "click-extra";
    tag = "v${finalAttrs.version}";
    hash = "sha256-msQCQVmLET5WZtRK3r2T6c0VGW/d7FbD7IUvgx3zb2Q=";
  };

  build-system = [ uv-build ];

  # wcwidth backs the ``tabulate[widechars]`` extra pinned in pyproject.toml
  # and is also a direct runtime dependency since 8.4.
  dependencies = [
    boltons
    click
    cloup
    deepmerge
    extra-platforms
    tabulate
    wcmatch
    wcwidth
  ];

  nativeCheckInputs = [
    pytestCheckHook
    # Optional libraries imported at module level by the test files:
    # ``test_table.py`` needs hjson, tomlkit, xmltodict and yaml;
    # ``test_pygments.py`` needs pygments; ``test_carapace.py`` gates its
    # completion-spec validation tests behind jsonschema;
    # ``test_config.py`` drives remote configuration loading through
    # pytest-httpserver's ``httpserver`` fixture; ``tests/sphinx`` builds
    # documents with sphinx and myst-parser and its matrix tests assemble
    # synthetic git repositories; ``requests`` is imported at module level
    # by tests whose network-marked cases are deselected below.
    gitMinimal
    hjson
    jsonschema
    myst-parser
    pygments
    pytest-httpserver
    pyyaml
    requests
    sphinx
    tomlkit
    xmltodict
  ];

  # Tests marked ``network`` make HTTPS requests; the build sandbox has no
  # system TLS CA bundle.
  disabledTestMarks = [ "network" ];

  disabledTestPaths = [
    # tests/mkdocs requires mkdocs-click, not packaged in nixpkgs.
    "tests/mkdocs"
  ];

  disabledTests = [
    # The four integration tests below assert against debug output that
    # should not include the test sandbox's ``$HOME``; click-extra logs
    # the search pattern using the runtime environment HOME instead of
    # the test fixture's ``tmp_path``.
    "test_integrated_color_option"
    "test_required_command"
    "test_unset_conf_debug_message"
    "test_integrated_verbosity_options"
  ];

  pythonImportsCheck = [ "click_extra" ];

  meta = {
    description = "Drop-in replacement for Click to build colorful CLI";
    homepage = "https://github.com/kdeldycke/click-extra";
    changelog = "https://github.com/kdeldycke/click-extra/blob/v${finalAttrs.version}/changelog.md";
    license = lib.licenses.gpl2Plus;
    # Add: maintainers = with lib.maintainers; [ kdeldycke ];
  };
})
