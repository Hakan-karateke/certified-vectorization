"""Herhangi bir vektörleştiricinin SVG çıktısını bağımsız denetleyiciyle sertifikalar.

Denetleyici yalnızca bir modele ve referans piksel sınırına ihtiyaç duyar; modeli
kimin ürettiği önemli değildir. Akış:

    1. python examples/certify_svg.py bitmap girdi.png normal.png
       Girdiyi eşikler ve 1000 × 1000 çalışma düzlemine yerleştirir. Denetlenecek
       araç bu dosyayı izlemelidir; böylece iki taraf aynı referansı görür.
    2. Aracı normal.png üzerinde ikili (tek renk, üst üste binmeyen) kipte çalıştırın.
    3. python examples/certify_svg.py audit girdi.png cikti.svg

Desteklenen yol komutları: M L H V C S Q T Z (mutlak ve göreli) ve path/g
öğelerindeki translate, scale, rotate, matrix dönüşümleri. Eliptik yay (A)
desteklenmez. SVG kullanıcı birimi bir piksel sayılır; viewBox ile width/height
farklıysa viewBox birimleri kullanılır. Her kapalı alt yol bir halkadır ve
referans halkalarla en düşük maliyetli eşlemeyle eşlenir; halka sayısı
farklıysa model sertifikalanamaz.
"""

import argparse
import io
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?"
COUNTS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "Z": 0}


def _transform(text: str | None) -> np.ndarray:
    matrix = np.eye(3)
    for name, body in re.findall(r"(\w+)\s*\(([^)]*)\)", text or ""):
        v = [float(x) for x in re.findall(NUMBER, body)]
        step = np.eye(3)
        if name == "translate":
            step[0, 2], step[1, 2] = v[0], v[1] if len(v) > 1 else 0.0
        elif name == "scale":
            step[0, 0], step[1, 1] = v[0], v[1] if len(v) > 1 else v[0]
        elif name == "rotate" and len(v) == 1:
            c, s = np.cos(np.radians(v[0])), np.sin(np.radians(v[0]))
            step[:2, :2] = [[c, -s], [s, c]]
        elif name == "matrix":
            step[:2, :] = [[v[0], v[2], v[4]], [v[1], v[3], v[5]]]
        else:
            raise ValueError(f"Desteklenmeyen dönüşüm: {name}")
        matrix = matrix @ step
    return matrix


def _subpaths(data: str) -> list[list[tuple[str, list[np.ndarray]]]]:
    """Yol verisini kapalı alt yollara ayırır; parça = ('line'|'bezier', kontrol noktaları)."""
    tokens = re.findall(rf"[A-Za-z]|{NUMBER}", data)
    rings, ring = [], []
    position = start = np.zeros(2)
    previous, command, i = None, None, 0
    while i < len(tokens):
        if tokens[i].isalpha():
            command = tokens[i]
            i += 1
            if command.upper() not in COUNTS:
                raise ValueError(f"Desteklenmeyen yol komutu: {command}")
            if command.upper() == "Z":
                if ring:
                    if np.hypot(*(position - start)) > 0:
                        ring.append(("line", [position, start]))
                    rings.append(ring)
                ring, position, previous = [], start, None
            continue
        kind = command.upper()
        values = np.asarray(tokens[i : i + COUNTS[kind]], dtype=float)
        i += COUNTS[kind]
        relative = command.islower()
        if kind == "H":
            target = np.array([values[0] + (position[0] if relative else 0.0), position[1]])
            points = [target]
        elif kind == "V":
            target = np.array([position[0], values[0] + (position[1] if relative else 0.0)])
            points = [target]
        else:
            points = [p + position if relative else p for p in values.reshape(-1, 2)]
        if kind == "M":
            if ring:
                raise ValueError("Kapanmamış alt yol; her halka Z ile kapanmalıdır.")
            position = start = points[0]
            command = "l" if relative else "L"
            previous = None
            continue
        if kind in "LHV":
            controls = [position, points[0]]
        elif kind == "C":
            controls = [position, *points]
        elif kind == "S":
            mirror = 2 * position - previous[1][-2] if previous and previous[0] == "C" else position
            controls = [position, mirror, *points]
        elif kind == "Q":
            controls = [position, *points]
        else:  # T
            mirror = 2 * position - previous[1][-2] if previous and previous[0] == "Q" else position
            controls = [position, mirror, points[0]]
        ring.append(("line" if len(controls) == 2 else "bezier", controls))
        previous = ("C" if kind in "CS" else "Q" if kind in "QT" else "L", controls)
        position = controls[-1]
    if ring:
        raise ValueError("Kapanmamış alt yol; her halka Z ile kapanmalıdır.")
    return rings


def read_svg(path: Path, height: float) -> list[list[tuple[str, list[np.ndarray]]]]:
    """SVG'deki bütün kapalı alt yolları çalışma düzlemi koordinatlarında döndürür."""
    root = ET.parse(path).getroot()
    base = np.eye(3)
    box = [float(x) for x in re.findall(NUMBER, root.get("viewBox", ""))]
    if len(box) == 4:
        base = _transform(f"translate({-box[0]},{-box[1]})")
    rings = []

    def visit(node: ET.Element, matrix: np.ndarray) -> None:
        matrix = matrix @ _transform(node.get("transform"))
        if node.tag.rsplit("}", 1)[-1] == "path":
            for ring in _subpaths(node.get("d", "")):
                moved = []
                for kind, controls in ring:
                    out = []
                    for point in controls:
                        x, y, _ = matrix @ np.array([point[0], point[1], 1.0])
                        out.append(np.array([x, height - y]))
                    moved.append((kind, out))
                rings.append(moved)
        for child in node:
            visit(child, matrix)

    visit(root, base)
    return rings


