"""shot_view.py A|B xy|time OUT.png CYCLE_LOG [BRINGUP_DIR]: waits for the scope's cycle to switch to that view (its log
line), 1.5 s more, then the screen (the lab driver's screenshot) to a PNG.  The cycle only talks to the scope at a
switch, so a shot inside a view's 5 / 10 s does not collide with it."""
import os, sys, time
which, view, out, log = sys.argv[1:5]
br = sys.argv[5] if len(sys.argv) > 5 else os.path.expanduser("~/OpticsPCBs/CostasLink-PYNQ-Z2/bringup")
sys.path.insert(0, br)
os.chdir(br)
import scope_e  # noqa: E402
key = "XY" if view == "xy" else "time view"
n0 = len(open(log).read().splitlines())
t0 = time.time()
while time.time() - t0 < 60:
    lines = open(log).read().splitlines()[n0:]
    if any(key in l for l in lines):
        break
    time.sleep(0.2)
else:
    sys.exit("no '%s' line in 60 s" % key)
time.sleep(1.5)
s = scope_e.open_scope(which)
try:
    bmp = out[:-4] + ".bmp"
    s.screenshot(bmp)
finally:
    s.close()
from PIL import Image  # noqa: E402
Image.open(bmp).save(out)
os.remove(bmp)
print(out)
