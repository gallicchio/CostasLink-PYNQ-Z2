#!/bin/bash
# Copy the overlay and the driver to the PYNQ-Z2, all in one directory as gateware/README.md says, and record which
# bitstream went:
#   bringup/deploy_pynq.sh [xilinx@192.168.8.142]
#   OVERLAY=build/pynq/overlay_2022.1 bringup/deploy_pynq.sh ...   # another build (default build/pynq/overlay)
# Once per PYNQ, so scp asks no password:  ssh-copy-id xilinx@192.168.2.99   (the password is xilinx)
# Then start the server from the PYNQ's Jupyter (New -> Terminal is a root shell there):
#   /home/xilinx/costaslink/pynq_serve.sh
# or have it start at every boot (once, as root): /home/xilinx/costaslink/install_service.sh
set -euo pipefail
HOST=${1:-xilinx@192.168.8.142}
HERE=$(cd "$(dirname "$0")" && pwd)
P=$(dirname "$HERE")
OV=$P/${OVERLAY:-build/pynq/overlay}
FILES=(
    "$OV/costaslink_top.bit" "$OV/costaslink_top.hwh"
    "$P/gateware/driver/costaslink.py" "$P/gateware/driver/netbus.py" "$P/gateware/driver/pynq_serve.sh"
    "$P/gateware/regmap.py" "$P/gateware/max2871_regs.py" "$P/gateware/board_constants.py"
    "$HERE/install_service.sh"
)
ssh "$HOST" mkdir -p costaslink
scp -p "${FILES[@]}" "$HOST":costaslink/
ssh "$HOST" "cd costaslink && chmod +x pynq_serve.sh install_service.sh && sha256sum costaslink_top.bit costaslink_top.hwh"
echo "deployed $OV to $HOST:costaslink/ ($(git -C "$P" rev-parse --short HEAD)$(git -C "$P" diff --quiet -- gateware || echo ' + uncommitted gateware/ changes'))"
