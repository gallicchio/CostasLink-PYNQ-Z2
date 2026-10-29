# The rev A bring-up, from the bench PC

Started 2026-10-28, the day the boards came back (JLCPCB order 13544840A_Y21: 5 boards, 2 assembled).  The procedure is
[`../BRINGUP.md`](../BRINGUP.md); this folder is how it is run on the bench and what it found.

| file | what |
|---|---|
| [`BRINGUP_LOG.md`](BRINGUP_LOG.md) | what was done and measured, stage by stage, board by board, against each pass condition: the as-built rev A |
| [`REVB.md`](REVB.md) | everything a rev B should change, each with the measurement or reading that showed it |
| `bench.py` | the instruments (`~/lab-instrument-control`) and the board (the driver over the network) in one place; every reading appended to `data/board_<X>/<date>.jsonl` |
| `stages.py` | BRINGUP.md's measurements as procedures, each with its verdict (`python3 bringup/stages.py` lists them) |
| `bench_config.json` | the instruments' addresses and serial ports, the PYNQ's address (written with defaults the first time) |
| `deploy_pynq.sh`, `install_service.sh` | the overlay and the driver to the PYNQ; the server started at every boot |
| `data/` | the raw log (JSON lines) and the analyser's traces (CSV), one folder a board |

## How the pieces talk

```
 bench PC  --LAN-->  DSA875 spectrum analyzer (192.168.8.114, raw socket), SDS2104X Plus oscilloscope (.203),
                    SDG1032X function generator (.246)   (all three also on USB, once the udev rule is installed)
           --USB-RS232-->  E3646A power supply, output 1 (the board's 5 V); Fluke 45 multimeter (the rails)
           --USB 3-->  USRP B210 SDR (a 5.8 GHz carrier or a second receiver)
           --LAN-->  PYNQ-Z2 (192.168.8.142 by DHCP, or its static 192.168.2.99): netbus.py on port 5800 runs the
                     driver (gateware/driver/costaslink.py) against the overlay, as root
```

`gateware/driver/netbus.py` is new for the bring-up: the PYNQ serves its `CostasLink` object, one JSON line a call, so
`RemoteCostasLink("192.168.2.99").detectors()` runs on the board and returns here, and one program logs the board and the
instruments together.  It is tested end to end against the RTL simulation (`test_netbus.py`, in `make sim-driver`), and
`python3 gateware/driver/netbus.py serve --sim` serves the simulation on this PC for a rehearsal
(`COSTAS_PYNQ_HOST=127.0.0.1 python3 bringup/bench.py --board SIM board snapshot`).  In the simulation the driver's
waits are wall-clock, so `pll_init()` and I2C writes time out there; on the board they take milliseconds.

## Setting up (once)

1. **The SD card:** on the bench since 2026-10-29, the stock PYNQ 3.0.1 (`~/Downloads/pynq_z2_v3.0.1.img`), with the
   overlay built by Vivado 2022.1 (PYNQ 3.0's tools) in `build/pynq/overlay_2022.1/`:
   `OVERLAY=build/pynq/overlay_2022.1 bringup/deploy_pynq.sh`.  PYNQ 3.1.1 (`~/Downloads/pynq_z2_v3.1.1.zip`) goes with
   the 2024.1 overlay in `build/pynq/overlay/`.  With the card in a reader, find it with `lsblk`
   (a removable disk of the card's size, nothing mounted from it that matters), then
   `sudo dd if=~/Downloads/pynq_z2_v3.1.1/pynq_z2_v3.1.1.img of=/dev/sdX bs=4M conv=fsync status=progress`.
2. **The network:** the PYNQ's Ethernet to the lab switch (DHCP gives it a 192.168.8.x address: read it on the serial
   console, the micro-USB at 115200, `ip -br addr`) or straight to this PC's spare port (`enp1s0f1np1`) with
   `sudo nmcli con add type ethernet ifname enp1s0f1np1 con-name pynq ipv4.method manual ipv4.addresses 192.168.2.1/24`:
   PYNQ answers at 192.168.2.99 on that link as well.  Put the address in `bench_config.json`.
3. **The driver on the PYNQ:** `ssh-copy-id xilinx@<address>` (password `xilinx`), then `bringup/deploy_pynq.sh
   xilinx@<address>`, then in the PYNQ's Jupyter, New -> Terminal (a root shell): `/home/xilinx/costaslink/install_service.sh`.
   From then on the overlay loads and the server starts at every boot, before the CostasLink board is powered.
   `python3 gateware/driver/netbus.py ping <address>` says whether it is up.
4. **The serial instruments:** plug the USB-RS-232 adapters in, `python3 ~/lab-instrument-control/scpi_link.py identify`
   (sends `*IDN?` only), and put the supply's (E3646A or E3632A) and the Fluke 45's `/dev/serial/by-id/...` paths in `bench_config.json`.
   `python3 bringup/bench.py check` then says who answers.

## The stages as commands

Each command logs what it read; `python3 bringup/bench.py show` prints the log's tail.  `--board A` (or B) on every one,
`--stage` when a reading belongs to a step the command does not know.

| BRINGUP | cabled | command |
|---|---|---|
| 1.0 | nothing: the loupe | `bench.py note "..." --stage 1.0` for each finding |
| 1.1 | E3646A output 1 -> USB-C | `bench.py psu smoke` |
| 1.2 | the Fluke on each TP | `bench.py psu on`, then `bench.py dmm +5V_IN`, `dmm +5V_RF`, ... (`RAILS` in bench.py) |
| 1.3-1.4 | the IR camera | `bench.py psu log --seconds 600` (in the background), the camera's readings as notes |
| 1.5 | on the PYNQ (PYNQ first) | `bench.py run stage1.i2c` (`--eeprom true` once a board: the DACs' power-up values) |
| 2.1 | | `bench.py run stage2.pll` |
| 2.2 | LO TX MON J204 / LO RX MON J109 -> DSA875; REF OUT J108 -> scope | `run stage2.lo --which tx` (and `rx`), `run stage2.vcxo`, `run stage2.ref_out` |
| 2.3 | TX MON J201 -> DSA875, TX ANT terminated | `run stage2.tx`, `run stage2.null` |
| 2.4 | SDG CH1 -> REF IN J203, JP201 to REF IN | `run stage2.ref_in` |
| 3.x | the 40 dB loopback | to be written as the stage comes (the driver's `loopback_latency`, `agc`, `threshold_scan` ...) |
