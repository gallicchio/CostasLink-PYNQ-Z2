<!-- made by sim/link_rates.py; the plan and the chat copy these -->

**Range, 5 % wrong** (metres unless km; free space plus margin; the shorter of the noise limit and the comparator floor; '-' below 1 m)

| scenario | amplifier | path | BPSK | QPSK | FSK | OOK | whitened |
|---|---|---|---|---|---|---|---|
| lab: 2 dBi whips on the SMAs, no cables | board alone ($0) | fast | 72 m | 51 m | 72 m | 27 m | 72 m |
| lab: 2 dBi whips on the SMAs, no cables | board alone ($0) | slow | 569 m | 402 m | 308 m | 97 m | 622 m |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | 720 m | 510 m | 720 m | 267 m | 720 m |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | 5.7 km | 4.0 km | 3.1 km | 975 m | 6.2 km |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at its P1dB (+33) (compressed) | fast | 1.0 km | 733 m | 1.0 km | 384 m | 1.0 km |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at its P1dB (+33) (compressed) | slow | 8.2 km | 5.8 km | 4.4 km | 1.4 km | 8.9 km |
| lab: 2 dBi whips on the SMAs, no cables | 10 W amplifier (+40) ($300+) | fast | 2.3 km | 1.6 km | 2.3 km | 860 m | 2.3 km |
| lab: 2 dBi whips on the SMAs, no cables | 10 W amplifier (+40) ($300+) | slow | 18.3 km | 12.9 km | 9.9 km | 3.1 km | 20.0 km |
| campus: panels, 10 m cables, amplifiers at the board | board alone ($0) | fast | 5.7 km | 4.0 km | 3.8 km | 1.2 km | 5.7 km |
| campus: panels, 10 m cables, amplifiers at the board | board alone ($0) | slow | 25.4 km | 18.0 km | 13.8 km | 4.4 km | 27.8 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | 57.2 km | 40.5 km | 37.7 km | 11.9 km | 57.2 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | >100 km | >100 km | >100 km | 43.5 km | >100 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at its P1dB (+33) (compressed) | fast | 82.3 km | 58.2 km | 54.2 km | 17.1 km | 82.3 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at its P1dB (+33) (compressed) | slow | >100 km | >100 km | >100 km | 62.6 km | >100 km |
| campus: panels, 10 m cables, amplifiers at the board | 10 W amplifier (+40) ($300+) | fast | >100 km | >100 km | >100 km | 38.4 km | >100 km |
| campus: panels, 10 m cables, amplifiers at the board | 10 W amplifier (+40) ($300+) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| campus: panels, PA and LNA at the panel | board alone ($0) | fast | 18.1 km | 12.8 km | 18.1 km | 6.7 km | 18.1 km |
| campus: panels, PA and LNA at the panel | board alone ($0) | slow | >100 km | >100 km | 77.0 km | 24.4 km | >100 km |
| campus: panels, PA and LNA at the panel | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | >100 km | >100 km | >100 km | 66.7 km | >100 km |
| campus: panels, PA and LNA at the panel | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| campus: panels, PA and LNA at the panel | 2 W module at its P1dB (+33) (compressed) | fast | >100 km | >100 km | >100 km | 96.0 km | >100 km |
| campus: panels, PA and LNA at the panel | 2 W module at its P1dB (+33) (compressed) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| campus: panels, PA and LNA at the panel | 10 W amplifier (+40) ($300+) | fast | >100 km | >100 km | >100 km | >100 km | >100 km |
| campus: panels, PA and LNA at the panel | 10 W amplifier (+40) ($300+) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | board alone ($0) | fast | 72.0 km | 51.0 km | 72.0 km | 26.6 km | 72.0 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | board alone ($0) | slow | >100 km | >100 km | >100 km | 97.0 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 2 W module at its P1dB (+33) (compressed) | fast | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 2 W module at its P1dB (+33) (compressed) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 10 W amplifier (+40) ($300+) | fast | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 10 W amplifier (+40) ($300+) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |

