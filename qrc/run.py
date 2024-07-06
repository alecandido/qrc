"""Run."""

from pathlib import Path

from fabric import Connection


def run(c: Connection, commands: str):
    """Run commands."""
    for command in commands.splitlines():
        c.run(command)


SBATCH = "sbatched"


def sbatch(c: Connection, script: str, queue: str = "qw5q_platinum"):
    """Sbatch."""
    sbatch_dir = Path.home() / SBATCH
    path = sbatch_dir / "ciao"

    path.write_text(script)

    c.run(f"sbatch -p {queue} {path}")


if __name__ == "__main__":
    c = Connection("qrccluster")
