"""A small frequency-domain nodal solver and the element models the as-laid simulation is made of.

Every element stamps an admittance matrix referenced to ground (node "0").  Nodes are strings.  A port is a
50 ohm termination; a source is a Norton current into a node.  Solve one frequency at a time.
"""
import cmath, math
import numpy as np

C0 = 299792458.0
MU0 = 4e-7 * math.pi
E0 = 8.854187817e-12
TAN_D = 0.02            # 7628 prepreg / FR4 core at a few GHz
SIGMA_CU = 5.8e7
ROUGH = 1.4             # electrodeposited copper's roughness on the conductor loss, a few GHz


class Circuit:
    def __init__(self, name=""):
        self.name = name
        self.idx = {"0": -1}
        self.els = []           # (nodes, fn(f) -> matrix)
        self.ports = {}         # name -> (node, z0)
        self.srcs = {}          # name -> (node, fn(f) -> complex current)  (Norton)
        self.notes = []

    def node(self, n):
        if n not in self.idx:
            self.idx[n] = len(self.idx) - 1
        return n

    def y2(self, a, b, yf):
        """a two-terminal admittance between a and b (b may be "0")"""
        self.node(a), self.node(b)
        self.els.append(((a, b), lambda f, yf=yf: (lambda y: np.array([[y, -y], [-y, y]]))(yf(f))))

    def z2(self, a, b, zf):
        self.y2(a, b, lambda f, zf=zf: 1.0 / zf(f))

    def block(self, nodes, Yf):
        """an n-port referenced to ground: Yf(f) is n x n"""
        for n in nodes:
            self.node(n)
        self.els.append((tuple(nodes), Yf))

    def port(self, name, node, z0=50.0):
        self.node(node)
        self.ports[name] = (node, z0)
        self.y2(node, "0", lambda f, z0=z0: 1.0 / z0)

    def source(self, name, node, If):
        self.node(node)
        self.srcs[name] = (node, If)

    def solve(self, f, inject):
        """inject: {node: complex current}; returns {node: voltage}"""
        n = len(self.idx) - 1
        Y = np.zeros((n, n), complex)
        for nodes, fn in self.els:
            M = fn(f)
            ii = [self.idx[x] for x in nodes]
            for a, ia in enumerate(ii):
                if ia < 0:
                    continue
                for b, ib in enumerate(ii):
                    if ib < 0:
                        continue
                    Y[ia, ib] += M[a, b]
        I = np.zeros(n, complex)
        for node, cur in inject.items():
            I[self.idx[node]] += cur
        V = np.linalg.solve(Y, I)
        out = {k: (V[i] if i >= 0 else 0.0) for k, i in self.idx.items()}
        return out

    def drive_port(self, f, name):
        """the port's 50 ohm source with an incident wave of 1 V: Norton 2 V / z0"""
        node, z0 = self.ports[name]
        return self.solve(f, {node: 2.0 / z0})

    def s21(self, f, src, dst):
        V = self.drive_port(f, src)
        return V[self.ports[dst][0]]

    def gain_to(self, f, src, load_nodes, load_r):
        """transducer gain from port `src` (its available power) into a resistor across load_nodes"""
        node, z0 = self.ports[src]
        V = self.drive_port(f, src)
        a, b = load_nodes
        vd = V[a] - (V[b] if b != "0" else 0.0)
        p_load = abs(vd) ** 2 / (2 * load_r)
        p_av = abs(2.0) ** 2 / (8 * z0)
        return p_load / p_av


# ---- lines ----
def tl_y(z0, eeff, length_m, f, w_m=0.29e-3, er=4.4, tand=TAN_D, rough=ROUGH):
    beta = 2 * math.pi * f * math.sqrt(eeff) / C0
    rs = math.sqrt(math.pi * f * MU0 / SIGMA_CU)
    a_c = rough * rs / (z0 * w_m)
    a_d = (math.pi * f / C0) * er * (eeff - 1) / (math.sqrt(eeff) * (er - 1)) * tand if eeff > 1 else 0.0
    g = complex(a_c + a_d, beta) * length_m
    if abs(g) < 1e-6:
        g = 1e-6
    coth = 1 / cmath.tanh(g)
    csch = 1 / cmath.sinh(g)
    return np.array([[coth, -csch], [-csch, coth]]) / z0


def add_tl(c, a, b, z0, eeff, length_mm, w_mm=0.29):
    L = length_mm * 1e-3
    if length_mm < 0.005:
        c.y2(a, b, lambda f: 1e3)
        return
    c.block((a, b), lambda f, z0=z0, e=eeff, L=L, w=w_mm * 1e-3: tl_y(z0, e, L, f, w))


def add_coupled(c, a1, a2, b1, b2, ze, zo, ee, eo, length_mm, w_mm=0.29):
    """an edge-coupled pair: line a from a1 to a2, line b from b1 to b2 (b1 beside a1)"""
    L = length_mm * 1e-3

    def Y(f):
        ye = tl_y(ze, ee, L, f, w_mm * 1e-3)
        yo = tl_y(zo, eo, L, f, w_mm * 1e-3)
        s, d = (ye + yo) / 2, (ye - yo) / 2
        M = np.zeros((4, 4), complex)
        # order a1 a2 b1 b2
        M[np.ix_([0, 1], [0, 1])] = s
        M[np.ix_([2, 3], [2, 3])] = s
        M[np.ix_([0, 1], [2, 3])] = d
        M[np.ix_([2, 3], [0, 1])] = d
        return M
    c.block((a1, a2, b1, b2), Y)


# ---- lumped parts ----
def z_cap(C, esl=0.3e-9, esr=0.15):
    return lambda f: esr + 1j * 2 * math.pi * f * esl + 1 / (1j * 2 * math.pi * f * C)


def z_ind(L, srf, q=30.0, q_f=1e9):
    """a wirewound inductor: L with its Q (at q_f, R rising as sqrt f) and its self-resonance's parallel C"""
    cp = 1.0 / ((2 * math.pi * srf) ** 2 * L)

    def z(f):
        w = 2 * math.pi * f
        r = (2 * math.pi * q_f * L / q) * math.sqrt(f / q_f)
        zl = r + 1j * w * L
        return 1.0 / (1.0 / zl + 1j * w * cp)
    return z


def z_res(R, esl=0.3e-9, cp=0.03e-12):
    return lambda f: 1.0 / (1.0 / (R + 1j * 2 * math.pi * f * esl) + 1j * 2 * math.pi * f * cp)


def z_l(L, r=0.0):
    return lambda f: r + 1j * 2 * math.pi * f * L


def y_c(C):
    return lambda f: 1j * 2 * math.pi * f * C


# ---- n-ports from S ----
def s2y(S, z0=50.0):
    n = S.shape[0]
    I = np.eye(n)
    return (I - S) @ np.linalg.inv(I + S) / z0


def unilateral_amp(y_in, gain_db, y_out=1 / 50.0):
    """Y of a unilateral amplifier: input admittance y_in(f) (complex), output 50 ohm, and the transconductance
    that gives gain_db(f) of S21 when both ports are matched"""
    def Y(f):
        g = 10 ** (gain_db(f) / 20) / 25.0      # |S21| = 25 |Y21| for matched 50 ohm ports
        return np.array([[y_in(f), 0], [-g, y_out]], complex)
    return Y
