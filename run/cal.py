"""Calibration script for qw5q_platinum using the qibocal protocol execution
interface from qiboteam/qibocal#1716.

A protocol is imported by name from ``qibocal.protocols``, called with its
parameters, and passed to the executor. ``e(...)`` runs acquisition, fit, report
and update, and returns a ``Completed`` with ``.data``, ``.results`` and
``.reports``. ``targets`` is an execution option passed to ``e(...)``; pass
``skip_fit=True`` to only acquire.

``Executor.open`` creates the output folder, connects the platform, and on exit
disconnects and dumps the metadata and the updated platform. Direct execution does
not save data or results.

``QIBOLAB_PLATFORMS`` is set by ``run/env.bash``, and the results folder is the
first argument (``var/``, passed by the ``run/*.bash`` job scripts).
"""

import logging
import os
import shutil
import sys
from datetime import datetime
from numbers import Integral
from pathlib import Path

from qibocal import Executor
from qibocal.cli.report import report
from qibocal.protocols import (  # noqa: F401
    PROTOCOLS,
    resonator_spectroscopy,
    standard_rb_2q,
    standard_rb_2q_inter,
)

# - resonator spectroscopy
# - resonator frequency-flux arc
# - qubit spectroscopy
# - qubit frequency-flux arc
# - rabi amplitude
# - dispersive shift
# - ramsey
# - SSRO
# - flipping
# - drag tuning
# - all-xy
# - RB
# - metrics (T1, T2, readout fidelity)
#
# from time to time mixer cal


logging.basicConfig(level=logging.INFO)
start_time = datetime.now()


os.environ["QIBO_PLATFORM"] = "qw5q_platinum"

platform = "qw5q_platinum"

results_path = Path(sys.argv[1])


with Executor.open(
    path=results_path / "qibocal_report",
    platform=platform,
    targets=[2],
    update=True,
    force=True,
) as executor:
    for target in range(5):
        executor(
            resonator_spectroscopy(
                # frequency=("linspace", 7.1e9, 7.9e9, 2**12),
                frequency=("lincenter", 10e6, 500),
                # amplitude=0.22,
                nshots=1000,
                relaxation_time=100,
                power_level="low",
                # fit_function="s21",
                # phase_sign=False,
            ),
            targets=[target],
        )

    # e(
    #     standard_rb_2q(
    #         depths=[2**i for i in range(3)],
    #         niter=30,
    #         nshots=200,
    #     ),
    #     targets=[[2, 4]],
    # )

    # rb_inter = e(
    #     standard_rb_2q_inter(
    #         depths=[2**i for i in range(6)],
    #         niter=50,
    #         nshots=1000,
    #         interleave="CZ",
    #     ),
    #     targets=[[2, 4]],
    # )
    # outputs.append(rb_inter)
assert isinstance(executor.path, Path)
report(executor.path, executor.history)


def extract_qubits_from_history(history):
    """Return sorted unique qubit ids that appear in completed task targets."""
    qubits = set()
    for completed in history.values():
        targets = completed.task.targets or []
        for target in targets:
            if isinstance(target, (list, tuple, set)):
                for qubit in target:
                    if isinstance(qubit, Integral):
                        qubits.add(int(qubit))
            elif isinstance(target, Integral):
                qubits.add(int(target))
    return sorted(qubits)


task_str = "_".join(set(executor.history._tasks.keys()))
qubits = extract_qubits_from_history(executor.history)
qubit_str = "_".join(map(str, qubits))
time_str = start_time.strftime("%H-%M-%S")
date = start_time.strftime("%y%m%d")

final_path = results_path / f"{platform}/{date}/{time_str}-{task_str}-{qubit_str}"
final_path.parent.mkdir(parents=True, exist_ok=True)
shutil.move(executor.path, final_path)
