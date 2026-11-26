"""Figure 1: pipeline overview (README).

Five panels, a-e, drawn to journal specifications (190 mm wide, Arial 7 pt,
bold lowercase panel labels, black text, Wong 2011 colour-blind-safe colours).

What is computed and what is drawn:
  a  a 2D phantom: two fibre bundles crossing at 85 degrees, with noise.
  b  the plain 2D structure tensor's two scales, drawn at their true size
     (disc radius 2*sigma, dashed circle radius 2*rho; sigma = 1, rho = 4 px).
  c  COMPUTED: the Stage 2 gate, c_s <= FA, applied in 2D to a 21 x 21 px
     patch at each glyph. Blue = gate keeps one direction (the plain tensor's,
     also computed). Orange = gate routes the patch to HOST. At routed tissue
     patches the two orange segments are the phantom's TRUE directions: HOST's
     peak recovery is a 3D method and is not reproduced in 2D (2D gradients put
     the order-6 minimum at the bisector), so that part is schematic.
     Routed background patches carry no direction (HOST labels them
     disorganised), so nothing is drawn there.
  d  a line drawing of the two junction types and their brightness ratio S.
  e  the recorded Stage 4 sweep, results/seed_rho_curves.json (5,000 seeds).

Why 85 degrees: in 2D, two gradient families theta apart give
c_s ~ 1 - cos(theta), so at ~60 degrees c_s ~ FA and the 2D gate cannot
separate them. In 3D the gate separates the certified 40-degree phantom
(c_s 0.81 vs FA 0.18, 1_sigma_rho_selection/gate_scales.json).

Writes pipeline_overview.png (600 dpi) and pipeline_overview.pdf.

    python docs/figures/make_pipeline_overview.py
"""

import json
import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                          # noqa: E402
from matplotlib.lines import Line2D                      # noqa: E402
from matplotlib.patches import Circle, FancyArrowPatch   # noqa: E402
from scipy.ndimage import gaussian_filter                # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(ROOT, "results", "seed_rho_curves.json")
OUT = os.path.join(HERE, "pipeline_overview")

# Wong (2011), Nature Methods 8:441 -- colour-blind-safe.
BLUE, ORANGE = "#0072B2", "#D55E00"
INK, GREY = "#000000", "#808080"

MM = 1 / 25.4
FW, FH = 190 * MM, 47 * MM          # double-column width

N = 160                              # phantom size (px)
ANG_A, ANG_B = 20.0, -65.0           # bundle directions, 85 degrees apart
SPACING, RADIUS, NOISE = 8.0, 1.5, 0.2
SIGMA, RHO = 1.0, 4.0                # plain tensor scales (px), panels b-c
GATE_HALF = 10                       # 21 x 21 px gate patch
EPS = 1e-12


# --------------------------------------------------------------------------
# Phantom, plain tensor, and the Stage 2 gate in 2D
# --------------------------------------------------------------------------
def bundle(yy, xx, ang_deg, offset, width=44.0):
    a = np.deg2rad(ang_deg)
    n = np.array([-np.sin(a), np.cos(a)])
    u = (xx - N / 2) * n[0] + (yy - N / 2) * n[1] - offset
    d = (u + SPACING / 2) % SPACING - SPACING / 2
    edge = 1 / (1 + np.exp((np.abs(u) - width / 2) / 1.5))
    return np.exp(-d ** 2 / (2 * RADIUS ** 2)) * edge, np.abs(u) < width / 2


def phantom():
    yy, xx = np.mgrid[0:N, 0:N].astype(float)
    a, in_a = bundle(yy, xx, ANG_A, -8)
    b, in_b = bundle(yy, xx, ANG_B, 10)
    rng = np.random.default_rng(0)
    img = a + b + 0.1 + NOISE * rng.standard_normal((N, N))
    return img, in_a | in_b


def plain_tensor_angle(img):
    """Fibre angle = smaller-eigenvalue eigenvector of the 2D structure tensor."""
    gy = gaussian_filter(img, SIGMA, order=(1, 0))
    gx = gaussian_filter(img, SIGMA, order=(0, 1))
    jxx = gaussian_filter(gx * gx, RHO)
    jxy = gaussian_filter(gx * gy, RHO)
    jyy = gaussian_filter(gy * gy, RHO)
    return 0.5 * np.arctan2(2 * jxy, jxx - jyy) + np.pi / 2


