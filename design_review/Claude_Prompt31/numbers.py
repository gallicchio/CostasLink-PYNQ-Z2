import math, json
B = json.load(open('./build/budget.json'))
P = B['parts']
db = lambda x: 10*math.log10(x)
print("== 1. Costas loop")
Kd, Ko = B['loop_Kd'], B['loop_Ko']; R1, R2, C = B['loop_R1_fit'], B['loop_R2_fit'], B['loop_C_fit']
wn = math.sqrt(Kd*Ko/(R1*C)); z = wn*R2*C/2
print("fn %.0f Hz zeta %.2f; crossover ~ %.1f kHz" % (wn/2/math.pi, z, 2*z*wn/2/math.pi))
# extra lags at crossover: VCXO modulation BW 15 kHz (min), MAX2871 PLL 80 kHz, PM 50
fx = 2*z*wn/2/math.pi
lag_vcxo = math.degrees(math.atan(fx/15e3)); lag_pll = math.degrees(math.atan(fx/80e3))*1.3
pm_pi = math.degrees(math.atan(2*z/math.sqrt(math.sqrt(4*z**4+1)-2*z**2)))
print("PI loop PM %.0f deg; VCXO 15 kHz pole -%.0f, PLL ~-%.0f: ~%.0f deg left" % (pm_pi, lag_vcxo, lag_pll, pm_pi-lag_vcxo-lag_pll))
# loop gain vs level
for name, dBrel in (("regulated", 0), ("DSA at power-up 31.75 (10 m)", -(31.75-5.25)), ("fast floor -81 dBm", -(-59.2+81)), ("30 dB pad loopback, DSA max", 7.5)):
    k = 10**(dBrel/20); wn2 = wn*math.sqrt(k); print("  %-32s Kd x%.3f: fn %.0f Hz zeta %.2f" % (name, k, wn2/2/math.pi, z*math.sqrt(k)))
# static phase error from offsets: one leg of Q, slope a/2 per rad
a = B['a_reg_V']; slope = a/2
for off_mV, why in ((20, "ADL5380 +-10 mV diff x4, one leg"), (5.8, "THS4541 Vocm offset max"), (2.5, "THS4541 Vos 0.5 mV x noise gain 5"), (28.3, "sum")):
    print("  offset %.1f mV (%s): static phase %.1f deg" % (off_mV, why, math.degrees(off_mV*1e-3/slope)))
print("  Q_OFF_F reach +-%.0f mV at output = +-%.0f mV a leg = +-%.0f deg" % (B['fast_trim_V']*1e3, B['fast_trim_V']*1e3/2, math.degrees(B['fast_trim_V']/2/slope)))
# pull-in
for dfk in (29, 61, 290, 322):
    dw = 2*math.pi*dfk*1e3; print("  pull-in from %3.0f kHz: %.3f s (Δω/ωn = %.0f)" % (dfk, dw**2/(2*z*wn**3), dw/wn))
# frequency offsets
print("  TCXO +-(2+2.5+1) ppm = +-%.0f kHz each; VCXO overall +-50 ppm = +-290 kHz at centre; APR +-50 ppm" % (5.5e-6*5.8e9/1e3))
# phase noise at 5.8 GHz
N = 232; dBN = 20*math.log10(N)
print("  x232 = +%.1f dB on the reference's phase noise" % dBN)
def integ(L, f1, f2, n=4000):
    s = 0; lf1, lf2 = math.log(f1), math.log(f2)
    for i in range(n):
        f = math.exp(lf1 + (lf2-lf1)*(i+0.5)/n); df = f*(lf2-lf1)/n
        s += 10**(L(f)/10)*df
    return 2*s   # both sidebands, rad^2
floor = -230 + dBN + db(25e6)
vco = lambda f: -71 - 20*math.log10(f/1e4) if f < 2e6 else -128 - 20*math.log10(f/1e6)   # 6 GHz VCO: -71/10k, -101/100k, -128/1M
pll = lambda f: max(floor, vco(f)) if f > 80e3 else floor
tcxo = lambda f: dBN + (-110 - 20*math.log10(f/100) if f < 1e3 else max(-155, -130 - 20*math.log10(f/1e3)))   # TC32H4 example figures
vcxo_a = lambda f: tcxo(f) + 10     # a VCXO 10 dB worse than the TCXO (unspecified!)
vcxo_b = lambda f: tcxo(f) + 20
fL = 3e3   # Costas tracks below ~3 kHz
for nm, L in (("MAX2871 PLL+VCO (one)", pll), ("TCXO x232 in-band to 80k", lambda f: tcxo(f) if f < 80e3 else -200), ("VCXO x232 (TCXO+10 dB)", lambda f: vcxo_a(f) if f < 80e3 else -200), ("VCXO x232 (TCXO+20 dB)", lambda f: vcxo_b(f) if f < 80e3 else -200)):
    v = integ(L, fL, 100e6); print("  %-32s above %.0f kHz: %.2e rad^2 = %.1f mrad = %.2f deg rms" % (nm, fL/1e3, v, 1e3*math.sqrt(v), math.degrees(math.sqrt(v))))
