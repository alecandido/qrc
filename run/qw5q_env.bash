#!/usr/bin/env bash
# Isolated environment for run/qw5q_coherence_flux.py, outside of this repository.
#
# Qibocal, Qibolab and the platforms are checked out at the verified upstream
# commits (cf. run/qw5q_calibration.md): the project submodules are not used, nor
# modified.
#
# Usage: run/qw5q_env.bash [DEST]     (default: /tmp/qw5q-env)
# Requires git, uv and Python 3.13, e.g. in: nix shell nixpkgs#uv nixpkgs#python313

set -euo pipefail

SCRIPTDIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
mkdir -p "${1:-/tmp/qw5q-env}"
DEST=$(cd "${1:-/tmp/qw5q-env}" && pwd)
PYTHON=${PYTHON:-python3.13}

QIBOCAL_REF=539a32f86ef40b8b3f14858623f973ddf2751d2c
QIBOLAB_REF=004c14b4f622448f593476a9e0a80714954ceed6
PLATFORMS_REF=e77ac724ccac2c3d98baf2e310ff6794a8823646

for cmd in git uv "$PYTHON"; do
    command -v "$cmd" >/dev/null || {
        echo "Missing '$cmd': try 'nix shell nixpkgs#uv nixpkgs#python313'"
        exit 1
    }
done

checkout() {
    local repo=$1 ref=$2 dir="$DEST/src/$1"
    if [ ! -d "$dir/.git" ]; then
        git clone --quiet --filter=blob:none --no-checkout \
            "https://github.com/qiboteam/$repo.git" "$dir"
    fi
    git -C "$dir" fetch --quiet --filter=blob:none origin "$ref"
    git -C "$dir" -c advice.detachedHead=false checkout --quiet --detach "$ref"
    echo "$repo: $(git -C "$dir" rev-parse HEAD)"
}

mkdir -p "$DEST/src"

checkout qibocal "$QIBOCAL_REF"
checkout qibolab "$QIBOLAB_REF"
checkout qibolab_platforms_qrc "$PLATFORMS_REF"

[ -d "$DEST/venv" ] || uv venv --quiet --python "$PYTHON" "$DEST/venv"
VIRTUAL_ENV="$DEST/venv" uv pip install --quiet \
    --constraint "$SCRIPTDIR/qw5q_constraints.txt" \
    --editable "$DEST/src/qibolab" \
    --editable "$DEST/src/qibocal" \
    marimo lark qblox-instruments qcodes qcodes_contrib_drivers pytest ruff

cat >"$DEST/env.bash" <<EOF
export VIRTUAL_ENV="$DEST/venv"
export PATH="$DEST/venv/bin:\$PATH"
export QIBOLAB_PLATFORMS="$DEST/src/qibolab_platforms_qrc"
export QIBO_BACKEND=numpy
EOF

cat <<EOF

Environment ready. From the repository root:

    . $DEST/env.bash
    pytest run/test_qw5q_helpers.py         # offline, mock platform
    marimo edit run/qw5q_coherence_flux.py  # preflight is offline
EOF
