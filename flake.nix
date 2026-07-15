{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    systems.url = "github:nix-systems/default";
    devenv.url = "github:cachix/devenv";
    nixpkgs-python.url = "github:cachix/nixpkgs-python";
  };

  outputs = {
    self,
    nixpkgs,
    devenv,
    systems,
    ...
  } @ inputs: let
    forEachSystem = nixpkgs.lib.genAttrs (import systems);
  in {
    devShells =
      forEachSystem
      (system: let
        pkgs = nixpkgs.legacyPackages.${system};
      in {
        default = devenv.lib.mkShell {
          inherit inputs pkgs;

          modules = [
            ({
              lib,
              pkgs,
              config,
              ...
            }: {
              packages = with pkgs; [pre-commit jupyter];

              env = {
                QIBOLAB_PLATFORMS = (dirOf config.env.DEVENV_ROOT) + "/qibolab_platforms_qrc";
                LD_LIBRARY_PATH = builtins.concatStringsSep ":" (map (p: "${p}/lib") (with pkgs; [
                  stdenv.cc.cc.lib
                  zlib
                ]));
                PYTHONBREAKPOINT = "pudb.set_trace";
              };

              languages.python = {
                enable = true;
                version = "3.13";
                libraries = with pkgs; [zlib];
                poetry = {
                  enable = true;
                  install = {
                    enable = true;
                    groups = ["dev"];
                  };
                };
              };
            })
          ];
        };
      });
  };
}
