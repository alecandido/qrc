from pathlib import Path

import numpy as np
import rich.console
from qibolab import (
    Acquisition,
    AcquisitionType,
    AveragingMode,
    Delay,
    Gaussian,
    PulseSequence,
    Pulse,
    Readout,
    Rectangular,
    create_platform
)
from qibolab._core.components.configs import LogConfig

cons = rich.console.Console(color_system="truecolor")

platform = create_platform("qw21q-d")
q0 = platform.natives.single_qubit["D1"]

def pulse(kind="pi-x"):
    scale = 2 if "2" not in kind else 1
    phase = 1.5707963267948966 if "y" in kind else 0.0
    return (
            "D1/drive",
            Pulse(
                duration=40.0,
                amplitude=scale*0.04869214911314345,
                envelope=Gaussian(rel_sigma=0.2),
                relative_phase=phase,
            ),
        )

seq = lambda *labels: PulseSequence([
        *(pulse(lab) for lab in labels if lab != "i"),
        ("D1/acquisition", Delay(duration=80.0)),
        (
            "D1/acquisition",
            Readout(
                acquisition=Acquisition(duration=1200.0),
                probe=Pulse(
                    duration=1200.0,
                    amplitude=0.4,
                    envelope=Rectangular(),
                    relative_phase=0.0,
                ),
            ),
        ),
    ])

#cons.print(seq())
seqs = [seq("i", "i"),
     seq("pi-x", "pi-x"),
     seq("pi-y", "pi-y"),
     seq("pi-x", "pi-y"),
     seq("pi-y", "pi-x"),
     seq("pi/2-x", "i"),
     seq("pi/2-y", "i"),
     seq("pi/2-x", "pi/2-y"),
     seq("pi/2-y", "pi/2-x"),
     seq("pi/2-x", "pi-y"),
     seq("pi/2-y", "pi-x"),
     seq("pi-x", "pi/2-y"),
     seq("pi-y", "pi/2-x"),
     seq("pi/2-x", "pi-x"),
     seq("pi-x", "pi/2-x"),
     seq("pi/2-y", "pi-y"),
     seq("pi-y", "pi/2-y"),
     seq("pi-x", "i"),
     seq("pi-y", "i"),
     seq("pi/2-x", "pi/2-x"), 
     seq("pi/2-y", "pi/2-y")]

platform.connect()
options = dict(
    nshots=1e3,
    averaging_mode=AveragingMode.SINGLESHOT,
    acquisition_type=AcquisitionType.DISCRIMINATION,
)
res = platform.execute(seqs, **options)
ress = {}
for seq in seqs:
    ress.update(platform.execute([seq], **options))
platform.disconnect()

#cons.print(res)
for r in (res, ress):
    states = np.array(list(r.values()))
    cons.print(states.mean(axis=1))

