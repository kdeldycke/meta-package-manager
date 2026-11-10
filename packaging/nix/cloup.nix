{
  lib,
  buildPythonPackage,
  fetchFromGitHub,
  pythonOlder,
  pytestCheckHook,
  hatch-vcs,
  hatchling,
  click,
  typing-extensions,
}:

buildPythonPackage (finalAttrs: {
  pname = "cloup";
  # Bumped by hand: update.py follows the first-party definitions only, and this
  # file goes away once nixpkgs ships cloup 4.
  version = "4.0.0";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "janluke";
    repo = "cloup";
    tag = "v${finalAttrs.version}";
    hash = "sha256-sXJvGVw6TZoZ/tnalRDPyX9WN9GJg6PdiRYYRJYVMOE=";
  };

  build-system = [
    hatch-vcs
    hatchling
  ];

  dependencies = [ click ] ++ lib.optionals (pythonOlder "3.12") [ typing-extensions ];

  nativeCheckInputs = [
    pytestCheckHook
    # tests/test_styling.py and tests/test_typing.py import it on every Python
    # version, not only below the 3.12 the package needs it for.
    typing-extensions
  ];

  pythonImportsCheck = [ "cloup" ];

  meta = {
    description = "Click extended with option groups, constraints, aliases, help themes";
    homepage = "https://github.com/janluke/cloup";
    changelog = "https://github.com/janluke/cloup/releases/tag/v${finalAttrs.version}";
    license = lib.licenses.bsd3;
  };
})
