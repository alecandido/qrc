"""Testing qblox driver."""

from pathlib import Path
import tempfile

import numpy as np
from qibolab import Delay
import rich.console
from qibolab import create_platform, PulseSequence, Parameter, Sweeper, Pulse, Rectangular

from qibolab._core.execution_parameters import AcquisitionType, AveragingMode


# ---

cons = rich.console.Console(color_system="truecolor")
headers = "b i color(8)"

# ---

platform = create_platform("qbc02")
ch = platform.qubits["D1"].flux

sequence = PulseSequence([(ch, Pulse(amplitude=0.6, duration=4000, envelope=Rectangular()))])

platform.connect()
res = platform.execute(
    [sequence],
    nshots=1e8,
    averaging_mode=AveragingMode.CYCLIC,
    acquisition_type=AcquisitionType.INTEGRATION,
)
platform.disconnect()

cons.print(f"\n[{headers}]results[/]", res)
