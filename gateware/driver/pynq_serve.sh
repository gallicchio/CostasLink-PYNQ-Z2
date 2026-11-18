#!/bin/bash
# On the PYNQ-Z2: serve the CostasLink driver to the bench PC (netbus.py, port 5800).
#   sudo ./pynq_serve.sh                 # loads costaslink_top.bit (and .hwh) from this directory
#   sudo ./pynq_serve.sh --no-download   # the overlay is loaded already
#   the read-only status page: http://<the PYNQ>:8080/
# PYNQ 3.x keeps its Python in a venv that root's shell does not have: source it first (as its Jupyter does).
for f in /etc/profile.d/pynq_venv.sh /etc/profile.d/xrt_setup.sh; do
    [ -f "$f" ] && source "$f"
done
cd "$(dirname "$0")" || exit 1
exec python3 netbus.py serve --dashboard 8080 --linkd --selftest "$@"   # the status page on port 8080 (dashboard.py),
                                    # the automatic recovery while no client drives (linkd.py), the link's own rounds of
                                    # single symbols and data, off until switched on from the page (selftest.py)
