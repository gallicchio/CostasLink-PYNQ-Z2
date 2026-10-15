# CostasLink-PYNQ-Z2 rev A: what the first order costs

Written by `mfg/cost_estimate.py` on 2026-10-14 for 5 bare boards, 2 of them assembled by JLCPCB on the top (Standard PCBA for the through-hole SMAs and headers; the 2x20 socket on the back is soldered at home).  Parts: JLCPCB's parts API at the times in the table.  Fees: the ECP5-2ADC-2DAC cart of 2026-10-09 (CLAUDE_PCB.md section 8).  The bare boards and the shipping are estimates with a range; the cart replaces them.

## The three buckets

| where | what | cost |
|---|---|--:|
| **JLCPCB** | 5 bare boards 120 x 100 mm, 4 layers, ENIG: model $28.50-$65.26 | $46.88 |
| | assembly: setup $25.75, stencils $8.27, fixture $16.54, feeder loading 52 Extended codes x $2.70 = $140.40, SMT 1102 pads x 2 boards, through-hole 93 joints x 2, packaging, confirmation, depanel | $208.24 |
| | their parts: 80 BOM lines, 386 placements a board, with attrition, x 1.0066 | $425.34 |
| | US duty, 35 % of the above, collected under DDP | $238.16 |
| | shipping, UPS Express Saver DDP | $25.00-$40.00 |
| | **JLCPCB total** | **$943.62-$958.62** |
| **Digi-Key** | nothing consigned: every part is on JLCPCB's shelf (the ADI chips' fallback below is unused) | **$0.00** |
| | shipping the consignment to JLCPCB (USPS Priority International to FedEx) | $0.00-$0.00 |
| **other** | the bench and the field (table below) | **$141.50-$271.00** |
| | **everything** | **$1085.12-$1229.62** |

## Digi-Key: the consigned parts

None.  The balun is the TDK HHM1907B1 from JLCPCB's shelf (Prompt 31; the Johanson 5400 the ADL5380's sheet uses has 0 there), and the two ADI chips are bought from their shelf while it covers the order.

**The ADI chips' fallback** (gen/parts.py consign=): ADL5380 C579152, JLCPCB 18 at $21.62 (1-9), its parts API 2026-10-14; ADL5375 C579150, JLCPCB 4 at $16.40 (1-9), its parts API 2026-10-14.  If either shelf cannot cover the order on the day, that line is consigned (CONSIGNMENT.md then says what to buy).  What that costs, Jason's way of counting it (Prompt 31): consigning both means 8 pieces at Digi-Key, 4 of them spares that are never used, plus tax, Digi-Key's shipping and the shipment to Shenzhen: $197.26-$222.26 against $76.04 on JLCPCB's shelf for the 4 pieces the boards need; so the shelf wins by $121.22-$146.22 for 2 boards, and a shelf part is worth buying up to that much dearer than Digi-Key's price.  With more boards assembled the spares and the shipment are spread thinner.

## Other: the bench and the field

| item | low | high |
|---|--:|--:|
| SMA attenuators: 30 dB (loopback), 20 dB x 2 (in front of the PA modules) | $30.00 | $50.00 |
| U.FL-to-SMA pigtails, 10 | $12.00 | $18.00 |
| MMCX-to-SMA leads, 5 (REF OUT and the four MMCX monitors: ERR, VC, TRIG IN, I SLOW; Response 10) | $12.50 | $20.00 |
| 5.8 GHz whips, SMA, x 4 | $16.00 | $24.00 |
| SMA leads: 3 x 150 mm, 2 x 1 m; 50 ohm terminations x 2 | $20.00 | $35.00 |
| USB-C PD power banks 5 V / 3 A x 2 (the amplifiers in the field) | $40.00 | $60.00 |
| M3 standoffs and screws (nylon kit) | $6.00 | $10.00 |
| a heatsink or fan for the 2 W PA module (it dissipates about 9 W) | $5.00 | $12.00 |
| a second PA ($29 with shipping) and LNA ($13) module for the far end, when the tests demand | $0.00 | $42.00 |

## What to look at

- **C17271830 HMC536MS8G**: 5 in stock against 2 for this order
- **C579150 ADL5375-05ACPZ-R7**: 4 in stock against 2 for this order
- **C650158 AD5696RARUZ**: 2 in stock against 2 for this order
- Feeder loading is the largest assembly fee after the setup: 52 Extended codes x $2.70 = $140.40.  Every value merged saves $2.70.
- Hand-soldering the 2x20 socket (J302, alone on the back) makes the order one-sided: half the setup and the stencil, its feeder and joints, about $38 before duty.  Economic PCBA would not take the through-hole SMAs and headers, so Standard it stays.

## Parts (80 BOM lines)

