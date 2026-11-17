"""Makale şekillerini deney çıktılarından ve çekirdek işlevlerden üretir.

Kullanım (depo kökünden):
    python paper/make_figures.py models   # fig_models.pdf
    python paper/make_figures.py scale    # fig_scale.pdf
    python paper/make_figures.py color    # fig_color.pdf
"""

import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "paper" / "figures"
sys.path.insert(0, str(ROOT / "examples"))

INK = "#1b1b1b"
REF = "#b9b9b9"
ACCENT = "#c0392b"
BLUE = "#1f5fa8"


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 8,
            "axes.titlesize": 8,
            "axes.linewidth": 0.5,
            "pdf.fonttype": 42,
        }
    )


def models(icon: str = "bi_wrench", epsilon: float = 2.0) -> None:
    from compare_potrace import UNIT, flatten, parse_paths

    from sekilden_denkleme.curves import flatten as flatten_piece
    from sekilden_denkleme.evaluation import reference_topology
    from sekilden_denkleme.fitting import polygon_pieces
    from sekilden_denkleme.geometry import trace_boundaries
    from sekilden_denkleme.imaging import normalize_image
    from sekilden_denkleme.optimal_arcs import min_piece_boundaries
    from sekilden_denkleme.optimal_polygon import min_link_boundaries

    png = ROOT / "examples/icon_dataset/png" / f"{icon}.png"
    mask, _ = normalize_image(io.BytesIO(png.read_bytes()), 127, 20)
    boundaries = trace_boundaries(mask)
    components = [r["component_id"] for r in reference_topology(boundaries)["rings"]]
    spacing = min(1.0, max(0.05, epsilon / 4))
    delta = min(0.05, max(0.0001, epsilon / 16))
    rings, _ = min_link_boundaries(boundaries, epsilon - spacing / 2 - 1e-6, 2)
    polygon = [p for i, b in enumerate(rings) for p in polygon_pieces(b, i, components[i])]
    arcs, _ = min_piece_boundaries(boundaries, epsilon - spacing / 2 - 2 * delta - 1e-6, components)
    with tempfile.TemporaryDirectory() as temporary:
        bitmap, target = Path(temporary) / "in.pbm", Path(temporary) / "out.svg"
        Image.fromarray(np.where(mask, 0, 255).astype("uint8")).convert("1").save(bitmap)
        executable = ROOT / ".tmp/potrace/potrace-1.16.win64/potrace.exe"
        subprocess.run(
            [
                str(executable),
                "-b",
                "svg",
                "-u",
                str(UNIT),
                "-r",
                "72",
                str(bitmap),
                "-o",
                str(target),
            ],
            check=True,
            capture_output=True,
        )
        potrace = parse_paths(target.read_text(encoding="utf-8"))

    def draw_pieces(axis, pieces) -> None:
        for piece in pieces:
            curve = np.asarray(flatten_piece(piece, 0.01))
            colour = ACCENT if piece.kind == "circle" else INK
            axis.plot(curve[:, 0], curve[:, 1], color=colour, lw=0.9, solid_capstyle="round")
        nodes = np.asarray([piece.start for piece in pieces])
        axis.plot(nodes[:, 0], nodes[:, 1], "o", ms=1.6, color=BLUE, mew=0)

    def draw_reference(axis) -> None:
        for boundary in boundaries:
            ring = np.asarray([*boundary.vertices, boundary.vertices[0]], dtype=float)
            axis.plot(ring[:, 0], ring[:, 1], color=REF, lw=0.6)

    def draw_potrace(axis) -> None:
        for ring in potrace:
            curve = flatten(ring)
            curve = np.vstack([curve, curve[:1]])
            axis.plot(curve[:, 0], curve[:, 1], color=INK, lw=0.9)
            nodes = np.asarray([points[0] for _, points in ring])
            axis.plot(nodes[:, 0], nodes[:, 1], "o", ms=1.6, color=BLUE, mew=0)

    everything = np.concatenate([np.asarray(b.vertices, dtype=float) for b in boundaries])
    low, high = everything.min(0), everything.max(0)
    centre = np.asarray(max(boundaries, key=lambda b: len(b.vertices)).vertices, dtype=float)
    focus = centre[len(centre) // 3]
    half = 0.11 * (high - low).max()
    titles = [
        f"pixel boundary, {sum(len(b.vertices) for b in boundaries)} edges",
        f"minimal polygon, {len(polygon)} edges",
        f"minimal line–arc, {len(arcs)} pieces",
        f"Potrace, {sum(len(r) for r in potrace)} pieces",
    ]
    _style()
    figure, axes = plt.subplots(2, 4, figsize=(7.0, 3.7))
    for column, title in enumerate(titles):
        for row in range(2):
            axis = axes[row, column]
            draw_reference(axis)
            if column == 1:
                draw_pieces(axis, polygon)
            elif column == 2:
                draw_pieces(axis, arcs)
            elif column == 3:
                draw_potrace(axis)
            axis.set_aspect("equal")
            axis.set_xticks([])
            axis.set_yticks([])
            if row == 0:
                axis.set_title(title)
                axis.set_xlim(low[0] - 15, high[0] + 15)
                axis.set_ylim(low[1] - 15, high[1] + 15)
                axis.add_patch(
                    plt.Rectangle(focus - half, 2 * half, 2 * half, fill=False, ec=BLUE, lw=0.5)
                )
            else:
                axis.set_xlim(focus[0] - half, focus[0] + half)
                axis.set_ylim(focus[1] - half, focus[1] + half)
    figure.tight_layout(pad=0.4)
    OUT.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUT / "fig_models.pdf")
    (OUT / "fig_models.json").write_text(
        json.dumps(
            {
                "icon": icon,
                "epsilon": epsilon,
                "reference_edges": sum(len(b.vertices) for b in boundaries),
                "polygon_edges": len(polygon),
                "line_arc_pieces": len(arcs),
                "line_arc_arcs": sum(p.kind == "circle" for p in arcs),
                "potrace_pieces": sum(len(r) for r in potrace),
            },
            indent=1,
        ),
        encoding="utf-8",
    )


