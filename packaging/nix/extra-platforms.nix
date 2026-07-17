{
  lib,
  buildPythonPackage,
  fetchFromGitHub,
  pytestCheckHook,
  pytest-cov-stub,
  pytest-xdist,
  uv-build,
}:

buildPythonPackage (finalAttrs: {
  pname = "extra-platforms";
  version = "13.3.1";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "kdeldycke";
    repo = "extra-platforms";
    tag = "v${finalAttrs.version}";
    hash = "sha256-uNapgmmducyLcSBF7wiEkyho/IMD9jutXpx6aHcCQFg=";
  };

  build-system = [ uv-build ];

  nativeCheckInputs = [
    pytestCheckHook
    # The pyproject ``addopts`` pass --cov and --numprocesses/--dist flags,
    # so the coverage and xdist plugins must resolve for pytest to start.
    pytest-cov-stub
    pytest-xdist
  ];

  # Tests marked ``network`` reach out to PyPI; the build sandbox has no
  # system TLS CA bundle.
  disabledTestMarks = [ "network" ];

  disabledTestPaths = [
    # Shells out to ``uv`` to render the docs as a side effect; not
    # available in the build sandbox.
    "tests/test_sphinx_crossrefs.py"
  ];

  disabledTests = [
    # Both tests assume the CI runner environment (the ``GITHUB_RUNNER_OS``
    # env var, the expected number of detected platform traits per runner
    # image). Neither is available inside a hermetic build sandbox.
    "test_platform_detection"
    "test_current_funcs"
  ];

  pythonImportsCheck = [ "extra_platforms" ];

  meta = {
    description = "Detect platforms, architectures and OS families";
    homepage = "https://github.com/kdeldycke/extra-platforms";
    changelog = "https://github.com/kdeldycke/extra-platforms/blob/v${finalAttrs.version}/changelog.md";
    license = lib.licenses.asl20;
    # Add: maintainers = with lib.maintainers; [ kdeldycke ];
  };
})
