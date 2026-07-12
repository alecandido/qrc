from collections.abc import Iterable
from pathlib import Path
import logging
import datetime
import shutil

from qibolab import LogConfig
import rich
from qibocal.auto.execute import Executor
from qibocal.cli.report import report

# Configure the global logging threshold to DEBUG
logging.basicConfig(level=logging.INFO)

data = Path(__file__).parents[1] / "var"
path = data / "cal"
log = data / "log"
shutil.rmtree(log, ignore_errors=True)
log.mkdir()

targets = [0, 1, 2, 3]

with Executor.open(
    platform="qpu169",
    targets=targets,
    path=path,
    force=True,
) as e:
    e.platform.parameters.configs["log"] = LogConfig(path=log)

    # e.calibrate_mixers()

    for q in targets:
        qs = e.qubit_spectroscopy(
            frequency=("lincenter", 10e6, 200),
            drive_duration=8e3,
            drive_amplitude=3e-3,
            nshots=2000,
            relaxation_time=2e3,
            targets=[q],
        )

        ras = e.rabi_amplitude_signal(
            min_amp=0.05,
            max_amp=0.8,
            step_amp=0.01,
            nshots=200,
            targets=[q],
        )

        ssc = e.single_shot_classification(
            nshots=int(2e3),
            targets=[q],
        )

        ra = e.rabi_amplitude(
            min_amp=0.05,
            max_amp=0.8,
            step_amp=0.01,
            nshots=500,
            targets=[q],
        )

        # rm = e.ramsey(
        #     detuning=2e6,
        #     delay_between_pulses_end=2000,
        #     delay_between_pulses_start=20,
        #     delay_between_pulses_step=40,
        #     nshots=500,
        #     targets=[q],
        # )

        rm = e.ramsey(
            detuning=0.5e6,
            delay_between_pulses_end=5000,
            delay_between_pulses_start=20,
            delay_between_pulses_step=100,
            nshots=500,
            targets=[q],
        )

        ssc = e.single_shot_classification(
            nshots=int(2e3),
            targets=[q],
        )

        # dsh = e.dispersive_shift(
        #     freq_width=5e6,
        #     freq_step=0.05e6,
        #     nshots=500,
        #     targets=[q],
        # )

        drs = e.drag_simple(
            beta_start=-2,
            beta_end=2,
            beta_step=0.1,
            targets=[q],
            nshots=300,
        )

        flp = e.flipping(
            delta_amplitude=0.05,
            nflips_max=30,
            nflips_step=1,
            targets=[q],
            nshots=300,
        )

        axy = e.allxy(
            targets=[q],
            nshots=200,
        )

    # rsa = e.resonator_amplitude(
    #     amplitude_step=0.00,
    #     amplitude_start=0.001,
    #     amplitude_stop=0.1,
    #     nshots=500,
    # )

    # rso = e.resonator_optimization(
    #     freq_width=1e6,
    #     freq_step=0.1e6,
    #     amplitude_step=0.02,
    #     amplitude_min=0.02,
    #     amplitude_max=0.35,
    #     delay=1000,
    #     nshots=1000,
    # )

    # t1 = e.t1(
    #     delay_before_readout_end=30e3,
    #     delay_before_readout_start=20,
    #     delay_before_readout_step=500,
    #     nshots=400,
    # )

    # t2 = e.t2(
    #     delay_between_pulses_end=30e3,
    #     delay_between_pulses_start=20,
    #     delay_between_pulses_step=500,
    #     nshots=400,
    # )

    # for q in targets:
    #     srb = e.standard_rb(
    #         depths=[2**i for i in range(1, 8)],
    #         niter=50,
    #         nshots=1000,
    #         targets=[q],
    #     )


report(e.path, e.history)


def save(path: Path, e: Executor):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    targets = ":".join(
        [
            "-".join(str(s) for s in t) if isinstance(t, Iterable) else str(t)
            for t in e.targets
        ]
    )
    now = datetime.datetime.now().strftime("%H:%M:%S")
    exp = f"{now}_[{targets}]_pi-pulse"
    folder = data / e.platform.name / today

    folder.mkdir(exist_ok=True, parents=True)
    path.rename(folder / exp)
    print(f"Saved experiment to {folder / exp}")


save(path, e)