def scale() -> None:
    merged = {}
    for name in ("scale_polygon", "scale_polygon_8192", "scale_linearc"):
        path = ROOT / "examples/native_inputs" / name / "results.json"
        if not path.exists():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            for family in ("polygon", "linearc"):
                # Yalnızca sınıfında optimal ve sertifikası kanıtlı koşular çizilir.
                done = family in row and row[family]["optimal_in_class"]
                if done and row[family]["certificate_status"] == "proven":
                    merged[(row["kind"], row["size"], row["epsilon"], family)] = row
    rows = list(merged.values())
    _style()
    figure, axes = plt.subplots(1, 2, figsize=(7.0, 2.6), sharex=True)
    for kind, marker in (("terrain", "o"), ("drawing", "s")):
        for family, colour in (("polygon", INK), ("linearc", ACCENT)):
            data = sorted(
                (r["reference_edges"], r[family]["search_seconds"], r[family]["certify_seconds"])
                for r in rows
                if r.get("kind") == kind and r.get("epsilon") == 1.0 and family in r
            )
            if not data:
                continue
            edges, search, certify = map(np.asarray, zip(*data, strict=True))
            label = f"{kind}, {'polygon' if family == 'polygon' else 'line–arc'}"
            axes[0].loglog(edges, search, marker=marker, color=colour, lw=0.8, ms=3, label=label)
            axes[1].loglog(edges, certify, marker=marker, color=colour, lw=0.8, ms=3, label=label)
    axes[0].set_title("search time (s)")
    axes[1].set_title("certificate time (s)")
    for axis in axes:
        axis.set_xlabel("reference edges")
        axis.grid(True, which="major", lw=0.3, color="#dddddd")
    axes[0].legend(frameon=False, fontsize=7)
    figure.tight_layout(pad=0.4)
    OUT.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUT / "fig_scale.pdf")


def color() -> None:
    folder = ROOT / "examples/native_inputs/color"
    results = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    size = results[0]["size"]
    chosen = [r for r in results if r["family"] == "polygon"][:2]
    panels = [(f"quantised input, {size} \u00d7 {size}", folder / f"terrain_{size}.png")]
    for r in chosen:
        panels.append(
            (
                f"model, \u03b5 = {r['epsilon']:g}, {r['pieces']} edges",
                folder / f"terrain_{size}_{r['family']}_e{r['epsilon']:g}.png",
            )
        )
    _style()
    figure, axes = plt.subplots(1, len(panels), figsize=(7.0, 2.5))
    window = slice(size // 4, size // 4 + size // 3)
    for axis, (title, path) in zip(axes, panels, strict=True):
        axis.imshow(np.asarray(Image.open(path))[window, window], interpolation="nearest")
        axis.set_title(title)
        axis.set_xticks([])
        axis.set_yticks([])
    figure.tight_layout(pad=0.4, rect=(0, 0, 1, 0.97))
    OUT.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUT / "fig_color.pdf")


if __name__ == "__main__":
    {"models": models, "scale": scale, "color": color}[sys.argv[1]]()
