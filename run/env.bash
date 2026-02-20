if [ -z "$1" ]; then
    echo "Positional argument in position 1 required:"
    echo "Base directory containing 'qibolab_platforms_qrc'"
    return 1
fi

BASEDIR=$(realpath "$1")
QIBOLAB_PLATFORMS=$(realpath "$BASEDIR/qibolab_platforms_qrc")
PYTHONBREAKPOINT="pudb.set_trace"

export QIBOLAB_PLATFORMS
#export PYTHONBREAKPOINT
