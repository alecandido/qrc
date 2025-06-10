#!/usr/bin/env bash
#SBATCH -p iqm5q
#SBATCH -o var/debug.out

BASEDIR=$(realpath "$SLURM_SUBMIT_DIR")
QIBOLAB_PLATFORMS=$(realpath "$BASEDIR/qibolab_platforms_qrc")
PYTHONBREAKPOINT="pudb.set_trace"
export QIBOLAB_PLATFORMS
export PYTHONBREAKPOINT

poetry run python "$BASEDIR/run/cal.py" "$BASEDIR/var"
