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

targets = [1]

with Executor.open(
    platform="qpu169",
    targets=targets,
    path=path,
    force=True,
) as e:
    e.platform.parameters.configs["log"] = LogConfig(path=log)

    # rs = e.resonator_spectroscopy(
    #     frequency=("linspace", 6.99e7, 7.36e7, int(1e5)),
    #     power_level="high",
    #     amplitude=0.2,
    #     relaxation_time=500,
    #     nshots=50,
    # )

    # e.calibrate_mixers()

    # for q, center in zip(targets, [7.01157e9, 7.0851e9, 7.1944e9, 7.2931e9]):
    #     rs = e.resonator_spectroscopy(
    #         frequency=("linwindow", center, 10e6, int(2e4)),
    #         power_level="high",
    #         amplitude=0.2,
    #         targets=[q],
    #         relaxation_time=500,
    #         nshots=400,
    #     )

    # rs = e.resonator_spectroscopy(
    #     frequency=("lincenter", 10e6, int(2e4)),
    #     power_level="low",
    #     relaxation_time=500,
    #     nshots=200,
    # )

    # rp = e.resonator_punchout(
    #     freq_width=5e6,
    #     freq_step=0.1e6,
    #     min_amp=0.005,
    #     max_amp=0.6,
    #     step_amp=0.02,
    #     nshots=500,
    #     relaxation_time=500,
    # )

    # qs = e.qubit_spectroscopy(
    #     frequency=("lincenter", 100e6, 2000),
    #     drive_duration=8e3,
    #     drive_amplitude=3e-3,
    #     nshots=500,
    #     relaxation_time=2e3,
    # )

    # qps = e.qubit_power_spectroscopy(
    #     frequency=("lincenter", 300e6, 1000),
    #     amplitude=("linspace", 1e-3, 300e-3, 40),
    #     duration=4e3,
    #     nshots=100,
    #     relaxation_time=2e3,
    # )

    # qs = e.qubit_spectroscopy(
    #     frequency=("lincenter", 10e6, 200),
    #     drive_duration=8e3,
    #     drive_amplitude=3e-3,
    #     nshots=2000,
    #     relaxation_time=2e3,
    # )

    # tlc = e.two_levels_crossing(
    #     drive1=("lincenter", 40e6, 100),
    #     drive2=("lincenter", 40e6, 100),
    #     duration=8e3,
    #     amplitude=(0.02, 0.2),
    #     nshots=100,
    #     relaxation_time=2e3,
    # )

    for q in targets:
        dsh = e.dispersive_shift(
            freq_width=5e6,
            freq_step=0.05e6,
            nshots=500,
            targets=[q],
        )

        qse = e.qubit_spectroscopy_ef(
            frequency=("lincenter", 60e6, 200),
            drive_duration=2e3,
            drive_amplitude=0.3,
            nshots=1000,
            relaxation_time=20e3,
            targets=[q],
        )

        rae = e.rabi_amplitude_ef(
            min_amp=0.05,
            max_amp=0.8,
            step_amp=0.01,
            pulse_length=40,
            nshots=500,
            targets=[q],
        )

        sse = e.qutrit_classification(
            nshots=int(2e3),
            targets=[q],
        )

    # qf = e.qubit_flux(
    #     bias_step=0.001,
    #     bias_width=0.05,
    #     freq_step=300_000,
    #     freq_width=20_000_000,
    #     drive_amplitude=0.015,
    #     nshots=500,
    #     relaxation_time=10_000,
    # )

    # ras = e.rabi_amplitude_signal(
    #     min_amp=0.05,
    #     max_amp=0.8,
    #     step_amp=0.01,
    #     nshots=200,
    # )

    # rafs = e.rabi_amplitude_frequency_signal(
    #     min_amp=0.05,
    #     max_amp=0.8,
    #     step_amp=0.01,
    #     min_freq=-20e6,
    #     max_freq=20e6,
    #     step_freq=1e6,
    #     nshots=200,
    # )

    # for q in targets:
    # ssc = e.single_shot_classification(
    #     nshots=int(2e3),
    #     # targets=[q],
    # )

    # ra = e.rabi_amplitude(
    #     min_amp=0.05,
    #     max_amp=0.8,
    #     step_amp=0.01,
    #     nshots=500,
    #     # targets=[q],
    # )

    #     rm = e.ramsey(
    #         detuning=0.5e6,
    #         delay_between_pulses_end=5000,
    #         delay_between_pulses_start=20,
    #         delay_between_pulses_step=100,
    #         targets=[q],
    #         nshots=500,
    #     )

    #     ssc = e.single_shot_classification(
    #         nshots=int(2e3),
    #         targets=[q],
    #     )

    # dsh = e.dispersive_shift(
    #     freq_width=5e6,
    #     freq_step=0.05e6,
    #     nshots=500,
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

    # for q in targets:
    #     drs = e.drag_simple(
    #         beta_start=-2,
    #         beta_end=2,
    #         beta_step=0.1,
    #         targets=[q],
    #         nshots=300,
    #     )

    #     flp = e.flipping(
    #         delta_amplitude=0.05,
    #         nflips_max=30,
    #         nflips_step=1,
    #         targets=[q],
    #         nshots=300,
    #     )

    #     axy = e.allxy(
    #         targets=[q],
    #         nshots=200,
    #     )

    # for q, duration in zip(targets, [40e3, 40e3, 20e3, 10e3]):
    #     t1 = e.t1(
    #         delay_before_readout_end=duration,
    #         delay_before_readout_start=20,
    #         delay_before_readout_step=int(duration / 50),
    #         targets=[q],
    #         nshots=400,
    #     )

    #     t2 = e.t2(
    #         delay_between_pulses_end=duration,
    #         delay_between_pulses_start=20,
    #         delay_between_pulses_step=int(duration / 50),
    #         targets=[q],
    #         nshots=400,
    #     )

    # for q in targets:
    #     srb = e.standard_rb(
    #         depths=[2**i for i in range(1, 8)],
    #         niter=50,
    #         nshots=1000,
    #         targets=[q],
    #     )

    # for q in targets:
    #     rzz = e.ramsey_zz(
    #         delay_between_pulses_start=10,
    #         delay_between_pulses_end=2000,
    #         delay_between_pulses_step=50,
    #         detuning=0.5e6,
    #         nshots=400,
    #         targets=[tuple(q)],
    #     )

    # for q in targets:
    #     crl = e.cr_length(
    #         duration_range=[10, 400, 10],
    #         pulse_amplitude=0.3,
    #         echo=False,
    #         nshots=1000,
    #         targets=[tuple(q)],
    #     )

    # cra = e.cr_amplitude(
    #     amplitude_range=[0.01, 0.5, 0.01],
    #     pulse_duration=161,
    #     echo=False,
    #     nshots=1000,
    #     targets=[tuple(q)],
    # )

    # cpt = e.cancellation_phase_tuning(
    #     duration_range=[10, 400, 20],
    #     phase_range=[0.0, 6.2, 0.5],
    #     pulse_duration=161,
    #     echo=False,
    #     nshots=1000,
    #     targets=[tuple(q)],
    # )

    # faf = e.flux_amplitude_frequency(
    #     amplitude_min=0.0,
    #     amplitude_max=0.1,
    #     amplitude_step=0.005,
    #     duration=200,
    # )

    # cry = e.cryoscope(
    #     duration_min=1,
    #     duration_max=80,
    #     duration_step=1,
    #     flux_pulse_amplitude=0.1,
    #     relaxation_time=5000,
    # )

    # co = e.correct_virtual_z_phases(
    #     theta_start=0,
    #     theta_end=-6.28,
    #     theta_step=-0.1,
    #     nshots=200,
    #     sweep=True,
    # )

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
    protocols = ("-".join([t.id for t in e.history]))[:100]
    exp = f"{now}_[{targets}]_{protocols}"
    folder = data / e.platform.name / today

    folder.mkdir(exist_ok=True, parents=True)
    path.rename(folder / exp)
    print(f"Saved experiment to {folder / exp}")


save(path, e)
