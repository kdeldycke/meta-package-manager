# The Python package-set overrides `mpm` needs, shared by both entry points.
#
# Kept in one file because those entry points are built by different commands:
# `nix-build` reads default.nix, while `nix build ./packaging/nix` reads the
# flake, and both must build the same set.
{ pkgs }:
self: super: {
  click-extra = self.callPackage ./click-extra.nix { };

  # click-extra 10 and cloup 4 declare `click>=8.5`, above the 8.4.x nixpkgs
  # ships, so their runtime dependency check rejects them before mpm is reached.
  #
  # Pinned to that floor, the smallest step from what nixpkgs ships: an override
  # here reaches every package in this set, not just click-extra, and runs the
  # test suites of those it rebuilds, some of which turn the deprecation
  # warnings of a newer click into errors.
  #
  # Drop this once nixpkgs ships click 8.5.0 or newer. NixOS/nixpkgs#506145
  # needs it there too, with cloup 4, before it can package mpm 8.3.0.
  click = super.click.overridePythonAttrs (_: rec {
    version = "8.5.0";
    src = pkgs.fetchFromGitHub {
      owner = "pallets";
      repo = "click";
      tag = version;
      hash = "sha256-VYdaEN9l2MRVz42I8t8IDOpG5XeDM8bf34dLZy3yf10=";
    };
  });

  # click-extra 10 declares `cloup>=4`, above the 3.1.0 nixpkgs ships. Drop this
  # once nixpkgs ships cloup 4.0.0 or newer.
  cloup = self.callPackage ./cloup.nix { };

  extra-platforms = self.callPackage ./extra-platforms.nix { };

  # The click override above rebuilds the HTTP stack behind mpm's check inputs,
  # and with it their own test suites. On a loaded macOS runner their timing
  # tests fail at random: `test_h2_timeout_during_response` of httpcore2 on one
  # run, `TestReceive.test_receive_timeout` of httpx2 on another. Both suites
  # pass on nixpkgs' own builders, so skip them on the one platform they flake.
  httpcore2 = super.httpcore2.overridePythonAttrs (_: {
    doCheck = !pkgs.stdenv.hostPlatform.isDarwin;
  });
  httpx2 = super.httpx2.overridePythonAttrs (_: {
    doCheck = !pkgs.stdenv.hostPlatform.isDarwin;
  });
}
