"""LNA input network as laid out on rev A vs Skyworks' circuit: power delivered into the LNA's input conductance
relative to the available power, the LNA modelled as the admittance that Skyworks' 0.5 pF at the pin matches."""
import os, sys, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "sim"))
import rf_lines as R
c0 = 299.792458e6
ESL = 0.3e-9           # an 0402 capacitor's mounted ESL


def line(w, L_mm, f):
    z, e = R.cpwg_z0(w, 0.25)
    b = 2 * np.pi * f * np.sqrt(e) / c0 * L_mm * 1e-3
    return np.array([[np.cos(b), 1j * z * np.sin(b)], [1j * np.sin(b) / z, np.cos(b)]])


def ser(Z): return np.array([[1, Z], [0, 1]], complex)
def sh(Y): return np.array([[1, 0], [Y, 1]], complex)


def zstub(w, L, ZL, f):
    A = line(w, L, f)
    return (A[0, 0] * ZL + A[0, 1]) / (A[1, 0] * ZL + A[1, 1])


def gain(f, case="as laid", lg=0.5e-9):
    w = 2 * np.pi * f
    Cp = 1 / ((2 * np.pi * 6.4e9) ** 2 * 6.8e-9)
    ZL101 = 1 / (1 / (1j * w * 6.8e-9 + 0.5) + 1j * w * Cp) + 1j * w * 0.3e-9
    Zc101 = 1 / (1j * w * 1.5e-12) + 1j * w * ESL
    Zc102 = 1 / (1j * w * 0.5e-12) + 1j * w * (ESL + lg)
    Ylna = 1 / 50 - 1j * w * 0.5e-12
    M = line(0.29, 4.55, f) @ sh(1 / zstub(0.20, 2.4, ZL101, f)) @ line(0.29, 1.76, f) @ ser(Zc101)
    if case == "as laid":
        M = M @ sh(1 / zstub(0.20, 1.8, Zc102, f)) @ line(0.29, 1.64, f) @ line(0.25, 0.6, f)
    elif case == "C102 removed":
        M = M @ line(0.29, 1.64, f) @ line(0.25, 0.6, f)
    elif case == "C102 at the pin":
        M = M @ line(0.29, 1.64, f) @ line(0.25, 0.6, f) @ sh(1 / (1 / (1j * w * 0.5e-12) + 1j * w * (ESL + 0.15e-9)))
    elif case == "Skyworks":
        M = M @ sh(1 / (1 / (1j * w * 0.5e-12) + 1j * w * (ESL + 0.15e-9)))
    ZL = 1 / Ylna
    A, B_, C, D = M.ravel()
    Zin = (A * ZL + B_) / (C * ZL + D)
    Vin = Zin / (Zin + 50)
    VL, IL = np.linalg.solve(M, [Vin, Vin / Zin])
    return 10 * np.log10((abs(VL) ** 2 / 50 / 2) / (1 / (8 * 50)))


if __name__ == "__main__":
    cases = ["Skyworks", "as laid", "C102 removed", "C102 at the pin"]
    print("  GHz  " + "  ".join("%15s" % c for c in cases) + "   as laid, ground 0.2 / 1.0 nH")
    for f in (3.0, 3.5, 4.0, 4.5, 5.0, 5.25, 5.5, 5.75, 5.8, 5.9, 6.0, 6.5, 7.0):
        F = f * 1e9
        print("%5.2f  " % f + "  ".join("%15.1f" % gain(F, c) for c in cases) + "   %5.1f %5.1f" % (gain(F, "as laid", 0.2e-9), gain(F, "as laid", 1.0e-9)))
