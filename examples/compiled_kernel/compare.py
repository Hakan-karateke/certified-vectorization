"""Doğru + yay aramasının baskın çekirdeğini NumPy ve derlenmiş C# ile karşılaştırır.

optimal_arcs._arc_steps, bir halkanın bütün düğüm çiftleri için uygun yay
olup olmadığını (üst küme) hesaplar ve arama süresinin büyük kısmını alır.
Bu betik her halka için NumPy süresini ölçer, girdiyi ikili dosyaya yazar,
ArcKernel.cs'yi PowerShell üzerinden derleyip çalıştırır ve iki matrisin
aynı olup olmadığını denetler. Tam aritmetik doğrulama ve tur araması
karşılaştırmaya dahil değildir.

Kullanım (depo kökünden, Windows):
    python examples/compiled_kernel/compare.py examples/compiled_kernel/results
"""

import io
import json
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
ICONS = ("bi_wrench", "bi_3-square", "bi_gear", "bi_feather", "bi_globe", "bi_alexa")
EPSILONS = (1.0, 2.0, 5.0)
MAX_SPAN = 512


def main() -> None:
    from sekilden_denkleme.geometry import trace_boundaries
    from sekilden_denkleme.imaging import normalize_image
    from sekilden_denkleme.optimal_arcs import _arc_steps, dense_nodes
    from sekilden_denkleme.optimal_polygon import _shortcut_steps

    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob("*.in"):
        stale.unlink()
    cases = {}
    for icon in ICONS:
        png = ROOT / "examples/icon_dataset/png" / f"{icon}.png"
        mask, _ = normalize_image(io.BytesIO(png.read_bytes()), 127, 20)
        boundaries = trace_boundaries(mask)
        for epsilon in EPSILONS:
            spacing = min(1.0, max(0.05, epsilon / 4))
            delta = min(0.05, max(0.0001, epsilon / 16))
            tolerance = epsilon - spacing / 2 - 2 * delta - 1e-6
            eager = tolerance < 1.5
            refine, full_below = (64, 256) if eager else (0, 0)
            for ring, boundary in enumerate(boundaries):
                points = dense_nodes(boundary)
                m = len(points)
                if m < 8:
                    continue
                lines = _shortcut_steps(points, tolerance)
                started = time.perf_counter()
                valid, _ = _arc_steps(points, tolerance, MAX_SPAN, lines, 12, refine, full_below)
                seconds = time.perf_counter() - started
                depth = len(valid)
                straight = np.zeros((depth + 1, m), dtype=np.uint8)
                for i, steps in enumerate(lines):
                    straight[steps[steps <= depth], i] = 1
                name = f"{icon}_e{epsilon:g}_r{ring}"
                with (output / f"{name}.in").open("wb") as handle:
                    handle.write(struct.pack("<5id", m, depth, 12, refine, full_below, tolerance))
                    handle.write(points.astype("<f8").tobytes())
                    handle.write(straight.tobytes())
                np.save(output / f"{name}.npy", valid)
                cases[name] = {
                    "icon": icon,
                    "epsilon": epsilon,
                    "nodes": m,
                    "numpy_seconds": seconds,
                    "valid_pairs": int(valid.sum()),
                }
    done = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
        + [str(Path(__file__).parent / "run.ps1"), "-Folder", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    runtime = done.stdout.strip().splitlines()[-1]
    timings = json.loads((output / "timings.json").read_text(encoding="utf-8-sig"))
    for name, case in cases.items():
        valid = np.load(output / f"{name}.npy")
        compiled = np.fromfile(output / f"{name}.out", dtype=np.uint8).reshape(valid.shape) != 0
        case["compiled_seconds"] = timings[name]
        case["differing_pairs"] = int((compiled != valid).sum())
    for pattern in ("*.in", "*.out", "*.npy"):
        for file in output.glob(pattern):
            file.unlink()
    rows = []
    for epsilon in EPSILONS:
        part = [c for c in cases.values() if c["epsilon"] == epsilon]
        rows.append(
            {
                "epsilon": epsilon,
                "rings": len(part),
                "nodes": sum(c["nodes"] for c in part),
                "valid_pairs": sum(c["valid_pairs"] for c in part),
                "differing_pairs": sum(c["differing_pairs"] for c in part),
                "numpy_seconds": sum(c["numpy_seconds"] for c in part),
                "compiled_seconds": sum(c["compiled_seconds"] for c in part),
                "speedup": sum(c["numpy_seconds"] for c in part)
                / sum(c["compiled_seconds"] for c in part),
            }
        )
    summary = {"runtime": runtime, "icons": list(ICONS), "by_epsilon": rows, "cases": cases}
    (output / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps({"runtime": runtime, "by_epsilon": rows}, indent=1))


if __name__ == "__main__":
    main()
