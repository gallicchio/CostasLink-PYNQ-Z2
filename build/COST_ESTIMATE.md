# CostasLink-PYNQ-Z2 rev A: what the first order costs

Written by `mfg/cost_estimate.py` on 2026-10-12 for 5 bare boards, 2 of them assembled by JLCPCB on the top (Standard PCBA for the through-hole SMAs and headers; the 2x20 socket on the back is soldered at home).  Parts: JLCPCB's parts API at the times in the table.  Fees: the ECP5-2ADC-2DAC cart of 2026-10-09 (CLAUDE_PCB.md section 8).  The bare boards and the shipping are estimates with a range; the cart replaces them.

## The three buckets

| where | what | cost |
|---|---|--:|
| **JLCPCB** | 5 bare boards 120 x 100 mm, 4 layers, ENIG: model $28.50-$65.26 | $46.88 |
| | assembly: setup $25.75, stencils $8.27, fixture $16.54, feeder loading 45 Extended codes x $2.70 = $121.50, SMT 984 pads x 2 boards, through-hole 64 joints x 2, packaging, confirmation | $185.71 |
| | their parts: 70 BOM lines, 347 placements a board, with attrition, x 1.0066 | $324.32 |
| | US duty, 35 % of the above, collected under DDP | $194.92 |
| | shipping, UPS Express Saver DDP | $25.00-$40.00 |
| | **JLCPCB total** | **$776.82-$791.82** |
| **Digi-Key** | the consigned parts (table below): $129.64, plus 9.5 % tax and $8.00 shipping | **$149.96** |
| | shipping the consignment to JLCPCB (USPS Priority International to FedEx) | $35.00-$60.00 |
| **other** | the bench and the field (table below) | **$139.00-$267.00** |
| | **everything** | **$1100.78-$1268.78** |

## Digi-Key: the consigned parts

| key | MPN | Digi-Key number | a board | order | unit | line | seen |
|---|---|---|--:|--:|--:|--:|---|
| ADL5380 | ADL5380ACPZ-R7 | ADL5380ACPZ-R7CT-ND | 1 | 4 | $17.96 | $71.84 | Digi-Key 4,527 at $17.96 (1-9), Jason 2026-10-09 |
| ADL5375 | ADL5375-05ACPZ-R7 | ADL5375-05ACPZ-R7CT-ND | 1 | 4 | $14.12 | $56.48 | Digi-Key 2,262 at $14.12, aggregator snapshot 2026-10-09 |
| BALUN | 5400BL15B0050001E | 712-1363-1-ND | 1 | 4 | $0.33 | $1.32 | Digi-Key, under the new number 5400BL15B0050001E |

The order is the placements on the assembled boards plus one spare each for JLCPCB's attrition and one for the bench.  JLCPCB had 8 ADL5380 and 6 ADL5375-05 in stock on 2026-10-09 at $23.60 and $16.00: buying those two from their stock and consigning only the balun (none in stock anywhere at JLCPCB: 5400BL15B050E, HHM1595A1, TCW4-582+ all 0) saves the chips' consignment handling but costs $15 more on the parts; the consignment shipment is needed either way for the balun.

## Other: the bench and the field

| item | low | high |
|---|--:|--:|
| SMA attenuators: 30 dB (loopback), 20 dB x 2 (in front of the PA modules) | $30.00 | $50.00 |
| U.FL-to-SMA pigtails, 10 | $12.00 | $18.00 |
| MMCX-to-SMA leads, 4 (REF OUT and the three MMCX monitors, Response 10) | $10.00 | $16.00 |
| 5.8 GHz whips, SMA, x 4 | $16.00 | $24.00 |
| SMA leads: 3 x 150 mm, 2 x 1 m; 50 ohm terminations x 2 | $20.00 | $35.00 |
| USB-C PD power banks 5 V / 3 A x 2 (the amplifiers in the field) | $40.00 | $60.00 |
| M3 standoffs and screws (nylon kit) | $6.00 | $10.00 |
| a heatsink or fan for the 2 W PA module (it dissipates about 9 W) | $5.00 | $12.00 |
| a second PA ($29 with shipping) and LNA ($13) module for the far end, when the tests demand | $0.00 | $42.00 |

## What to look at

