# Example data (board A)

A few small, representative records of the bench, kept in git so the formats and the tools can be seen without the
full record.  The full record (about 250 MB of JSONL and JSON, 2026-10-28 on) stays on the bench PC in
`bringup/data/board_A/` and is not tracked (`.gitignore`); BRINGUP_LOG's paths point there.

| file | what | BRINGUP_LOG |
|---|---|---|
| `pullin_5200_20261031_061201.json` | the unlocked loop's VC rate against its offset from the lock, 5.2 GHz (the map of docs/LOCK.md section 6) | 4.12 |
| `eye_5000_20261031_033840.json` | CMP_I folded against the TX's own pins during PRBS, and timing-recovered segments with the recovery's state | 4.11 |
| `skewtrim_5000_20261031_054154.json` | I_OFF_F stepped against CMP_I's skew (RX_CDR_SKEW, the eye fold) and the push | 4.12 |
| `abuse3.log` | the automatic recovery from the PC against forced losses and noise bursts | 4.15 |
| `linkd2.log` | the recovery on the board itself (linkd), end to end | 4.16 |
| `shakeout1.log` | the link left alone with the B210's random interference | 4.17 |
