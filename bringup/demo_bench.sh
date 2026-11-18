#!/bin/bash
# the courtyard demo on the bench: both stations from this laptop, A's TRIG A off (the bench's TRIG A -> TRIG IN wiring)
#   [A_ARGS=...] [B_ARGS=...] demo_bench.sh start [extra args for both]     logs/demo_A.out, logs/demo_B.out, pids in logs/demo_A.pid, demo_B.pid
#   demo_bench.sh stop                            SIGTERM to the two PIDs (SIGINT does not get through the lock) (their keepers stop; the boards are left as they are)
S=$(cd "$(dirname "$0")" && pwd)
BR=/home/jason/OpticsPCBs/CostasLink-PYNQ-Z2/bringup
case "$1" in
  start)
    shift
    cd "$BR" || exit 1
    python3 demo.py A --tx 4800 --rx 5400 --port 8090 --trig_a off $A_ARGS "$@" > "$S/logs/demo_A.out" 2>&1 & echo $! > "$S/logs/demo_A.pid"
    sleep 0.5
    python3 demo.py B --tx 5400 --rx 4800 --port 8091 $B_ARGS "$@" > "$S/logs/demo_B.out" 2>&1 & echo $! > "$S/logs/demo_B.pid"
    sleep 1
    ps -o pid,lstart,args -p "$(cat "$S/logs/demo_A.pid")" -p "$(cat "$S/logs/demo_B.pid")" | cut -c1-100
    ;;
  stop)
    for w in A B; do
      P=$(cat "$S/logs/demo_$w.pid" 2>/dev/null) || continue
      ps -o pid,args -p "$P" | grep -q "demo.py $w" && kill -TERM "$P" && echo "stopped $w ($P)"
    done
    ;;
  *) echo "start | stop"; exit 1;;
esac
