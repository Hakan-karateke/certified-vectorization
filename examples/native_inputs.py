"""Kendi çözünürlüğünde (1000 birimlik tuvale küçültmeden) büyük ve renkli girdi deneyleri.

Uygulamanın hattı her görseli 1000 × 1000 çalışma düzlemine yeniden örnekler; bu
betik o adımı atlar ve çekirdek işlevleri (sınır izleme, kanıtlı en az parçalı
çokgen ve doğru + yay halkası, bağımsız sertifika) doğrudan kaynak piksel
ızgarasında çalıştırır. Tolerans kaynak pikseli birimindedir.

Girdiler sentetiktir ve tohumla yeniden üretilir:
    terrain: yumuşatılmış gürültünün eş yükselti bantları (harita benzeri);
    drawing: kalın çizgi, çember ve dikdörtgenlerden teknik çizim benzeri raster.

Kullanım:
    python examples/native_inputs.py scale examples/native_inputs/scale --sizes 1024 2048 4096
    python examples/native_inputs.py color examples/native_inputs/color --size 2048
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

SEED = 20261115
FEATURE = 48.0  # terrain: Gauss süzgecinin standart sapması, piksel
NODE_LIMIT = 2_000_000
SEARCH_LIMIT = 3000  # ortak aramanın dış düğüm sınırı (varsayılan 300)
EDGE_LIMIT = 8_000_000
SAMPLE_LIMIT = 20_000_000


def terrain_field(size: int, seed: int = SEED) -> np.ndarray:
    """[0, 1] aralığına sıralanmış yumuşak rastgele yükseklik alanı (özellik ölçeği sabit)."""
    rng = np.random.default_rng(seed)
    field = ndimage.gaussian_filter(rng.standard_normal((size, size)), FEATURE, mode="wrap")
    ranks = field.ravel().argsort().argsort().reshape(field.shape)
    return ranks / (field.size - 1)


def drawing_mask(size: int, seed: int = SEED) -> np.ndarray:
    """Çizgi kalınlığı ve nesne sayısı görsel boyutuyla ölçeklenen teknik çizim benzeri maske."""
    rng = np.random.default_rng(seed)
    image = Image.new("L", (size, size), 255)
    draw = ImageDraw.Draw(image)
    cells = max(2, size // 256)
    step = size / cells
    for row in range(cells):
        for col in range(cells):
            x0, y0 = col * step + 0.12 * step, row * step + 0.12 * step
            x1, y1 = (col + 1) * step - 0.12 * step, (row + 1) * step - 0.12 * step
            kind = int(rng.integers(4))
            width = int(rng.integers(3, 9))
            if kind == 0:
                draw.ellipse((x0, y0, x1, y1), outline=0, width=width)
            elif kind == 1:
                draw.rounded_rectangle((x0, y0, x1, y1), radius=step * 0.18, outline=0, width=width)
            elif kind == 2:
                points = rng.uniform((x0, y0), (x1, y1), (5, 2))
                draw.line([tuple(p) for p in points], fill=0, width=width, joint="curve")
            else:
                draw.pieslice((x0, y0, x1, y1), 20, 290, fill=0)
                inset = 0.3 * (x1 - x0)
                draw.ellipse((x0 + inset, y0 + inset, x1 - inset, y1 - inset), fill=255)
    return np.asarray(image) == 0


def analyse_mask(mask: np.ndarray, epsilon: float, families: tuple[str, ...]) -> tuple[dict, dict]:
    """Bir ikili maskeyi çözer; (kayıt, aile → parçalar) döndürür."""
    from sekilden_denkleme import certification
    from sekilden_denkleme.certification import certify
    from sekilden_denkleme.evaluation import reference_topology
    from sekilden_denkleme.fitting import polygon_pieces
    from sekilden_denkleme.geometry import trace_boundaries
    from sekilden_denkleme.models import Boundary, Candidate
    from sekilden_denkleme.optimal_arcs import min_piece_boundaries
    from sekilden_denkleme.optimal_polygon import constrained_min_link, node_sequence

    certification.MAX_SAMPLES = SAMPLE_LIMIT
    started = time.perf_counter()
    boundaries = trace_boundaries(mask, EDGE_LIMIT)
    trace_seconds = time.perf_counter() - started
    started = time.perf_counter()
    topology = reference_topology(boundaries)
    components = [r["component_id"] for r in topology["rings"]]
    record = {
        "epsilon": epsilon,
        "pixels": int(mask.size),
        "rings": len(boundaries),
        "reference_edges": sum(len(b.vertices) for b in boundaries),
        "largest_ring_edges": max(len(b.vertices) for b in boundaries),
        "contacts": len(topology["contacts"]),
        "trace_seconds": trace_seconds,
        "topology_seconds": time.perf_counter() - started,
    }
    spacing = min(0.5, max(0.05, epsilon / 4))
    delta = min(0.025, max(0.0001, epsilon / 32))
    models = {}
    for family in families:
        started = time.perf_counter()
        if family == "polygon":
            # min_link_boundaries ile aynı çözüm; yalnızca 40.000 düğüm sınırı kaldırılır.
            nodes = [node_sequence(boundary, 2) for boundary in boundaries]
            info = constrained_min_link(
                nodes, epsilon - spacing / 2 - 1e-6, 0.25, SEARCH_LIMIT, NODE_LIMIT
            )
            rings = [
                Boundary([tuple(map(float, n[i])) for i in cycle], b.kind, b.original_vertex_count)
                for b, n, cycle in zip(boundaries, nodes, info["cycles"], strict=True)
            ]
            pieces = [p for i, b in enumerate(rings) for p in polygon_pieces(b, i, components[i])]
        else:
            pieces, info = min_piece_boundaries(
                boundaries, epsilon - spacing / 2 - 2 * delta - 1e-6, components
            )
        search_seconds = time.perf_counter() - started
        started = time.perf_counter()
        proof = certify(Candidate(family, family, pieces), boundaries, epsilon, spacing, delta)
        record[family] = {
            "pieces": len(pieces),
            "arcs": sum(p.kind == "circle" for p in pieces),
            "optimal_in_class": bool(info["optimal"]),
            "search_seconds": search_seconds,
            "certify_seconds": time.perf_counter() - started,
            "certificate_status": proof["status"],
            "certified_upper_bound": proof.get("hausdorff_upper_bound"),
            "topology_method": proof.get("topology_method"),
            "certificate_reasons": proof["reasons"],
        }
        models[family] = pieces
    return record, models


def render_layers(shape: tuple[int, int], layers: list[list], delta: float = 0.01) -> np.ndarray:
    """Katmanları arkadan öne boyar; her piksel merkezinin katman indeksini döndürür.

    İkili ölçek büyütme yapılmaz: çokgenler piksel merkezi kuralıyla, çift-tek
    doldurmayla taranır. Katman k, k ve sonrasındaki renklerin birleşimidir.
    """
    from matplotlib.path import Path as MplPath

    from sekilden_denkleme.curves import model_rings

    height, width = shape
    label = np.zeros(shape, dtype=np.int16)
    ys, xs = np.mgrid[0:height, 0:width]
    centres = np.column_stack((xs.ravel() + 0.5, height - (ys.ravel() + 0.5)))
    for index, pieces in enumerate(layers, start=1):
        # Çift-tek doldurma: her halka ayrı sınanır ve sonuçlar XOR'lanır, böylece
        # iç içe halkalarda delikler yönlerinden bağımsız olarak çıkarılır.
        inside = np.zeros(len(centres), dtype=bool)
        for ring in model_rings(pieces, delta).values():
            ring = np.asarray(ring)
            low, high = ring.min(0), ring.max(0)
            near = np.flatnonzero(((centres >= low) & (centres <= high)).all(1))
            inside[near] ^= MplPath(ring, closed=False).contains_points(centres[near])
        label[inside.reshape(shape)] = index
    return label


def run_scale(options: argparse.Namespace) -> None:
    options.output.mkdir(parents=True, exist_ok=True)
    records = []
    for kind in options.kinds:
        for size in options.sizes:
            mask = terrain_field(size) >= 0.5 if kind == "terrain" else drawing_mask(size)
            Image.fromarray(np.where(mask, 0, 255).astype("uint8")).save(
                options.output / f"{kind}_{size}.png"
            )
            for epsilon in options.epsilons:
                try:
                    record, _ = analyse_mask(mask, epsilon, tuple(options.families))
                except (ValueError, MemoryError) as error:
                    record = {"epsilon": epsilon, "failed": repr(error)}
                record.update(kind=kind, size=size)
                records.append(record)
                print(json.dumps(record, ensure_ascii=False), flush=True)
                (options.output / "results.json").write_text(
                    json.dumps(records, indent=1, ensure_ascii=False), encoding="utf-8"
                )


def run_color(options: argparse.Namespace) -> None:
    from scipy.spatial import cKDTree

    from sekilden_denkleme.geometry import sample_boundaries, trace_boundaries

    options.output.mkdir(parents=True, exist_ok=True)
    size, levels = options.size, options.levels
    field = terrain_field(size)
    index = np.minimum((field * levels).astype(np.int16), levels - 1)
    palette = np.asarray(
        [
            (38, 84, 124),
            (86, 150, 170),
            (196, 214, 160),
            (150, 180, 110),
            (176, 140, 90),
            (240, 240, 235),
        ]
    )[:levels]
    Image.fromarray(palette[index].astype("uint8")).save(options.output / f"terrain_{size}.png")
    results = []
    for epsilon in options.epsilons:
        for family in options.families:
            layers, rows = [], []
            for level in range(1, levels):
                mask = index >= level
                record, models = analyse_mask(mask, epsilon, (family,))
                record["layer"] = level
                rows.append(record)
                layers.append(models[family])
            started = time.perf_counter()
            label = render_layers(index.shape, layers)
            wrong = label != index
            distance = 0.0
            if wrong.any():
                rings = [
                    b
                    for level in range(1, levels)
                    for b in trace_boundaries(index >= level, EDGE_LIMIT)
                ]
                length = sum(
                    np.hypot(*(np.roll(v, -1, axis=0) - v).T).sum()
                    for v in (np.asarray(b.vertices, dtype=float) for b in rings)
                )
                points = sample_boundaries(rings, int(4 * length))
                ys, xs = np.nonzero(wrong)
                centres = np.column_stack((xs + 0.5, size - (ys + 0.5)))
                distance = float(cKDTree(points).query(centres)[0].max())
            Image.fromarray(palette[label].astype("uint8")).save(
                options.output / f"terrain_{size}_{family}_e{epsilon:g}.png"
            )
            summary = {
                "size": size,
                "levels": levels,
                "epsilon": epsilon,
                "family": family,
                "layers": rows,
                "pieces": sum(r[family]["pieces"] for r in rows),
                "reference_edges": sum(r["reference_edges"] for r in rows),
                "all_layers_proven": all(r[family]["certificate_status"] == "proven" for r in rows),
                "all_layers_optimal_in_class": all(r[family]["optimal_in_class"] for r in rows),
                "search_seconds": sum(r[family]["search_seconds"] for r in rows),
                "certify_seconds": sum(r[family]["certify_seconds"] for r in rows),
                "mismatched_pixels": int(wrong.sum()),
                "mismatched_fraction": float(wrong.mean()),
                "max_mismatch_distance_to_boundary": distance,
                "render_seconds": time.perf_counter() - started,
            }
            results.append(summary)
            print(json.dumps({k: v for k, v in summary.items() if k != "layers"}), flush=True)
            (options.output / "results.json").write_text(
                json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    scale = commands.add_parser("scale")
    scale.add_argument("output", type=Path)
    scale.add_argument("--sizes", type=int, nargs="+", default=[1024, 2048, 4096])
    scale.add_argument("--kinds", nargs="+", default=["terrain", "drawing"])
    scale.set_defaults(run=run_scale)
    color = commands.add_parser("color")
    color.add_argument("output", type=Path)
    color.add_argument("--size", type=int, default=2048)
    color.add_argument("--levels", type=int, default=6)
    color.set_defaults(run=run_color)
    for sub in (scale, color):
        sub.add_argument("--epsilons", type=float, nargs="+", default=[1.0, 2.0])
        sub.add_argument("--families", nargs="+", default=["polygon", "linearc"])
    options = parser.parse_args()
    options.run(options)


if __name__ == "__main__":
    main()
