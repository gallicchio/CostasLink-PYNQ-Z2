"""Draw a region of the board, F.Cu / In1 / In2 side by side, from the board file.

    python3 bringup/layout/draw_region.py x0,y0,x1,y1 out.png [title]
"""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rfgeo as G
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Circle
from matplotlib.collections import PatchCollection

RF = set(json.load(open(G.ROOT + "/build/netclasses.json"))["RF"])
B = G.load()
box = [float(v) for v in sys.argv[1].split(",")]       # x0,y0,x1,y1
out = sys.argv[2]
title = sys.argv[3] if len(sys.argv) > 3 else None
refs_only = None
x0, y0, x1, y1 = box
PLANE = {"GND": "#d9d6cc", "+5V_RF": "#f4c9a8", "+3V3_ANA": "#bfe3d0", "+3V3_DIG": "#d6cdf2", "+5V_IN": "#f6dd9c",
         "+3V3_PLL_RX": "#cfe0f6", "+3V3_PLL_TX": "#f3cde0"}


def inbox(x, y, m=1.0):
    return x0 - m <= x <= x1 + m and y0 - m <= y <= y1 + m


def colour(net):
    if net in RF:
        return "#2a78d6"
    if net == "GND":
        return "#52514e"
    if net.startswith("+"):
        return "#eb6834"
    return "#9a988f"


fig, axs = plt.subplots(1, 3, figsize=(18, 18 * (y1 - y0) / (3 * (x1 - x0)) + 1.2), facecolor="#f9f9f7")
for ax, lay, ttl in zip(axs, ("F.Cu", "In1.Cu", "In2.Cu"), ("top copper (F.Cu)", "In1 (the ground plane 0.21 mm below)", "In2 (split planes, 1.28 mm below)")):
    ax.set_facecolor("#ffffff")
    for (l, net), polys in B["fill"].items():
        if l != lay:
            continue
        for P in polys:
            if P[:, 0].max() < x0 or P[:, 0].min() > x1 or P[:, 1].max() < y0 or P[:, 1].min() > y1:
                continue
            ax.add_patch(Polygon(P, closed=True, fc=PLANE.get(net, "#e1e0d9"), ec="none", lw=0))
    if lay == "F.Cu":
        for (xa, ya, xb, yb, w, l, net) in B["seg"]:
            if l == lay and (inbox(xa, ya) or inbox(xb, yb)):
                ax.plot([xa, xb], [ya, yb], color=colour(net), lw=w * 72 / 25.4 * fig.get_figwidth() / 3 * 25.4 / (x1 - x0) / 1.0 * 0.82,
                        solid_capstyle="round", zorder=3)
        for p in B["pad"]:
            if "F.Cu" in p["layers"] and inbox(p["x"], p["y"]):
                ax.add_patch(Polygon(G.pad_poly(p), closed=True, fc=colour(p["net"]), ec="none", alpha=0.9, zorder=4))
        for ref, (fx, fy, rot, value, lib, side) in B["fp"].items():
            if inbox(fx, fy, 0) and side == "F.Cu" and (refs_only is None or ref in refs_only):
                ax.text(fx, fy, ref, fontsize=7.5, ha="center", va="center", color="#0b0b0b", zorder=6,
                        bbox=dict(fc="white", ec="none", alpha=0.6, pad=0.5))
    else:
        for p in B["pad"]:
            if p["drill"] and inbox(p["x"], p["y"]):
                ax.add_patch(Circle((p["x"], p["y"]), p["drill"] / 2, fc="white", ec="#898781", lw=0.5, zorder=4))
    for (vx, vy, size, drill, net, lays) in B["via"]:
        if inbox(vx, vy):
            ax.add_patch(Circle((vx, vy), size / 2, fc=("#1baf7a" if net == "GND" else colour(net)), ec="#0b0b0b", lw=0.4, zorder=5))
    ax.set_xlim(x0, x1)
    ax.set_ylim(y1, y0)
    ax.set_aspect("equal")
    ax.set_title(ttl, fontsize=11, loc="left", color="#0b0b0b")
    ax.tick_params(labelsize=8, colors="#898781")
    for s in ax.spines.values():
        s.set_color("#c3c2b7")
handles = [plt.Line2D([], [], color="#2a78d6", lw=4, label="RF net"), plt.Line2D([], [], color="#eb6834", lw=4, label="supply net"),
           plt.Line2D([], [], color="#52514e", lw=4, label="GND pad"), plt.Line2D([], [], marker="o", ls="", mfc="#1baf7a", mec="#0b0b0b", ms=8, label="GND via"),
           ] + [plt.Line2D([], [], color=c, lw=8, label="plane: " + n) for n, c in PLANE.items()]
fig.legend(handles=handles, loc="lower center", ncol=6, frameon=False, fontsize=9)
if title:
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, fontweight="bold", color="#0b0b0b")
fig.tight_layout(rect=(0, 0.04, 1, 0.97 if title else 1))
fig.savefig(out, dpi=130)
print(out)
