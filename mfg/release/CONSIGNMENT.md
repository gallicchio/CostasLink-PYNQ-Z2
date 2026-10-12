# CostasLink-PYNQ-Z2 rev A: the consigned parts

Written by `mfg/make_release.py` on 2026-10-12 for 2 assembled boards.  Three parts are not deep enough at JLCPCB to order from their stock (PLAN.md section 4), so they are bought at Digi-Key and sent to JLCPCB, who fit them like any other part.  In `BOM_JLCPCB.csv` each sits under the LCSC code JLCPCB's consigned-parts process files it by, with CONSIGNED in its Note column.

## What to buy

| part | MPN | Digi-Key | Mouser | refs | a board | **send** | unit | line | stock seen |
|---|---|---|---|---|--:|--:|--:|--:|---|
| BALUN | 5400BL15B0050001E | 712-5400BL15B0050001ECT-ND | 609-5400BL15B0050001E | T101 | 1 | **4** | $0.69 | $2.76 | Digi-Key 6,874 at $0.69 (1-9), its search 2026-10-12 |
| ADL5375 | ADL5375-05ACPZ-R7 | 505-ADL5375-05ACPZ-R7CT-ND | 584-ADL5375-05ACPZR7 | U201 | 1 | **4** | $17.26 | $69.04 | Digi-Key 5,829 at $17.26 (1-9), its product page 2026-10-12 |
| ADL5380 | ADL5380ACPZ-R7 | 505-ADL5380ACPZ-R7CT-ND | 584-ADL5380ACPZ-R7 | U104 | 1 | **4** | $17.96 | $71.84 | Digi-Key 4,512 at $17.96 (1-9), its product page 2026-10-12 |

The quantity to send is the placements on the 2 assembled boards plus 2 spares a line: JLCPCB asks for attrition on consigned parts, and a loose spare serves the bench.  Parts $143.64, plus 9.5 % sales tax and $8.00 shipping: about $165.29 (mfg/cost_estimate.py's Digi-Key bucket).

**For home, in the same cart** (hand_solder_bom.csv; these stay with you, they do not go to JLCPCB):

| part | MPN | Digi-Key | buy | unit | why |
|---|---|---|--:|--:|---|
| J302, the PYNQ-Z2 socket | PPTC202LFBN-RC | S6104-ND | 3 | $2.14 | Sullins 2x20 female, 2.54 mm, 8.51 mm insulator, through-hole: C2977589's height |
| jumper shunts | SPC02SYAN | S9001-ND | 20 | $0.03 | Sullins 2.54 mm shunt |

## How JLCPCB takes them

1. Before the order, on jlcpcb.com under **Parts Manager > Consigned Parts** (their name for parts the customer supplies), register each part by its LCSC code below so the BOM line matches it:

   - **C2837312** = 5400BL15B0050001E (JLCPCB's model 5400BL15B050E; the maker's new number is 5400BL15B0050001E): 4 pieces for T101
   - **C579150** = ADL5375-05ACPZ-R7 (JLCPCB's model ADL5375-05ACPZ-R7): 4 pieces for U201
   - **C579152** = ADL5380ACPZ-R7 (JLCPCB's model ADL5380ACPZ-R7): 4 pieces for U104

2. JLCPCB gives the consignment a shipping label and the address of its consignment warehouse in Shenzhen (the Consigned Parts page shows both); send the three reels' cut tape in one padded envelope, each bag labelled with its LCSC code and the order number (USPS Priority Mail International or FedEx: $35.00-$60.00, the estimate's range).
3. In the order's BOM matching step, each of these lines must show the consigned stock as its source, not JLCPCB's shelf stock (JLCPCB had 0 of C2837312, 4 of C579150, 18 of C579152 when this release was written: too few, or none, to rely on).
4. Assembly starts when the parts have arrived and been counted; allow a week for the post.

The parts, and why (gen/parts.py):

- **BALUN** (T101): 1:1 balun 4.9-5.875 GHz at the ADL5380's RF input (the datasheet's 5.8 GHz circuit). CONSIGNED: bought at Digi-Key/Mouser, shipped to JLCPCB (PLAN.md section 4)
- **ADL5375** (U201): IQ modulator 0.4-6 GHz, 0.5 V baseband bias: the transmitter. CONSIGNED: bought at Digi-Key/Mouser, shipped to JLCPCB (PLAN.md section 4)
- **ADL5380** (U104): IQ demodulator 0.4-6 GHz, 390 MHz baseband, DC-coupled outputs: the Costas loop's phase detector. CONSIGNED: bought at Digi-Key/Mouser, shipped to JLCPCB (PLAN.md section 4)

