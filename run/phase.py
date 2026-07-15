import datetime
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt
import rich
from qibocal.auto.execute import Executor
from qibocal.calibration.calibration import QubitId
from qibolab._core.native import SingleQubitNatives

from qibolab import (
    AveragingMode,
    LogConfig,
    Parameter,
    PulseSequence,
    Qubit,
    Sweeper,
    VirtualZ,
)

Results = dict[QubitId, npt.NDArray[np.float64]]
HERE = Path(__file__).parent

# Configure the global logging threshold to DEBUG
logging.basicConfig(level=logging.INFO)

platform = "qpu169"
targets: list[QubitId] = [2]
endph, nph = 12 * np.pi, 200
phases = np.linspace(0.0, endph, nph)
swept = True


def prepare_folder() -> Path:
    now = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
    exp = f"{now}_[{targets}]_phase"

    folder = HERE / platform / exp
    folder.mkdir(parents=True)

    return folder


def loop(
    e: Executor, qubit: Qubit, natives: SingleQubitNatives, mz: PulseSequence
) -> npt.NDArray[np.float64]:
    meas = mz[0][1].id
    assert qubit.drive is not None

    values = []
    for ph in phases:
        vz = VirtualZ(phase=ph)
        seq = natives.R(np.pi / 2) | [(qubit.drive, vz)] | natives.R(np.pi / 2) | mz
        res = e.platform.execute(
            [seq], [], nshots=1e3, averaging_mode=AveragingMode.CYCLIC
        )
        values.append(res[meas])
    return np.array(values)


def sweep(
    e: Executor, qubit: Qubit, natives: SingleQubitNatives, mz: PulseSequence
) -> npt.NDArray[np.float64]:
    meas = mz[0][1].id
    assert qubit.drive is not None

    vz = VirtualZ(phase=0)
    seq = natives.R(np.pi / 2) | [(qubit.drive, vz)] | natives.R(np.pi / 2) | mz
    phs = Sweeper(parameter=Parameter.phase, range=(0, endph, endph / nph), pulses=[vz])
    res = e.platform.execute(
        [seq], [[phs]], nshots=1e3, averaging_mode=AveragingMode.CYCLIC
    )
    return res[meas]


def plot(
    phases: npt.NDArray[np.float64],
    results: dict[QubitId, npt.NDArray[np.float64]],
    path: Path,
) -> None:
    path.mkdir(exist_ok=True, parents=True)
    for t, res in results.items():
        fig = plt.figure(figsize=(6, 4))
        fig.axes[0].scatter(phases, res)
        fig.savefig(path / f"oscillation-{t}.png", dpi=300)


def run(report: Path, log: Path) -> Results:
    results: Results = {}
    with Executor.open(platform=platform, targets=targets, path=report) as e:
        e.platform.parameters.configs["log"] = LogConfig(path=log)
        for t in e.targets:
            assert isinstance(t, (int, str))
            qubit = e.platform.qubits[t]
            natives = e.platform.natives.single_qubit[t]
            assert natives.MZ is not None
            mz = natives.MZ()
            results[t] = (
                sweep(e, qubit, natives, mz) if swept else loop(e, qubit, natives, mz)
            )
    return results


def main():
    folder = prepare_folder()
    report = folder / "report"
    log = folder / "log"

    res = run(report, log)
    rich.print(res)
    plot(phases, res, report / "data")


if __name__ == "__main__":
    main()
