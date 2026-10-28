{ config, pkgs, ... }:
{
  packages = with pkgs; [
    prek
    poethepoet
    jupyter
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
    poetry = {
      enable = true;
      install = {
        enable = true;
        groups = [ "dev" ];
      };
    };
  };
}
