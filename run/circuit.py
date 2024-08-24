import qibo

c = qibo.Circuit(5)
c.add(qibo.gates.M(0))
r = c(nshots=100)

print(r)
