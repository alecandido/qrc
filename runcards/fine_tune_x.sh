#!/bin/bash
#SBATCH --job-name=qibocal
#SBATCH --partition=qw5q_platinum
#SBATCH -o "var/debug.o"

export QIBO_PLATFORM="qw11q"
poetry run python runcards/fine_tune_x.py
