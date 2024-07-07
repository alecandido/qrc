"""Run."""

import base64
import random
from pathlib import Path

from fabric import Connection


def run(c: Connection, commands: str):
    """Run commands."""
    for command in commands.splitlines():
        c.run(command)


SBATCH = "sbatched"
SBATCH_DIR = Path.home() / SBATCH


def _random_name() -> str:
    return base64.urlsafe_b64encode(random.randbytes(20)).decode()


def sbatch(c: Connection, script: str, queue: str = "qw5q_platinum"):
    """Sbatch."""
    folder = SBATCH_DIR / _random_name()
    path = folder / "sbatch.sh"
    path.write_text(script)

    c.run(f"sbatch -p {queue} {path}")


if __name__ == "__main__":
    c = Connection("qrccluster")
