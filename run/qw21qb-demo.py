import rich
from qibolab import (
    AcquisitionType,
    Gaussian,
    Pulse,
    PulseSequence,
    Rectangular,
    create_platform,
)

platform = create_platform("qw21q-b")
b1 = platform.natives.single_qubit["B1"]

platform.connect()

# using calibrated gates
res = platform.execute([b1.RX() | b1.MZ()], nshots=1e3)
rich.print(res)

# with arbitrary pulses
drive = PulseSequence(
    [(b1.RX()[0][0], Pulse(amplitude=0.2, duration=10, envelope=Rectangular()))]
)
res = platform.execute([drive | b1.MZ()], nshots=1e3)
rich.print(res)

# with arbitrary pulses - integrated signal (no classification)
drive = PulseSequence(
    [
        (
            b1.RX()[0][0],
            Pulse(amplitude=0.2, duration=10, envelope=Gaussian(rel_sigma=0.2)),
        )
    ]
)
res = platform.execute(
    [drive | b1.MZ()], acquisition_type=AcquisitionType.INTEGRATION, nshots=1e3
)
rich.print(res)

platform.disconnect()
