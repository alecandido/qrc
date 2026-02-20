from pathlib import Path

import rich
from qibocal.auto.execute import Executor
from qibocal.cli.report import report

path = Path(__file__).parents[1] / "var" / "cal"
targets = ["D1"]

with Executor.open(
    "myexec", platform="qw21q-d", targets=targets, path=path, force=True
) as e:
    failed = False
    i = 0
    while not failed:
        print(f"\n\nITERATION\n---------\n{i}\n\n")
        ras = e.rabi_amplitude_signal(nshots=2000, min_amp=0.05, max_amp=0.8, step_amp=0.01)
        failed = targets[0] not in ras.results.amplitude
        i += 1
        if i > 100:
            break

report(e.path, e.history)

