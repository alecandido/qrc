from qibolab import (
    AcquisitionType,
    Gaussian,
    Drag,
    Pulse,
    PulseSequence,
    Rectangular,
    create_platform,
)
import numpy as np
 
platform = create_platform("qw21q-b")
b1 = platform.natives.single_qubit["B3"]
platform.connect()
 
# using calibrated gates
res = platform.execute([b1.RX() | b1.MZ()], nshots=1e3)
print(res)
 
y = next(reversed(res.values()))
np.savetxt("data/data_calibrated_gates_b3.txt",y,fmt = '%.8f', delimiter="\t ", newline="\n")
 
# using calibrated gates (no classification)
res = platform.execute(
    [b1.RX()| b1.MZ()], acquisition_type=AcquisitionType.INTEGRATION, nshots=1e3
)
print(res)
 
y = next(reversed(res.values()))
np.savetxt("data/data_calibrated_gates_b3_2.txt",y,fmt = '%.8f', delimiter="\t ", newline="\n")
 
 
platform.disconnect()
