#!/usr/bin/env bash
#SBATCH -J calibration-script
#SBATCH -p qw11q
#SBATCH -o var/debug.out

BASEDIR=$(realpath "$SLURM_SUBMIT_DIR")
QIBOLAB_PLATFORMS=$(realpath "$BASEDIR/qibolab_platforms_qrc")
export QIBOLAB_PLATFORMS

poetry run python "$BASEDIR/run/cal.py" "$BASEDIR/var"
