import sys
from pathlib import Path

from qibocal.cli.report import report
from qibocal.auto.execute import Executor

path = Path(sys.argv[1]) / "cal"

with Executor.open("myexec", platform="dummy", path=path, force=True) as e:
    ssc = e.single_shot_classification(nshots=1000)
    print("\nfidelities:\n", ssc.results.fidelity, "\n")

report(path)
