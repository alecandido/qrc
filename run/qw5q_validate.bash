#!/usr/bin/env bash
# Mandatory offline validation of run/qw5q_coherence_flux.py: no hardware involved.
#
# Run from the repository root, in the environment created by run/qw5q_env.bash:
#
#     . /tmp/qw5q-env/env.bash
#     run/qw5q_validate.bash
#
# Fails on an unverified environment, on any failed or skipped test, and on any
# connection attempt during the headless notebook exports.

set -euo pipefail

SCRIPTDIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
: "${QIBOLAB_PLATFORMS:?source the env.bash created by run/qw5q_env.bash}"
MIN_TESTS=65
OUT=$(mktemp -d)
export PYTHONDONTWRITEBYTECODE=1 QIBO_BACKEND=numpy
echo "outputs in $OUT"

step() { printf '\n== %s\n' "$*"; }

step "environment"
python - "$SCRIPTDIR" <<'PY'
import sys

sys.path.insert(0, sys.argv[1])
import qw5q_helpers as h

components = h.check_environment("qw5q_platinum")
for row in h.environment_rows(components):
    print(f"{row['status']:>4}  {row['component']:<22} {row['detail']}")
if not h.environment_verified(components):
    sys.exit("environment does not match the tested one")
PY

step "tests"
python -m pytest -p no:cacheprovider -q --junitxml "$OUT/junit.xml" \
    "$SCRIPTDIR/test_qw5q_helpers.py"
python - "$OUT/junit.xml" "$MIN_TESTS" <<'PY'
import sys
import xml.etree.ElementTree as ET

suite = ET.parse(sys.argv[1]).getroot().find("testsuite")
counts = {k: int(suite.get(k, 0)) for k in ("tests", "failures", "errors", "skipped")}
print(counts)
if counts["failures"] or counts["errors"] or counts["skipped"]:
    sys.exit("failed, errored or skipped tests")
if counts["tests"] < int(sys.argv[2]):
    sys.exit(f"only {counts['tests']} tests collected, expected >= {sys.argv[2]}")
PY

step "marimo check"
marimo check --strict "$SCRIPTDIR/qw5q_coherence_flux.py"

step "guarded headless exports"
MOCK=$(python -c 'import pathlib, qibocal; print(pathlib.Path(qibocal.__file__).resolve().parents[2] / "tests" / "platforms")')
for platform in qw5q_platinum mock; do
    platforms=$QIBOLAB_PLATFORMS
    [ "$platform" = mock ] && platforms=$MOCK
    PYTHONPATH="$SCRIPTDIR/qw5q_guard" QW5Q_GUARD_LOG="$OUT/violations.log" \
        QW5Q_PLATFORM=$platform QIBOLAB_PLATFORMS=$platforms \
        python - "$SCRIPTDIR/qw5q_coherence_flux.py" "$OUT/$platform.html" <<'PY'
import subprocess
import sys

cmd = ["marimo", "-q", "-y", "export", "html", sys.argv[1], "-o", sys.argv[2]]
try:
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
except subprocess.TimeoutExpired:
    sys.exit("export timed out (kernel did not shut down)")
if out.returncode or out.stdout.strip() or out.stderr.strip():
    print(out.stdout, out.stderr)
    sys.exit(f"export failed or produced output (exit {out.returncode})")
PY
    echo "$platform: exported"
done
if [ -s "$OUT/violations.log" ]; then
    cat "$OUT/violations.log"
    echo "hardware guard violations"
    exit 1
fi

step "static checks"
ruff check --no-cache "$SCRIPTDIR"/qw5q_*.py "$SCRIPTDIR"/test_qw5q_helpers.py \
    "$SCRIPTDIR/qw5q_guard"
ruff format --no-cache --check "$SCRIPTDIR"/qw5q_*.py \
    "$SCRIPTDIR"/test_qw5q_helpers.py "$SCRIPTDIR/qw5q_guard"
for script in qw5q_env.bash qw5q_validate.bash; do
    bash -n "$SCRIPTDIR/$script"
done

step "all validations passed"
