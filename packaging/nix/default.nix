# Install meta-package-manager from a local checkout while the nixpkgs PR is
# pending (https://github.com/NixOS/nixpkgs/pull/506145).
#
# Usage:
#   nix-env -f ./packaging/nix -i
#   nix-shell -p -f ./packaging/nix --run "mpm --version"
#
# Once click-extra and extra-platforms land in nixpkgs, the overlay below
# becomes unnecessary and this file reduces to a single callPackage.
{ pkgs ? import <nixpkgs> { } }:

let
  python3 = pkgs.python3.override {
    packageOverrides = self: _super: {
      click-extra = self.callPackage ./click-extra.nix { };
      extra-platforms = self.callPackage ./extra-platforms.nix { };
    };
  };
in
pkgs.callPackage ./package.nix {
  python3Packages = python3.pkgs;
  inherit (pkgs) lib fetchFromGitHub;
}
