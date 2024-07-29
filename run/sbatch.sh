#!/usr/bin/env bash
#SBATCH -p spinq10q
#SBATCH -o var/debug.out

BASEDIR=$(realpath "$SLURM_SUBMIT_DIR")
QIBOLAB_PLATFORMS=$(realpath "$BASEDIR/qibolab_platforms_qrc")
export QIBOLAB_PLATFORMS
unset QIBO_PLATFORM

poetry run qq auto "$BASEDIR/run/card.yml" -o "$BASEDIR/var/spinq10q-zcu111" -f
