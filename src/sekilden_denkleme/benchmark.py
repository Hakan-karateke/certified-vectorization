"""Analitik sürekli referans ile raster sınırını ayrı ölçen yerel deney düzeneği."""

import csv
import json
import platform
import sys
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event

import numpy as np
import shapely
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PIL import Image
from shapely.geometry import MultiLineString, Polygon

from .curves import flatten, model_rings, new_piece
from .evaluation import sample_ring
from .export import ExportOptions, export_result
from .fitting import checkpoint
from .models import AnalysisConfig, CurvePiece
from .pipeline import analyze


def analytic_dataset() -> dict[str, list[list[CurvePiece]]]:
    """Deterministik, çalışma koordinatlarında tam katsayılı 11 şekil üretir."""

    def polygon(points, boundary=0, component=0):
        """Verilen sürekli çokgenin sonlu kenarlarını oluşturur."""
        return [
            new_piece("line", {"a": list(a), "b": list(b)}, [0.0, 1.0], boundary, component)
            for a, b in zip(points, points[1:] + points[:1], strict=True)
        ]

    def circle(radius, boundary=0, center=(500, 500), hole=False, component=0):
        """Yönlü analitik çember halkası üretir."""
        return [
            new_piece(
                "circle",
                {"center": list(center), "radius": radius, "direction": 1 if hole else -1},
                [0.0, 2 * np.pi],
                boundary,
                component,
            )
        ]

    def bezier(controls, boundary=0):
        """Analitik kübik parçaları ortak uçlarla birleştirir."""
        return [new_piece("bezier", {"controls": c}, [0.0, 1.0], boundary, 0) for c in controls]

    square = polygon([(200, 200), (200, 800), (800, 800), (800, 200)])
    ellipse = [
        new_piece(
            "ellipse",
            {"center": [500, 500], "radii": [330, 190], "rotation": 0.35, "direction": -1},
            [0.0, 2 * np.pi],
            0,
            0,
        )
    ]
    cubic = bezier(
        [
            [[220, 500], [220, 850], [780, 850], [780, 500]],
            [[780, 500], [780, 150], [220, 150], [220, 500]],
        ]
    )
    mixed = [
        *polygon([(200, 200), (200, 650), (800, 650), (800, 200)])[:1],
        *bezier([[[200, 650], [200, 950], [800, 950], [800, 650]]]),
        *polygon([(800, 650), (800, 200), (200, 200)])[:2],
    ]
    freeform = bezier(
        [
            [[200, 450], [100, 800], [430, 950], [530, 730]],
            [[530, 730], [800, 950], [950, 450], [710, 400]],
            [[710, 400], [700, 100], [250, 80], [200, 450]],
        ]
    )
    return {
        "square": [square],
        "polygon": [
            polygon([(160, 230), (180, 710), (430, 850), (800, 720), (730, 210), (420, 370)])
        ],
        "circle": [circle(300)],
        "ellipse": [ellipse],
        "bezier": [cubic],
        "ring": [circle(330), circle(150, 1, hole=True)],
        "components": [
            circle(140, center=(240, 550)),
            polygon([(650, 350), (650, 650), (900, 650), (900, 350)], 1, 1),
        ],
        "corner_curve": [mixed],
        "thin_stroke": [circle(290), circle(282, 1, hole=True)],
        "thick_stroke": [circle(310), circle(260, 1, hole=True)],
        "freeform": [freeform],
        "noisy_circle": [circle(300)],
    }


def _rasterize(rings: list[list[CurvePiece]], noisy: bool = False) -> np.ndarray:
    """Piksel merkezinde içerilme ile rasterleştirir; sürekli referansı değiştirmez."""
    coords = np.arange(1000) + 0.5
    x, y = np.meshgrid(coords, coords[::-1])
    mask = np.zeros((1000, 1000), dtype=bool)
    for pieces in rings:
        q = np.vstack([*[flatten(p, 0.01)[:-1] for p in pieces], pieces[-1].end])
        inside = shapely.contains_xy(Polygon(q), x, y)
        mask ^= inside
    if noisy:
        rng = np.random.default_rng(20261014)
        # Bilinen ideal çemberin yakınında ölçülebilir deterministik kirlenme.
        for _ in range(16):
            angle = rng.uniform(0, 2 * np.pi)
            radius = rng.uniform(304, 312)
            col = int(500 + radius * np.cos(angle))
            row = int(500 - radius * np.sin(angle))
            mask[row : row + 2, col : col + 2] = True
    return mask


