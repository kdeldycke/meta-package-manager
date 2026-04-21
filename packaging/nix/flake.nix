# Usage:
#   nix run github:kdeldycke/meta-package-manager?dir=packaging/nix -- --version
#   nix profile install github:kdeldycke/meta-package-manager?dir=packaging/nix
#   nix build ./packaging/nix
{
  description = "Meta Package Manager: CLI wrapping all package managers with a unifying interface";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs =
    { nixpkgs, ... }:
    let
      forAllSystems = nixpkgs.lib.genAttrs [
        "aarch64-darwin"
        "aarch64-linux"
        "x86_64-darwin"
        "x86_64-linux"
      ];
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          python3 = pkgs.python3.override {
            packageOverrides = self: _super: {
              click-extra = self.callPackage ./click-extra.nix { };
              extra-platforms = self.callPackage ./extra-platforms.nix { };
            };
          };
          mpm = pkgs.callPackage ./package.nix {
            python3Packages = python3.pkgs;
            inherit (pkgs) lib fetchFromGitHub;
          };
        in
        {
          default = mpm;
          meta-package-manager = mpm;
        }
      );
    };
}
