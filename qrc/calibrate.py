"""Run calibration."""

import inspect
from pathlib import Path
from typing import Optional


def setup(branch: Optional[str] = None):
    """Set up instructions."""
    switch = f"git switch {branch}" if branch is not None else ""
    commands = f"""
    git clone git@github.com:alecandido/qrc
    cd qrc/
    {switch}
    git submodule init
    git submodule update
    poetry install --with dev
    """
    return inspect.cleandoc(commands).replace("\n\n", "\n")


def calibrate(path: Path):
    """Generate calibration batch file."""
    command = "auto runcards/string-targets.yml -o var/test-qibocal-909"

    return f"""
    #!/bin/sh
    cd {path}
    export QIBOLAB_PLATFORMS=$(realpath ./qibolab_platforms_qrc)
    poetry run qq {command}
    """
