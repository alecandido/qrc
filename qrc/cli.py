from pathlib import Path

import click

from .calibrate import calibrate, setup


@click.command("qrc")
@click.argument("path", type=click.Path(path_type=Path))
def run(path: Path):
    print(setup())
