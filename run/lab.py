from pathlib import Path
import tempfile

from qibolab import create_platform, PulseSequence, Parameter, Sweeper
from qibolab._core.components.configs import LogConfig

platform = create_platform("iqm5q")

q0 = platform.natives.single_qubit[0]
assert q0.RX is not None
assert q0.MZ is not None

sequence = PulseSequence()
rx = q0.RX()
sequence |= rx
sequence |= q0.MZ()

log = Path(tempfile.mkdtemp(prefix="qblox-"))
res = platform.execute(
    [sequence],
    nshots=1e3,
    updates=[{"log": LogConfig(path=log).model_dump()}],
    sweepers=[
        [Sweeper(parameter=Parameter.amplitude, range=(0, 1, 0.2), pulses=[rx[0][1]])]
    ],
)

print(res)
print(log)
