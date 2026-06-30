from collections.abc import Iterable
from pathlib import Path
import logging
import datetime
import shutil

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
import rich
from qibolab import AveragingMode, LogConfig, Parameter, Sweeper, VirtualZ
from qibocal.auto.execute import Executor

# Configure the global logging threshold to DEBUG
logging.basicConfig(level=logging.INFO)

data = Path(__file__).parents[1] / "var"
path = data / "cal"
log = data / "log"
shutil.rmtree(log, ignore_errors=True)
log.mkdir()

targets = [[2, 4]]
results: dict[tuple[int, int], dict[int, npt.NDArray[np.float64]]] = {}
endph, nph = 12 * np.pi, 200
phases = np.linspace(0.0, endph, nph)


with Executor.open(
    platform="qw5q_platinum", targets=targets, path=path, force=True
) as e:
    e.platform.parameters.configs["log"] = LogConfig(path=log)
    for t in e.targets:
        q0 = e.platform.qubits[t[0]]
        q1 = e.platform.qubits[t[1]]
        n0 = e.platform.natives.single_qubit[t[0]]
        n1 = e.platform.natives.single_qubit[t[1]]
        m0 = n0.MZ()
        m1 = n1.MZ()
        meas = {t[0]: m0[0][1].id, t[1]: m1[0][1].id}
        # values = []
        # for ph in phases:
        #     seq = (
        #         n0.R(np.pi / 2)
        #         | [(q0.drive, VirtualZ(phase=ph))]
        #         | n0.R(np.pi / 2)
        #         | m0
        #         | m1
        #     )
        #     res = e.platform.execute(
        #         [seq], [], nshots=1e3, averaging_mode=AveragingMode.CYCLIC
        #     )
        #     values.append({k: res[v] for k, v in meas.items()})
        # results[t] = {i: np.array([v[i] for v in values]) for i in t}
        vz = VirtualZ(phase=0)
        seq = n0.R(np.pi / 2) | [(q0.drive, vz)] | n0.R(np.pi / 2) | m0 | m1
        phs = Sweeper(
            parameter=Parameter.phase, range=(0, endph, endph / nph), pulses=[vz]
        )
        res = e.platform.execute(
            [seq], [[phs]], nshots=1e3, averaging_mode=AveragingMode.CYCLIC
        )
        results[t] = {k: res[v] for k, v in meas.items()}


def plot(
    phases: npt.NDArray[np.float64],
    results: dict[tuple[int, int], dict[int, npt.NDArray[np.float64]]],
    path: Path,
) -> None:
    path.mkdir(exist_ok=True, parents=True)
    for t, res in results.items():
        fig, axs = plt.subplots(2, 1, sharex=True, figsize=(6, 4))
        for ax, values in zip(axs, res.values()):
            ax.scatter(phases, values)
        fig.savefig(path / f"oscillation-{t}.png", dpi=300)


rich.print(results)
plot(phases, results, e.path / "data")


def save(path: Path, e: Executor) -> None:
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    targets = ":".join(
        [
            "-".join(str(s) for s in t) if isinstance(t, Iterable) else str(t)
            for t in e.targets
        ]
    )
    now = datetime.datetime.now().strftime("%H:%M:%S")
    protocols = "-".join([t.id for t in e.history])
    exp = f"{now}_[{targets}]_{protocols}"
    folder = data / e.platform.name / today

    folder.mkdir(exist_ok=True, parents=True)
    path.rename(folder / exp)
    print(f"Saved experiment to {folder / exp}")


save(path, e)
