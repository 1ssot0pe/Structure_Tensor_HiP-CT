# The pipeline, step by step

What runs, in order, with the file, input and output of each step. The file
lists below are **measured**, not assumed: they are the modules Python actually
loads during a run.

Setup (environment, data location) is in the [main README](../README.md#setup).
All commands run from the repository root.

```powershell
.\tools\run_all.ps1                  # all three checks, stops at the first failure
.\tools\run_all.ps1 -Quick -SkipI74  # ~1 min smoke test, no real data needed
```

Or run the steps yourself, in this order — each is more trustworthy than the
next, so a failure early makes the later ones meaningless:

```bash
python 3_global_tractography/test_frame_convention.py   # known answer
python 3_global_tractography/run_pipeline.py            # known truth
python 3_global_tractography/run_pipeline.py --i74      # no ground truth
```

Results go to `results/` at the repository root. The first two exit non-zero
on failure, so they work as checks, not just as output to read; CI runs both on
every push.

---

## Logic flow (`run_pipeline.py`)

Each step asks one question. The **decisions** are what the pipeline is; the
boxes are just where they happen.

```
                    core.reconstruction.load_volume()      real scan, no truth
                    core.localized_phantoms.raw_*()        phantom, known truth
                                   │
                                   ▼   vol (z, y, x) float32

┌─ STEP 1 · At what scale do we measure? ─────────────  1_sigma_rho_selection
│
│    A structure tensor has two knobs, and the tissue sets both:
│
│      first peak of the Lindeberg response  →  σ    how wide a gradient
│      where angular drift flattens          →  ρ    how far to average
│
│    σ too small measures noise; too large blurs neighbouring fibres.
│    ρ too small leaves direction jittery; too large averages across fibres.
│    Picked per 32³ block, because the best σ varies ~1–6 across a volume.
│
│    ? does the block hold tissue    block mean ≥ 5% of the volume max
│      ├─ yes → pick (σ, ρ) for it, and use that
│      └─ no  → BACKGROUND. skipped before any scale pick is attempted;
│               those patches fall back to σ = ρ = 0.85  ⚠ WARNS
│
│    A sparse volume can fail this on every block — then Step 1 never ran,
│    and the whole run is on one fixed scale. Cost, measured: ~20° of
│    angular error on the kissing phantom.
└──────────────────────────────────────────────────────────────────────────
                                   │
                                   ▼   sigma_map, rho_map

┌─ STEP 2 · Can ONE direction be trusted here? ───────  2_host_classification
│
│    A tensor gives one direction per voxel. Where two fibres cross, that
│    answer is not imprecise — it is meaningless. Find those places, and
│    spend the expensive method only there.
│
│    per patch (half = 14):   host_fod.analyse(σ_grad = 4.0)
│                               → c_s   how much it has NO dominant direction
│                               → FA    how strongly directional it is
│
│    ? c_s ≤ FA  AND  fewer than 3 peaks        ← both from the same
│      │                                          eigenvalues, so no
│      │                                          threshold to tune
│      ├─ yes → SINGLE.  keep Step 1's e3, one direction, done
│      │
│      └─ no  → ROUTE TO HOST-FOD, at a different scale:
│               analyse(σ_grad = 2.5) → up to 2 directions
│               classify() → single, crossing, dispersed,
│                            disorganised, complex
│
│    Three scales, not interchangeable:  σ≈1.0 for direction,
│    5.0 for the gate, 2.5 for peaks. At 1.0 the gate never fires;
│    at 5.0 the second peak is already smoothed away. All three are
│    certified, not written down — select_scales.py picks the first
│    from the data, certify_gate_scales.py picks the other two
│    against phantoms with known truth.
└──────────────────────────────────────────────────────────────────────────
                                   │
                                   ▼   GatedField → results/unified_field_*.npz

┌─ STEP 3 · Real crossing, or fibres just touching? ── 3_global_tractography
│
│  (a) MEASURE — from the image, once per junction. Brightness adds:
│
│        S = (I_c − I₀) ⁄ ((I_a − I₀) + (I_b − I₀))
│
│        S ≈ 1.0   both fibres deposit here      →  CROSSING
│        S ≈ 0.5   only one is really here       →  TANGENCY
│        decision at 0.75, ±0.10 reported as AMBIGUOUS
│
│  (b) FIT — θ = (step, angle, seed density, link weight)
│
│        ┌───────────────────────────────────────────────────────┐
│        │                                                       │
│        ▼                                                       │
│      integrate streamlines through the field                   │
│        └─ S is a WALL here: a path may run ALONG a tangency,   │
│           never THROUGH it                                     │
│        │                                                       │
│        ▼                                                       │
│      rasterise → D_rec    arc-length weighted, so density 2    │
│        │                  literally means two fibres           │
│        ▼                                                       │
│      L = MSE(D_rec, D_obs)        does it explain the image?   │
│          + verdict penalty        does it obey S?              │
│        │                            CROSSING wants density 2   │
│        │                            TANGENCY wants density ≤ 1 │
│        ▼                                                       │
│      coordinate descent — one knob at a time, keep what helps ─┘
│        (no gradient: streamlines terminate discretely, so L is
│         flat, then jumps. There is no slope to follow.)
│
│      stop when a full sweep improves nothing
└──────────────────────────────────────────────────────────────────────────
                                   │
                                   ▼

     results/pipeline_results.json    S + verdict per junction, fitted θ
     results/unified_field_*.npz      the orientation field
     results/field_*.png              greyscale + orientations, to check by eye
     stdout                           PASS / FAIL, or a verdict with no
                                      correctness claim on real data
```

**Where the loop closes.** S is measured once from the image and never revised.
θ adapts to S; S never adapts to θ. So a wrong verdict is optimised *toward*,
not away from — the honest limit of the current design.

## What `run_pipeline.py` loads

Traced from a real run of the phantom validation:

```
run_pipeline.py                                  the only entry point
 ├─ core/reconstruction.py       load_volume         → vol
 │  or core/localized_phantoms.py raw_* phantoms     → vol + known truth
 │
 ├─ sigma_rho_gated_field.py                       STEP 1 + 2
 │   ├─ sigma_rho_adaptive.py → pick_sigma_rho.py → core/orthogonality_residual.py
 │   └─ core/host_fod.py → two_orientation_test.py → crossing_shape_3d.py
 │                                                 → kissing_phantom.py
 ├─ self_optimising_tractography.py                STEP 3
 │   └─ tract_density.py
 └─ render_field.py                                figures
```

Each run writes `results/field_*.png` — the greyscale image with the recovered
orientations drawn on top, so a run can be checked by eye, not just read.

This is the crossing/kissing validation path. The Stage 3 optimisation loop
(`descent_loop.py`) and Stage 4 are separate entry points; see below.

---

## 0. Pointing the code at a volume

Set `HIPCT_VOLUME_DIR` to the folder of `*.tif` slices (default: `data/i74/`;
relative paths resolve from the repository root) and `HIPCT_VOXEL_UM` to its
voxel size (default 20 µm, i74). See [Using any dataset](../README.md#using-any-dataset).

`load_volume(crop=(a, b))` carves a central cube `[a:b]` **on all three axes**.
That one setting feeds every step below.

---

## Step 0 — Get a volume

| | |
|---|---|
| **Question** | What are we measuring? |
| **File** | `core/reconstruction.py` — real data · `core/localized_phantoms.py` — synthetic |
| **In** | folder of TIFF slices, `crop` · or phantom geometry parameters |
| **Out** | `vol` — float32 array indexed `(z, y, x)` |

Phantoms come first because they have known truth. `raw_localized_crossing`
builds two fibre families that genuinely cross inside a bounded zone;
`raw_kissing` builds two curved bundles that touch and turn away. Locally these
look identical — that is the whole problem the pipeline exists to solve.

---

## Step 1 — Choose the measurement scales (σ, ρ)

| | |
|---|---|
| **Question** | How wide a region should we measure over? |
| **Files** | `1_sigma_rho_selection/sigma_rho_adaptive.py` → `pick_sigma_rho.py` → `core/orthogonality_residual.py` |
| **In** | `vol`, `block=32` |
| **Out** | `sigma_map`, `rho_map`, block edges `zs, ys, xs` |

The structure tensor has two knobs and both have a right answer set by the
tissue, not by taste:

- **σ**, the differentiation scale — too small measures noise, too large blurs
  neighbouring fibres together. Correct when it matches the fibre's own width.
  Found as the *first* peak of the Lindeberg response (first, not highest, so a
  slow background gradient cannot pose as the fibre scale).
- **ρ**, the integration scale — too small leaves the direction jittery, too
  large averages across genuinely different fibres. Found where angular drift
  flattens.

Picked **per 32³ block**, because the best σ varies ~1–6 across a real volume, so
one global value is wrong nearly everywhere.

> If you see `[stage 1] WARNING: only N% of blocks certified`, the run fell back
> to a single fixed σ and this step contributed nothing.

---

## Step 2 — Decide where one direction is enough

| | |
|---|---|
| **Question** | Can the cheap one-direction answer be trusted here? |
| **Files** | `2_host_classification/sigma_rho_gated_field.py` → `core/host_fod.py` → `core/two_orientation_test.py`, `core/crossing_shape_3d.py` |
| **In** | `vol`, the (σ, ρ) maps, patch half-width 14, `stride` |
| **Out** | `GatedField` → `results/unified_field_*.npz` |

A structure tensor returns one direction per voxel. Where two fibres cross,
there is no single correct direction, so the answer is not merely imprecise —
it is meaningless. This step finds those places and spends the expensive method
only there.

Per patch:

1. `host_fod.analyse(patch, σ_grad=4.0)` → **c_s** (sphericity, "no dominant
   direction") and **FA** (anisotropy, "strongly directional").
2. **c_s ≤ FA** → single fibre. Keep Step 1's `e3`.
   Otherwise → `analyse(patch, σ_grad=2.5)` → up to 2 directions, `classify()`
   → `single` / `crossing` / `dispersed` / `disorganised` / `complex`.

Both quantities come from the same three eigenvalues of the same patch, so the
rule is local and has **no threshold to tune**. It replaced a fixed cutoff that
called only ~3% of real tissue single, implausibly few; this gives ~29%.

Three different σ are in play and they are not interchangeable — at Stage 1's
σ (~1.0) the gate never fires at all, and at 4.0 the second peak that justified
gating is already smoothed away:

| σ | job |
|---|---|
| ~0.85–1.0 (Step 1, per block) | the single-fibre direction |
| 4.0 | the routing decision |
| 2.5 | extracting peak directions |

---

## Step 3 — Resolve which flagged crossings are real

| | |
|---|---|
| **Question** | Do two fibres genuinely cross here, or merely touch? |
| **Files** | `3_global_tractography/dense_field.py` → `dense_tracker.py` → `dense_optimise.py` → `tract_density.py` |
| **In** | **`DenseField`** (one direction per voxel), `vol` |
| **Out** | per-junction S + verdict, fitted (lookahead, θ), `results/pipeline_results.json` |

### The input is a dense per-voxel field

Stage 3 consumes a **voxel grid, not a patch list**:

| | |
|---|---|
| `vec1` | Stage 1's e3 at **every** voxel, overwritten by HOST's first peak inside the patches the gate routed |
| `vec2` | HOST's second peak, zero everywhere else |

So a tracker walks continuously through single-fibre tissue on Stage 1's own
measurement, and sees a second option only where Stage 2 found one. This
replaced `field_from_gated(..., host_only=True)`, which **dropped every
non-routed patch** — on i74 that was 987 of 1331, i.e. all the single-fibre
evidence — leaving streamlines confined to 8-voxel bubbles around the 344 HOST
patches. That is why `host_support` existed; with a dense field there is no
forbidden region, so the loss is scored over the whole tissue mask.

> **Honesty about resolution.** `vec1` is a genuine per-voxel measurement only
> where it is Stage 1's e3. `vec2` and the labels are per-*patch* evidence
> (HOST sees a 29³ neighbourhood) upsampled by nearest-centre fill, capped at
> `max_radius` so a patch never claims voxels it did not see.

A single voxel cannot answer the crossing/kissing question: crossing and kissing
look the same up close. You have to follow the fibres and see whether both
continue. Two independent signals are used:

**Superposition (local, physical).** At a real crossing both fibres deposit
intensity at the same point, so it is roughly their sum. At a kissing point
neither centreline passes through, so it can never exceed about one fibre.
`superposition_S` reads that ratio; `S ≳ 0.75` → CROSSING, low → TANGENCY.

**Global consistency.** Cone-search streamlines are integrated through the dense
field and rasterised into a reconstructed density `D_rec`
(`tract_density.rasterise`, trilinear splatting so density 2 literally means two
fibres). This is compared against `D_obs`, taken from the image's own anisotropy
`λ1 − λ3`. Coordinate descent over **(lookahead, θ)** — how far ahead the cone
gathers evidence, and how sharply it may turn — minimises
`L = mse(D_rec, D_obs) + verdict penalty`.

At a two-direction voxel the candidate directions are scored against
`max(|d·vec1|, |d·vec2|)`, so a walker arriving along either fibre keeps its own
evidence. `vec2` is zero in single-fibre tissue and `|d·0| = 0`, so the `max`
degrades exactly to the one-direction case with no branch. A demotion needs no
special case in the tracker either: zeroing `vec2` simply removes the option.

Two things are **not** searched, because neither has a minimum to find:

- **`alpha`**, the cone's angular sampling — cost scales as `(θ/alpha)²` and
  finer is always at least as good, so a descent on it just walks to the edge of
  its ladder. Fixed; `--alpha-check` re-runs the descent at `alpha/2` and reports
  whether the optimum actually moves. θ is quantised in units of alpha (the cone
  carries `round(θ/alpha)` tilt rings), so θ = 0.15, 0.20 and 0.30 give
  bit-identical tracts at alpha = 0.2 — a reported θ means nothing finer than alpha.
- **the seed budget** — more streamlines is more columns in the design matrix, so
  the fitted residual can essentially only fall (see `weight_fit.py`).

> **Brightness picks when to stop, not which way to turn.** The support that
> selects a direction is `max(|d·vec1|, |d·vec2|)` alone; intensity enters only
> the floor that ends a walk. Weighting the turn by brightness made the tracker
> follow the intensity ridge instead of the director: measured on the crossing
> phantom, tracts left Stage 1's e3 by a median **12.7°** in voxels carrying one
> direction, where there is nothing to decide — while e3 itself is coherent to
> 1.4° voxel-to-voxel. Removing it gives **5.7°** at no cost whatsoever to
> crossing traversal (0.104 either way) or kissing bridging (0.000 either way).
> `single_fibre_check.py` is the standing gate.

> **Directors are interpolated as `v vᵀ`, never componentwise.** e3's sign is
> arbitrary per voxel, so trilinear interpolation averages `v` against `−v` and
> returns ≈0: 13.2% of adjacent voxel pairs on the crossing phantom are
> sign-opposed, and sampling `vec1` at half-voxel offsets gave |v| with a median
> of 0.78 and 31.8% of reads below 0.5. The outer product is invariant under
> `v → −v`, and `dᵀ T d = (d·v)²` recovers the alignment exactly. This is the
> same seam problem the Stage 3a note records for sign alignment, dissolved
> rather than worked around.

> **The join.** `host_fod` returns directions as `(x, y, z)`; Step 3 indexes
> positions as `(z, y, x)`. `field_from_gated` reverses every direction. Getting
> this wrong does not crash — every streamline just walks a mirrored path.
> `test_frame_convention.py` guards it.

---

## Step 3, continued — the optimisation loop

| | |
|---|---|
| **Question** | Which tracking parameters make the tractogram explain the image, and what field results? |
| **Files** | `3_global_tractography/descent_loop.py` → `smooth_tracker.py`, `gradient_optimise.py`, `tdi_mse.py`, `viz_export.py` |
| **In** | i74 chunk (`--centre`, `--radius`) or the crossing phantom (`--dataset crossing`) |
| **Out** | `results/<run>/descent_loop.json`, `refined_field_vec1.npz` (with `--refine-field`), `.trk` tractograms, NIfTI, HTML viewers |

A gradient descent on the search cone (lookahead L, turn limit θ, step α),
scored by MSE or MAE (`--metric`) between the preprocessed image and the
normalised track-density image. With `--refine-field` the field is relaxed by
the optimised cone after each accepted iteration, and the accumulated field is
written out for Stage 4. Details and measured findings:
[3_global_tractography/README.md](../3_global_tractography/README.md) (section 3d).

```bash
python 3_global_tractography/descent_loop.py --radius 24 --seeds 5000 \
    --turn relax --refine-field --variant vec1 --outdir results/seed_5000
```

---

## Step 4 — Which single (σ, ρ) reproduces the refined field?

| | |
|---|---|
| **Question** | Is there a plain structure tensor, at one (σ, ρ), that gives the same directions as the refined field? |
| **Files** | `4_optimising_parameters/sigma_rho_match.py`, `coarse_to_fine.py` |
| **In** | a Stage 3 run directory holding `refined_field_vec1.npz` |
| **Out** | `stage4_sigma_rho.json` — angular error over the (σ, ρ) grid and the best pair |

See [4_optimising_parameters/README.md](../4_optimising_parameters/README.md).

```bash
python 4_optimising_parameters/sigma_rho_match.py --run results/seed_5000 --n 7
python 4_optimising_parameters/coarse_to_fine.py  --run results/seed_5000 --levels 3
```

---

## What comes out

| Output | Meaning |
|---|---|
| `results/field_*.png` | greyscale slab with the recovered orientations drawn on it |
| `results/unified_field_*.npz` | the orientation field: per patch, its directions, label, c_s, FA, σ, ρ |
| `results/dense_field_*_optimised.npz` | the per-voxel field Stage 3 tracked through, after demotion |
| `results/vec1_*.nii.gz`, `vec2_*`, `labels_*`, `ndirs_*` | the same field as NIfTI, before and after |
| `results/pipeline_results.json` | per-junction S and verdict, fitted θ, loss trace |
| stdout | `PASS` / `FAIL` per phantom; on real data, verdict with no correctness claim |

The figures (`render_field.py`, `--no-figures` to skip) are how you check a run
rather than only read it — a field that has stopped following the fibres is
obvious in a picture and invisible in a summary line. Blue = the gate trusted
one direction; orange/aqua = a junction scored CROSSING/TANGENCY, with a ring
marker so the verdict is not carried by colour alone; grey = routed but never
scored.

Glyphs are **line segments, not arrows**: a fibre orientation is a director, so
e3 and −e3 mean the same thing and an arrowhead would assert a direction the
measurement does not contain. A glyph drawn short means the fibre is leaving the
viewing plane, not that the measurement is weak.

On phantoms the crossing scores S ≈ 1.0 → CROSSING, and the kissing pair
produces no junction at all — the gate never routes it, so no crossing is
invented. Both are passes.

On real i74 every scored junction comes back TANGENCY (S median ≈ 0.44),
consistent with the independent tractography and mass-conservation findings that
HOST over-calls crossings on this data.

---

## Optional: measuring the noise

Needs **two half-reconstructions** (even/odd projection subsets) of one scan.
Their difference `n = (A − B)/√2` cancels the shared signal and leaves pure
noise — the only clean way to see noise on its own.

| Step | Command | Result |
|---|---|---|
| Cache the slabs | `python noise_model/build_lung_slab.py` | `lung_A/B.npy` (gitignored) |
| Measure | `python noise_model/half_map_analysis.py --a EVEN --b ODD --vox 16.5 --crop 256` | noise is **correlated** (slope ≈ −3.5, not white's −5) and **anisotropic** (λ1/λ3 ≈ 1.5–1.9) |
| Correct | `python noise_model/run_lung_subtractN.py` | subtracts the measured N from the tensor |
| Decide | `python 3_global_tractography/archive/phase3.py generative` | noise-whitened likelihood; selects the true geometry |

Check the printed `corr(A, B)` first — if the two halves are not well
registered, nothing downstream means anything.

---

## Caveats

- **σ and ρ are not auto-threaded.** Steps 1–3 share them; standalone scripts
  have their own `SIGMA` / `RHO` constants you must set to match.
- **Voxel size is per-script** (`VOXEL_SIZE_UM` / `--vox` / `VOX_UM`).
- **i74 has no half-maps.** It is brain; every "real noise" result borrows lung
  noise as a proxy. Only the isotropic spectral shape is verified to transfer —
  the anisotropy is not.
- **`D_obs = λ1 − λ3` is a proxy, not truth.** It cannot distinguish one bright
  fibre from two dim crossing ones.
- **The generative likelihood is validated as a model selector**, but is not yet
  inside the tractography link-scoring. That is the one open build.