def _sample(ring: list, per_piece: int = 24) -> np.ndarray:
    points = []
    u = np.linspace(0, 1, per_piece, endpoint=False)[:, None]
    for _, controls in ring:
        level = [np.asarray(c, dtype=float)[None, :] for c in controls]
        while len(level) > 1:
            level = [(1 - u) * a + u * b for a, b in zip(level, level[1:], strict=False)]
        points.append(np.broadcast_to(level[0], (per_piece, 2)))
    return np.concatenate(points)


def _area(ring: np.ndarray) -> float:
    x, y = ring[:, 0], ring[:, 1]
    return float(x @ np.roll(y, -1) - y @ np.roll(x, -1)) / 2


def _reference(ring: np.ndarray, spacing: float = 1.0) -> np.ndarray:
    closed = np.vstack([ring, ring[:1]])
    parts = []
    for a, b in zip(closed, closed[1:], strict=False):
        count = max(1, int(np.ceil(np.hypot(*(b - a)) / spacing)))
        parts.append(a + (b - a) * (np.arange(count) / count)[:, None])
    return np.concatenate(parts)


def audit(mask: np.ndarray, rings: list, spacing: float = 0.25, delta: float = 0.005) -> dict:
    """Halkaları referansla eşler ve sertifikayı çalıştırır."""
    from sekilden_denkleme.certification import certify
    from sekilden_denkleme.curves import new_piece
    from sekilden_denkleme.evaluation import reference_topology
    from sekilden_denkleme.geometry import trace_boundaries
    from sekilden_denkleme.models import Candidate

    boundaries = trace_boundaries(mask)
    topology = reference_topology(boundaries)
    components = [r["component_id"] for r in topology["rings"]]
    record = {
        "reference_rings": len(boundaries),
        "model_rings": len(rings),
        "reference_contacts": len(topology["contacts"]),
        "pieces": sum(len(ring) for ring in rings),
    }
    if len(rings) != len(boundaries):
        return {**record, "status": "ring_count_mismatch"}
    samples = [_sample(ring) for ring in rings]
    reference = [_reference(np.asarray(b.vertices, dtype=float)) for b in boundaries]
    trees = [cKDTree(points) for points in reference]
    cost = np.empty((len(samples), len(reference)))
    for i, points in enumerate(samples):
        own = cKDTree(points)
        for j, tree in enumerate(trees):
            cost[i, j] = max(tree.query(points)[0].max(), own.query(reference[j])[0].max())
    rows, columns = linear_sum_assignment(cost)
    pieces = []
    for i, j in zip(rows.tolist(), columns.tolist(), strict=True):
        ring = rings[i]
        if _area(samples[i]) * _area(np.asarray(boundaries[j].vertices, dtype=float)) < 0:
            ring = [(kind, controls[::-1]) for kind, controls in ring[::-1]]
        first = np.asarray(ring[0][1][0], dtype=float)
        position = first
        for index, (kind, controls) in enumerate(ring):
            controls = [np.asarray(c, dtype=float) for c in controls]
            # Tam C0 kapanış: her parça öncekinin bittiği sayıda başlar.
            controls[0] = position
            if index == len(ring) - 1:
                if np.hypot(*(controls[-1] - first)) > 1e-6:
                    raise ValueError("Halka kapanmıyor.")
                controls[-1] = first
            position = controls[-1]
            if kind == "line":
                if np.array_equal(controls[0], controls[1]):
                    continue
                params = {"a": controls[0].tolist(), "b": controls[1].tolist()}
                pieces.append(new_piece("line", params, [0.0, 1.0], j, components[j]))
            else:
                params = {"controls": [c.tolist() for c in controls]}
                pieces.append(new_piece("bezier", params, [0.0, 1.0], j, components[j]))
    pieces.sort(key=lambda piece: piece.boundary_id)
    started = time.perf_counter()
    proof = certify(Candidate("external", "bezier", pieces), boundaries, 1000.0, spacing, delta)
    return {
        **record,
        "status": "certified",
        "certify_seconds": time.perf_counter() - started,
        "certified_upper_bound": proof.get("hausdorff_upper_bound"),
        "topology_proven": bool(proof.get("analytic_isotopy_proven")),
        "topology_method": proof.get("topology_method"),
        "certificate_reasons": proof["reasons"],
    }


def main() -> None:
    from sekilden_denkleme.imaging import normalize_image

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    bitmap = commands.add_parser("bitmap")
    bitmap.add_argument("input", type=Path)
    bitmap.add_argument("output", type=Path)
    check = commands.add_parser("audit")
    check.add_argument("input", type=Path)
    check.add_argument("svg", type=Path)
    check.add_argument("--spacing", type=float, default=0.25)
    check.add_argument("--delta", type=float, default=0.005)
    options = parser.parse_args()
    mask, _ = normalize_image(io.BytesIO(options.input.read_bytes()), 127, 20)
    if options.command == "bitmap":
        Image.fromarray(np.where(mask, 0, 255).astype("uint8")).save(options.output)
        return
    try:
        rings = read_svg(options.svg, float(mask.shape[0]))
        report = audit(mask, rings, options.spacing, options.delta)
    except ValueError as error:
        report = {"status": "unsupported", "error": str(error)}
    print(json.dumps(report, indent=1, ensure_ascii=False))
    sys.exit(0 if report["status"] == "certified" else 1)


if __name__ == "__main__":
    main()
