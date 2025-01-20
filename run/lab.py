from pathlib import Path
import tempfile

from qibolab import create_platform, PulseSequence, Parameter, Sweeper
from qibolab._core.components.configs import LogConfig
from qibolab._core.execution_parameters import AveragingMode
from qibolab.instruments.qblox import mock as qblox_mock

qblox_mock.install()
platform = create_platform("iqm5q")

q0 = platform.natives.single_qubit[0]
assert q0.RX is not None
assert q0.MZ is not None

sequence = PulseSequence()
rx = q0.RX()
sequence |= rx
sequence |= q0.MZ()

log = Path(tempfile.mkdtemp(prefix="qblox-"))

platform.connect()
res = platform.execute(
    [sequence],
    nshots=1e3,
    updates=[{"log": LogConfig(path=log).model_dump()}],
    averaging_mode=AveragingMode.CYCLIC,
    sweepers=[
        [Sweeper(parameter=Parameter.amplitude, range=(0, 1, 0.09), pulses=[rx[0][1]])],
        [
            Sweeper(
                parameter=Parameter.relative_phase,
                range=(0, 1e9, 3e6),
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
platform.disconnect()

print(res)
print(log)