**Range, 1 % wrong** (metres unless km; free space plus margin; the shorter of the noise limit and the comparator floor; '-' below 1 m)

| scenario | amplifier | path | BPSK | QPSK | FSK | OOK | whitened |
|---|---|---|---|---|---|---|---|
| lab: 2 dBi whips on the SMAs, no cables | board alone ($0) | fast | 72 m | 51 m | 65 m | 20 m | 72 m |
| lab: 2 dBi whips on the SMAs, no cables | board alone ($0) | slow | 402 m | 284 m | 236 m | 75 m | 488 m |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | 720 m | 510 m | 648 m | 205 m | 720 m |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | 4.0 km | 2.8 km | 2.4 km | 748 m | 4.9 km |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at its P1dB (+33) (compressed) | fast | 1.0 km | 733 m | 931 m | 295 m | 1.0 km |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at its P1dB (+33) (compressed) | slow | 5.8 km | 4.1 km | 3.4 km | 1.1 km | 7.0 km |
| lab: 2 dBi whips on the SMAs, no cables | 10 W amplifier (+40) ($300+) | fast | 2.3 km | 1.6 km | 2.1 km | 659 m | 2.3 km |
| lab: 2 dBi whips on the SMAs, no cables | 10 W amplifier (+40) ($300+) | slow | 12.9 km | 9.2 km | 7.6 km | 2.4 km | 15.7 km |
| campus: panels, 10 m cables, amplifiers at the board | board alone ($0) | fast | 4.9 km | 3.5 km | 2.9 km | 915 m | 5.7 km |
| campus: panels, 10 m cables, amplifiers at the board | board alone ($0) | slow | 18.0 km | 12.7 km | 10.6 km | 3.3 km | 21.8 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | 49.2 km | 34.8 km | 28.9 km | 9.1 km | 57.2 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | >100 km | >100 km | >100 km | 33.4 km | >100 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at its P1dB (+33) (compressed) | fast | 70.7 km | 50.0 km | 41.6 km | 13.2 km | 82.3 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at its P1dB (+33) (compressed) | slow | >100 km | >100 km | >100 km | 48.0 km | >100 km |
| campus: panels, 10 m cables, amplifiers at the board | 10 W amplifier (+40) ($300+) | fast | >100 km | >100 km | 93.1 km | 29.5 km | >100 km |
| campus: panels, 10 m cables, amplifiers at the board | 10 W amplifier (+40) ($300+) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| campus: panels, PA and LNA at the panel | board alone ($0) | fast | 18.1 km | 12.8 km | 16.2 km | 5.1 km | 18.1 km |
| campus: panels, PA and LNA at the panel | board alone ($0) | slow | >100 km | 71.0 km | 59.1 km | 18.7 km | >100 km |
| campus: panels, PA and LNA at the panel | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | >100 km | >100 km | >100 km | 51.2 km | >100 km |
| campus: panels, PA and LNA at the panel | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| campus: panels, PA and LNA at the panel | 2 W module at its P1dB (+33) (compressed) | fast | >100 km | >100 km | >100 km | 73.6 km | >100 km |
| campus: panels, PA and LNA at the panel | 2 W module at its P1dB (+33) (compressed) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| campus: panels, PA and LNA at the panel | 10 W amplifier (+40) ($300+) | fast | >100 km | >100 km | >100 km | >100 km | >100 km |
| campus: panels, PA and LNA at the panel | 10 W amplifier (+40) ($300+) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | board alone ($0) | fast | 72.0 km | 51.0 km | 64.4 km | 20.4 km | 72.0 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | board alone ($0) | slow | >100 km | >100 km | >100 km | 74.4 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 2 W module at its P1dB (+33) (compressed) | fast | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 2 W module at its P1dB (+33) (compressed) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 10 W amplifier (+40) ($300+) | fast | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 10 W amplifier (+40) ($300+) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |

