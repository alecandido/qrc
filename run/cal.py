import sys
from pathlib import Path
from pprint import pprint

from qibocal.cli.report import report
from qibocal.auto.execute import Executor

path = Path(sys.argv[1]) / "cal"

with Executor.open("myexec", platform="iqm5q", path=path, force=True) as e:
    ssc = e.resonator_spectroscopy(nshots=1000)
    pprint(ssc.results)
    print()

report(path)
