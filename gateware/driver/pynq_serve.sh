#!/bin/bash
# On the PYNQ-Z2: serve the CostasLink driver to the bench PC (netbus.py, port 5800).
#   sudo ./pynq_serve.sh                 # loads costaslink_top.bit (and .hwh) from this directory
#   sudo ./pynq_serve.sh --no-download   # the overlay is loaded already
# PYNQ 3.x keeps its Python in a venv that root's shell does not have: source it first (as its Jupyter does).
for f in /etc/profile.d/pynq_venv.sh /etc/profile.d/xrt_setup.sh; do
    [ -f "$f" ] && source "$f"
done
cd "$(dirname "$0")" || exit 1
exec python3 netbus.py serve "$@"
