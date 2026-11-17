# Certified raster-to-vector conversion

Implementation, experiments and manuscript for

> **Certified raster-to-vector conversion with provably minimal polygons and
> line–arc rings** — Hakan Karateke

Archived release: [doi:10.5281/zenodo.24299983](https://doi.org/10.5281/zenodo.24299983)

Given a binary image, the software returns a vector model of its pixel
boundary together with a certificate that an independent checker re-derives
from the stored coefficients alone:

* a two-sided **Hausdorff error bound** computed with outward-rounded
  interval arithmetic on exact rational subdivisions;
* a proof that the **planar topology** (components, holes, nesting and point
  contacts) is unchanged;
* for two model families, a proof that the model has the **minimum number of
  pieces** in its class: node-restricted polygons (jointly over all rings,
  preserving contacts) and node-restricted rings of line segments and
  circular arcs.

The checker needs only a model and the reference boundary, so it can also be
attached to the output of other tracers (`examples/certify_svg.py`).

The application name, *Şekilden Denkleme*, is Turkish for "from shape to
equation". The user interface and the in-code documentation are in Turkish;
the manuscript and this file are in English. The original Turkish user guide
is kept as [`docs/README.tr.md`](docs/README.tr.md).

## Installation

Python 3.10 or newer is required; the experiments were run with Python 3.12.8.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

On Windows, `kur_windows.cmd` performs the same steps and `baslat_windows.cmd`
starts the desktop application.

## Quick start

```bash
sekilden-denkleme input.png --tolerance 2 --family auto --certificate strict
```

By default the image is **not resampled**: one working unit is one source
pixel and the tolerance is given in source pixels. `--working-size 1000`
restores the behaviour of versions before 3.0, in which the shape was scaled
to a 1000 × 1000 plane and all guarantees referred to the resampled image.

From Python:

```python
from sekilden_denkleme import AnalysisConfig, analyze

result = analyze(
    "input.png", AnalysisConfig(tolerance=2, family="linearc", certificate_mode="strict")
)
selected = next(c for c in result.candidates if c.id == result.selected_id)
print(selected.metrics["certification"]["status"])  # "proven"
```

## Repository layout

| Path | Content |
| --- | --- |
| `src/sekilden_denkleme/` | library, command line and desktop application |
| `src/sekilden_denkleme/certification.py` | the independent checker |
| `src/sekilden_denkleme/optimal_polygon.py` | minimal polygons, joint contact-preserving search |
| `src/sekilden_denkleme/optimal_arcs.py` | minimal line–arc rings, tangent smoothing |
| `src/sekilden_denkleme/contact_certificate.py` | exact certificate for touching rings |
| `tests/` | test suite |
| `examples/` | experiment scripts and their recorded results |
| `paper/` | manuscript (LaTeX), figures and the script that draws them |
| `docs/` | design notes and file-format schemas |

## Reproducing the experiments

All icon experiments of the paper are run by one script (about 14 hours with
12 worker processes on a 10-core laptop):

```bash
bash examples/run_all_experiments.sh 12
```

| Script | Result directory | Paper |
| --- | --- | --- |
| `examples/optimality_gap.py` | `examples/icon_dataset/optimality_gap` | optimality gap, contact-preserving optimum |
| `python -m sekilden_denkleme.stress` + `examples/summarize_sweep.py` | `examples/icon_dataset/pipeline_sweep` | full pipeline, cost-model and family ablation |
| `examples/line_arc_optimum.py` | `examples/icon_dataset/line_arc_optimum` | minimal line–arc rings |
| `examples/line_arc_sensitivity.py` | `examples/icon_dataset/line_arc_sensitivity`, `clearance_*` | parameter sensitivity, tangent smoothing |
| `examples/compare_potrace.py`, `examples/certify_potrace.py` | `examples/icon_dataset/potrace_*` | measurement and certification of Potrace |
| `examples/native_inputs.py` | `examples/native_inputs` | large inputs, colour layers |
| `examples/scan_degradation.py resample` | `examples/icon_dataset/resampling_topology` | effect of resampling on the topology |
| `examples/real_scans.py` | `examples/real_scans/results` | one crop of a scanned map |
| `examples/compiled_kernel/compare.py` | `examples/compiled_kernel/results` | NumPy against a compiled kernel (run with version 2.9 on the resampled bitmaps) |
| `paper/make_figures.py` | `paper/figures` | figures |

Two scripts are included but their experiments are **not part of the paper**
because they were not completed: `examples/scan_degradation.py scan`
(synthetic scan degradation) and `examples/audit_published_results.py` (a
raster-based measurement of the published results of other vectorisers; its
alignment step still needs validation). The last three stages of
`run_all_experiments.sh` were likewise not completed for release 3.0.

Potrace 1.16 is expected at `.tmp/potrace/potrace-1.16.win64/potrace.exe`;
`examples/audit_published_results.py` and `paper/make_figures.py` additionally
need the `pymupdf` package.
The scanned documents and the published result sheets of other methods are
not redistributed; see [`THIRD_PARTY.md`](THIRD_PARTY.md) for their sources.

## Tests

```bash
python -m pytest -q
python -m ruff check src tests examples paper tools
```

## Scope

The method is meant for settings in which a stated error bound and an
unchanged topology are worth computation time (CAD exchange, manufacturing,
metrology, archival of line art). It works on binary images and on
flat-colour images treated as stacked binary layers; photographs and
gradients are out of scope. It optimises a description cost, not visual
quality, and it is orders of magnitude slower than a conventional tracer.
The manuscript states the limits in detail.

## Licence

The software is released under the [MIT License](LICENSE). Third-party
material is listed in [`THIRD_PARTY.md`](THIRD_PARTY.md).
