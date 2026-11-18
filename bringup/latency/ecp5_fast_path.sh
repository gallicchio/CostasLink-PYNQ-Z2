#!/bin/sh
# The fast path alone on the Icepi Zero's ECP5 (LFE5U-25F-6, its header's balls from gateware/icepi_zero.lpf), placed and
# routed by nextpnr at speed grades 6 (the Icepi's) and 8: comparator pins to ladder pins, no clock (bring-up, 2026-10-29,
# Jason: "Could the Icepi Zero FPGA go faster because it has no 200 resistors, or would it go slower because of the FPGA
# turnaround?").  top_icepi.v does not build turnaround.v's fast path, so these stand in for it:
#   fp_test.v  four of gateware/fp_lut5.v (a reloadable 5-input table, the generic one: Yosys makes a 32:1 mux of
#              flip-flops, four LUT levels)
#   fp_ram.v   the four windows (CMP_I left out, as B2 and A3r do) addressing one 16x4 distributed RAM read with no
#              clock: one level
# nextpnr times from the input's IO cell to the output's: the pad buffers are not in its figure.
#     BIN=/path/to/oss-cad-suite/bin sh bringup/latency/ecp5_fast_path.sh [outdir]
set -e
D=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-${TMPDIR:-/tmp}/ecp5_fast_path}
B=${BIN:+$BIN/}
mkdir -p "$OUT"
cd "$OUT"
for top in fp_test fp_ram; do
    srcs="$D/$top.v"
    [ $top = fp_test ] && srcs="$srcs $D/../../gateware/fp_lut5.v"
    ${B}yosys -q -p "read_verilog $srcs; synth_ecp5 -top $top -json $top.json"
    for sp in 6 8; do
        ${B}nextpnr-ecp5 --25k --package CABGA256 --speed $sp --json $top.json --lpf "$D/$top.lpf" --log ${top}_$sp.log >/dev/null 2>&1
        # the last (routed) critical path from an input pin to an output pin: its logic plus its routing
        awk '/Critical path report for cross-domain path .<async>. -> .<async>./{f=1} f && /ns logic,/{l=$2; r=$5; f=0}
             END{printf "'$top' speed '$sp': %.2f ns IO cell to IO cell (%.2f logic, %.2f routing)\n", l+r, l, r}' ${top}_$sp.log
    done
done
