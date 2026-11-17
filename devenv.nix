{
  config,
  pkgs,
  ...
}: {
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
    libraries = with pkgs; [zlib];
    venv.enable = true;
    uv = {
      enable = true;
      sync = {
        enable = true;
        arguments = ["--locked"];
        groups = [
          "dev"
          "qblox"
        ];
      };
    };
  };
}
