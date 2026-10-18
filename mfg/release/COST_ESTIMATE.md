# CostasLink-PYNQ-Z2 rev A: cost estimate

Written by `mfg/make_release.py` on 2026-10-17.  Parts: JLCPCB's live prices and stock (their parts API, asked at the times in the table), with their attrition and minimum purchase, x 1.0066 as the cart charges.  Fees: JLCPCB's cart on the ECP5-2ADC-2DAC order of 2026-10-09 (`mfg/cost_estimate.py` FEES, CLAUDE_PCB.md section 8).  The bare boards: a model with a range until the cart gives the number.

**The order:** 5 bare boards of 120.0 x 100.0 mm, 4 layers, 1.6 mm, green, ENIG, JLC04161H-7628; **2 of them assembled on one side** (Standard PCBA), J302 soldered at home (hand_solder_bom.csv: the part to order loose, and the jumper shunts); nothing consigned: every part from JLCPCB's shelf (CONSIGNMENT.md).

## The three buckets

| where | what | cost |
|---|---|--:|
| **JLCPCB** | 5 bare boards: ESTIMATE, $28.50-$65.26: GPiBridge's cart (2026-10-06, 4 layers, ENIG: $24.80 for 5 boards of 15.3 cm2) for the fixed part, plus 600 cm2 at $70.6-350 per m2 (JLCPCB's published 4-layer board charge, and five times it for a small order), plus $0-20 for ENIG; the cart's number replaces it | $46.88 |
| | confirm production file | $1.05 |
| | Standard PCBA setup, one side | $25.75 |
| | stencil, one side | $8.27 |
| | PCB assembly fixture | $16.54 |
| | feeder loading, 53 Extended codes x $2.70 (Basic and Preferred parts are free; the 0 consigned lines may be charged the same) | $143.10 |
| | SMT, 1164 pads a board x $0.0017 + $1.50 a board, x 2 | $6.96 |
| | through-hole: $3.61 labour an order + 102 joints a board (25 parts) x 2 x $0.0157 | $6.81 |
| | packaging | $0.51 |
| | special components | $0.12 |
| | depanel: JLCPCB's assembly rails taken off before delivery (the ECP5 cart's $2.32) | $2.32 |
| | their parts: 81 BOM lines, 415 placements a board, for 2 boards with attrition, x 1.0066 | $430.59 |
| | **goods before duty and shipping** | **$688.89** |
| | US duty, 35 % of the goods, collected under DDP | $241.11 |
| | shipping, UPS Express Saver DDP | $25.00-$40.00 |
| | **JLCPCB total** | **$955.01-$970.01** |
| **Digi-Key** | nothing consigned (CONSIGNMENT.md): every part is on JLCPCB's shelf | **$0.00** |
| | shipping a consignment to JLCPCB | $0.00-$0.00 |
| **other** | the bench and the field (mfg/cost_estimate.py's list) | **$141.50-$271.00** |
| | **everything** | **$1096.51-$1241.01** |

An assembled board: about $344.45 of the JLCPCB goods.  The range on the bare boards moves the goods from $670.51 to $707.28.

## Per-part fees: Basic, Preferred, Extended

| library | distinct parts | placements a board |
|---|--:|--:|
| Basic | 25 | 244 |
| Preferred | 3 | 28 |
| **Extended** | **53** | 143 |
| consigned | 0 | 0 |

Feeder loading is the largest assembly fee after the setup: 53 Extended codes x $2.70 = $143.10.  Every value merged into another saves $2.70.

The 53 distinct Extended parts: C10425 (SN74LVC1G17DCKR), C113126 (LQW18AN43NG00D), C113952 (SMAJ5.0A), C13564 (NCP18XH103F03RB), C137968 (RC0402FR-074K02L), C144499 (AC1206FR-072R2L), C14461 (SN74LVC2G34DCKR), C162241 (GRM1885C1H682JA01D), C165948 (TYPE-C-31-M-12), C170182 (1206N104J500CT), C17271830 (HMC536MS8G), C19270534 (1010100506TR), C2058382 (THS4541IRGTT), C2059281 (OPA2388IDGKR), C208262 (ADL5611ARKZ-R7), C210262 (SKY65404-31), C210837 (MF-MSMF200-2), C2188753 (GCM1555C1H161JA16D), C23380874 (LP5907MFX-3.3), C25107 (0402WGF3480TCE), C25132 (0402WGF7500TCE), C25135 (0402WGF8200TCE), C282239 (CC0402JRNPO9BN391), C285052 (0402CG0R5B500NT), C2862740 (TPS7A2033PDBVR), C2937625 (PZ254V-11-03P), C2974371 (TLV3601DCKR), C37593 (ADS1115IDGSR), C38663 (SN74LVC1G3157DCKR), C42711 (AD8310ARMZ-REEL7), C46388 (TS5A3159DCKR), C470929 (PE43711B-Z), C474132 (0402WGF4704TCE), C478093 (MCP4728T-E/UN), C492401 (PZ254V-11-02P), C496551 (BWSMA-KWE-Z001), C5119013 (TC32H4-25.000-33GNDTNL), C5126227 (FRC0402F4530TS), C5137198 (BWMMCX-KE), C5179998 (SX3V25.000B20100F30TNN), C5213955 (TLV3603DCKR), C531388 (HHM1907B1), C579150 (ADL5375-05ACPZ-R7), C579152 (ADL5380ACPZ-R7), C627342 (MCP4728A1T-E/UN), C650158 (AD5696RARUZ), C7458627 (MAX2871ETJ+T), C8207 (SN74LVC1G04DCKR), C82919 (LQW15AN6N8G00D), C85840 (BLM21PG221SN1D), C882469 (LQW15AN27NG80D), C88374 (U.FL-R-SMT-1(80)), C95042 (MLG1005S0N6CT000).

## What to look at

- The bare boards are the least certain line ($28.50 to $65.26): read the price off JLCPCB's cart
- **C2058382 THS4541IRGTT** costs $57.14 for the order (8 x $7.14)
- **C650158 AD5696RARUZ** costs $44.58 for the order (2 x $22.29)
- **C579152 ADL5380ACPZ-R7** costs $43.27 for the order (2 x $21.64)
- **C7458627 MAX2871ETJ+T** costs $39.80 for the order (4 x $9.95)
- **C208262 ADL5611ARKZ-R7** costs $35.92 for the order (6 x $5.99)
- **C579150 ADL5375-05ACPZ-R7** costs $32.81 for the order (2 x $16.41)
- **C579152 ADL5380ACPZ-R7**: 18 in stock against 2 for this order: order soon, or it may run out
- **C17271830 HMC536MS8G**: 5 in stock against 2 for this order: order soon, or it may run out
- **C650158 AD5696RARUZ**: 2 in stock against 2 for this order: order soon, or it may run out
- **The fallback** (gen/parts.py consign=): ADL5380 C579152: JLCPCB 18 in stock at $21.64; ADL5375 C579150: JLCPCB 654 in stock at $16.41.  Each is bought from JLCPCB's shelf while the shelf covers the order; if it is short on the day, mfg/make_release.py consigns that line and this file says what to buy.  Consigning both would mean 8 pieces at Digi-Key, 4 of them the spares JLCPCB asks for as attrition and never used, plus tax, Digi-Key's shipping and the shipment to Shenzhen: $197.26-$222.26 against $76.04 on the shelf for the 4 pieces the boards need.  So for 2 boards a shelf part up to $121.22-$146.22 dearer than Digi-Key's price is still the cheaper buy, and with more boards the spares and the shipment are spread thinner (CLAUDE_PCB.md section 3).
- Not in the total: baking the moisture-sensitive parts (the QFNs are MSL 3; about $7.50 if ticked), shipping, and duty beyond the 35 %

## Parts (81 BOM lines; the consigned ones at the end)

| LCSC | part | a board | ordered | library | unit | line | stock | left after | asked |
|---|---|--:|--:|---|--:|--:|--:|--:|---|
| C2058382 | THS4541IRGTT (THS4541) | 4 | 8 | Extended | $7.1423 | $57.14 | 262 | 254 | 2026-10-17 17:15 |
| C650158 | AD5696RARUZ (AD5696R) | 1 | 2 | Extended | $22.2921 | $44.58 | 2 | 0 | 2026-10-17 17:15 |
| C579152 | ADL5380ACPZ-R7 (ADL5380) | 1 | 2 | Extended | $21.6375 | $43.27 | 18 | 16 | 2026-10-17 17:15 |
| C7458627 | MAX2871ETJ+T (MAX2871) | 2 | 4 | Extended | $9.9503 | $39.80 | 3,133 | 3,129 | 2026-10-17 17:15 |
| C208262 | ADL5611ARKZ-R7 (ADL5611) | 3 | 6 | Extended | $5.9865 | $35.92 | 2,996 | 2,990 | 2026-10-17 17:15 |
| C579150 | ADL5375-05ACPZ-R7 (ADL5375-05) | 1 | 2 | Extended | $16.4069 | $32.81 | 654 | 652 | 2026-10-17 17:15 |
| C5213955 | TLV3603DCKR (TLV3603) | 4 | 8 | Extended | $4.0030 | $32.02 | 2,844 | 2,836 | 2026-10-17 17:15 |
| C17271830 | HMC536MS8G (HMC536) | 1 | 2 | Extended | $11.5664 | $23.13 | 5 | 3 | 2026-10-17 17:15 |
| C42711 | AD8310ARMZ-REEL7 (AD8310) | 1 | 2 | Extended | $10.5478 | $21.10 | 2,685 | 2,683 | 2026-10-17 17:15 |
| C2974371 | TLV3601DCKR (TLV3601) | 4 | 8 | Extended | $2.2023 | $17.62 | 2,425 | 2,417 | 2026-10-17 17:15 |
| C2059281 | OPA2388IDGKR (OPA2388) | 2 | 4 | Extended | $2.2937 | $9.17 | 1,639 | 1,635 | 2026-10-17 17:15 |
| C470929 | PE43711B-Z (PE43711) | 1 | 2 | Extended | $3.7516 | $7.50 | 1,805 | 1,803 | 2026-10-17 17:15 |
| C496551 | BWSMA-KWE-Z001 (RX ANT/TX ANT/REF IN/TRI) | 9 | 18 | Extended | $0.4114 | $7.41 | 137,064 | 137,046 | 2026-10-17 17:14 |
| C627342 | MCP4728A1T-E/UN (MCP4728A1 0x61) | 1 | 2 | Extended | $2.9990 | $6.00 | 50 | 48 | 2026-10-17 17:15 |
| C5137198 | BWMMCX-KE (ERR MON/VC MON/REF OUT/T) | 6 | 12 | Extended | $0.4833 | $5.80 | 20,492 | 20,480 | 2026-10-17 17:14 |
| C88374 | U.FL-R-SMT-1(80) (RX MON/CMP I MON/I MON/Q) | 22 | 48 | Extended | $0.1192 | $5.72 | 136,500 | 136,452 | 2026-10-17 17:14 |
| C478093 | MCP4728T-E/UN (MCP4728) | 1 | 2 | Extended | $2.6268 | $5.25 | 20,332 | 20,330 | 2026-10-17 17:15 |
| C37593 | ADS1115IDGSR (ADS1115) | 2 | 4 | Extended | $1.2228 | $4.89 | 13,943 | 13,939 | 2026-10-17 17:15 |
| C5119013 | TC32H4-25.000-33GNDTNL (TCXO 25MHz) | 1 | 2 | Extended | $1.5722 | $3.14 | 435 | 433 | 2026-10-17 17:15 |
| C5179998 | SX3V25.000B20100F30TNN (VCXO 25MHz) | 1 | 2 | Extended | $1.5069 | $3.01 | 408 | 406 | 2026-10-17 17:15 |
| C45783 | CL21A226MAQNNNE (22uF) | 3 | 10 | Basic | $0.1935 | $1.94 | 3,775,784 | 3,775,774 | 2026-10-17 17:13 |
| C2862740 | TPS7A2033PDBVR (TPS7A2033) | 4 | 9 | Extended | $0.2106 | $1.90 | 167,300 | 167,291 | 2026-10-17 17:15 |
| C210262 | SKY65404-31 (SKY65404-31) | 1 | 2 | Extended | $0.9012 | $1.80 | 1,002 | 1,000 | 2026-10-17 17:15 |
| C882469 | LQW15AN27NG80D (27nH) | 8 | 20 | Extended | $0.0900 | $1.80 | 19,158 | 19,138 | 2026-10-17 17:14 |
| C15850 | CL21A106KAYNNNE (10uF) | 10 | 30 | Basic | $0.0438 | $1.31 | 6,500,441 | 6,500,411 | 2026-10-17 17:13 |
| C15127 | AO3401A (AO3401A) | 2 | 8 | Basic | $0.1021 | $0.82 | 698,309 | 698,301 | 2026-10-17 17:14 |
| C46388 | TS5A3159DCKR (TS5A3159) | 1 | 2 | Extended | $0.3762 | $0.75 | 30,038 | 30,036 | 2026-10-17 17:15 |
| C1525 | CL05B104KO5NNNC (100nF) | 68 | 146 | Basic | $0.0051 | $0.74 | 24,757,395 | 24,757,249 | 2026-10-17 17:13 |
| C82919 | LQW15AN6N8G00D (6.8nH) | 3 | 10 | Extended | $0.0729 | $0.73 | 20,966 | 20,956 | 2026-10-17 17:14 |
| C8207 | SN74LVC1G04DCKR (74LVC1G04) | 2 | 8 | Extended | $0.0854 | $0.68 | 70,133 | 70,125 | 2026-10-17 17:15 |
| C170182 | 1206N104J500CT (100nF) | 1 | 4 | Extended | $0.1620 | $0.65 | 171,063 | 171,059 | 2026-10-17 17:13 |
| C14461 | SN74LVC2G34DCKR (74LVC2G34) | 1 | 4 | Extended | $0.1595 | $0.64 | 21,917 | 21,913 | 2026-10-17 17:15 |
| C10425 | SN74LVC1G17DCKR (74LVC1G17) | 2 | 8 | Extended | $0.0699 | $0.56 | 73,935 | 73,927 | 2026-10-17 17:15 |
| C23380874 | LP5907MFX-3.3 (LP5907 3.3V) | 1 | 4 | Extended | $0.1352 | $0.54 | 762 | 758 | 2026-10-17 17:15 |
| C113126 | LQW18AN43NG00D (43nH) | 3 | 10 | Extended | $0.0536 | $0.54 | 27,493 | 27,483 | 2026-10-17 17:14 |
| C210837 | MF-MSMF200-2 (2A PTC) | 2 | 8 | Extended | $0.0649 | $0.52 | 10,262 | 10,254 | 2026-10-17 17:14 |
| C38663 | SN74LVC1G3157DCKR (74LVC1G3157) | 1 | 6 | Extended | $0.0734 | $0.44 | 215,053 | 215,047 | 2026-10-17 17:15 |
| C531388 | HHM1907B1 (HHM1907B1) | 1 | 4 | Extended | $0.1032 | $0.41 | 7,884 | 7,880 | 2026-10-17 17:15 |
| C19270534 | 1010100506TR (100uF) | 1 | 3 | Extended | $0.1367 | $0.41 | 3,075 | 3,072 | 2026-10-17 17:13 |
| C165948 | TYPE-C-31-M-12 (USB-C 5V) | 1 | 2 | Extended | $0.1865 | $0.37 | 365,197 | 365,195 | 2026-10-17 17:14 |
| C23630 | CL10A225KO8NNNC (2.2uF) | 8 | 26 | Basic | $0.0134 | $0.35 | 3,396,900 | 3,396,874 | 2026-10-17 17:13 |
| C85840 | BLM21PG221SN1D (220R@100MHz 2A) | 1 | 10 | Extended | $0.0345 | $0.35 | 122,667 | 122,657 | 2026-10-17 17:14 |
| C144499 | AC1206FR-072R2L (2.2R) | 2 | 14 | Extended | $0.0223 | $0.31 | 91,423 | 91,409 | 2026-10-17 17:15 |
| C13564 | NCP18XH103F03RB (NTC 10k) | 1 | 6 | Extended | $0.0507 | $0.30 | 159,838 | 159,832 | 2026-10-17 17:15 |
| C11702 | 0402WGF1001TCE (1k) | 37 | 84 | Basic | $0.0035 | $0.29 | 13,763,337 | 13,763,253 | 2026-10-17 17:14 |
| C52923 | CL05A105KA5NQNC (1uF) | 15 | 40 | Basic | $0.0068 | $0.27 | 9,087,352 | 9,087,312 | 2026-10-17 17:13 |
| C162241 | GRM1885C1H682JA01D (6.8nF) | 2 | 12 | Extended | $0.0223 | $0.27 | 96,855 | 96,843 | 2026-10-17 17:13 |
| C1552 | 0402CG1R5C500NT (1.5pF) | 24 | 58 | Preferred | $0.0045 | $0.26 | 213,489 | 213,431 | 2026-10-17 17:13 |
| C113952 | SMAJ5.0A (SMAJ5.0A) | 1 | 6 | Extended | $0.0412 | $0.25 | 524,269 | 524,263 | 2026-10-17 17:13 |
| C2937625 | PZ254V-11-03P (TR/SIGN/SEL/REF) | 5 | 12 | Extended | $0.0198 | $0.24 | 931,581 | 931,569 | 2026-10-17 17:14 |
| C81598 | 1N4148W (1N4148W) | 1 | 16 | Basic | $0.0124 | $0.20 | 4,480,335 | 4,480,319 | 2026-10-17 17:13 |
| C2188753 | GCM1555C1H161JA16D (160pF) | 2 | 14 | Extended | $0.0123 | $0.17 | 8,607 | 8,593 | 2026-10-17 17:13 |
| C492401 | PZ254V-11-02P (50R/HDR 5V/SDA PU/SCL PU) | 4 | 8 | Extended | $0.0187 | $0.15 | 1,093,416 | 1,093,408 | 2026-10-17 17:14 |
| C14441 | CL05C680JB5NNNC (68pF) | 3 | 18 | Preferred | $0.0081 | $0.15 | 117,219 | 117,201 | 2026-10-17 17:13 |
| C8545 | 2N7002 (2N7002) | 1 | 7 | Basic | $0.0175 | $0.12 | 2,596,923 | 2,596,916 | 2026-10-17 17:14 |
| C2286 | KT-0603R (5V/3V3) | 2 | 14 | Basic | $0.0076 | $0.11 | 7,574,260 | 7,574,246 | 2026-10-17 17:13 |
| C25744 | 0402WGF1002TCE (10k) | 30 | 70 | Basic | $0.0015 | $0.10 | 20,293,490 | 20,293,420 | 2026-10-17 17:14 |
| C282239 | CC0402JRNPO9BN391 (390pF) | 3 | 20 | Extended | $0.0050 | $0.10 | 15,539 | 15,519 | 2026-10-17 17:13 |
| C95042 | MLG1005S0N6CT000 (0.6nH) | 1 | 12 | Extended | $0.0076 | $0.09 | 18,550 | 18,538 | 2026-10-17 17:14 |
| C285052 | 0402CG0R5B500NT (0.5pF) | 1 | 12 | Extended | $0.0065 | $0.08 | 58,162 | 58,150 | 2026-10-17 17:13 |
| C1523 | 0402B102K500NT (1nF) | 4 | 18 | Basic | $0.0038 | $0.07 | 2,949,518 | 2,949,500 | 2026-10-17 17:13 |
| C25741 | 0402WGF1003TCE (100k) | 16 | 42 | Basic | $0.0016 | $0.07 | 9,218,288 | 9,218,246 | 2026-10-17 17:14 |
| C15195 | CL05B103KB5NNNC (10nF) | 3 | 16 | Basic | $0.0041 | $0.07 | 6,164,750 | 6,164,734 | 2026-10-17 17:13 |
| C1562 | 0402CG330J500NT (33pF) | 4 | 18 | Basic | $0.0032 | $0.06 | 1,278,855 | 1,278,837 | 2026-10-17 17:13 |
| C25120 | 0402WGF499JTCE (49.9R) | 5 | 20 | Basic | $0.0023 | $0.05 | 1,236,499 | 1,236,479 | 2026-10-17 17:14 |
| C25905 | 0402WGF5101TCE (5.1k) | 4 | 18 | Basic | $0.0023 | $0.04 | 5,094,662 | 5,094,644 | 2026-10-17 17:14 |
| C1546 | 0402CG101J500NT (100pF) | 1 | 12 | Basic | $0.0033 | $0.04 | 3,787,231 | 3,787,219 | 2026-10-17 17:13 |
| C25105 | 0402WGF330JTCE (33R) | 11 | 32 | Basic | $0.0012 | $0.04 | 1,682,524 | 1,682,492 | 2026-10-17 17:14 |
| C137968 | RC0402FR-074K02L (4.02k) | 4 | 18 | Extended | $0.0021 | $0.04 | 319,818 | 319,800 | 2026-10-17 17:14 |
| C4109 | 0402WGF2001TCE (2k) | 2 | 14 | Basic | $0.0026 | $0.04 | 7,682,293 | 7,682,279 | 2026-10-17 17:14 |
| C25900 | 0402WGF4701TCE (4.7k) | 3 | 16 | Basic | $0.0021 | $0.03 | 15,982,465 | 15,982,449 | 2026-10-17 17:14 |
| C5126227 | FRC0402F4530TS (453R) | 9 | 28 | Extended | $0.0012 | $0.03 | 73,705 | 73,677 | 2026-10-17 17:14 |
| C25102 | 0402WGF3000TCE (300R) | 1 | 12 | Preferred | $0.0021 | $0.03 | 730,645 | 730,633 | 2026-10-17 17:14 |
| C25135 | 0402WGF8200TCE (820R) | 2 | 14 | Extended | $0.0018 | $0.03 | 106,979 | 106,965 | 2026-10-17 17:14 |
| C474132 | 0402WGF4704TCE (4.7M) | 1 | 12 | Extended | $0.0020 | $0.02 | 40,810 | 40,798 | 2026-10-17 17:15 |
| C25765 | 0402WGF2002TCE (20k) | 4 | 18 | Basic | $0.0013 | $0.02 | 2,442,655 | 2,442,637 | 2026-10-17 17:15 |
| C25879 | 0402WGF2201TCE (2.2k) | 5 | 20 | Basic | $0.0011 | $0.02 | 2,128,914 | 2,128,894 | 2026-10-17 17:14 |
| C25076 | 0402WGF1000TCE (100R) | 4 | 18 | Basic | $0.0012 | $0.02 | 8,006,988 | 8,006,970 | 2026-10-17 17:14 |
| C25132 | 0402WGF7500TCE (750R) | 2 | 14 | Extended | $0.0012 | $0.02 | 936,350 | 936,336 | 2026-10-17 17:14 |
| C17168 | 0402WGF0000TCE (0R) | 1 | 12 | Basic | $0.0011 | $0.01 | 8,664,799 | 8,664,787 | 2026-10-17 17:15 |
| C25107 | 0402WGF3480TCE (348R) | 1 | 12 | Extended | $0.0007 | $0.01 | 9,236 | 9,224 | 2026-10-17 17:14 |

"ordered" is what JLCPCB charges for: the placements on 2 boards plus its attrition (`lossNumber`) or minimum purchase, at the price break for that quantity; for a consigned line it is what we send (CONSIGNMENT.md).  A Preferred part is an Extended part JLCPCB keeps on its machines.

`mfg/cost_estimate.py`'s last run (build/COST_ESTIMATE.md) put the JLCPCB goods at $680.46 (boards $46.88, assembly $208.24, parts $425.34); this release $688.89.  The two share the fees, the prices and the pad count, so they differ only when the prices were asked at different times.

