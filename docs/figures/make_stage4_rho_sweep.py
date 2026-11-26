"""Figure 2: Stage 4 integration-scale sweep (the README's main result).

Median angular error between the Stage 3 refined field and a plain structure
tensor, against the integration scale rho. Line: the 5,000-seed run. Band:
range over the five seed counts (1,000-5,000). Plotted exactly as recorded in
results/seed_rho_curves.json (14 log-spaced rho; no smoothing).

Drawn to journal specifications: 90 mm single-column width, Arial 7 pt, no
title or gridlines, units on both axes, black text, Wong (2011) blue.

Writes stage4_rho_sweep.png (600 dpi) and stage4_rho_sweep.pdf (vector).

    python docs/figures/make_stage4_rho_sweep.py

Data: i74, 48^3 chunk at centre 384, sigma = 1.00, MSE objective, relax turn
mode, six field updates per run.
"""

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                          # noqa: E402
from matplotlib.lines import Line2D                      # noqa: E402
from matplotlib.patches import Patch                     # noqa: E402
from matplotlib.ticker import FixedLocator, NullLocator  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(ROOT, "results", "seed_rho_curves.json")
OUT = os.path.join(HERE, "stage4_rho_sweep")

RHO_STAGE1 = 2 ** 0.5    # Stage 1's rho on this chunk (stage4_sigma_rho.json)
CHUNK_HALF = 24          # 48^3 chunk; the Gaussian window reaches ~4 rho
LINE_SEEDS = "5000"

BLUE, GREY, SHADE = "#0072B2", "#808080", "#ececec"   # Wong (2011) blue
MM = 1 / 25.4


def main():
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "mathtext.fontset": "custom", "mathtext.rm": "Arial",
        "mathtext.it": "Arial:italic",
        "font.size": 7, "axes.labelsize": 7,
        "xtick.labelsize": 6.5, "ytick.labelsize": 6.5,
        "axes.linewidth": 0.5,
        "xtick.major.width": 0.5, "ytick.major.width": 0.5,
        "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "axes.spines.top": False, "axes.spines.right": False,
        "pdf.fonttype": 42, "savefig.facecolor": "white",
    })
    with open(DATA) as f:
        d = json.load(f)
    rhos = d["rhos"]
    seeds = sorted(d["res"], key=int)
    med = {s: d["res"][s]["median"] for s in seeds}
    i_min = {s: min(range(len(rhos)), key=med[s].__getitem__) for s in seeds}
    assert len(set(i_min.values())) == 1, "minima differ between seed counts"
    j = i_min[LINE_SEEDS]
    lo = [min(med[s][i] for s in seeds) for i in range(len(rhos))]
    hi = [max(med[s][i] for s in seeds) for i in range(len(rhos))]
    line = med[LINE_SEEDS]

    fig, ax = plt.subplots(figsize=(90 * MM, 60 * MM))
    fig.subplots_adjust(left=0.13, right=0.97, top=0.96, bottom=0.17)

    # Where the 4-rho Gaussian window exceeds the chunk's half-width.
    xmax = rhos[-1] * 1.1
    ax.axvspan(CHUNK_HALF / 4, xmax, color=SHADE, lw=0, zorder=0)
    ax.text((CHUNK_HALF / 4 * xmax) ** 0.5, 2, "window >\nchunk", fontsize=6,
            ha="center", va="bottom", linespacing=1.1)

    # Stage 1's data-driven choice.
    ax.axvline(RHO_STAGE1, color=GREY, lw=0.6, ls=(0, (3, 2)), zorder=1)
    ax.text(RHO_STAGE1 * 1.05, 44, "Stage 1\n" + r"($\rho$ = 1.41)",
            fontsize=6.5, va="top", linespacing=1.15)

    ax.fill_between(rhos, lo, hi, color=BLUE, alpha=0.25, lw=0, zorder=2)
    ax.plot(rhos, line, color=BLUE, lw=1.0, marker="o", ms=2.2, zorder=3)
    ax.plot(rhos[j], line[j], "o", ms=5, mfc=BLUE, mec="white", mew=0.6,
            zorder=4)
    ax.annotate(r"$\rho$* = " + f"{rhos[j]:.2f}\n{line[j]:.1f}°",
                (rhos[j], line[j]), xytext=(0, -6),
                textcoords="offset points", ha="center", va="top",
                fontsize=6.5, linespacing=1.15)

    ticks = [1, 2, 4, 8]
    ax.set_xscale("log", base=2)
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xticklabels([str(t) for t in ticks])
    ax.set_xlim(rhos[0] / 1.1, xmax)
    ax.set_ylim(0, 45)
    ax.set_yticks([0, 10, 20, 30, 40])
    ax.set_xlabel(r"Integration scale $\rho$ (voxels)")
    ax.set_ylabel("Median angular error (°)")

    handles = [
        Line2D([], [], color=BLUE, lw=1.0, marker="o", ms=2.2,
               label=f"{int(LINE_SEEDS):,} seeds"),
        Patch(fc=BLUE, alpha=0.25, lw=0,
              label=f"range, {int(seeds[0]):,}–{int(seeds[-1]):,} seeds"),
    ]
    ax.legend(handles=handles, frameon=False, loc="lower left",
              bbox_to_anchor=(0.33, 0.0), fontsize=6.5, handlelength=1.6,
              borderaxespad=0.3)

    fig.savefig(f"{OUT}.png", dpi=600)
    fig.savefig(f"{OUT}.pdf")
    print(f"wrote {OUT}.png and {OUT}.pdf")


if __name__ == "__main__":
    main()
