from pathlib import Path
import rich

from qibocal.cli.report import report
from qibocal.auto.execute import Executor

path = Path(__file__).parents[1] / "var" / "cal"

with Executor.open("myexec", platform="iqm5q", path=path, force=True) as e:
    ssc = e.single_shot_classification(nshots=1000)
    rich.print(ssc.results)
    print()

report(path)
