# Prompt 31's fresh reviews (2026-10-14)

Three independent reviews of build 33 (the state after Prompt 30 plus Prompt 31's balun swap), each by a
Claude Fable 5.1 agent that read the tree and wrote only to its own scratch directory, formed before it read
`DESIGN_REVIEW_RESPONSE.md` or the earlier `design_review_*/`.  The scripts beside each report are what it
measured with (`/usr/bin/python3 -I <script>` from this directory; the board scripts read the board file of
the build they reviewed, `git show a261e2c:CostasLink-PYNQ-Z2/hardware/CostasLink-PYNQ-Z2.kicad_pcb`).

- `REVIEW_A_schematic.md`: the schematic against the datasheets, pin by pin.  Found the two blocking faults
  of the round: both ADS1115 input filters drawn capacitor-first (100 nF on the fast arms' outputs), and no
  DC blocks between the balun and the ADL5380's RF inputs.
- `REVIEW_B_board_release.md`: the board and the JLCPCB package.  The SMA launches' inner-layer rings, the
  5 V rail through single vias, decoupling kept out by the fan band; everything else measured and right.
- `REVIEW_C_system.md`: the system as a red team.  The own-transmitter model and the compression limit, the
  oscillators' phase noise, the static phase error, the slow stage's overdrive recovery, WiFi against
  sign(I) x Q; probabilities and a salvage table.

What was done with each finding is in `../REVA_CHANGES.md` rows 32-36 and `../CLAUDE_CODE_CHAT.md`
Response 31.