tot_a = 2*integ(pll, fL, 1e8) + integ(lambda f: tcxo(f) if f<80e3 else -200, fL, 1e8) + integ(lambda f: vcxo_a(f) if f<80e3 else -200, fL, 1e8)
tot_b = tot_a - integ(lambda f: vcxo_a(f) if f<80e3 else -200, fL, 1e8) + integ(lambda f: vcxo_b(f) if f<80e3 else -200, fL, 1e8)
print("  TOTAL link phase jitter outside the Costas loop: %.2f deg (VCXO +10) .. %.2f deg (VCXO +20) rms" % (math.degrees(math.sqrt(tot_a)), math.degrees(math.sqrt(tot_b))))
for snr in (38.2, 22.6):
    s_th = 1/math.sqrt(10**(snr/10)); print("  thermal phase sigma at SNR %.1f dB: %.2f deg" % (snr, math.degrees(s_th)))
print("  LO self-mixing etc not included; 25 MHz PFD spur -88 dBc typ (50 kHz loop) -> at 80 kHz maybe -80 dBc")

print("\n== 2. Self-interference, own TX 600 MHz away")
pr10 = B['rx_in_dBm']; tx = B['tx_out_dBm']; Grf = B['G_rf_dB']; dsa = B['dsa_set_dB']
rej2 = lambda df: db(1+(df/390)**2) + db(1+(df/94.4)**2)
rej_bud = lambda df: 2*db(1+(df/100)**2)
for df in (100, 200, 600):
    print("  %4.0f MHz: budget 2 poles@100: %.1f dB; real poles 390 + 94: %.1f dB" % (df, rej_bud(df), rej2(df)))
for ip1, why in ((11.6, "budget's IP1dB (900 MHz row)"), (8.2, "datasheet 5800 MHz row")):
    for ngb, w2 in ((1, "budget formula, 1 gain block"), (2, "2 gain blocks as built")):
        comp = (ip1-10) - (13-2.4-dsa+ngb*14.3)
        print("  compression limit at RX port: %.1f dBm (%s; %s)" % (comp, why, w2))
for d, pr, lab in ((10, pr10, "10 m whips"), (300, B['rx_rows']['300 m 24 dBi'], "300 m panels"), (3000, B['rx_rows']['3000 m 24 dBi'], "3 km panels")):
    want = pr - 10 + rej2(600); comp = (8.2-10) - (13-2.4-dsa+28.6)
    print("  %-14s wanted %.1f dBm: leak must be < %.1f dBm (wanted-10+%.1f) and < %.1f (compression): isolation %.0f dB (budget says 42)" % (lab, pr, want, rej2(600), comp, tx - min(want, comp)))
lam = 3e8/5.8e9
for dm in (0.032, 0.3, 1.0, 3.0):
    iso = 20*math.log10(4*math.pi*dm/lam) - 4   # two 2 dBi whips, free space, no coupling
    print("  two whips %.2f m apart: ~%.0f dB (Friis) -> leak %.0f dBm at RX ANT (LNA P1dB -4, abs max +1)" % (dm, iso, tx-iso))
print("  LO leak back out of RX ANT: -47 (ADL5380 LO-RF) -1 balun -26.7 x2 (ADL5611 S12) -%.1f DSA -26 LNA S12 = %.0f dBm" % (2.4+dsa, -47-1-2*26.7-(2.4+dsa)-26))
print("  bench loopback with a 30 dB pad: %.1f dBm at RX ANT; DSA max 31.75 -> demod at %.1f dBm (IP1dB 8.2), arms +-%.0f mV" % (tx-30, tx-30+Grf-31.75, a*1e3*10**((tx-30+Grf-31.75+20)/20)))

print("\n== 3. Decision margins")
nf = B['noise_floor_dBm']
for d, g, cab, lab in ((10, 2, 0, "10 m whips"), (100, 2, 0, "100 m whips"), (100, 24, 10, "100 m panels+10 m cables"), (1000, 24, 10, "1 km panels+10 m cables"), (1000, 2, 0, "1 km whips")):
    pl = 20*math.log10(4*math.pi*d/lam); pr = tx + 2*g - 2*cab*0.5 - pl; snr = pr - nf
    sig = a/math.sqrt(10**(snr/10)); u = math.sqrt(2*math.log(2*183e6*3600))
    print("  %-26s RX %.1f dBm SNR %.1f dB; sigma %.1f mV (a=249 mV) ; CFAR window (1/h, 2 cmp) %.1f sigma = %.2f a; jitter sigma/slope ~ %.2f ns" % (lab, pr, snr, sig*1e3, u, u*sig/a, (u*sig/a)/(0.5/2.4) if u*sig/a < 0.9 else float('nan')))
print("  TLV3601: offset 5 mV max, hyst 3 typ/5 max, tpd 2.5 ns at 50 mV overdrive, +0.6 ns dispersion 10..125 mV; window on ONE leg sees a/2 = %.0f mV" % (a*1e3/2))
print("  slow path: idle I = 20 x 249 = %.1f V diff vs THS4541 swing 2.9 V: saturated; overdrive recovery 20 ns (datasheet) not in the 37 ns" % (20*a))

print("\n== 4. Power")
I = B['I_total_mA']; print("  %.2f A at 5 V = %.1f W; +5V_RF %.0f mA" % (I/1e3, I*5e-3, B['rails_mA']['RF']))
for nm, w, th in (("ADL5380", 0.245*5, 53), ("ADL5375", 0.203*5, 54), ("ADL5611 (each)", 0.124*5, 52), ("MAX2871 (each)", 0.2*3.3, 29), ("PLL LDO", 0.25, 187)):
    print("  %-16s %.2f W x %3d C/W = +%.0f C (junction %.0f C at 25 C ambient, %.0f C at 60 C box)" % (nm, w, th, w*th, 25+w*th, 60+w*th))
