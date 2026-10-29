"""plotstyle.py: one look for the bring-up's plots (matplotlib, PNG, light).  The colours are the data-viz reference
palette's validated categorical order, in fixed order (never cycled), and its light-surface chrome; one axis per chart;
2 px lines, 8 px markers; recessive grid; a legend for two or more series and direct labels on few."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE, PAGE = "#fcfcfb", "#f9f9f7"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]    # blue, light -> dark


def setup():
    plt.rcParams.update({
        "figure.facecolor": PAGE, "axes.facecolor": SURFACE, "savefig.facecolor": PAGE,
        "font.family": "sans-serif", "font.size": 10.5,
        "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "axes.labelcolor": INK2, "axes.titlecolor": INK,
        "axes.titlesize": 12.5, "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.titlepad": 24,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
        "axes.prop_cycle": matplotlib.cycler(color=SERIES),
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
        "lines.linewidth": 2.0, "lines.markersize": 5.5,
        "legend.frameon": False, "legend.labelcolor": INK2, "legend.fontsize": 9.5,
    })


def subtitle(ax, text):
    """the line under the title: what was measured and how, in secondary ink"""
    ax.text(0, 1.005, text, transform=ax.transAxes, fontsize=9, color=INK2, va="bottom", ha="left")


def source(fig, text):
    fig.text(0.01, -0.045, text, fontsize=7.5, color=MUTED, ha="left", va="bottom")


def save(fig, path):
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path