def gate_routes(patch, mag_frac=0.1):
    """2D form of core.host_fod: route to HOST when c_s > FA."""
    gy = gaussian_filter(patch, SIGMA, order=(1, 0), mode="nearest")
    gx = gaussian_filter(patch, SIGMA, order=(0, 1), mode="nearest")
    G = np.stack([gx.ravel(), gy.ravel()], 1)
    m = np.linalg.norm(G, axis=1)
    G = G[m > mag_frac * (m.max() + EPS)]
    lam = np.sort(np.linalg.eigvalsh(G.T @ G))
    c_s = 2 * lam[0] / (lam.sum() + EPS)
    fa = abs(lam[1] - lam[0]) / (np.sqrt((lam ** 2).sum()) + EPS)
    return c_s > fa


# --------------------------------------------------------------------------
# Layout helpers (all positions in inches)
# --------------------------------------------------------------------------
def rect(x, y, w, h):
    return [x / FW, y / FH, w / FW, h / FH]


def text(fig, x, y, s, **kw):
    kw.setdefault("fontsize", 7)
    kw.setdefault("color", INK)
    fig.text(x / FW, y / FH, s, **kw)


def image_axes(fig, x, y, s, img, alpha=1.0):
    ax = fig.add_axes(rect(x, y, s, s))
    ax.imshow(img, cmap="gray", vmin=0, vmax=1.6, origin="lower",
              interpolation="bilinear", alpha=alpha)
    ax.set_facecolor("black")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlim(-0.5, N - 0.5)
    ax.set_ylim(-0.5, N - 0.5)
    for sp in ax.spines.values():
        sp.set_linewidth(0.5)
    return ax


def segment(ax, x, y, ang, length, color, lw=1.1):
    # orientations are directors (v == -v): segments, never arrows
    dx, dy = 0.5 * length * np.cos(ang), 0.5 * length * np.sin(ang)
    ax.plot([x - dx, x + dx], [y - dy, y + dy], color=color, lw=lw,
            solid_capstyle="round")


def key_line(fig, x, y, color, label):
    fig.add_artist(Line2D([x / FW, (x + 0.14) / FW], [y / FH, y / FH],
                          color=color, lw=1.2, solid_capstyle="round"))
    text(fig, x + 0.19, y, label, va="center")


def arrow(fig, x0, x1, y):
    fig.add_artist(FancyArrowPatch((x0 / FW, y / FH), (x1 / FW, y / FH),
                                   transform=fig.transFigure,
                                   arrowstyle="-|>", mutation_scale=7,
                                   lw=0.8, color=GREY))


