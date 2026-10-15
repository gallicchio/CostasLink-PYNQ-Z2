# CostasLink-PYNQ-Z2 rev A: the consigned parts

Written by `mfg/make_release.py` on 2026-10-14 for 2 assembled boards.  **Nothing is consigned on this order:** every part JLCPCB places is on its shelf, deep enough for the order (COST_ESTIMATE.md).  The balun is the TDK HHM1907B1 from JLCPCB's stock (Prompt 31; the Johanson 5400 the ADL5380's sheet uses has 0 there), and the two ADI chips are bought from JLCPCB's shelf.  No Parts Manager registration, no parcel to Shenzhen, no week of waiting.

**The fallback** (gen/parts.py consign=): ADL5380 C579152: JLCPCB 18 in stock at $21.61; ADL5375 C579150: JLCPCB 4 in stock at $16.39.  Each is bought from JLCPCB's shelf while the shelf covers the order; if it is short on the day, mfg/make_release.py consigns that line and this file says what to buy.  Consigning both would mean 8 pieces at Digi-Key, 4 of them the spares JLCPCB asks for as attrition and never used, plus tax, Digi-Key's shipping and the shipment to Shenzhen: $197.26-$222.26 against $76.04 on the shelf for the 4 pieces the boards need.  So for 2 boards a shelf part up to $121.22-$146.22 dearer than Digi-Key's price is still the cheaper buy, and with more boards the spares and the shipment are spread thinner (CLAUDE_PCB.md section 3).

**For home** (hand_solder_bom.csv; any distributor, or the drawer):

| part | MPN | Digi-Key | buy | unit | why |
|---|---|---|--:|--:|---|
| J302, the PYNQ-Z2 socket | PPTC202LFBN-RC | S6104-ND | 3 | $2.14 | Sullins 2x20 female, 2.54 mm, 8.51 mm insulator, through-hole: C2977589's height |
| jumper shunts | SPC02SYAN | S9001-ND | 20 | $0.03 | Sullins 2.54 mm shunt |
