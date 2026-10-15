# CostasLink-PYNQ-Z2 rev A: cost estimate

Written by `mfg/make_release.py` on 2026-10-15.  Parts: JLCPCB's live prices and stock (their parts API, asked at the times in the table), with their attrition and minimum purchase, x 1.0066 as the cart charges.  Fees: JLCPCB's cart on the ECP5-2ADC-2DAC order of 2026-10-09 (`mfg/cost_estimate.py` FEES, CLAUDE_PCB.md section 8).  The bare boards: a model with a range until the cart gives the number.

**The order:** 5 bare boards of 120.0 x 100.0 mm, 4 layers, 1.6 mm, green, ENIG, JLC04161H-7628; **2 of them assembled on one side** (Standard PCBA), J302 soldered at home (hand_solder_bom.csv: the part to order loose, and the jumper shunts); nothing consigned: every part from JLCPCB's shelf (CONSIGNMENT.md).

## The three buckets

| where | what | cost |
|---|---|--:|
| **JLCPCB** | 5 bare boards: ESTIMATE, $28.50-$65.26: GPiBridge's cart (2026-10-06, 4 layers, ENIG: $24.80 for 5 boards of 15.3 cm2) for the fixed part, plus 600 cm2 at $70.6-350 per m2 (JLCPCB's published 4-layer board charge, and five times it for a small order), plus $0-20 for ENIG; the cart's number replaces it | $46.88 |
| | confirm production file | $1.05 |
| | Standard PCBA setup, one side | $25.75 |
| | stencil, one side | $8.27 |
| | PCB assembly fixture | $16.54 |
| | feeder loading, 52 Extended codes x $2.70 (Basic and Preferred parts are free; the 0 consigned lines may be charged the same) | $140.40 |
| | SMT, 1104 pads a board x $0.0017 + $1.50 a board, x 2 | $6.75 |
| | through-hole: $3.61 labour an order + 93 joints a board (22 parts) x 2 x $0.0157 | $6.53 |
| | packaging | $0.51 |
| | special components | $0.12 |
| | depanel: JLCPCB's assembly rails taken off before delivery (the ECP5 cart's $2.32) | $2.32 |
| | their parts: 80 BOM lines, 387 placements a board, for 2 boards with attrition, x 1.0066 | $425.20 |
| | **goods before duty and shipping** | **$680.32** |
| | US duty, 35 % of the goods, collected under DDP | $238.11 |
| | shipping, UPS Express Saver DDP | $25.00-$40.00 |
| | **JLCPCB total** | **$943.43-$958.43** |
| **Digi-Key** | nothing consigned (CONSIGNMENT.md): every part is on JLCPCB's shelf | **$0.00** |
| | shipping a consignment to JLCPCB | $0.00-$0.00 |
| **other** | the bench and the field (mfg/cost_estimate.py's list) | **$141.50-$271.00** |
| | **everything** | **$1084.93-$1229.43** |

An assembled board: about $340.16 of the JLCPCB goods.  The range on the bare boards moves the goods from $661.94 to $698.70.

## Per-part fees: Basic, Preferred, Extended

| library | distinct parts | placements a board |
|---|--:|--:|
| Basic | 25 | 232 |
| Preferred | 3 | 29 |
| **Extended** | **52** | 126 |
| consigned | 0 | 0 |

Feeder loading is the largest assembly fee after the setup: 52 Extended codes x $2.70 = $140.40.  Every value merged into another saves $2.70.

The 52 distinct Extended parts: C10425 (SN74LVC1G17DCKR), C113126 (LQW18AN43NG00D), C113952 (SMAJ5.0A), C13564 (NCP18XH103F03RB), C137968 (RC0402FR-074K02L), C144499 (AC1206FR-072R2L), C14461 (SN74LVC2G34DCKR), C162241 (GRM1885C1H682JA01D), C165948 (TYPE-C-31-M-12), C170182 (1206N104J500CT), C17271830 (HMC536MS8G), C19270534 (1010100506TR), C2058382 (THS4541IRGTT), C2059281 (OPA2388IDGKR), C208262 (ADL5611ARKZ-R7), C210262 (SKY65404-31), C210837 (MF-MSMF200-2), C2188753 (GCM1555C1H161JA16D), C23380874 (LP5907MFX-3.3), C25132 (0402WGF7500TCE), C25135 (0402WGF8200TCE), C282239 (CC0402JRNPO9BN391), C285052 (0402CG0R5B500NT), C2862740 (TPS7A2033PDBVR), C2937625 (PZ254V-11-03P), C2974371 (TLV3601DCKR), C37593 (ADS1115IDGSR), C38663 (SN74LVC1G3157DCKR), C42711 (AD8310ARMZ-REEL7), C46388 (TS5A3159DCKR), C470929 (PE43711B-Z), C474132 (0402WGF4704TCE), C478093 (MCP4728T-E/UN), C492401 (PZ254V-11-02P), C496551 (BWSMA-KWE-Z001), C5119013 (TC32H4-25.000-33GNDTNL), C5126227 (FRC0402F4530TS), C5137198 (BWMMCX-KE), C5179998 (SX3V25.000B20100F30TNN), C5213955 (TLV3603DCKR), C531388 (HHM1907B1), C579150 (ADL5375-05ACPZ-R7), C579152 (ADL5380ACPZ-R7), C627342 (MCP4728A1T-E/UN), C650158 (AD5696RARUZ), C7458627 (MAX2871ETJ+T), C8207 (SN74LVC1G04DCKR), C82919 (LQW15AN6N8G00D), C85840 (BLM21PG221SN1D), C882469 (LQW15AN27NG80D), C88374 (U.FL-R-SMT-1(80)), C95042 (MLG1005S0N6CT000).

## What to look at

- The bare boards are the least certain line ($28.50 to $65.26): read the price off JLCPCB's cart
- **C2058382 THS4541IRGTT** costs $57.07 for the order (8 x $7.13)
- **C650158 AD5696RARUZ** costs $44.53 for the order (2 x $22.26)
- **C579152 ADL5380ACPZ-R7** costs $43.22 for the order (2 x $21.61)
- **C7458627 MAX2871ETJ+T** costs $39.75 for the order (4 x $9.94)
- **C208262 ADL5611ARKZ-R7** costs $35.87 for the order (6 x $5.98)
- **C579150 ADL5375-05ACPZ-R7** costs $32.79 for the order (2 x $16.39)
- **C579152 ADL5380ACPZ-R7**: 18 in stock against 2 for this order: order soon, or it may run out
- **C579150 ADL5375-05ACPZ-R7**: 4 in stock against 2 for this order: order soon, or it may run out
- **C17271830 HMC536MS8G**: 5 in stock against 2 for this order: order soon, or it may run out
- **C650158 AD5696RARUZ**: 2 in stock against 2 for this order: order soon, or it may run out
- **The fallback** (gen/parts.py consign=): ADL5380 C579152: JLCPCB 18 in stock at $21.61; ADL5375 C579150: JLCPCB 4 in stock at $16.39.  Each is bought from JLCPCB's shelf while the shelf covers the order; if it is short on the day, mfg/make_release.py consigns that line and this file says what to buy.  Consigning both would mean 8 pieces at Digi-Key, 4 of them the spares JLCPCB asks for as attrition and never used, plus tax, Digi-Key's shipping and the shipment to Shenzhen: $197.26-$222.26 against $76.04 on the shelf for the 4 pieces the boards need.  So for 2 boards a shelf part up to $121.22-$146.22 dearer than Digi-Key's price is still the cheaper buy, and with more boards the spares and the shipment are spread thinner (CLAUDE_PCB.md section 3).
- Not in the total: baking the moisture-sensitive parts (the QFNs are MSL 3; about $7.50 if ticked), shipping, and duty beyond the 35 %

## Parts (80 BOM lines; the consigned ones at the end)

| LCSC | part | a board | ordered | library | unit | line | stock | left after | asked |
|---|---|--:|--:|---|--:|--:|--:|--:|---|
| C2058382 | THS4541IRGTT (THS4541) | 4 | 8 | Extended | $7.1332 | $57.07 | 318 | 310 | 2026-10-15 04:54 |
| C650158 | AD5696RARUZ (AD5696R) | 1 | 2 | Extended | $22.2637 | $44.53 | 2 | 0 | 2026-10-15 04:55 |
| C579152 | ADL5380ACPZ-R7 (ADL5380) | 1 | 2 | Extended | $21.6099 | $43.22 | 18 | 16 | 2026-10-15 04:54 |
| C7458627 | MAX2871ETJ+T (MAX2871) | 2 | 4 | Extended | $9.9376 | $39.75 | 3,135 | 3,131 | 2026-10-15 04:55 |
| C208262 | ADL5611ARKZ-R7 (ADL5611) | 3 | 6 | Extended | $5.9789 | $35.87 | 3,002 | 2,996 | 2026-10-15 04:54 |
| C579150 | ADL5375-05ACPZ-R7 (ADL5375-05) | 1 | 2 | Extended | $16.3942 | $32.79 | 4 | 2 | 2026-10-15 04:55 |
| C5213955 | TLV3603DCKR (TLV3603) | 4 | 8 | Extended | $3.9979 | $31.98 | 2,893 | 2,885 | 2026-10-15 04:55 |
| C17271830 | HMC536MS8G (HMC536) | 1 | 2 | Extended | $11.5517 | $23.10 | 5 | 3 | 2026-10-15 04:55 |
| C42711 | AD8310ARMZ-REEL7 (AD8310) | 1 | 2 | Extended | $10.0794 | $20.16 | 2,638 | 2,636 | 2026-10-15 04:55 |
| C2974371 | TLV3601DCKR (TLV3601) | 4 | 8 | Extended | $2.1995 | $17.60 | 2,947 | 2,939 | 2026-10-15 04:54 |
| C2059281 | OPA2388IDGKR (OPA2388) | 2 | 4 | Extended | $2.2908 | $9.16 | 1,641 | 1,637 | 2026-10-15 04:54 |
| C470929 | PE43711B-Z (PE43711) | 1 | 2 | Extended | $3.7468 | $7.49 | 1,815 | 1,813 | 2026-10-15 04:54 |
| C496551 | BWSMA-KWE-Z001 (RX ANT/TX ANT/REF IN/TRI) | 9 | 18 | Extended | $0.4109 | $7.40 | 144,150 | 144,132 | 2026-10-15 04:53 |
| C627342 | MCP4728A1T-E/UN (MCP4728A1 0x61) | 1 | 2 | Extended | $2.9952 | $5.99 | 50 | 48 | 2026-10-15 04:55 |
| C478093 | MCP4728T-E/UN (MCP4728) | 1 | 2 | Extended | $2.6234 | $5.25 | 20,694 | 20,692 | 2026-10-15 04:54 |
| C37593 | ADS1115IDGSR (ADS1115) | 2 | 4 | Extended | $1.2229 | $4.89 | 21,017 | 21,013 | 2026-10-15 04:54 |
| C5137198 | BWMMCX-KE (ERR MON/VC MON/REF OUT/T) | 5 | 10 | Extended | $0.4533 | $4.53 | 20,572 | 20,562 | 2026-10-15 04:53 |
| C5119013 | TC32H4-25.000-33GNDTNL (TCXO 25MHz) | 1 | 2 | Extended | $1.5702 | $3.14 | 444 | 442 | 2026-10-15 04:55 |
| C88374 | U.FL-R-SMT-1(80) (RX MON/CMP I MON/I MON/Q) | 12 | 26 | Extended | $0.1191 | $3.10 | 155,858 | 155,832 | 2026-10-15 04:53 |
| C5179998 | SX3V25.000B20100F30TNN (VCXO 25MHz) | 1 | 2 | Extended | $1.5049 | $3.01 | 412 | 410 | 2026-10-15 04:55 |
| C15850 | CL21A106KAYNNNE (10uF) | 10 | 30 | Basic | $0.0689 | $2.07 | 3,661,072 | 3,661,042 | 2026-10-15 04:53 |
| C210262 | SKY65404-31 (SKY65404-31) | 1 | 2 | Extended | $0.9001 | $1.80 | 1,005 | 1,003 | 2026-10-15 04:54 |
| C882469 | LQW15AN27NG80D (27nH) | 8 | 20 | Extended | $0.0899 | $1.80 | 19,342 | 19,322 | 2026-10-15 04:53 |
| C2862740 | TPS7A2033PDBVR (TPS7A2033) | 4 | 8 | Extended | $0.2104 | $1.68 | 171,036 | 171,028 | 2026-10-15 04:55 |
| C45783 | CL21A226MAQNNNE (22uF) | 3 | 6 | Basic | $0.2371 | $1.42 | 3,350,615 | 3,350,609 | 2026-10-15 04:53 |
| C15127 | AO3401A (AO3401A) | 2 | 8 | Basic | $0.1020 | $0.82 | 579,402 | 579,394 | 2026-10-15 04:53 |
| C46388 | TS5A3159DCKR (TS5A3159) | 1 | 2 | Extended | $0.3757 | $0.75 | 31,743 | 31,741 | 2026-10-15 04:54 |
| C82919 | LQW15AN6N8G00D (6.8nH) | 3 | 10 | Extended | $0.0728 | $0.73 | 22,277 | 22,267 | 2026-10-15 04:53 |
| C8207 | SN74LVC1G04DCKR (74LVC1G04) | 2 | 8 | Extended | $0.0853 | $0.68 | 79,431 | 79,423 | 2026-10-15 04:55 |
| C14461 | SN74LVC2G34DCKR (74LVC2G34) | 1 | 4 | Extended | $0.1593 | $0.64 | 22,120 | 22,116 | 2026-10-15 04:55 |
| C1525 | CL05B104KO5NNNC (100nF) | 68 | 146 | Basic | $0.0043 | $0.63 | 22,536,936 | 22,536,790 | 2026-10-15 04:52 |
| C170182 | 1206N104J500CT (100nF) | 1 | 4 | Extended | $0.1553 | $0.62 | 171,292 | 171,288 | 2026-10-15 04:53 |
| C10425 | SN74LVC1G17DCKR (74LVC1G17) | 2 | 8 | Extended | $0.0700 | $0.56 | 81,515 | 81,507 | 2026-10-15 04:55 |
| C23380874 | LP5907MFX-3.3 (LP5907 3.3V) | 1 | 4 | Extended | $0.1351 | $0.54 | 1,013 | 1,009 | 2026-10-15 04:55 |
| C113126 | LQW18AN43NG00D (43nH) | 3 | 10 | Extended | $0.0535 | $0.54 | 27,503 | 27,493 | 2026-10-15 04:53 |
| C210837 | MF-MSMF200-2 (2A PTC) | 2 | 8 | Extended | $0.0648 | $0.52 | 10,375 | 10,367 | 2026-10-15 04:53 |
| C23630 | CL10A225KO8NNNC (2.2uF) | 8 | 26 | Basic | $0.0181 | $0.47 | 3,521,978 | 3,521,952 | 2026-10-15 04:53 |
| C38663 | SN74LVC1G3157DCKR (74LVC1G3157) | 1 | 6 | Extended | $0.0746 | $0.45 | 222,285 | 222,279 | 2026-10-15 04:54 |
| C531388 | HHM1907B1 (HHM1907B1) | 1 | 4 | Extended | $0.1031 | $0.41 | 7,884 | 7,880 | 2026-10-15 04:54 |
| C19270534 | 1010100506TR (100uF) | 1 | 3 | Extended | $0.1365 | $0.41 | 4,081 | 4,078 | 2026-10-15 04:53 |
| C165948 | TYPE-C-31-M-12 (USB-C 5V) | 1 | 2 | Extended | $0.1862 | $0.37 | 381,715 | 381,713 | 2026-10-15 04:53 |
| C85840 | BLM21PG221SN1D (220R@100MHz 2A) | 1 | 10 | Extended | $0.0345 | $0.35 | 162,873 | 162,863 | 2026-10-15 04:53 |
| C52923 | CL05A105KA5NQNC (1uF) | 15 | 40 | Basic | $0.0081 | $0.32 | 7,569,328 | 7,569,288 | 2026-10-15 04:53 |
| C144499 | AC1206FR-072R2L (2.2R) | 2 | 14 | Extended | $0.0222 | $0.31 | 91,838 | 91,824 | 2026-10-15 04:54 |
| C13564 | NCP18XH103F03RB (NTC 10k) | 1 | 6 | Extended | $0.0465 | $0.28 | 165,714 | 165,708 | 2026-10-15 04:54 |
| C162241 | GRM1885C1H682JA01D (6.8nF) | 2 | 12 | Extended | $0.0222 | $0.27 | 98,215 | 98,203 | 2026-10-15 04:53 |
| C1552 | 0402CG1R5C500NT (1.5pF) | 24 | 58 | Preferred | $0.0045 | $0.26 | 214,929 | 214,871 | 2026-10-15 04:52 |
| C113952 | SMAJ5.0A (SMAJ5.0A) | 1 | 6 | Extended | $0.0411 | $0.25 | 535,779 | 535,773 | 2026-10-15 04:53 |
| C11702 | 0402WGF1001TCE (1k) | 29 | 68 | Basic | $0.0035 | $0.24 | 14,432,279 | 14,432,211 | 2026-10-15 04:54 |
| C2937625 | PZ254V-11-03P (TR/SIGN/SEL/REF) | 5 | 12 | Extended | $0.0198 | $0.24 | 941,398 | 941,386 | 2026-10-15 04:53 |
| C25744 | 0402WGF1002TCE (10k) | 30 | 70 | Basic | $0.0033 | $0.23 | 21,581,005 | 21,580,935 | 2026-10-15 04:54 |
| C2188753 | GCM1555C1H161JA16D (160pF) | 2 | 14 | Extended | $0.0123 | $0.17 | 8,857 | 8,843 | 2026-10-15 04:53 |
| C81598 | 1N4148W (1N4148W) | 1 | 12 | Basic | $0.0124 | $0.15 | 4,621,063 | 4,621,051 | 2026-10-15 04:53 |
| C14441 | CL05C680JB5NNNC (68pF) | 3 | 18 | Preferred | $0.0081 | $0.15 | 118,484 | 118,466 | 2026-10-15 04:52 |
| C8545 | 2N7002 (2N7002) | 1 | 7 | Basic | $0.0175 | $0.12 | 1,824,050 | 1,824,043 | 2026-10-15 04:54 |
| C2286 | KT-0603R (5V/3V3) | 2 | 14 | Basic | $0.0076 | $0.11 | 7,838,196 | 7,838,182 | 2026-10-15 04:53 |
| C95042 | MLG1005S0N6CT000 (0.6nH) | 1 | 12 | Extended | $0.0076 | $0.09 | 18,650 | 18,638 | 2026-10-15 04:53 |
| C282239 | CC0402JRNPO9BN391 (390pF) | 3 | 16 | Extended | $0.0050 | $0.08 | 15,828 | 15,812 | 2026-10-15 04:53 |
| C285052 | 0402CG0R5B500NT (0.5pF) | 1 | 12 | Extended | $0.0065 | $0.08 | 58,292 | 58,280 | 2026-10-15 04:52 |
| C492401 | PZ254V-11-02P (50R/HDR 5V) | 2 | 4 | Extended | $0.0186 | $0.07 | 1,117,646 | 1,117,642 | 2026-10-15 04:53 |
| C1523 | 0402B102K500NT (1nF) | 4 | 18 | Basic | $0.0041 | $0.07 | 3,120,926 | 3,120,908 | 2026-10-15 04:52 |
| C15195 | CL05B103KB5NNNC (10nF) | 3 | 16 | Basic | $0.0041 | $0.07 | 6,351,265 | 6,351,249 | 2026-10-15 04:53 |
| C25741 | 0402WGF1003TCE (100k) | 15 | 40 | Basic | $0.0015 | $0.06 | 9,723,981 | 9,723,941 | 2026-10-15 04:54 |
| C1562 | 0402CG330J500NT (33pF) | 4 | 18 | Basic | $0.0032 | $0.06 | 1,314,254 | 1,314,236 | 2026-10-15 04:53 |
| C25120 | 0402WGF499JTCE (49.9R) | 5 | 20 | Basic | $0.0023 | $0.05 | 1,292,361 | 1,292,341 | 2026-10-15 04:54 |
| C25905 | 0402WGF5101TCE (5.1k) | 4 | 18 | Basic | $0.0024 | $0.04 | 5,305,675 | 5,305,657 | 2026-10-15 04:54 |
| C25105 | 0402WGF330JTCE (33R) | 11 | 32 | Basic | $0.0012 | $0.04 | 1,426,436 | 1,426,404 | 2026-10-15 04:54 |
| C137968 | RC0402FR-074K02L (4.02k) | 4 | 18 | Extended | $0.0021 | $0.04 | 331,532 | 331,514 | 2026-10-15 04:54 |
| C1546 | 0402CG101J500NT (100pF) | 1 | 12 | Basic | $0.0031 | $0.04 | 3,978,756 | 3,978,744 | 2026-10-15 04:53 |
| C4109 | 0402WGF2001TCE (2k) | 2 | 14 | Basic | $0.0026 | $0.04 | 7,747,305 | 7,747,291 | 2026-10-15 04:54 |
| C25102 | 0402WGF3000TCE (300R) | 2 | 14 | Preferred | $0.0021 | $0.03 | 791,385 | 791,371 | 2026-10-15 04:54 |
| C25900 | 0402WGF4701TCE (4.7k) | 1 | 12 | Basic | $0.0023 | $0.03 | 16,153,178 | 16,153,166 | 2026-10-15 04:54 |
| C5126227 | FRC0402F4530TS (453R) | 6 | 22 | Extended | $0.0012 | $0.03 | 73,745 | 73,723 | 2026-10-15 04:54 |
| C25135 | 0402WGF8200TCE (820R) | 2 | 14 | Extended | $0.0018 | $0.03 | 117,365 | 117,351 | 2026-10-15 04:54 |
| C474132 | 0402WGF4704TCE (4.7M) | 1 | 12 | Extended | $0.0020 | $0.02 | 41,370 | 41,358 | 2026-10-15 04:54 |
| C25765 | 0402WGF2002TCE (20k) | 4 | 18 | Basic | $0.0013 | $0.02 | 2,429,196 | 2,429,178 | 2026-10-15 04:54 |
| C25076 | 0402WGF1000TCE (100R) | 4 | 18 | Basic | $0.0012 | $0.02 | 8,299,741 | 8,299,723 | 2026-10-15 04:54 |
| C25879 | 0402WGF2201TCE (2.2k) | 4 | 18 | Basic | $0.0011 | $0.02 | 2,039,553 | 2,039,535 | 2026-10-15 04:54 |
| C25132 | 0402WGF7500TCE (750R) | 2 | 14 | Extended | $0.0012 | $0.02 | 936,841 | 936,827 | 2026-10-15 04:54 |
| C17168 | 0402WGF0000TCE (0R) | 1 | 12 | Basic | $0.0011 | $0.01 | 9,233,330 | 9,233,318 | 2026-10-15 04:54 |

"ordered" is what JLCPCB charges for: the placements on 2 boards plus its attrition (`lossNumber`) or minimum purchase, at the price break for that quantity; for a consigned line it is what we send (CONSIGNMENT.md).  A Preferred part is an Extended part JLCPCB keeps on its machines.

`mfg/cost_estimate.py`'s last run (build/COST_ESTIMATE.md) put the JLCPCB goods at $680.46 (boards $46.88, assembly $208.24, parts $425.34); this release $680.32.  The two share the fees, the prices and the pad count, so they differ only when the prices were asked at different times.

