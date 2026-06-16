{
  description = "deid-module devshell";

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

          # Things needed only at compile-time.
          packagesBasic = with pkgs; [
            age
            bash
            coreutils
            curl
            fd
            findutils
            gettext
            git
            kubernetes-helm
            k9s
            jq
            just
            kubectl
            minikube
            sops
            (import ./packages/treefmt.nix { inherit inputs pkgs; })
            vendir
            zsh
            yamlfmt
            ytt
          ];
        in
        {
          devShells = {
            default = pkgs.mkShell {
              packages = packagesBasic;
            };

            ci = pkgs.mkShell {
              packages = packagesBasic;

              # Due to some weird handling of TMPDIR inside containers:
              # https://github.com/NixOS/nix/issues/8355
              # We have to reset the TMPDIR to make `nix build` work inside
              # a development shell.
              # Without `nix develop` it works.
              shellHook = "unset TMPDIR";
            };

            surrogate = devenv.lib.mkShell {
              inherit pkgs inputs;
              modules = import ./shells/surrogate.nix { inherit pkgs; };
            };
          };
        };
    in
    # Creates an attribute map `{ <key>.<system>.default = ...}`
    # by calling function `defineOutput`.
    # Key sofar is only `devShells` but can be any output `key` for a flake.
    flake-utils.lib.eachDefaultSystem defineOutput;
}