# --------------------------------------------------------------------------
def main():
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "mathtext.fontset": "custom", "mathtext.rm": "Arial",
        "mathtext.it": "Arial:italic", "mathtext.bf": "Arial:bold",
        "font.size": 7, "axes.linewidth": 0.5,
        "xtick.major.width": 0.5, "ytick.major.width": 0.5,
        "xtick.major.size": 2, "ytick.major.size": 2,
        "xtick.labelsize": 6, "ytick.labelsize": 6,
        "pdf.fonttype": 42, "savefig.facecolor": "white",
    })
    img, tissue = phantom()
    theta = plain_tensor_angle(img)

    fig = plt.figure(figsize=(FW, FH))
    S = 1.12                              # panel square size (in)
    x0s = [0.10 + k * 1.50 for k in range(5)]
    YB, YT = 0.40, 0.40 + S               # image bottom / top
    titles = ["HiP-CT volume", "Stage 1: scale", "Stage 2: crossing gate",
              "Stage 3: tractography", "Stage 4: optimisation"]
    for k, (x, ti) in enumerate(zip(x0s, titles)):
        text(fig, x - 0.04, YT + 0.13, "abcde"[k], fontsize=8,
             fontweight="bold", va="bottom")
        text(fig, x + 0.10, YT + 0.13, ti, va="bottom")
    for x in x0s[:-1]:
        arrow(fig, x + S + 0.07, x + 1.50 - 0.07, YB + S / 2)

    # a ---------------------------------------------------------------
    image_axes(fig, x0s[0], YB, S, img)
    text(fig, x0s[0], YB - 0.13, "3D image; 2D phantom shown", va="center")

    # b ---------------------------------------------------------------
    ax = image_axes(fig, x0s[1], YB, S, img)
    c = (N / 2 + 12, N / 2 + 30)
    ax.add_patch(Circle(c, 2 * RHO, fc="none", ec="white", lw=0.8,
                        ls=(0, (2, 1.5))))
    ax.add_patch(Circle(c, 2 * SIGMA, fc="white", ec="none"))
    text(fig, x0s[1], YB - 0.13, r"disc: $\sigma$ (derivative)",
         va="center")
    text(fig, x0s[1], YB - 0.27, r"circle: $\rho$ (integration)",
         va="center")

    # c ---------------------------------------------------------------
    ax = image_axes(fig, x0s[2], YB, S, img, alpha=0.4)
    step, h = 12, GATE_HALF
    for y in range(h + 4, N - h, step):
        for x in range(h + 4, N - h, step):
            routed = gate_routes(img[y - h:y + h + 1, x - h:x + h + 1])
            if not tissue[y, x]:
                continue                  # background: no direction
            if routed:
                segment(ax, x, y, np.deg2rad(ANG_A), 9, ORANGE)
                segment(ax, x, y, np.deg2rad(ANG_B), 9, ORANGE)
            else:
                segment(ax, x, y, theta[y, x], 10, BLUE)
    key_line(fig, x0s[2], YB - 0.13, BLUE, "one direction (tensor)")
    key_line(fig, x0s[2], YB - 0.27, ORANGE, "routed to HOST")

    # d ---------------------------------------------------------------
    s = np.linspace(-1.1, 1.1, 60)
    w = (S - 0.08) / 2
    for k, kind in enumerate(("crossing", "touching")):
        ax = fig.add_axes(rect(x0s[3] + k * (w + 0.08), YB + 0.10, w, S - 0.2))
        ax.set_xlim(-1.25, 1.25)
        ax.set_ylim(-1.6, 1.6)
        ax.axis("off")
        if kind == "crossing":
            ax.plot(s, 0.6 * s, color=GREY, lw=1.2)
            ax.plot(s, -0.6 * s, color=GREY, lw=1.2)
            ring, label = ORANGE, r"$S \approx 1$"
        else:
            ax.plot(s, 0.14 + 0.5 * s ** 2, color=GREY, lw=1.2)
            ax.plot(s, -0.14 - 0.5 * s ** 2, color=GREY, lw=1.2)
            ring, label = BLUE, r"$S \approx 0.5$"
        ax.plot(0, 0, "o", ms=6, mfc="none", mec=ring, mew=1.2)
        ax.text(0, -1.25, kind, ha="center", va="top", fontsize=7)
        ax.text(0, 1.3, label, ha="center", va="bottom", fontsize=7)
    text(fig, x0s[3], YB - 0.13, r"$S$: junction brightness ratio",
         va="center")
    text(fig, x0s[3], YB - 0.27, r"kept as crossing if $S$ > 0.75",
         va="center")

    # e ---------------------------------------------------------------
    with open(DATA) as f:
        d = json.load(f)
    rhos = np.array(d["rhos"])
    err = np.array(d["res"]["5000"]["median"])
    j = int(np.argmin(err))
    ax = fig.add_axes(rect(x0s[4] + 0.30, YB + 0.06, S - 0.32, S - 0.06))
    ax.plot(rhos, err, color=BLUE, lw=1.0)
    ax.plot(rhos[j], err[j], "o", ms=3.5, color=BLUE)
    ax.annotate(r"$\rho$* = " + f"{rhos[j]:.2f}", (rhos[j], err[j]),
                xytext=(0, -5), textcoords="offset points", ha="center",
                va="top", fontsize=6.5)
    ax.set_xscale("log", base=2)
    ax.set_xticks([1, 2, 4, 8])
    ax.set_xticklabels(["1", "2", "4", "8"])
    ax.minorticks_off()
    ax.set_ylim(0, 45)
    ax.set_yticks([0, 20, 40])
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.set_xlabel(r"$\rho$ (voxels)", fontsize=7, labelpad=1)
    ax.set_ylabel("Error (°)", fontsize=7, labelpad=1)

    fig.savefig(f"{OUT}.png", dpi=600)
    fig.savefig(f"{OUT}.pdf")
    print(f"wrote {OUT}.png and {OUT}.pdf")


if __name__ == "__main__":
    main()
