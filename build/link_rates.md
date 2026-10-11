<!-- made by sim/link_rates.py; the plan and the chat copy these -->

**Range, 5 % wrong** (metres unless km; free space plus margin; the shorter of the noise limit and the comparator floor; '-' below 1 m)

| scenario | amplifier | path | BPSK | QPSK | FSK | OOK | whitened |
|---|---|---|---|---|---|---|---|
| lab: 2 dBi whips on the SMAs, no cables | board alone ($0) | fast | 72 m | 51 m | 72 m | 28 m | 72 m |
| lab: 2 dBi whips on the SMAs, no cables | board alone ($0) | slow | 599 m | 424 m | 325 m | 103 m | 655 m |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | 720 m | 510 m | 720 m | 281 m | 720 m |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | 6.0 km | 4.2 km | 3.2 km | 1.0 km | 6.6 km |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at its P1dB (+33) (compressed) | fast | 1.0 km | 733 m | 1.0 km | 405 m | 1.0 km |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at its P1dB (+33) (compressed) | slow | 8.6 km | 6.1 km | 4.7 km | 1.5 km | 9.4 km |
| lab: 2 dBi whips on the SMAs, no cables | 10 W amplifier (+40) ($300+) | fast | 2.3 km | 1.6 km | 2.3 km | 906 m | 2.3 km |
| lab: 2 dBi whips on the SMAs, no cables | 10 W amplifier (+40) ($300+) | slow | 19.3 km | 13.6 km | 10.5 km | 3.3 km | 21.1 km |
| campus: panels, 10 m cables, amplifiers at the board | board alone ($0) | fast | 5.7 km | 4.0 km | 4.0 km | 1.3 km | 5.7 km |
| campus: panels, 10 m cables, amplifiers at the board | board alone ($0) | slow | 26.8 km | 18.9 km | 14.5 km | 4.6 km | 29.3 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | 57.2 km | 40.5 km | 39.7 km | 12.6 km | 57.2 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | >100 km | >100 km | >100 km | 45.9 km | >100 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at its P1dB (+33) (compressed) | fast | 82.3 km | 58.2 km | 57.2 km | 18.1 km | 82.3 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at its P1dB (+33) (compressed) | slow | >100 km | >100 km | >100 km | 66.0 km | >100 km |
| campus: panels, 10 m cables, amplifiers at the board | 10 W amplifier (+40) ($300+) | fast | >100 km | >100 km | >100 km | 40.5 km | >100 km |
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
| lab: 2 dBi whips on the SMAs, no cables | board alone ($0) | fast | 72 m | 51 m | 68 m | 22 m | 72 m |
| lab: 2 dBi whips on the SMAs, no cables | board alone ($0) | slow | 424 m | 300 m | 249 m | 79 m | 514 m |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | 720 m | 510 m | 682 m | 216 m | 720 m |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | 4.2 km | 3.0 km | 2.5 km | 788 m | 5.1 km |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at its P1dB (+33) (compressed) | fast | 1.0 km | 733 m | 982 m | 310 m | 1.0 km |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at its P1dB (+33) (compressed) | slow | 6.1 km | 4.3 km | 3.6 km | 1.1 km | 7.4 km |
| lab: 2 dBi whips on the SMAs, no cables | 10 W amplifier (+40) ($300+) | fast | 2.3 km | 1.6 km | 2.2 km | 695 m | 2.3 km |
| lab: 2 dBi whips on the SMAs, no cables | 10 W amplifier (+40) ($300+) | slow | 13.6 km | 9.6 km | 8.0 km | 2.5 km | 16.5 km |
| campus: panels, 10 m cables, amplifiers at the board | board alone ($0) | fast | 5.2 km | 3.7 km | 3.0 km | 964 m | 5.7 km |
| campus: panels, 10 m cables, amplifiers at the board | board alone ($0) | slow | 18.9 km | 13.4 km | 11.1 km | 3.5 km | 23.0 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | 51.8 km | 36.7 km | 30.5 km | 9.6 km | 57.2 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | >100 km | >100 km | >100 km | 35.2 km | >100 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at its P1dB (+33) (compressed) | fast | 74.6 km | 52.7 km | 43.8 km | 13.9 km | 82.3 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at its P1dB (+33) (compressed) | slow | >100 km | >100 km | >100 km | 50.6 km | >100 km |
| campus: panels, 10 m cables, amplifiers at the board | 10 W amplifier (+40) ($300+) | fast | >100 km | >100 km | 98.2 km | 31.0 km | >100 km |
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
| lab: 2 dBi whips on the SMAs, no cables | board alone ($0) | fast | 72 m | 51 m | 46 m | 15 m | 72 m |
| lab: 2 dBi whips on the SMAs, no cables | board alone ($0) | slow | 265 m | 187 m | 169 m | 53 m | 350 m |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | 720 m | 510 m | 462 m | 146 m | 720 m |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | 2.7 km | 1.9 km | 1.7 km | 534 m | 3.5 km |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at its P1dB (+33) (compressed) | fast | 1.0 km | 733 m | 665 m | 210 m | 1.0 km |
| lab: 2 dBi whips on the SMAs, no cables | 2 W module at its P1dB (+33) (compressed) | slow | 3.8 km | 2.7 km | 2.4 km | 768 m | 5.0 km |
| lab: 2 dBi whips on the SMAs, no cables | 10 W amplifier (+40) ($300+) | fast | 2.3 km | 1.6 km | 1.5 km | 471 m | 2.3 km |
| lab: 2 dBi whips on the SMAs, no cables | 10 W amplifier (+40) ($300+) | slow | 8.5 km | 6.0 km | 5.4 km | 1.7 km | 11.3 km |
| campus: panels, 10 m cables, amplifiers at the board | board alone ($0) | fast | 3.2 km | 2.3 km | 2.1 km | 653 m | 4.3 km |
| campus: panels, 10 m cables, amplifiers at the board | board alone ($0) | slow | 11.8 km | 8.4 km | 7.5 km | 2.4 km | 15.6 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at +30 dBm (20 dB pad) ($29, owned) | fast | 32.4 km | 22.9 km | 20.7 km | 6.5 km | 42.8 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at +30 dBm (20 dB pad) ($29, owned) | slow | >100 km | 83.7 km | 75.4 km | 23.9 km | >100 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at its P1dB (+33) (compressed) | fast | 46.6 km | 33.0 km | 29.7 km | 9.4 km | 61.5 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W module at its P1dB (+33) (compressed) | slow | >100 km | >100 km | >100 km | 34.3 km | >100 km |
| campus: panels, 10 m cables, amplifiers at the board | 10 W amplifier (+40) ($300+) | fast | >100 km | 73.8 km | 66.5 km | 21.0 km | >100 km |
| campus: panels, 10 m cables, amplifiers at the board | 10 W amplifier (+40) ($300+) | slow | >100 km | >100 km | >100 km | 76.8 km | >100 km |
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

