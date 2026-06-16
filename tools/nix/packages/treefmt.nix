{
  inputs,
  pkgs,
  ...
}:
let
  # Configure formatter.
  treefmtEval = inputs.treefmt-nix.lib.evalModule pkgs {
    projectRootFile = ".git/config";
    settings.global.excludes = [ "external/*" ];

    # Markdown, JSON, YAML, etc.
    programs.prettier = {
      enable = true;
      package = pkgs.prettier;
    };

    # Python
    programs.ruff.enable = true;

    # Shell.
    programs.shfmt = {
      enable = true;
      indent_size = 4;
    };

    programs.shellcheck.enable = true;
    settings.formatter.shellcheck = {
      options = [
        "-e"
        "SC1091"
      ];
    };

    # Lua.
    programs.stylua.enable = true;

    # Nix.
    programs.nixfmt.enable = true;

    # Typos.
    programs.typos.enable = false;
  };

  treefmt = treefmtEval.config.build.wrapper;
in
treefmt
