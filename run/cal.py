from pathlib import Path
import rich

from qibocal.cli.report import report
from qibocal.auto.execute import Executor

path = Path(__file__).parents[1] / "var" / "cal"

with Executor.open("myexec", platform="qw21q-d", path=path, force=True) as e:
    #rs = e.resonator_spectroscopy(nshots=1000, 0)
    qf = e.qubit_flux(nshots=1000, relaxation_time=1000, bias_step=0.005, bias_width=0.2, freq_step=2_000_000, freq_width=10_000_000)
    #ssc = e.single_shot_classification(nshots=1000)
    kras = e.rabi_amplitude_signal(nshots=1000, min_amp=0.1, max_amp=0.5, step_amp=0.01)
    #ra = e.rabi_amplitude(nshots=1000, min_amp=0.1, max_amp=0.5, step_amp=0.01)
    #rich.print(rabi.results)
    print()

report(path)
