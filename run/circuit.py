import qibo

c = qibo.Circuit(5)
for n in range(c.nqubits):
    c.add(qibo.gates.GPI2(n, phi=0.1))
    c.add(qibo.gates.M(n))
r = c(nshots=10)

print(r.samples())