def run_benchmark(
    directory: str | Path,
    *,
    cancel: Event | None = None,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """12 girdide gerçek aday sonuçlarını CSV/JSON ve karşılaştırma PNG'sine yazar.

    Sürekli referansa hata, her iki eğrinin 0.02 birim poligon yaklaşımı ve
    en çok 1 birim yay örneklemesiyle ölçülür; kesin Hausdorff olarak sunulmaz.
    """
    directory = Path(directory)
    data_dir = directory / "dataset"
    data_dir.mkdir(parents=True, exist_ok=True)
    records = []
    selected_examples = []
    started = time.perf_counter()
    config = AnalysisConfig(padding=0, tolerance=3, family="auto", degree=4, max_fit_points=1500)
    for name, rings in analytic_dataset().items():
        checkpoint(cancel)
        if progress:
            progress(f"Doğrulama: {name}")
        path = data_dir / f"{name}.png"
        Image.fromarray(
            np.where(_rasterize(rings, name == "noisy_circle"), 0, 255).astype("uint8")
        ).save(path)
        truth = {
            "coordinate_system": "working_1000_y_up",
            "rasterization": "pixel_center_contains",
            "curve_flatten_bound": 0.01,
            "noise_seed": 20261014 if name == "noisy_circle" else None,
            "pieces": [[p.__dict__ for p in ring] for ring in rings],
        }
        (data_dir / f"{name}.truth.json").write_text(
            json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        result = analyze(path, config, cancel=cancel, progress=progress)
        truth_lines = [
            np.vstack([*[flatten(p, 0.02)[:-1] for p in ps], ps[-1].end]) for ps in rings
        ]
        truth_geometry = MultiLineString(truth_lines)
        for c in result.candidates:
            checkpoint(cancel)
            analytic_max = None
            if c.pieces:
                model = list(model_rings(c.pieces, 0.02).values())
                model_geometry = MultiLineString(model)
                fwd = np.concatenate(
                    [
                        shapely.distance(shapely.points(sample_ring(q, 1)[0]), model_geometry)
                        for q in truth_lines
                    ]
                )
                back = np.concatenate(
                    [
                        shapely.distance(shapely.points(sample_ring(q, 1)[0]), truth_geometry)
                        for q in model
                    ]
                )
                analytic_max = float(max(fwd.max(), back.max()))
            records.append(
                {
                    "shape": name,
                    "candidate": c.id,
                    "family": c.family,
                    "accepted": c.accepted,
                    "selected": c.id == result.selected_id,
                    "pareto": c.pareto,
                    "pixel_sampled_H": c.metrics.get("sampled_hausdorff"),
                    "pixel_H_upper": c.metrics.get("hausdorff_upper_bound"),
                    "pixel_rms": c.metrics.get("rms"),
                    "analytic_sampled_H": analytic_max,
                    "piece_count": len(c.pieces),
                    "parameters_upper": c.complexity.get("free_parameters_upper"),
                    "complexity_bits": c.complexity.get("score_bits"),
                    "topology_pass": c.metrics.get("topology", {}).get("preserved", False)
                    or c.family == "exact",
                    "topology_scope": c.metrics.get("topology", {}).get("scope"),
                    "seconds": c.metrics.get("elapsed_seconds"),
                    "rejection": "; ".join(c.reasons),
                }
            )
        poly = result.polynomial
        poly_paths = [np.asarray(p) for p in poly.diagnostics["zero_paths"]]
        poly_analytic = None
        if poly_paths:
            poly_geometry = MultiLineString(poly_paths)
            forward = np.concatenate(
                [
                    shapely.distance(shapely.points(sample_ring(q, 1)[0]), poly_geometry)
                    for q in truth_lines
                ]
            )
            backward = np.concatenate(
                [
                    shapely.distance(shapely.points(sample_ring(q, 1)[0]), truth_geometry)
                    for q in poly_paths
                ]
            )
            poly_analytic = float(max(forward.max(), backward.max()))
        records.append(
            {
                "shape": name,
                "candidate": "implicit-degree4",
                "family": "implicit",
                "accepted": False,
                "selected": False,
                "pareto": False,
                "pixel_sampled_H": poly.diagnostics["sampled_point_cloud_distance"],
                "pixel_H_upper": None,
                "pixel_rms": poly.diagnostics["sampled_point_cloud_rms"],
                "analytic_sampled_H": poly_analytic,
                "piece_count": None,
                "parameters_upper": len(poly.terms) - 1,
                "complexity_bits": len(poly.terms) * 64 + 32,
                "topology_pass": False,
                "topology_scope": "unproven_grid_diagnostic",
                "seconds": poly.diagnostics["elapsed_seconds"],
                "rejection": "Izgara sıfır dallarının tamlığını kanıtlamaz; seçilebilir aday değil.",
            }
        )
        if name in {"square", "circle", "ellipse", "corner_curve"}:
            selected_examples.append((name, result))
        if name in {"circle", "corner_curve"}:
            export_result(result, directory / name, options=ExportOptions(pixel_size=1200))
    fields = list(records[0])
    with (directory / "results.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    payload = {
        "method": "bounded_family_search_v2",
        "config": config.__dict__,
        "seed": 20261014,
        "python": sys.version,
        "platform": platform.platform(),
        "versions": result.provenance["versions"],
        "elapsed_seconds": time.perf_counter() - started,
        "analytic_metric": "sampled bidirectional point-to-polyline; spacing<=1, both flatten bounds<=0.02",
        "notes": "12 tek çözünürlüklü sentetik girdi; genelleme veya tüm platformlarda kararlılık kanıtı değil.",
        "records": records,
    }
    (directory / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8"
    )
    fig = Figure(figsize=(12, 9), dpi=130, layout="tight")
    FigureCanvasAgg(fig)
    for ax, (name, res) in zip(fig.subplots(2, 2).flat, selected_examples, strict=True):
        for b in res.reference_boundaries:
            q = np.asarray([*b.vertices, b.vertices[0]])
            ax.plot(q[:, 0], q[:, 1], color="#a9b6c1", lw=2)
        for p in res.selected.pieces:
            q = flatten(p, 0.03)
            ax.plot(q[:, 0], q[:, 1], color="#087f8c", lw=1)
        ax.set_title(
            f"{name} · {res.selected_id}\nH üst={res.selected.metrics['hausdorff_upper_bound']:.3g}; parça={len(res.selected.pieces)}"
        )
        ax.set(xlim=(0, 1000), ylim=(0, 1000))
        ax.set_aspect("equal")
        ax.grid(alpha=0.2)
    fig.savefig(directory / "comparison.png")
    fig.clear()
    return directory / "results.json"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Analitik/raster ayrımlı yerel deney düzeneği")
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(run_benchmark(args.directory, progress=print))
