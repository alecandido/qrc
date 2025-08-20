import qibo
from qibo import gates as g

qibo.set_backend("qibolab", platform="iqm5q")

c = qibo.Circuit(5)
# for n in range(c.nqubits):
for n in [0]:
    # c.add(g.GPI2(n, phi=0.1))
    c.add(g.X(n))
    c.add(g.M(n))
r = c(nshots=10)

print(r.samples())
