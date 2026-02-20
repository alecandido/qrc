#!/usr/bin/env bash
#SBATCH -p agnostic2
#SBATCH -o var/debug.out

SCRIPTPATH=$(scontrol show job "$SLURM_JOB_ID" | awk -F= '/Command=/{print $2}')
SCRIPTDIR=$(dirname "$SCRIPTPATH")
BASEDIR=$(dirname "$SCRIPTDIR")
. "$SCRIPTDIR/env.bash" $BASEDIR

poetry run python -u "$SCRIPTDIR/$1.py" "$BASEDIR/var"