- **C17271830 HMC536MS8G**: 5 in stock against 2 for this order
- Feeder loading is the largest assembly fee after the setup: 45 Extended codes x $2.70 = $121.50.  Every value merged saves $2.70.
- Hand-soldering the 2x20 socket (J302, alone on the back) makes the order one-sided: half the setup and the stencil, its feeder and joints, about $38 before duty.  Economic PCBA would not take the through-hole SMAs and headers, so Standard it stays.

## Parts (70 BOM lines)

| LCSC | part | a board | ordered | library | unit | line | stock | asked |
|---|---|--:|--:|---|--:|--:|--:|---|
| C2058382 | THS4541IRGTT (THS4541) | 4 | 8 | Extended | $7.1256 | $57.00 | 380 | 2026-10-11 23:49 |
| C650158 | AD5696RARUZ (AD5696R) | 1 | 2 | Extended | $22.2398 | $44.48 | 7 | 2026-10-11 23:49 |
| C7458627 | MAX2871ETJ+T (MAX2871) | 2 | 4 | Extended | $9.9269 | $39.71 | 3,162 | 2026-10-11 23:49 |
| C208262 | ADL5611ARKZ-R7 (ADL5611) | 3 | 6 | Extended | $5.9725 | $35.84 | 3,016 | 2026-10-11 23:49 |
| C5213955 | TLV3603DCKR (TLV3603) | 4 | 8 | Extended | $3.9936 | $31.95 | 3,016 | 2026-10-11 23:49 |
| C17271830 | HMC536MS8G (HMC536) | 1 | 2 | Extended | $11.5393 | $23.08 | 5 | 2026-10-11 23:49 |
| C2974371 | TLV3601DCKR (TLV3601) | 4 | 8 | Extended | $2.8340 | $22.67 | 20,661 | 2026-10-11 23:49 |
| C470929 | PE43711B-Z (PE43711) | 1 | 2 | Extended | $3.7428 | $7.49 | 1,842 | 2026-10-11 23:48 |
| C496551 | BWSMA-KWE-Z001 (RX ANT/TX ANT/REF IN) | 9 | 18 | Extended | $0.4105 | $7.39 | 146,405 | 2026-10-11 23:48 |
| C627342 | MCP4728A1T-E/UN (MCP4728A1 0x61) | 1 | 2 | Extended | $2.9920 | $5.98 | 50 | 2026-10-11 23:49 |
| C478093 | MCP4728T-E/UN (MCP4728) | 1 | 2 | Extended | $2.6206 | $5.24 | 20,870 | 2026-10-11 23:49 |
| C2059281 | OPA2388IDGKR (OPA2388) | 1 | 2 | Extended | $2.2884 | $4.58 | 1,695 | 2026-10-11 23:49 |
| C5137198 | BWMMCX-KE (ERR MON/VC MON/REF O) | 5 | 10 | Extended | $0.4528 | $4.53 | 12,411 | 2026-10-11 23:48 |
| C5119013 | TC32H4-25.000-33GNDTNL (TCXO 25MHz) | 1 | 2 | Extended | $1.5685 | $3.14 | 473 | 2026-10-11 23:49 |
| C5179998 | SX3V25.000B20100F30TNN (VCXO 25MHz) | 1 | 2 | Extended | $1.5033 | $3.01 | 413 | 2026-10-11 23:49 |
| C88374 | U.FL-R-SMT-1(80) (RX MON/CMP I MON/I M) | 12 | 26 | Extended | $0.1137 | $2.96 | 97,866 | 2026-10-11 23:48 |
| C37593 | ADS1115IDGSR (ADS1115) | 1 | 2 | Extended | $1.2216 | $2.44 | 25,128 | 2026-10-11 23:49 |
| C15850 | CL21A106KAYNNNE (10uF) | 10 | 30 | Basic | $0.0688 | $2.06 | 4,206,459 | 2026-10-11 23:48 |
| C210262 | SKY65404-31 (SKY65404-31) | 1 | 2 | Extended | $0.8991 | $1.80 | 1,005 | 2026-10-11 23:48 |
| C882469 | LQW15AN27NG80D (27nH) | 8 | 20 | Extended | $0.0898 | $1.80 | 19,534 | 2026-10-11 23:48 |
| C2862740 | TPS7A2033PDBVR (TPS7A2033) | 4 | 8 | Extended | $0.2155 | $1.72 | 193,993 | 2026-10-11 23:49 |
| C45783 | CL21A226MAQNNNE (22uF) | 3 | 6 | Basic | $0.2369 | $1.42 | 3,634,715 | 2026-10-11 23:48 |
| C15127 | AO3401A (AO3401A) | 2 | 8 | Basic | $0.1018 | $0.81 | 683,803 | 2026-10-11 23:48 |
| C46388 | TS5A3159DCKR (TS5A3159) | 1 | 2 | Extended | $0.3753 | $0.75 | 37,015 | 2026-10-11 23:49 |
| C8207 | SN74LVC1G04DCKR (74LVC1G04) | 2 | 8 | Extended | $0.0838 | $0.67 | 75,977 | 2026-10-11 23:49 |
| C14461 | SN74LVC2G34DCKR (74LVC2G34) | 1 | 4 | Extended | $0.1592 | $0.64 | 22,430 | 2026-10-11 23:49 |
| C170182 | 1206N104J500CT (100nF) | 1 | 4 | Extended | $0.1587 | $0.63 | 173,595 | 2026-10-11 23:48 |
| C1525 | CL05B104KO5NNNC (100nF) | 60 | 130 | Basic | $0.0045 | $0.58 | 24,145,880 | 2026-10-11 23:48 |
| C10425 | SN74LVC1G17DCKR (74LVC1G17) | 2 | 8 | Extended | $0.0711 | $0.57 | 98,666 | 2026-10-11 23:49 |
| C23380874 | LP5907MFX-3.3 (LP5907 3.3V) | 1 | 4 | Extended | $0.1349 | $0.54 | 1,905 | 2026-10-11 23:49 |
| C113126 | LQW18AN43NG00D (43nH) | 3 | 10 | Extended | $0.0535 | $0.54 | 27,528 | 2026-10-11 23:48 |
| C210837 | MF-MSMF200-2 (2A PTC) | 2 | 8 | Extended | $0.0647 | $0.52 | 16,411 | 2026-10-11 23:48 |
| C23630 | CL10A225KO8NNNC (2.2uF) | 8 | 26 | Basic | $0.0181 | $0.47 | 3,693,393 | 2026-10-11 23:48 |
| C38663 | SN74LVC1G3157DCKR (74LVC1G3157) | 1 | 6 | Extended | $0.0727 | $0.44 | 209,067 | 2026-10-11 23:49 |
| C19270534 | 1010100506TR (100uF) | 1 | 3 | Extended | $0.1364 | $0.41 | 4,081 | 2026-10-11 22:29 |
| C165948 | TYPE-C-31-M-12 (USB-C 5V) | 1 | 2 | Extended | $0.1860 | $0.37 | 406,887 | 2026-10-11 23:48 |
| C144499 | AC1206FR-072R2L (2.2R) | 2 | 14 | Extended | $0.0264 | $0.37 | 95,275 | 2026-10-11 23:48 |
| C52923 | CL05A105KA5NQNC (1uF) | 15 | 40 | Basic | $0.0087 | $0.35 | 7,389,171 | 2026-10-11 23:48 |
| C85840 | BLM21PG221SN1D (220R@100MHz 2A) | 1 | 10 | Extended | $0.0344 | $0.34 | 219,226 | 2026-10-11 23:48 |
| C162241 | GRM1885C1H682JA01D (6.8nF) | 2 | 12 | Extended | $0.0222 | $0.27 | 101,035 | 2026-10-11 23:48 |
| C113952 | SMAJ5.0A (SMAJ5.0A) | 1 | 6 | Extended | $0.0411 | $0.25 | 563,914 | 2026-10-11 23:48 |
| C1552 | 0402CG1R5C500NT (1.5pF) | 22 | 54 | Preferred | $0.0045 | $0.24 | 217,148 | 2026-10-11 23:48 |
| C2937625 | PZ254V-11-03P (SIGN/SEL/REF/TR) | 5 | 12 | Extended | $0.0198 | $0.24 | 971,874 | 2026-10-11 23:48 |
| C11702 | 0402WGF1001TCE (1k) | 27 | 64 | Basic | $0.0035 | $0.22 | 8,113,164 | 2026-10-11 23:48 |
| C25744 | 0402WGF1002TCE (10k) | 22 | 54 | Basic | $0.0034 | $0.18 | 19,435,576 | 2026-10-11 23:48 |
| C2188753 | GCM1555C1H161JA16D (160pF) | 2 | 14 | Extended | $0.0123 | $0.17 | 9,057 | 2026-10-11 23:48 |
| C14441 | CL05C680JB5NNNC (68pF) | 3 | 18 | Preferred | $0.0081 | $0.15 | 124,131 | 2026-10-11 23:48 |
| C8545 | 2N7002 (2N7002) | 1 | 7 | Basic | $0.0178 | $0.12 | 1,367,779 | 2026-10-11 23:48 |
| C2286 | KT-0603R (5V/3V3) | 2 | 14 | Basic | $0.0076 | $0.11 | 7,174,565 | 2026-10-11 23:48 |
| C95042 | MLG1005S0N6CT000 (0.6nH) | 1 | 12 | Extended | $0.0076 | $0.09 | 18,950 | 2026-10-11 23:48 |
| C25741 | 0402WGF1003TCE (100k) | 14 | 38 | Basic | $0.0021 | $0.08 | 8,337,573 | 2026-10-11 23:48 |
| C285052 | 0402CG0R5B500NT (0.5pF) | 1 | 12 | Extended | $0.0065 | $0.08 | 74,051 | 2026-10-11 23:48 |
| C492401 | PZ254V-11-02P (HDR 5V/50R) | 2 | 4 | Extended | $0.0186 | $0.07 | 1,199,496 | 2026-10-11 23:48 |
| C282239 | CC0402JRNPO9BN391 (390pF) | 2 | 14 | Extended | $0.0050 | $0.07 | 66,778 | 2026-10-11 23:48 |
| C1523 | 0402B102K500NT (1nF) | 3 | 16 | Basic | $0.0041 | $0.07 | 3,356,242 | 2026-10-11 23:48 |
| C1562 | 0402CG330J500NT (33pF) | 4 | 18 | Basic | $0.0032 | $0.06 | 1,496,280 | 2026-10-11 23:48 |
| C25120 | 0402WGF499JTCE (49.9R) | 5 | 20 | Basic | $0.0027 | $0.05 | 1,275,084 | 2026-10-11 23:48 |
| C25905 | 0402WGF5101TCE (5.1k) | 4 | 18 | Basic | $0.0024 | $0.04 | 5,586,743 | 2026-10-11 23:48 |
| C25105 | 0402WGF330JTCE (33R) | 11 | 32 | Basic | $0.0012 | $0.04 | 1,635,588 | 2026-10-11 23:48 |
| C137968 | RC0402FR-074K02L (4.02k) | 4 | 18 | Extended | $0.0021 | $0.04 | 334,732 | 2026-10-11 23:48 |
| C4109 | 0402WGF2001TCE (2k) | 2 | 14 | Basic | $0.0026 | $0.04 | 7,982,777 | 2026-10-11 23:48 |
| C5126227 | FRC0402F4530TS (453R) | 6 | 22 | Extended | $0.0015 | $0.03 | 75,965 | 2026-10-11 23:48 |
| C25900 | 0402WGF4701TCE (4.7k) | 1 | 12 | Basic | $0.0027 | $0.03 | 14,410,758 | 2026-10-11 23:48 |
| C25879 | 0402WGF2201TCE (2.2k) | 4 | 18 | Basic | $0.0017 | $0.03 | 2,287,019 | 2026-10-11 23:48 |
| C17168 | 0402WGF0000TCE (0R) | 1 | 12 | Basic | $0.0025 | $0.03 | 9,565,020 | 2026-10-11 23:48 |
| C25102 | 0402WGF3000TCE (300R) | 2 | 14 | Preferred | $0.0021 | $0.03 | 801,305 | 2026-10-11 23:48 |
| C25135 | 0402WGF8200TCE (820R) | 2 | 14 | Extended | $0.0018 | $0.03 | 118,192 | 2026-10-11 23:48 |
| C25765 | 0402WGF2002TCE (20k) | 4 | 18 | Basic | $0.0013 | $0.02 | 2,614,361 | 2026-10-11 23:48 |
| C25076 | 0402WGF1000TCE (100R) | 3 | 16 | Basic | $0.0012 | $0.02 | 9,126,171 | 2026-10-11 23:48 |
| C25132 | 0402WGF7500TCE (750R) | 2 | 14 | Extended | $0.0012 | $0.02 | 943,006 | 2026-10-11 23:48 |
