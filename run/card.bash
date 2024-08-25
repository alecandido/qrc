#!/usr/bin/env bash
#SBATCH -p qw11q
#SBATCH -o var/debug.out

BASEDIR=$(realpath "$SLURM_SUBMIT_DIR")
QIBOLAB_PLATFORMS=$(realpath "$BASEDIR/qibolab_platforms_qrc")
export QIBOLAB_PLATFORMS

poetry run qq auto "$BASEDIR/run/card.yml" -o "$BASEDIR/var/card" -f
