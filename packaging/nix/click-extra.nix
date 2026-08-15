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
  version = "8.9.0";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "kdeldycke";
    repo = "click-extra";
    tag = "v${finalAttrs.version}";
    hash = "sha256-O+r2KpzYdczy/iaA2e8SJ/303OrlSoppJwRYBvte/iU=";
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
    # Optional libraries imported at module level by the test files.
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

  # The configuration tests are served over HTTP by a local pytest-httpserver.
  # It bound to ``localhost`` until 8.9.0 moved it to ``127.0.0.1``, which drops
  # the name lookup the Darwin build sandbox refuses (a ``gaierror``). Only that
  # lookup was ever proven to fail: whether the sandbox also gates the loopback
  # socket itself is untested, so the flag stays until a build without it comes
  # back green.
  __darwinAllowLocalNetworking = true;

  pythonImportsCheck = [ "click_extra" ];

  meta = {
    description = "Drop-in replacement for Click to build colorful CLI";
    homepage = "https://github.com/kdeldycke/click-extra";
    changelog = "https://github.com/kdeldycke/click-extra/blob/v${finalAttrs.version}/changelog.md";
    license = lib.licenses.gpl2Plus;
    # Add: maintainers = with lib.maintainers; [ kdeldycke ];
  };
})
