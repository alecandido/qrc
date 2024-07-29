import subprocess
from pathlib import Path

import click

from .calibrate import calibrate, setup


@click.group()
def _base():
    pass


@_base.command()
@click.argument("path", type=click.Path(path_type=Path))
def run(path: Path):
    print(setup())


@_base.command()
def install():
    subprocess.run("poetry install --with dev".split())


@_base.command()
def queue():
    subprocess.run("watch -n1 queue".split())

@_base.command()
def term():
    subprocess.run("export TERM='xterm'".split())
