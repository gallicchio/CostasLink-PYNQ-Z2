# CostasLink-PYNQ-Z2 rev A: cost estimate

Written by `mfg/make_release.py` on 2026-10-12.  Parts: JLCPCB's live prices and stock (their parts API, asked at the times in the table), with their attrition and minimum purchase, x 1.0066 as the cart charges.  Fees: JLCPCB's cart on the ECP5-2ADC-2DAC order of 2026-10-09 (`mfg/cost_estimate.py` FEES, CLAUDE_PCB.md section 8).  The bare boards: a model with a range until the cart gives the number.

**The order:** 5 bare boards of 120.0 x 100.0 mm, 4 layers, 1.6 mm, green, ENIG, JLC04161H-7628; **2 of them assembled on one side** (Standard PCBA), J302 soldered at home (hand_solder_bom.csv: the part to order loose, and the jumper shunts); 3 consigned parts bought at Digi-Key and sent to JLCPCB (CONSIGNMENT.md).

## The three buckets

| where | what | cost |
|---|---|--:|
| **JLCPCB** | 5 bare boards: ESTIMATE, $28.50-$65.26: GPiBridge's cart (2026-10-06, 4 layers, ENIG: $24.80 for 5 boards of 15.3 cm2) for the fixed part, plus 600 cm2 at $70.6-350 per m2 (JLCPCB's published 4-layer board charge, and five times it for a small order), plus $0-20 for ENIG; the cart's number replaces it | $46.88 |
| | confirm production file | $1.05 |
| | Standard PCBA setup, one side | $25.75 |
| | stencil, one side | $8.27 |
| | PCB assembly fixture | $16.54 |
| | feeder loading, 49 Extended codes x $2.70 (Basic and Preferred parts are free; the 3 consigned lines may be charged the same) | $132.30 |
| | SMT, 1100 pads a board x $0.0017 + $1.50 a board, x 2 | $6.74 |
| | through-hole: $3.61 labour an order + 93 joints a board (22 parts) x 2 x $0.0157 | $6.53 |
| | packaging | $0.51 |
| | special components | $0.12 |
| | depanel: JLCPCB's assembly rails taken off before delivery (the ECP5 cart's $2.32) | $2.32 |
| | their parts: 77 BOM lines, 381 placements a board, for 2 boards with attrition, x 1.0066 | $353.47 |
| | **goods before duty and shipping** | **$600.47** |
| | US duty, 35 % of the goods, collected under DDP | $210.17 |
| | shipping, UPS Express Saver DDP | $25.00-$40.00 |
| | **JLCPCB total** | **$835.64-$850.64** |
| **Digi-Key** | the consigned parts (CONSIGNMENT.md): $129.64, plus 9.5 % tax and $8.00 shipping | **$149.96** |
| | shipping the consignment to JLCPCB | $35.00-$60.00 |
| **other** | the bench and the field (mfg/cost_estimate.py's list) | **$139.00-$267.00** |
| | **everything** | **$1159.60-$1327.60** |

An assembled board: about $300.24 of the JLCPCB goods, plus its share of the consignment.  The range on the bare boards moves the goods from $582.09 to $618.86.

## Per-part fees: Basic, Preferred, Extended

| library | distinct parts | placements a board |
|---|--:|--:|
| Basic | 25 | 231 |
| Preferred | 3 | 27 |
| **Extended** | **49** | 123 |
| consigned | 3 | 3 |

Feeder loading is the largest assembly fee after the setup: 49 Extended codes x $2.70 = $132.30.  Every value merged into another saves $2.70.

The 49 distinct Extended parts: C10425 (SN74LVC1G17DCKR), C113126 (LQW18AN43NG00D), C113952 (SMAJ5.0A), C13564 (NCP18XH103F03RB), C137968 (RC0402FR-074K02L), C144499 (AC1206FR-072R2L), C14461 (SN74LVC2G34DCKR), C162241 (GRM1885C1H682JA01D), C165948 (TYPE-C-31-M-12), C170182 (1206N104J500CT), C17271830 (HMC536MS8G), C19270534 (1010100506TR), C2058382 (THS4541IRGTT), C2059281 (OPA2388IDGKR), C208262 (ADL5611ARKZ-R7), C210262 (SKY65404-31), C210837 (MF-MSMF200-2), C2188753 (GCM1555C1H161JA16D), C23380874 (LP5907MFX-3.3), C25132 (0402WGF7500TCE), C25135 (0402WGF8200TCE), C282239 (CC0402JRNPO9BN391), C285052 (0402CG0R5B500NT), C2862740 (TPS7A2033PDBVR), C2937625 (PZ254V-11-03P), C2974371 (TLV3601DCKR), C37593 (ADS1115IDGSR), C38663 (SN74LVC1G3157DCKR), C42711 (AD8310ARMZ-REEL7), C46388 (TS5A3159DCKR), C470929 (PE43711B-Z), C474132 (0402WGF4704TCE), C478093 (MCP4728T-E/UN), C492401 (PZ254V-11-02P), C496551 (BWSMA-KWE-Z001), C5119013 (TC32H4-25.000-33GNDTNL), C5126227 (FRC0402F4530TS), C5137198 (BWMMCX-KE), C5179998 (SX3V25.000B20100F30TNN), C5213955 (TLV3603DCKR), C627342 (MCP4728A1T-E/UN), C650158 (AD5696RARUZ), C7458627 (MAX2871ETJ+T), C8207 (SN74LVC1G04DCKR), C82919 (LQW15AN6N8G00D), C85840 (BLM21PG221SN1D), C882469 (LQW15AN27NG80D), C88374 (U.FL-R-SMT-1(80)), C95042 (MLG1005S0N6CT000).

## What to look at

- The bare boards are the least certain line ($28.50 to $65.26): read the price off JLCPCB's cart
- **C2058382 THS4541IRGTT** costs $57.00 for the order (8 x $7.13)
- **C650158 AD5696RARUZ** costs $44.48 for the order (2 x $22.24)
- **C7458627 MAX2871ETJ+T** costs $39.71 for the order (4 x $9.93)
- **C208262 ADL5611ARKZ-R7** costs $35.84 for the order (6 x $5.97)
- **C5213955 TLV3603DCKR** costs $31.95 for the order (8 x $3.99)
- **C17271830 HMC536MS8G** costs $23.08 for the order (2 x $11.54)
- **C17271830 HMC536MS8G**: 5 in stock against 2 for this order: order soon, or it may run out
- **C650158 AD5696RARUZ**: 7 in stock against 2 for this order: order soon, or it may run out
- JLCPCB had 4 of C579150, 18 of C579152 on 2026-10-09: buying the two ADI chips there and consigning only the balun would cost about $15.04 more on parts and save their consignment handling; the consignment shipment is needed either way for the balun (mfg/cost_estimate.py)
- Not in the total: baking the moisture-sensitive parts (the QFNs are MSL 3; about $7.50 if ticked), shipping, and duty beyond the 35 %

## Parts (80 BOM lines; the consigned ones at the end)

| LCSC | part | a board | ordered | library | unit | line | stock | left after | asked |
|---|---|--:|--:|---|--:|--:|--:|--:|---|
| C2058382 | THS4541IRGTT (THS4541) | 4 | 8 | Extended | $7.1256 | $57.00 | 380 | 372 | 2026-10-11 23:49 |
| C650158 | AD5696RARUZ (AD5696R) | 1 | 2 | Extended | $22.2398 | $44.48 | 7 | 5 | 2026-10-11 23:49 |
| C7458627 | MAX2871ETJ+T (MAX2871) | 2 | 4 | Extended | $9.9269 | $39.71 | 3,162 | 3,158 | 2026-10-11 23:49 |
| C208262 | ADL5611ARKZ-R7 (ADL5611) | 3 | 6 | Extended | $5.9725 | $35.84 | 3,016 | 3,010 | 2026-10-11 23:49 |
| C5213955 | TLV3603DCKR (TLV3603) | 4 | 8 | Extended | $3.9936 | $31.95 | 3,016 | 3,008 | 2026-10-11 23:49 |
| C17271830 | HMC536MS8G (HMC536) | 1 | 2 | Extended | $11.5393 | $23.08 | 5 | 3 | 2026-10-11 23:49 |
| C2974371 | TLV3601DCKR (TLV3601) | 4 | 8 | Extended | $2.8340 | $22.67 | 20,661 | 20,653 | 2026-10-11 23:49 |
| C42711 | AD8310ARMZ-REEL7 (AD8310) | 1 | 2 | Extended | $10.2315 | $20.46 | 2,625 | 2,623 | 2026-10-12 07:12 |
| C2059281 | OPA2388IDGKR (OPA2388) | 2 | 4 | Extended | $2.2884 | $9.15 | 1,695 | 1,691 | 2026-10-11 23:49 |
| C470929 | PE43711B-Z (PE43711) | 1 | 2 | Extended | $3.7428 | $7.49 | 1,842 | 1,840 | 2026-10-11 23:48 |
| C496551 | BWSMA-KWE-Z001 (RX ANT/TX ANT/REF IN/TRI) | 9 | 18 | Extended | $0.4105 | $7.39 | 146,405 | 146,387 | 2026-10-11 23:48 |
| C627342 | MCP4728A1T-E/UN (MCP4728A1 0x61) | 1 | 2 | Extended | $2.9920 | $5.98 | 50 | 48 | 2026-10-11 23:49 |
| C478093 | MCP4728T-E/UN (MCP4728) | 1 | 2 | Extended | $2.6206 | $5.24 | 20,870 | 20,868 | 2026-10-11 23:49 |
| C37593 | ADS1115IDGSR (ADS1115) | 2 | 4 | Extended | $1.2216 | $4.89 | 25,128 | 25,124 | 2026-10-11 23:49 |
| C5137198 | BWMMCX-KE (ERR MON/VC MON/REF OUT/T) | 5 | 10 | Extended | $0.4528 | $4.53 | 12,411 | 12,401 | 2026-10-11 23:48 |
| C5119013 | TC32H4-25.000-33GNDTNL (TCXO 25MHz) | 1 | 2 | Extended | $1.5685 | $3.14 | 473 | 471 | 2026-10-11 23:49 |
| C5179998 | SX3V25.000B20100F30TNN (VCXO 25MHz) | 1 | 2 | Extended | $1.5033 | $3.01 | 413 | 411 | 2026-10-11 23:49 |
| C88374 | U.FL-R-SMT-1(80) (RX MON/CMP I MON/I MON/Q) | 12 | 26 | Extended | $0.1137 | $2.96 | 97,866 | 97,840 | 2026-10-11 23:48 |
| C15850 | CL21A106KAYNNNE (10uF) | 10 | 30 | Basic | $0.0688 | $2.06 | 4,206,459 | 4,206,429 | 2026-10-11 23:48 |
| C210262 | SKY65404-31 (SKY65404-31) | 1 | 2 | Extended | $0.8991 | $1.80 | 1,005 | 1,003 | 2026-10-11 23:48 |
| C882469 | LQW15AN27NG80D (27nH) | 8 | 20 | Extended | $0.0898 | $1.80 | 19,534 | 19,514 | 2026-10-11 23:48 |
| C2862740 | TPS7A2033PDBVR (TPS7A2033) | 4 | 8 | Extended | $0.2155 | $1.72 | 193,993 | 193,985 | 2026-10-11 23:49 |
| C45783 | CL21A226MAQNNNE (22uF) | 3 | 6 | Basic | $0.2369 | $1.42 | 3,634,715 | 3,634,709 | 2026-10-11 23:48 |
| C15127 | AO3401A (AO3401A) | 2 | 8 | Basic | $0.1018 | $0.81 | 683,803 | 683,795 | 2026-10-11 23:48 |
| C46388 | TS5A3159DCKR (TS5A3159) | 1 | 2 | Extended | $0.3753 | $0.75 | 37,015 | 37,013 | 2026-10-11 23:49 |
| C82919 | LQW15AN6N8G00D (6.8nH) | 3 | 10 | Extended | $0.0727 | $0.73 | 23,999 | 23,989 | 2026-10-12 05:15 |
| C8207 | SN74LVC1G04DCKR (74LVC1G04) | 2 | 8 | Extended | $0.0838 | $0.67 | 75,977 | 75,969 | 2026-10-11 23:49 |
| C1525 | CL05B104KO5NNNC (100nF) | 68 | 146 | Basic | $0.0045 | $0.66 | 24,145,880 | 24,145,734 | 2026-10-11 23:48 |
| C14461 | SN74LVC2G34DCKR (74LVC2G34) | 1 | 4 | Extended | $0.1592 | $0.64 | 22,430 | 22,426 | 2026-10-11 23:49 |
| C170182 | 1206N104J500CT (100nF) | 1 | 4 | Extended | $0.1587 | $0.63 | 173,595 | 173,591 | 2026-10-11 23:48 |
| C10425 | SN74LVC1G17DCKR (74LVC1G17) | 2 | 8 | Extended | $0.0711 | $0.57 | 98,666 | 98,658 | 2026-10-11 23:49 |
| C23380874 | LP5907MFX-3.3 (LP5907 3.3V) | 1 | 4 | Extended | $0.1349 | $0.54 | 1,905 | 1,901 | 2026-10-11 23:49 |
| C113126 | LQW18AN43NG00D (43nH) | 3 | 10 | Extended | $0.0535 | $0.54 | 27,528 | 27,518 | 2026-10-11 23:48 |
| C210837 | MF-MSMF200-2 (2A PTC) | 2 | 8 | Extended | $0.0647 | $0.52 | 16,411 | 16,403 | 2026-10-11 23:48 |
| C23630 | CL10A225KO8NNNC (2.2uF) | 8 | 26 | Basic | $0.0181 | $0.47 | 3,693,393 | 3,693,367 | 2026-10-11 23:48 |
| C38663 | SN74LVC1G3157DCKR (74LVC1G3157) | 1 | 6 | Extended | $0.0727 | $0.44 | 209,067 | 209,061 | 2026-10-11 23:49 |
| C19270534 | 1010100506TR (100uF) | 1 | 3 | Extended | $0.1364 | $0.41 | 4,081 | 4,078 | 2026-10-11 22:29 |
| C165948 | TYPE-C-31-M-12 (USB-C 5V) | 1 | 2 | Extended | $0.1860 | $0.37 | 406,887 | 406,885 | 2026-10-11 23:48 |
| C144499 | AC1206FR-072R2L (2.2R) | 2 | 14 | Extended | $0.0264 | $0.37 | 95,275 | 95,261 | 2026-10-11 23:48 |
| C52923 | CL05A105KA5NQNC (1uF) | 15 | 40 | Basic | $0.0087 | $0.35 | 7,389,171 | 7,389,131 | 2026-10-11 23:48 |
| C85840 | BLM21PG221SN1D (220R@100MHz 2A) | 1 | 10 | Extended | $0.0344 | $0.34 | 219,226 | 219,216 | 2026-10-11 23:48 |
| C13564 | NCP18XH103F03RB (NTC 10k) | 1 | 6 | Extended | $0.0465 | $0.28 | 177,333 | 177,327 | 2026-10-12 07:12 |
| C162241 | GRM1885C1H682JA01D (6.8nF) | 2 | 12 | Extended | $0.0222 | $0.27 | 101,035 | 101,023 | 2026-10-11 23:48 |
| C113952 | SMAJ5.0A (SMAJ5.0A) | 1 | 6 | Extended | $0.0411 | $0.25 | 563,914 | 563,908 | 2026-10-11 23:48 |
| C1552 | 0402CG1R5C500NT (1.5pF) | 22 | 54 | Preferred | $0.0045 | $0.24 | 217,148 | 217,094 | 2026-10-11 23:48 |
| C11702 | 0402WGF1001TCE (1k) | 29 | 68 | Basic | $0.0035 | $0.24 | 8,113,164 | 8,113,096 | 2026-10-11 23:48 |
| C25744 | 0402WGF1002TCE (10k) | 30 | 70 | Basic | $0.0034 | $0.24 | 19,435,576 | 19,435,506 | 2026-10-11 23:48 |
| C2937625 | PZ254V-11-03P (TR/SIGN/SEL/REF) | 5 | 12 | Extended | $0.0198 | $0.24 | 971,874 | 971,862 | 2026-10-11 23:48 |
| C2188753 | GCM1555C1H161JA16D (160pF) | 2 | 14 | Extended | $0.0123 | $0.17 | 9,057 | 9,043 | 2026-10-11 23:48 |
| C81598 | 1N4148W (1N4148W) | 1 | 12 | Basic | $0.0123 | $0.15 | 4,806,430 | 4,806,418 | 2026-10-12 07:12 |
| C14441 | CL05C680JB5NNNC (68pF) | 3 | 18 | Preferred | $0.0081 | $0.15 | 124,131 | 124,113 | 2026-10-11 23:48 |
| C8545 | 2N7002 (2N7002) | 1 | 7 | Basic | $0.0178 | $0.12 | 1,367,779 | 1,367,772 | 2026-10-11 23:48 |
| C2286 | KT-0603R (5V/3V3) | 2 | 14 | Basic | $0.0076 | $0.11 | 7,174,565 | 7,174,551 | 2026-10-11 23:48 |
| C95042 | MLG1005S0N6CT000 (0.6nH) | 1 | 12 | Extended | $0.0076 | $0.09 | 18,950 | 18,938 | 2026-10-11 23:48 |
| C15195 | CL05B103KB5NNNC (10nF) | 3 | 16 | Basic | $0.0050 | $0.08 | 3,426,145 | 3,426,129 | 2026-10-12 07:12 |
| C282239 | CC0402JRNPO9BN391 (390pF) | 3 | 16 | Extended | $0.0050 | $0.08 | 66,778 | 66,762 | 2026-10-11 23:48 |
| C25741 | 0402WGF1003TCE (100k) | 14 | 38 | Basic | $0.0021 | $0.08 | 8,337,573 | 8,337,535 | 2026-10-11 23:48 |
| C285052 | 0402CG0R5B500NT (0.5pF) | 1 | 12 | Extended | $0.0065 | $0.08 | 74,051 | 74,039 | 2026-10-11 23:48 |
| C492401 | PZ254V-11-02P (50R/HDR 5V) | 2 | 4 | Extended | $0.0186 | $0.07 | 1,199,496 | 1,199,492 | 2026-10-11 23:48 |
| C1523 | 0402B102K500NT (1nF) | 4 | 18 | Basic | $0.0041 | $0.07 | 3,356,242 | 3,356,224 | 2026-10-11 23:48 |
| C1562 | 0402CG330J500NT (33pF) | 4 | 18 | Basic | $0.0032 | $0.06 | 1,496,280 | 1,496,262 | 2026-10-11 23:48 |
| C25120 | 0402WGF499JTCE (49.9R) | 5 | 20 | Basic | $0.0027 | $0.05 | 1,275,084 | 1,275,064 | 2026-10-11 23:48 |
| C1546 | 0402CG101J500NT (100pF) | 1 | 12 | Basic | $0.0042 | $0.05 | 4,171,950 | 4,171,938 | 2026-10-12 07:12 |
| C25905 | 0402WGF5101TCE (5.1k) | 4 | 18 | Basic | $0.0024 | $0.04 | 5,586,743 | 5,586,725 | 2026-10-11 23:48 |
| C25105 | 0402WGF330JTCE (33R) | 11 | 32 | Basic | $0.0012 | $0.04 | 1,635,588 | 1,635,556 | 2026-10-11 23:48 |
| C137968 | RC0402FR-074K02L (4.02k) | 4 | 18 | Extended | $0.0021 | $0.04 | 334,732 | 334,714 | 2026-10-11 23:48 |
| C4109 | 0402WGF2001TCE (2k) | 2 | 14 | Basic | $0.0026 | $0.04 | 7,982,777 | 7,982,763 | 2026-10-11 23:48 |
| C5126227 | FRC0402F4530TS (453R) | 6 | 22 | Extended | $0.0015 | $0.03 | 75,965 | 75,943 | 2026-10-11 23:48 |
| C25900 | 0402WGF4701TCE (4.7k) | 1 | 12 | Basic | $0.0027 | $0.03 | 14,410,758 | 14,410,746 | 2026-10-11 23:48 |
| C25879 | 0402WGF2201TCE (2.2k) | 4 | 18 | Basic | $0.0017 | $0.03 | 2,287,019 | 2,287,001 | 2026-10-11 23:48 |
| C17168 | 0402WGF0000TCE (0R) | 1 | 12 | Basic | $0.0025 | $0.03 | 9,565,020 | 9,565,008 | 2026-10-11 23:48 |
| C25102 | 0402WGF3000TCE (300R) | 2 | 14 | Preferred | $0.0021 | $0.03 | 801,305 | 801,291 | 2026-10-11 23:48 |
| C25135 | 0402WGF8200TCE (820R) | 2 | 14 | Extended | $0.0018 | $0.03 | 118,192 | 118,178 | 2026-10-11 23:48 |
| C474132 | 0402WGF4704TCE (4.7M) | 1 | 12 | Extended | $0.0020 | $0.02 | 46,290 | 46,278 | 2026-10-12 07:12 |
| C25765 | 0402WGF2002TCE (20k) | 4 | 18 | Basic | $0.0013 | $0.02 | 2,614,361 | 2,614,343 | 2026-10-11 23:48 |
| C25076 | 0402WGF1000TCE (100R) | 4 | 18 | Basic | $0.0012 | $0.02 | 9,126,171 | 9,126,153 | 2026-10-11 23:48 |
| C25132 | 0402WGF7500TCE (750R) | 2 | 14 | Extended | $0.0012 | $0.02 | 943,006 | 942,992 | 2026-10-11 23:48 |
| C2837312 | 5400BL15B050E (5400BL15B050) | 1 | 4 | consigned | Digi-Key | - | 0 | - | 2026-10-11 23:48 |
| C579150 | ADL5375-05ACPZ-R7 (ADL5375-05) | 1 | 4 | consigned | Digi-Key | - | 4 | - | 2026-10-11 23:49 |
| C579152 | ADL5380ACPZ-R7 (ADL5380) | 1 | 4 | consigned | Digi-Key | - | 18 | - | 2026-10-11 23:49 |

"ordered" is what JLCPCB charges for: the placements on 2 boards plus its attrition (`lossNumber`) or minimum purchase, at the price break for that quantity; for a consigned line it is what we send (CONSIGNMENT.md).  A Preferred part is an Extended part JLCPCB keeps on its machines.

`mfg/cost_estimate.py`'s last run (build/COST_ESTIMATE.md) put the JLCPCB goods at $593.70 (boards $46.88, assembly $194.08, parts $352.73); this release $600.47.  The two should agree within a few dollars: they share the fees and the prices, and differ by the depanel option and by how the joints are counted.

