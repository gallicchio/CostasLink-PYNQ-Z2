# CostasLink-PYNQ-Z2 rev A: what the first order costs

Written by `mfg/cost_estimate.py` on 2026-10-12 for 5 bare boards, 2 of them assembled by JLCPCB on the top (Standard PCBA for the through-hole SMAs and headers; the 2x20 socket on the back is soldered at home).  Parts: JLCPCB's parts API at the times in the table.  Fees: the ECP5-2ADC-2DAC cart of 2026-10-09 (CLAUDE_PCB.md section 8).  The bare boards and the shipping are estimates with a range; the cart replaces them.

## The three buckets

| where | what | cost |
|---|---|--:|
| **JLCPCB** | 5 bare boards 120 x 100 mm, 4 layers, ENIG: model $28.50-$65.26 | $46.88 |
| | assembly: setup $25.75, stencils $8.27, fixture $16.54, feeder loading 49 Extended codes x $2.70 = $132.30, SMT 1100 pads x 2 boards, through-hole 93 joints x 2, packaging, confirmation, depanel | $200.13 |
| | their parts: 77 BOM lines, 381 placements a board, with attrition, x 1.0066 | $353.05 |
| | US duty, 35 % of the above, collected under DDP | $210.02 |
| | shipping, UPS Express Saver DDP | $25.00-$40.00 |
| | **JLCPCB total** | **$835.08-$850.08** |
| **Digi-Key** | the consigned parts (table below): $143.64, plus 9.5 % tax and $8.00 shipping | **$165.29** |
| | shipping the consignment to JLCPCB (USPS Priority International to FedEx) | $35.00-$60.00 |
| **other** | the bench and the field (table below) | **$141.50-$271.00** |
| | **everything** | **$1176.86-$1346.36** |

## Digi-Key: the consigned parts

| key | MPN | Digi-Key number | a board | order | unit | line | seen |
|---|---|---|--:|--:|--:|--:|---|
| ADL5380 | ADL5380ACPZ-R7 | 505-ADL5380ACPZ-R7CT-ND | 1 | 4 | $17.96 | $71.84 | Digi-Key 4,512 at $17.96 (1-9), its product page 2026-10-12 |
| ADL5375 | ADL5375-05ACPZ-R7 | 505-ADL5375-05ACPZ-R7CT-ND | 1 | 4 | $17.26 | $69.04 | Digi-Key 5,829 at $17.26 (1-9), its product page 2026-10-12 |
| BALUN | 5400BL15B0050001E | 712-5400BL15B0050001ECT-ND | 1 | 4 | $0.69 | $2.76 | Digi-Key 6,874 at $0.69 (1-9), its search 2026-10-12 |

The order is the placements on the assembled boards plus 2 spares a line: JLCPCB's attrition and one for the bench.  JLCPCB had 8 ADL5380 and 6 ADL5375-05 in stock on 2026-10-09 at $23.60 and $16.00: buying those two from their stock and consigning only the balun (none in stock anywhere at JLCPCB: 5400BL15B050E, HHM1595A1, TCW4-582+ all 0) saves the chips' consignment handling but costs $8.76 more on the parts; the consignment shipment is needed either way for the balun.

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
- Feeder loading is the largest assembly fee after the setup: 49 Extended codes x $2.70 = $132.30.  Every value merged saves $2.70.
- Hand-soldering the 2x20 socket (J302, alone on the back) makes the order one-sided: half the setup and the stencil, its feeder and joints, about $38 before duty.  Economic PCBA would not take the through-hole SMAs and headers, so Standard it stays.

## Parts (77 BOM lines)

