from collections.abc import Iterable
from pathlib import Path
import logging
import shutil
import datetime

import rich
from qibocal.auto.execute import Executor
from qibocal.cli.report import report

# Configure the global logging threshold to DEBUG
logging.basicConfig(level=logging.INFO)

data = Path(__file__).parents[1] / "var"
path = data / "cal"
targets = [[2, 4]]

with Executor.open(
    platform="qw5q_platinum", targets=targets, path=path, force=True
) as e:
    # rs = e.resonator_spectroscopy(nshots=100, freq_width=30e6, freq_step=200e3, power_level="high", amplitude=0.2, relaxation_time=500)
    # rp = e.resonator_punchout(nshots=500, relaxation_time=20_000, freq_width=5_000_000, freq_step=100_000, min_amp=0.005, max_amp=0.6, step_amp=0.02)
    # qs = e.qubit_spectroscopy(nshots=1000, relaxation_time=1_000, freq_width=40_000_000, freq_step=100_000, drive_duration=8_000, drive_amplitude=0.02)
    # qf = e.qubit_flux(nshots=500, relaxation_time=10_000, bias_step=0.001, bias_width=0.05, freq_step=300_000, freq_width=20_000_000, drive_amplitude=0.015)
    # ras = e.rabi_amplitude_signal(nshots=2000, min_amp=0.05, max_amp=0.8, step_amp=0.01)
    # ssc = e.single_shot_classification(
    #     nshots=200,
    # )
    # ra = e.rabi_amplitude(
    #     min_amp=0.1,
    #     max_amp=0.5,
    #     step_amp=0.01,
    #     nshots=50,
    # )
    # rm = e.ramsey(detuning=500_000, delay_between_pulses_end=5000, delay_between_pulses_start=20, delay_between_pulses_step=100, nshots=500)
    # t1 = e.t1(delay_before_readout_end=30000, delay_before_readout_start=20, delay_before_readout_step=1000, nshots=1000)
    # rsa = e.resonator_amplitude(nshots=500, amplitude_step=0.00:, amplitude_start=0.001, amplitude_stop=0.1)
    # rso = e.resonator_optimization(nshots=1000, freq_width=2_000_000, freq_step=100_000, amplitude_step=0.01, amplitude_min=0.01, amplitude_max=0.6, delay=1000)
    # axy = e.allxy(nshots=200)
    # faf = e.flux_amplitude_frequency(amplitude_min=0.0, amplitude_max=0.1, amplitude_step=0.005, duration=200, relaxation_time=5000)
    # cry = e.cryoscope(duration_min=1, duration_max=80, duration_step=1, flux_pulse_amplitude=0.1, relaxation_time=5000)
    co = e.correct_virtual_z_phases(
        theta_start=-3.14,
        theta_end=3.14,
        theta_step=0.1,
        nshots=200,
    )

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
    protocols = "-".join([t.id for t in e.history])
    exp = f"{now}_[{targets}]_{protocols}"
    folder = data / e.platform.name / today

    folder.mkdir(exist_ok=True, parents=True)
    path.rename(folder / exp)


save(path, e)