| LCSC | part | a board | ordered | library | unit | line | stock | asked |
|---|---|--:|--:|---|--:|--:|--:|---|
| C2058382 | THS4541IRGTT (THS4541) | 4 | 8 | Extended | $7.1371 | $57.10 | 318 | 2026-10-14 17:50 |
| C650158 | AD5696RARUZ (AD5696R) | 1 | 2 | Extended | $22.2757 | $44.55 | 2 | 2026-10-14 17:51 |
| C579152 | ADL5380ACPZ-R7 (ADL5380) | 1 | 2 | Extended | $21.6216 | $43.24 | 18 | 2026-10-14 17:51 |
| C7458627 | MAX2871ETJ+T (MAX2871) | 2 | 4 | Extended | $9.9430 | $39.77 | 3,135 | 2026-10-14 17:51 |
| C208262 | ADL5611ARKZ-R7 (ADL5611) | 3 | 6 | Extended | $5.9821 | $35.89 | 3,007 | 2026-10-14 17:50 |
| C579150 | ADL5375-05ACPZ-R7 (ADL5375-05) | 1 | 2 | Extended | $16.4030 | $32.81 | 4 | 2026-10-14 17:51 |
| C5213955 | TLV3603DCKR (TLV3603) | 4 | 8 | Extended | $4.0000 | $32.00 | 2,899 | 2026-10-14 17:51 |
| C17271830 | HMC536MS8G (HMC536) | 1 | 2 | Extended | $11.5580 | $23.12 | 5 | 2026-10-14 17:50 |
| C42711 | AD8310ARMZ-REEL7 (AD8310) | 1 | 2 | Extended | $10.0849 | $20.17 | 2,738 | 2026-10-14 17:50 |
| C2974371 | TLV3601DCKR (TLV3601) | 4 | 8 | Extended | $2.2007 | $17.61 | 2,994 | 2026-10-14 17:50 |
| C2059281 | OPA2388IDGKR (OPA2388) | 2 | 4 | Extended | $2.2921 | $9.17 | 1,653 | 2026-10-14 17:50 |
| C470929 | PE43711B-Z (PE43711) | 1 | 2 | Extended | $3.7488 | $7.50 | 1,830 | 2026-10-14 17:51 |
| C496551 | BWSMA-KWE-Z001 (RX ANT/TX ANT/REF IN) | 9 | 18 | Extended | $0.4111 | $7.40 | 145,159 | 2026-10-14 17:51 |
| C627342 | MCP4728A1T-E/UN (MCP4728A1 0x61) | 1 | 2 | Extended | $2.9968 | $5.99 | 50 | 2026-10-14 17:51 |
| C478093 | MCP4728T-E/UN (MCP4728) | 1 | 2 | Extended | $2.6248 | $5.25 | 20,828 | 2026-10-14 17:51 |
| C37593 | ADS1115IDGSR (ADS1115) | 2 | 4 | Extended | $1.2235 | $4.89 | 19,913 | 2026-10-14 17:50 |
| C5137198 | BWMMCX-KE (ERR MON/VC MON/REF O) | 5 | 10 | Extended | $0.4536 | $4.54 | 21,212 | 2026-10-14 17:51 |
| C5119013 | TC32H4-25.000-33GNDTNL (TCXO 25MHz) | 1 | 2 | Extended | $1.5710 | $3.14 | 447 | 2026-10-14 17:51 |
| C5179998 | SX3V25.000B20100F30TNN (VCXO 25MHz) | 1 | 2 | Extended | $1.5058 | $3.01 | 413 | 2026-10-14 17:51 |
| C88374 | U.FL-R-SMT-1(80) (RX MON/CMP I MON/I M) | 12 | 26 | Extended | $0.1138 | $2.96 | 97,810 | 2026-10-14 17:51 |
| C15850 | CL21A106KAYNNNE (10uF) | 10 | 30 | Basic | $0.0689 | $2.07 | 3,794,192 | 2026-10-14 17:50 |
| C210262 | SKY65404-31 (SKY65404-31) | 1 | 2 | Extended | $0.9005 | $1.80 | 1,005 | 2026-10-14 17:50 |
| C882469 | LQW15AN27NG80D (27nH) | 8 | 20 | Extended | $0.0899 | $1.80 | 19,352 | 2026-10-14 17:51 |
| C2862740 | TPS7A2033PDBVR (TPS7A2033) | 4 | 8 | Extended | $0.2105 | $1.68 | 171,932 | 2026-10-14 17:50 |
| C45783 | CL21A226MAQNNNE (22uF) | 3 | 6 | Basic | $0.2372 | $1.42 | 3,398,815 | 2026-10-14 17:50 |
| C15127 | AO3401A (AO3401A) | 2 | 8 | Basic | $0.1020 | $0.82 | 604,027 | 2026-10-14 17:49 |
| C46388 | TS5A3159DCKR (TS5A3159) | 1 | 2 | Extended | $0.3759 | $0.75 | 32,989 | 2026-10-14 17:50 |
| C82919 | LQW15AN6N8G00D (6.8nH) | 3 | 10 | Extended | $0.0728 | $0.73 | 22,287 | 2026-10-14 17:51 |
| C8207 | SN74LVC1G04DCKR (74LVC1G04) | 2 | 8 | Extended | $0.0854 | $0.68 | 79,508 | 2026-10-14 17:51 |
| C14461 | SN74LVC2G34DCKR (74LVC2G34) | 1 | 4 | Extended | $0.1594 | $0.64 | 22,158 | 2026-10-14 17:49 |
| C1525 | CL05B104KO5NNNC (100nF) | 68 | 146 | Basic | $0.0043 | $0.63 | 22,938,019 | 2026-10-14 17:49 |
| C170182 | 1206N104J500CT (100nF) | 1 | 4 | Extended | $0.1554 | $0.62 | 171,346 | 2026-10-14 17:50 |
| C10425 | SN74LVC1G17DCKR (74LVC1G17) | 2 | 8 | Extended | $0.0700 | $0.56 | 96,989 | 2026-10-14 17:49 |
| C23380874 | LP5907MFX-3.3 (LP5907 3.3V) | 1 | 4 | Extended | $0.1351 | $0.54 | 1,168 | 2026-10-14 17:50 |
| C113126 | LQW18AN43NG00D (43nH) | 3 | 10 | Extended | $0.0536 | $0.54 | 27,503 | 2026-10-14 17:49 |
| C210837 | MF-MSMF200-2 (2A PTC) | 2 | 8 | Extended | $0.0648 | $0.52 | 14,375 | 2026-10-14 17:50 |
| C23630 | CL10A225KO8NNNC (2.2uF) | 8 | 26 | Basic | $0.0182 | $0.47 | 3,565,234 | 2026-10-14 17:50 |
| C38663 | SN74LVC1G3157DCKR (74LVC1G3157) | 1 | 6 | Extended | $0.0746 | $0.45 | 233,880 | 2026-10-14 17:50 |
| C531388 | HHM1907B1 (HHM1907B1) | 1 | 4 | Extended | $0.1031 | $0.41 | 7,884 | 2026-10-14 17:51 |
| C19270534 | 1010100506TR (100uF) | 1 | 3 | Extended | $0.1366 | $0.41 | 4,081 | 2026-10-14 17:50 |
| C165948 | TYPE-C-31-M-12 (USB-C 5V) | 1 | 2 | Extended | $0.1863 | $0.37 | 383,021 | 2026-10-14 17:50 |
| C144499 | AC1206FR-072R2L (2.2R) | 2 | 14 | Extended | $0.0265 | $0.37 | 92,140 | 2026-10-14 17:49 |
| C85840 | BLM21PG221SN1D (220R@100MHz 2A) | 1 | 10 | Extended | $0.0345 | $0.35 | 173,367 | 2026-10-14 17:51 |
| C52923 | CL05A105KA5NQNC (1uF) | 15 | 40 | Basic | $0.0081 | $0.32 | 7,603,722 | 2026-10-14 17:51 |
| C13564 | NCP18XH103F03RB (NTC 10k) | 1 | 6 | Extended | $0.0465 | $0.28 | 169,617 | 2026-10-14 17:49 |
| C162241 | GRM1885C1H682JA01D (6.8nF) | 2 | 12 | Extended | $0.0222 | $0.27 | 98,581 | 2026-10-14 17:50 |
| C1552 | 0402CG1R5C500NT (1.5pF) | 24 | 58 | Preferred | $0.0045 | $0.26 | 214,291 | 2026-10-14 17:49 |
| C113952 | SMAJ5.0A (SMAJ5.0A) | 1 | 6 | Extended | $0.0412 | $0.25 | 546,066 | 2026-10-14 17:49 |
| C11702 | 0402WGF1001TCE (1k) | 29 | 68 | Basic | $0.0035 | $0.24 | 7,650,948 | 2026-10-14 17:49 |
| C2937625 | PZ254V-11-03P (SIGN/SEL/REF/TR) | 5 | 12 | Extended | $0.0198 | $0.24 | 947,219 | 2026-10-14 17:50 |
| C25744 | 0402WGF1002TCE (10k) | 30 | 70 | Basic | $0.0033 | $0.23 | 21,805,567 | 2026-10-14 17:50 |
| C2188753 | GCM1555C1H161JA16D (160pF) | 2 | 14 | Extended | $0.0123 | $0.17 | 8,857 | 2026-10-14 17:50 |
| C81598 | 1N4148W (1N4148W) | 1 | 12 | Basic | $0.0124 | $0.15 | 4,681,411 | 2026-10-14 17:51 |
| C14441 | CL05C680JB5NNNC (68pF) | 3 | 18 | Preferred | $0.0081 | $0.15 | 118,848 | 2026-10-14 17:49 |
| C8545 | 2N7002 (2N7002) | 1 | 7 | Basic | $0.0175 | $0.12 | 1,860,970 | 2026-10-14 17:51 |
| C2286 | KT-0603R (5V/3V3) | 2 | 14 | Basic | $0.0076 | $0.11 | 7,930,344 | 2026-10-14 17:50 |
| C95042 | MLG1005S0N6CT000 (0.6nH) | 1 | 12 | Extended | $0.0076 | $0.09 | 18,750 | 2026-10-14 17:51 |
| C282239 | CC0402JRNPO9BN391 (390pF) | 3 | 16 | Extended | $0.0050 | $0.08 | 15,848 | 2026-10-14 17:50 |
| C285052 | 0402CG0R5B500NT (0.5pF) | 1 | 12 | Extended | $0.0065 | $0.08 | 58,998 | 2026-10-14 17:50 |
| C492401 | PZ254V-11-02P (HDR 5V/50R) | 2 | 4 | Extended | $0.0186 | $0.07 | 1,128,882 | 2026-10-14 17:51 |
| C1523 | 0402B102K500NT (1nF) | 4 | 18 | Basic | $0.0041 | $0.07 | 3,194,166 | 2026-10-14 17:49 |
| C15195 | CL05B103KB5NNNC (10nF) | 3 | 16 | Basic | $0.0041 | $0.07 | 6,380,879 | 2026-10-14 17:49 |
| C1562 | 0402CG330J500NT (33pF) | 4 | 18 | Basic | $0.0032 | $0.06 | 1,397,535 | 2026-10-14 17:50 |
| C25741 | 0402WGF1003TCE (100k) | 14 | 38 | Basic | $0.0015 | $0.06 | 9,806,404 | 2026-10-14 17:50 |
| C25120 | 0402WGF499JTCE (49.9R) | 5 | 20 | Basic | $0.0023 | $0.05 | 1,308,224 | 2026-10-14 17:50 |
| C25905 | 0402WGF5101TCE (5.1k) | 4 | 18 | Basic | $0.0024 | $0.04 | 5,363,934 | 2026-10-14 17:50 |
| C25105 | 0402WGF330JTCE (33R) | 11 | 32 | Basic | $0.0012 | $0.04 | 1,465,441 | 2026-10-14 17:50 |
| C137968 | RC0402FR-074K02L (4.02k) | 4 | 18 | Extended | $0.0021 | $0.04 | 332,812 | 2026-10-14 17:49 |
| C1546 | 0402CG101J500NT (100pF) | 1 | 12 | Basic | $0.0031 | $0.04 | 4,005,966 | 2026-10-14 17:49 |
| C4109 | 0402WGF2001TCE (2k) | 2 | 14 | Basic | $0.0026 | $0.04 | 7,820,560 | 2026-10-14 17:50 |
| C25102 | 0402WGF3000TCE (300R) | 2 | 14 | Preferred | $0.0021 | $0.03 | 793,813 | 2026-10-14 17:50 |
| C25900 | 0402WGF4701TCE (4.7k) | 1 | 12 | Basic | $0.0023 | $0.03 | 16,311,193 | 2026-10-14 17:50 |
| C5126227 | FRC0402F4530TS (453R) | 6 | 22 | Extended | $0.0012 | $0.03 | 73,865 | 2026-10-14 17:51 |
| C25135 | 0402WGF8200TCE (820R) | 2 | 14 | Extended | $0.0018 | $0.03 | 117,640 | 2026-10-14 17:50 |
| C474132 | 0402WGF4704TCE (4.7M) | 1 | 12 | Extended | $0.0020 | $0.02 | 42,390 | 2026-10-14 17:51 |
| C25765 | 0402WGF2002TCE (20k) | 4 | 18 | Basic | $0.0013 | $0.02 | 2,439,179 | 2026-10-14 17:50 |
| C25076 | 0402WGF1000TCE (100R) | 4 | 18 | Basic | $0.0012 | $0.02 | 8,387,472 | 2026-10-14 17:50 |
| C25879 | 0402WGF2201TCE (2.2k) | 4 | 18 | Basic | $0.0011 | $0.02 | 2,066,399 | 2026-10-14 17:50 |
| C25132 | 0402WGF7500TCE (750R) | 2 | 14 | Extended | $0.0012 | $0.02 | 937,171 | 2026-10-14 17:50 |
| C17168 | 0402WGF0000TCE (0R) | 1 | 12 | Basic | $0.0011 | $0.01 | 9,438,644 | 2026-10-14 17:50 |
