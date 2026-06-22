# This function returns a list of `devenv` modules
# which are passed to `mkShell`.
#
# Search for package at:
# https://search.nixos.org/packages
{ pkgs, ... }:
[
  {
    name = "python";
    packages = [
      pkgs.pyright
      pkgs.ruff
      pkgs.libxcb
      pkgs.libGL
      pkgs.glib
    ];

    languages.python = {
      enable = true;
      venv.enable = true;
      uv = {
        enable = true;
        package = pkgs.uv;
        sync = {
          enable = true;
          allExtras = true;
        };
      };
    };
  }
]
