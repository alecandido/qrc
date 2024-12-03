from qibolab import create_platform, PulseSequence

platform = create_platform("iqm5q")

q0 = platform.natives.single_qubit[0]
assert q0.MZ is not None

sequence = PulseSequence()
sequence |= q0.MZ()

res = platform.execute([sequence], nshots=1e3)

print(res)
