{
  lib,
  buildPythonPackage,
  fetchFromGitHub,
  pytestCheckHook,
  uv-build,
  boltons,
  click,
  cloup,
  deepmerge,
  extra-platforms,
  hjson,
  pygments,
  pytest-httpserver,
  pyyaml,
  requests,
  tabulate,
  tomlkit,
  wcmatch,
  xmltodict,
}:

buildPythonPackage (finalAttrs: {
  pname = "click-extra";
  version = "7.15.0";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "kdeldycke";
    repo = "click-extra";
    tag = "v${finalAttrs.version}";
    hash = "sha256-Hof1SFh8XXBoQ9Pr4qI/7jNlBDMpUi7+qs1QcT042tY=";
  };

  build-system = [ uv-build ];

  dependencies = [
    boltons
    click
    cloup
    deepmerge
    extra-platforms
    requests
    tabulate
    wcmatch
  ]
  # click-extra's pyproject.toml pins ``tabulate[widechars]``; the ``widechars``
  # extra adds ``wcwidth`` for correct column padding around wide Unicode
  # characters (e.g. emoji). Without it, ``tests/test_table.py`` rendering
  # assertions fail across most table formats.
  ++ tabulate.optional-dependencies.widechars;

  # Optional libraries imported at module-level by various test files:
  # tests/test_table.py needs hjson, pyyaml, tomlkit and xmltodict (the
  # [hjson], [yaml], [toml] and [xml] extras declared in pyproject.toml);
  # tests/test_pygments.py needs pygments; tests/test_config.py uses the
  # httpserver fixture from pytest-httpserver to test remote config loading.
  nativeCheckInputs = [
    pytestCheckHook
    hjson
    pygments
    pytest-httpserver
    pyyaml
    tomlkit
    xmltodict
  ];

  # Tests marked ``network`` make HTTPS requests; the build sandbox has
  # no system TLS CA bundle.
  disabledTestMarks = [ "network" ];

  disabledTestPaths = [
    # tests/sphinx requires the Sphinx ecosystem (myst-parser, furo, etc.).
    "tests/sphinx"
    # tests/mkdocs requires mkdocs-click.
    "tests/mkdocs"
  ];

  # These tests assert against debug output that should not include the
  # build sandbox's ``$HOME``: click-extra logs the search pattern using
  # the runtime environment HOME instead of the test fixture's tmp_path.
  disabledTests = [
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
