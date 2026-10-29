#!/bin/bash
# On the PYNQ-Z2, as root, once: run pynq_serve.sh (the CostasLink overlay and netbus.py on port 5800) at every boot.
#   sudo /home/xilinx/costaslink/install_service.sh          (or from a Jupyter terminal, which is root already)
#   systemctl status costaslink-netbus; journalctl -u costaslink-netbus -f
#   systemctl disable --now costaslink-netbus                (to give the PL back to the notebooks' overlays)
# The overlay is loaded before the CostasLink board is powered (PYNQ first, the board last: BRINGUP stage 1.5), so
# TX_EN is held low from the start.
set -euo pipefail
DIR=$(cd "$(dirname "$0")" && pwd)
cat > /etc/systemd/system/costaslink-netbus.service <<EOF
[Unit]
Description=CostasLink driver over the network (netbus.py, port 5800)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=$DIR/pynq_serve.sh
WorkingDirectory=$DIR
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now costaslink-netbus
systemctl --no-pager status costaslink-netbus | head -12
