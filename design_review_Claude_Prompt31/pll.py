import math, cmath
Kphi = 2.5569e-3/(2*math.pi); Nd = 232
C1, C2, C3, R2, R3 = 390e-12, 6.8e-9, 160e-12, 820.0, 2000.0   # fitted (PLAN.md section 3)
def pll_open(f, Kv):
    s = 2j*math.pi*f
    zin = 1/(s*C1 + 1/(R2 + 1/(s*C2)) + 1/(R3 + 1/(s*C3)))
    return Kphi*zin/(1+s*R3*C3)*Kv/(s*Nd)
def margin(Kv):
    lo, hi = 1e3, 1e7
    for _ in range(80):
        mid = math.sqrt(lo*hi); lo, hi = (mid, hi) if abs(pll_open(mid, Kv)) > 1 else (lo, mid)
    return lo, 180+math.degrees(cmath.phase(pll_open(lo, Kv)))
for kv in (40, 60, 80, 100, 130):
    fc, pm = margin(kv*1e6*2*math.pi); print("Kvco %3d MHz/V: fc %.0f kHz, PM %.0f deg" % (kv, fc/1e3, pm))
