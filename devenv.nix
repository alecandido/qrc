{ config, pkgs, ... }:
{
  packages = with pkgs; [
    prek
    poethepoet
  ];

  env = {
    QIBOLAB_PLATFORMS = config.devenv.root + "/qibolab_platforms_qrc";
    PYTHONBREAKPOINT = "pudb.set_trace";
  };

  languages.python = {
    enable = true;
    libraries = with pkgs; [ zlib ];
    # latest release in the nixpkgs-python cache: never build the interpreter
    version = "3.13.17";
    venv.enable = true;
    uv = {
      enable = true;
      sync = {
        enable = true;
        # keep the packages installed by install.bash
        arguments = [
          "--locked"
          "--inexact"
        ];
        groups = [ "dev" ];
      };
    };
  };
}