| LCSC | part | a board | ordered | library | unit | line | stock | asked |
|---|---|--:|--:|---|--:|--:|--:|---|
| C2058382 | THS4541IRGTT (THS4541) | 4 | 8 | Extended | $7.1256 | $57.00 | 328 | 2026-10-12 10:30 |
| C650158 | AD5696RARUZ (AD5696R) | 1 | 2 | Extended | $22.2398 | $44.48 | 7 | 2026-10-12 10:30 |
| C7458627 | MAX2871ETJ+T (MAX2871) | 2 | 4 | Extended | $9.9269 | $39.71 | 3,160 | 2026-10-12 10:30 |
| C208262 | ADL5611ARKZ-R7 (ADL5611) | 3 | 6 | Extended | $5.9725 | $35.84 | 3,017 | 2026-10-12 10:30 |
| C5213955 | TLV3603DCKR (TLV3603) | 4 | 8 | Extended | $3.9936 | $31.95 | 2,916 | 2026-10-12 10:30 |
| C17271830 | HMC536MS8G (HMC536) | 1 | 2 | Extended | $11.5393 | $23.08 | 5 | 2026-10-12 10:30 |
| C2974371 | TLV3601DCKR (TLV3601) | 4 | 8 | Extended | $2.8340 | $22.67 | 20,653 | 2026-10-12 10:30 |
| C42711 | AD8310ARMZ-REEL7 (AD8310) | 1 | 2 | Extended | $10.0686 | $20.14 | 2,828 | 2026-10-12 10:30 |
| C2059281 | OPA2388IDGKR (OPA2388) | 2 | 4 | Extended | $2.2884 | $9.15 | 1,845 | 2026-10-12 10:30 |
| C470929 | PE43711B-Z (PE43711) | 1 | 2 | Extended | $3.7428 | $7.49 | 1,840 | 2026-10-12 10:30 |
| C496551 | BWSMA-KWE-Z001 (RX ANT/TX ANT/REF IN) | 9 | 18 | Extended | $0.4105 | $7.39 | 145,072 | 2026-10-12 10:29 |
| C627342 | MCP4728A1T-E/UN (MCP4728A1 0x61) | 1 | 2 | Extended | $2.9920 | $5.98 | 50 | 2026-10-12 10:30 |
| C478093 | MCP4728T-E/UN (MCP4728) | 1 | 2 | Extended | $2.6206 | $5.24 | 20,870 | 2026-10-12 10:30 |
| C37593 | ADS1115IDGSR (ADS1115) | 2 | 4 | Extended | $1.2216 | $4.89 | 24,052 | 2026-10-12 10:30 |
| C5137198 | BWMMCX-KE (ERR MON/VC MON/REF O) | 5 | 10 | Extended | $0.4528 | $4.53 | 12,411 | 2026-10-12 10:29 |
| C5119013 | TC32H4-25.000-33GNDTNL (TCXO 25MHz) | 1 | 2 | Extended | $1.5685 | $3.14 | 463 | 2026-10-12 10:31 |
| C5179998 | SX3V25.000B20100F30TNN (VCXO 25MHz) | 1 | 2 | Extended | $1.5033 | $3.01 | 413 | 2026-10-12 10:31 |
| C88374 | U.FL-R-SMT-1(80) (RX MON/CMP I MON/I M) | 12 | 26 | Extended | $0.1137 | $2.96 | 96,706 | 2026-10-12 10:29 |
| C15850 | CL21A106KAYNNNE (10uF) | 10 | 30 | Basic | $0.0688 | $2.06 | 4,136,211 | 2026-10-12 10:29 |
| C210262 | SKY65404-31 (SKY65404-31) | 1 | 2 | Extended | $0.8991 | $1.80 | 1,005 | 2026-10-12 10:30 |
| C882469 | LQW15AN27NG80D (27nH) | 8 | 20 | Extended | $0.0898 | $1.80 | 19,534 | 2026-10-12 10:30 |
| C2862740 | TPS7A2033PDBVR (TPS7A2033) | 4 | 8 | Extended | $0.2155 | $1.72 | 185,077 | 2026-10-12 10:30 |
| C45783 | CL21A226MAQNNNE (22uF) | 3 | 6 | Basic | $0.2369 | $1.42 | 3,590,687 | 2026-10-12 10:29 |
| C15127 | AO3401A (AO3401A) | 2 | 8 | Basic | $0.1018 | $0.81 | 676,006 | 2026-10-12 10:30 |
| C46388 | TS5A3159DCKR (TS5A3159) | 1 | 2 | Extended | $0.3753 | $0.75 | 36,710 | 2026-10-12 10:30 |
| C82919 | LQW15AN6N8G00D (6.8nH) | 3 | 10 | Extended | $0.0727 | $0.73 | 23,999 | 2026-10-12 10:29 |
| C8207 | SN74LVC1G04DCKR (74LVC1G04) | 2 | 8 | Extended | $0.0838 | $0.67 | 75,982 | 2026-10-12 10:30 |
| C14461 | SN74LVC2G34DCKR (74LVC2G34) | 1 | 4 | Extended | $0.1592 | $0.64 | 22,361 | 2026-10-12 10:30 |
| C170182 | 1206N104J500CT (100nF) | 1 | 4 | Extended | $0.1587 | $0.63 | 173,559 | 2026-10-12 10:29 |
| C1525 | CL05B104KO5NNNC (100nF) | 68 | 146 | Basic | $0.0039 | $0.57 | 23,799,480 | 2026-10-12 10:29 |
| C10425 | SN74LVC1G17DCKR (74LVC1G17) | 2 | 8 | Extended | $0.0711 | $0.57 | 98,498 | 2026-10-12 10:30 |
| C23380874 | LP5907MFX-3.3 (LP5907 3.3V) | 1 | 4 | Extended | $0.1349 | $0.54 | 1,918 | 2026-10-12 10:30 |
| C113126 | LQW18AN43NG00D (43nH) | 3 | 10 | Extended | $0.0535 | $0.54 | 27,537 | 2026-10-12 10:29 |
| C210837 | MF-MSMF200-2 (2A PTC) | 2 | 8 | Extended | $0.0647 | $0.52 | 16,411 | 2026-10-12 10:29 |
| C23630 | CL10A225KO8NNNC (2.2uF) | 8 | 26 | Basic | $0.0181 | $0.47 | 3,671,773 | 2026-10-12 10:29 |
| C38663 | SN74LVC1G3157DCKR (74LVC1G3157) | 1 | 6 | Extended | $0.0727 | $0.44 | 208,578 | 2026-10-12 10:30 |
| C19270534 | 1010100506TR (100uF) | 1 | 3 | Extended | $0.1364 | $0.41 | 4,081 | 2026-10-12 10:29 |
| C165948 | TYPE-C-31-M-12 (USB-C 5V) | 1 | 2 | Extended | $0.1860 | $0.37 | 401,898 | 2026-10-12 10:29 |
| C144499 | AC1206FR-072R2L (2.2R) | 2 | 14 | Extended | $0.0264 | $0.37 | 94,485 | 2026-10-12 10:30 |
| C52923 | CL05A105KA5NQNC (1uF) | 15 | 40 | Basic | $0.0087 | $0.35 | 7,291,274 | 2026-10-12 10:29 |
| C85840 | BLM21PG221SN1D (220R@100MHz 2A) | 1 | 10 | Extended | $0.0344 | $0.34 | 218,329 | 2026-10-12 10:29 |
| C13564 | NCP18XH103F03RB (NTC 10k) | 1 | 6 | Extended | $0.0465 | $0.28 | 184,835 | 2026-10-12 10:30 |
| C162241 | GRM1885C1H682JA01D (6.8nF) | 2 | 12 | Extended | $0.0222 | $0.27 | 100,622 | 2026-10-12 10:29 |
| C113952 | SMAJ5.0A (SMAJ5.0A) | 1 | 6 | Extended | $0.0411 | $0.25 | 558,513 | 2026-10-12 10:29 |
| C1552 | 0402CG1R5C500NT (1.5pF) | 22 | 54 | Preferred | $0.0045 | $0.24 | 216,568 | 2026-10-12 10:29 |
| C11702 | 0402WGF1001TCE (1k) | 29 | 68 | Basic | $0.0035 | $0.24 | 8,074,474 | 2026-10-12 10:30 |
| C25744 | 0402WGF1002TCE (10k) | 30 | 70 | Basic | $0.0034 | $0.24 | 19,242,347 | 2026-10-12 10:30 |
| C2937625 | PZ254V-11-03P (SIGN/SEL/REF/TR) | 5 | 12 | Extended | $0.0198 | $0.24 | 967,503 | 2026-10-12 10:29 |
| C2188753 | GCM1555C1H161JA16D (160pF) | 2 | 14 | Extended | $0.0123 | $0.17 | 8,877 | 2026-10-12 10:29 |
| C81598 | 1N4148W (1N4148W) | 1 | 12 | Basic | $0.0123 | $0.15 | 4,802,887 | 2026-10-12 10:29 |
| C14441 | CL05C680JB5NNNC (68pF) | 3 | 18 | Preferred | $0.0081 | $0.15 | 121,585 | 2026-10-12 10:29 |
| C8545 | 2N7002 (2N7002) | 1 | 7 | Basic | $0.0178 | $0.12 | 1,336,328 | 2026-10-12 10:30 |
| C2286 | KT-0603R (5V/3V3) | 2 | 14 | Basic | $0.0076 | $0.11 | 7,120,820 | 2026-10-12 10:29 |
| C95042 | MLG1005S0N6CT000 (0.6nH) | 1 | 12 | Extended | $0.0076 | $0.09 | 18,950 | 2026-10-12 10:29 |
| C15195 | CL05B103KB5NNNC (10nF) | 3 | 16 | Basic | $0.0050 | $0.08 | 3,419,263 | 2026-10-12 10:29 |
| C282239 | CC0402JRNPO9BN391 (390pF) | 3 | 16 | Extended | $0.0050 | $0.08 | 66,778 | 2026-10-12 10:29 |
| C25741 | 0402WGF1003TCE (100k) | 14 | 38 | Basic | $0.0021 | $0.08 | 8,007,378 | 2026-10-12 10:30 |
| C285052 | 0402CG0R5B500NT (0.5pF) | 1 | 12 | Extended | $0.0065 | $0.08 | 63,761 | 2026-10-12 10:29 |
| C492401 | PZ254V-11-02P (HDR 5V/50R) | 2 | 4 | Extended | $0.0186 | $0.07 | 1,170,274 | 2026-10-12 10:29 |
| C1523 | 0402B102K500NT (1nF) | 4 | 18 | Basic | $0.0041 | $0.07 | 3,311,727 | 2026-10-12 10:29 |
| C1562 | 0402CG330J500NT (33pF) | 4 | 18 | Basic | $0.0032 | $0.06 | 1,475,025 | 2026-10-12 10:29 |
| C25120 | 0402WGF499JTCE (49.9R) | 5 | 20 | Basic | $0.0027 | $0.05 | 1,258,274 | 2026-10-12 10:30 |
| C1546 | 0402CG101J500NT (100pF) | 1 | 12 | Basic | $0.0042 | $0.05 | 4,170,106 | 2026-10-12 10:29 |
| C25905 | 0402WGF5101TCE (5.1k) | 4 | 18 | Basic | $0.0024 | $0.04 | 5,531,827 | 2026-10-12 10:30 |
| C25105 | 0402WGF330JTCE (33R) | 11 | 32 | Basic | $0.0012 | $0.04 | 1,589,287 | 2026-10-12 10:30 |
| C137968 | RC0402FR-074K02L (4.02k) | 4 | 18 | Extended | $0.0021 | $0.04 | 334,208 | 2026-10-12 10:30 |
| C4109 | 0402WGF2001TCE (2k) | 2 | 14 | Basic | $0.0026 | $0.04 | 7,970,109 | 2026-10-12 10:30 |
| C5126227 | FRC0402F4530TS (453R) | 6 | 22 | Extended | $0.0015 | $0.03 | 74,965 | 2026-10-12 10:30 |
| C25900 | 0402WGF4701TCE (4.7k) | 1 | 12 | Basic | $0.0027 | $0.03 | 14,275,548 | 2026-10-12 10:30 |
| C25879 | 0402WGF2201TCE (2.2k) | 4 | 18 | Basic | $0.0017 | $0.03 | 2,267,420 | 2026-10-12 10:30 |
| C17168 | 0402WGF0000TCE (0R) | 1 | 12 | Basic | $0.0025 | $0.03 | 9,323,955 | 2026-10-12 10:30 |
| C25102 | 0402WGF3000TCE (300R) | 2 | 14 | Preferred | $0.0021 | $0.03 | 800,312 | 2026-10-12 10:30 |
| C25135 | 0402WGF8200TCE (820R) | 2 | 14 | Extended | $0.0018 | $0.03 | 118,064 | 2026-10-12 10:30 |
| C474132 | 0402WGF4704TCE (4.7M) | 1 | 12 | Extended | $0.0020 | $0.02 | 46,290 | 2026-10-12 10:30 |
| C25765 | 0402WGF2002TCE (20k) | 4 | 18 | Basic | $0.0013 | $0.02 | 2,577,131 | 2026-10-12 10:30 |
| C25076 | 0402WGF1000TCE (100R) | 4 | 18 | Basic | $0.0012 | $0.02 | 8,883,588 | 2026-10-12 10:30 |
| C25132 | 0402WGF7500TCE (750R) | 2 | 14 | Extended | $0.0012 | $0.02 | 941,796 | 2026-10-12 10:30 |
