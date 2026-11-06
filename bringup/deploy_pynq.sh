#!/bin/bash
# Deploy the overlay and the driver to a PYNQ-Z2 the way the boards run since 2026-11-01: a directory
# /home/xilinx/costaslink_<stamp> holding everything, /home/xilinx/costaslink_current -> it, and the systemd service
# costaslink-netbus (install_service.sh) running costaslink_current/pynq_serve.sh.  The previous directory is kept as
# the rollback (ln -sfn <old> costaslink_current; systemctl restart costaslink-netbus).
#
#   bringup/deploy_pynq.sh 192.168.2.99 [192.168.2.98 ...]            # the PYNQs of boards A and B (pynq-a, pynq-b)
#   OVERLAY=build/pynq/overlay_2022.1_id13_laptop bringup/deploy_pynq.sh ...   # another build (this is the default)
#   NO_RESTART=1 bringup/deploy_pynq.sh ...                            # copy and switch only
#
# No SSH keys on the PYNQs (Jason's rule): the password (xilinx) goes through an askpass helper, and sudo there takes
# it on stdin.  The new directory starts as a copy of the current one, so the service's own files (learned.json,
# levels.json, windows.json, selftest.json, the link_*.json configs, the dashboard's logs) carry over untouched; only
# the files listed below are replaced.  link.json (linkd's unattended setup) is never written here.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
P=$(dirname "$HERE")
OV=$P/${OVERLAY:-build/pynq/overlay_2022.1_id13_laptop}
STAMP=${STAMP:-$(date +%Y%m%d_%H%M)}
ASK=$(mktemp)
printf '#!/bin/sh\necho xilinx\n' > "$ASK"
chmod 700 "$ASK"
trap 'rm -f "$ASK"' EXIT
export SSH_ASKPASS=$ASK SSH_ASKPASS_REQUIRE=force DISPLAY=${DISPLAY:-:0}
SSH="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"
FILES=(
    "$OV/costaslink_top.bit" "$OV/costaslink_top.hwh"
    "$P/gateware/driver/costaslink.py" "$P/gateware/driver/netbus.py" "$P/gateware/driver/linkd.py"
    "$P/gateware/driver/dashboard.py" "$P/gateware/driver/dashboard.html" "$P/gateware/driver/selftest.py"
    "$P/gateware/driver/pynq_serve.sh" "$P/gateware/driver/pullin_map.json"
    "$P/gateware/regmap.py" "$P/gateware/max2871_regs.py" "$P/gateware/board_constants.py"
    "$HERE/install_service.sh"
)
for f in "${FILES[@]}"; do [ -f "$f" ] || { echo "missing $f"; exit 1; }; done
SRC="$(git -C "$P" rev-parse --short HEAD)$(git -C "$P" diff --quiet -- gateware bringup/install_service.sh || echo ' + uncommitted changes')"
for HOST in "$@"; do
    H=xilinx@$HOST
    NEW=costaslink_$STAMP
    echo "== $HOST: $(${SSH} "$H" hostname) -> $NEW from $SRC, overlay $(basename "$OV")"
    ${SSH} "$H" "set -e; cd ~; if [ -e $NEW ]; then echo '$NEW exists'; exit 1; fi; cp -a \$(readlink -f costaslink_current) $NEW; rm -rf $NEW/__pycache__"
    scp -o StrictHostKeyChecking=no -p "${FILES[@]}" "$H:$NEW/"
    printf 'deployed %s from %s (%s) on %s\n' "$NEW" "$SRC" "$(basename "$OV")" "$(date '+%Y-%m-%d %H:%M %Z')" | ${SSH} "$H" "cat >> $NEW/SOURCE.txt"
    ${SSH} "$H" "cd ~/$NEW && chmod +x pynq_serve.sh install_service.sh && sha256sum costaslink_top.bit costaslink_top.hwh linkd.py costaslink.py netbus.py | cut -c1-16,65- > SHA256SUMS && cat SHA256SUMS && cd ~ && ln -sfn $NEW costaslink_current && ls -l costaslink_current"
    if [ -z "${NO_RESTART:-}" ]; then
        echo xilinx | ${SSH} "$H" "sudo -S systemctl restart costaslink-netbus 2>/dev/null; sleep 1; systemctl is-active costaslink-netbus"
    fi
done
echo "local: $(sha256sum "$OV/costaslink_top.bit" "$P/gateware/driver/linkd.py" "$P/gateware/driver/costaslink.py" | cut -c1-16,65- | tr '\n' ' ')"
