# hardware/lib: everything the board is drawn with

Made by `gen/library.py`; do not edit by hand.

- `CostasLink.kicad_sym`: KiCad's own symbols (flattened, so nothing points at a library you
  may not have), plus the ones drawn for this board in `gen/symbols.py` (MAX2871, ADL5380,
  ADL5375, PE43711, ADL5611, SKY65404-31, THS4541, TLV3601, the two analog switches, the
  oscillators, the balun, the power flags).
- `CostasLink.pretty/`: KiCad's own footprints, and four from `gen/footprints.py`: the LNA
  (JLCPCB's land pattern), the balun (TDK's drawing), the 2x20 socket (the GPSDO board's
  drawing) and the SMA (the ECP5 board's copy of JLCPCB's drawing).
- `CostasLink.3dshapes/`: KiCad's models, the SMA's and the USB-C's (vendored from the earlier
  boards), and plain boxes where KiCad names a model it never drew (`STAND_IN`).

Licences: KiCad's libraries are CC-BY-SA 4.0 with the KiCad libraries' exception (using them in
a design does not put the design under CC-BY-SA).  The rest is this project's (`LICENSE`).