**Range, quiet (1e-4)** (metres unless km; free space plus margin; the shorter of the noise limit and the comparator floor; '-' below 1 m)

| scenario | amplifier | path | BPSK | QPSK | FSK | OOK | whitened |
|---|---|---|---|---|---|---|---|
| lab: 2 dBi whips on the SMAs, no cables | board alone ($0) | fast | 69 m | 49 m | 44 m | 14 m | 72 m |
| lab: 2 dBi whips on the SMAs, no cables | board alone ($0) | slow | 251 m | 178 m | 160 m | 51 m | 332 m |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | 689 m | 487 m | 439 m | 139 m | 720 m |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | 2.5 km | 1.8 km | 1.6 km | 507 m | 3.3 km |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at its P1dB (+33) (compressed) | fast | 991 m | 701 m | 631 m | 200 m | 1.0 km |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at its P1dB (+33) (compressed) | slow | 3.6 km | 2.6 km | 2.3 km | 729 m | 4.8 km |
| lab: 2 dBi whips on the SMAs, no cables | 10 W amplifier (+40) ($300+) | fast | 2.2 km | 1.6 km | 1.4 km | 447 m | 2.3 km |
| lab: 2 dBi whips on the SMAs, no cables | 10 W amplifier (+40) ($300+) | slow | 8.1 km | 5.7 km | 5.2 km | 1.6 km | 10.7 km |
| campus: panels, 10 m cables, amplifiers at the board | board alone ($0) | fast | 3.1 km | 2.2 km | 2.0 km | 620 m | 4.1 km |
| campus: panels, 10 m cables, amplifiers at the board | board alone ($0) | slow | 11.2 km | 7.9 km | 7.2 km | 2.3 km | 14.8 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | 30.8 km | 21.8 km | 19.6 km | 6.2 km | 40.6 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | >100 km | 79.4 km | 71.6 km | 22.6 km | >100 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at its P1dB (+33) (compressed) | fast | 44.3 km | 31.3 km | 28.2 km | 8.9 km | 58.4 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at its P1dB (+33) (compressed) | slow | >100 km | >100 km | >100 km | 32.6 km | >100 km |
| campus: panels, 10 m cables, amplifiers at the board | 10 W amplifier (+40) ($300+) | fast | 99.1 km | 70.1 km | 63.1 km | 20.0 km | >100 km |
| campus: panels, 10 m cables, amplifiers at the board | 10 W amplifier (+40) ($300+) | slow | >100 km | >100 km | >100 km | 72.9 km | >100 km |
| campus: panels, PA and LNA at the panel | board alone ($0) | fast | 17.2 km | 12.2 km | 11.0 km | 3.5 km | 18.1 km |
| campus: panels, PA and LNA at the panel | board alone ($0) | slow | 62.9 km | 44.4 km | 40.0 km | 12.7 km | 82.9 km |
| campus: panels, PA and LNA at the panel | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | >100 km | >100 km | >100 km | 34.7 km | >100 km |
| campus: panels, PA and LNA at the panel | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| campus: panels, PA and LNA at the panel | 2 W module at its P1dB (+33) (compressed) | fast | >100 km | >100 km | >100 km | 49.9 km | >100 km |
| campus: panels, PA and LNA at the panel | 2 W module at its P1dB (+33) (compressed) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| campus: panels, PA and LNA at the panel | 10 W amplifier (+40) ($300+) | fast | >100 km | >100 km | >100 km | >100 km | >100 km |
| campus: panels, PA and LNA at the panel | 10 W amplifier (+40) ($300+) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | board alone ($0) | fast | 68.5 km | 48.5 km | 43.7 km | 13.8 km | 72.0 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | board alone ($0) | slow | >100 km | >100 km | >100 km | 50.4 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 2 W module at its P1dB (+33) (compressed) | fast | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 2 W module at its P1dB (+33) (compressed) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 10 W amplifier (+40) ($300+) | fast | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 10 W amplifier (+40) ($300+) | slow | >100 km | >100 km | >100 km | >100 km | >100 km |

