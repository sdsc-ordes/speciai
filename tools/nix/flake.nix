{
  description = "speciai development environment";

  nixConfig = {
    extra-substituters = [
      # Nix community's cache server
      "https://nix-community.cachix.org"
      "https://devenv.cachix.org"
    ];
    extra-trusted-public-keys = [
      "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
      "devenv.cachix.org-1:w1cLUi8dv3hnoSPGAuibQv+f9TZLr6cv/Hm9XgU50cw="
    ];
  };

  inputs = {

    # You can access packages and modules from different nixpkgs revs at the same time.
    nixpkgs.url = "github:cachix/devenv-nixpkgs/rolling";
    #nixpkgsStable.url = "github:nixos/nixpkgs/nixos-26.05";
    # Also see the 'stable-packages' overlay at 'overlays/default.nix'.

    flake-utils.url = "github:numtide/flake-utils";

    # Format the repo with nix-treefmt.
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    devenv = {
      url = "github:cachix/devenv";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      nixpkgs,
      flake-utils,
      devenv,
      ...
    }@inputs:
    let
      # The function which builds the flake output attrMap.
      defineOutput =
        system:
        let
          # inherit from nixpkgs
          pkgs = nixpkgs.legacyPackages.${system};

          baseTools = with pkgs; [
            bash
            coreutils
            curl
            fd
            findutils
            gettext
            git
            git-cliff
            jq
            just
            (import ./packages/treefmt.nix { inherit inputs pkgs; })
            vendir
            yamlfmt
          ];
          devTools = with pkgs; [
            age
            prek
            sops
            zsh
          ];
          pythonModule = import ./modules/python.nix { inherit pkgs; };
        in
        {
          devShells = {
            default = devenv.lib.mkShell {
              inherit pkgs inputs;
              modules = 
                pythonModule ++ [ 
                  {packages = baseTools;}
                  {packages = devTools;}
                ];
            };

            ci = devenv.lib.mkShell {
              inherit pkgs inputs;
              modules = 
                pythonModule ++ [ {packages = baseTools;}];
            };

          };
        };
    in
    flake-utils.lib.eachDefaultSystem defineOutput;
}
