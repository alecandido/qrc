# from pathlib import Path
# import tempfile

import numpy as np
from qibolab import Delay
import rich.console
from qibolab import create_platform, PulseSequence, Parameter, Sweeper

# from qibolab._core.components.configs import LogConfig
from qibolab._core.execution_parameters import AcquisitionType, AveragingMode
from qibolab.instruments.qblox import mock as qblox_mock

cons = rich.console.Console(color_system="truecolor")
headers = "b i color(8)"

# ----

qblox_mock.install()
platform = create_platform("iqm5q")

q0 = platform.natives.single_qubit[0]
assert q0.RX is not None
assert q0.MZ is not None

sequence = PulseSequence()
rx = q0.RX()
delay = Delay(duration=10)
sequence.append((rx[0][0], delay))
sequence |= rx
sequence |= q0.MZ()

# log = Path(tempfile.mkdtemp(prefix="qblox-"))

platform.connect()
res = platform.execute(
    [sequence],
    nshots=1e1,
    # updates=[{"log": LogConfig(path=log).model_dump()}],
    averaging_mode=AveragingMode.CYCLIC,
    acquisition_type=AcquisitionType.INTEGRATION,
    sweepers=[
        [
            Sweeper(parameter=Parameter.duration, range=(10, 100, 20), pulses=[delay]),
            Sweeper(
                parameter=Parameter.amplitude, range=(0, 1, 0.09), pulses=[rx[0][1]]
            ),
        ],
        [
            Sweeper(
                parameter=Parameter.amplitude,
                range=(1, 0, -3e-2),
                pulses=[rx[0][1]],
            ),
            Sweeper(
                parameter=Parameter.frequency,
                range=(-1e8, 1e8, 3.5e7),
                channels=[rx[0][0]],
            ),
        ],
    ],
)

mock_cluster = platform.instruments["qblox"].cluster
platform.disconnect()

# ---

for (slot, seq), prog in mock_cluster.programs.items():
    if prog.strip() == "":
        continue
    cons.print(f"\n[blue i]slot[/] {slot} [pink1]seq[/] {seq}")
    cons.print(prog)
    cons.print(f"[{headers}]waveforms[/]")
    wavs = mock_cluster.sequences[(slot, seq)]["waveforms"]
    for id_, wav in wavs.items():
        cons.print(id_)
        cons.print(wav | {"data": np.round(wav["data"][:5], 5).tolist() + ["..."]})
    cons.print(
        f"[{headers}]acquisitions[/]\n {mock_cluster.sequences[(slot, seq)]['acquisitions']}"
    )

cons.print(f"\n[{headers}]results[/]", res)
