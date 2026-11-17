"""Hash doğrulamalı yerel veri kümesinde yalıtılmış, devam ettirilebilir tolerans taraması.

Her analiz ayrı süreçte çalışır; süre aşımı ve iptal süreci sonlandırabilir.
Ara sonuçlar atomik saklanır. Raporlar ideal analitik şekli değil raster sınırını
ölçer. Kaynak kodu veya ayar değişirse eski çalışma sessizce devam ettirilmez.
"""

import argparse
import copy
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, replace
from pathlib import Path
from threading import Event
from typing import Any


def _atomic_json(path: Path, value: Any) -> None:
    """Tamamlanmış UTF-8 JSON'u aynı klasörde atomik olarak yayımlar."""
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf8"
    )
    temp.replace(path)


def source_digest(source_root: Path) -> str:
    """Analiz kaynak ağacını dosya adı ve içeriğiyle SHA-256 olarak tanımlar."""
    digest = hashlib.sha256()
    for path in sorted((source_root / "sekilden_denkleme").glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _brief(candidate: Any) -> dict:
    """Aday geometrisini çoğaltmadan ölçümleri ve kanıt kapsamını kaydeder."""
    return {
        "id": candidate.id,
        "family": candidate.family,
        "accepted": candidate.accepted,
        "pareto": candidate.pareto,
        "complexity": candidate.complexity,
        "types": dict(
            Counter(p.kind + ("_arc" if "arc" in p.params else "") for p in candidate.pieces)
        ),
        "metrics": {
            k: v
            for k, v in candidate.metrics.items()
            if k not in {"per_boundary", "topology_witness"}
        },
        "reasons": candidate.reasons,
    }


def _worker(path: Path, epsilon: float) -> dict:
    """Bir auto/dengeli analizi ve yeniden uydurmadan sıkı seçimi gerçek çalıştırır."""
    from sekilden_denkleme import AnalysisConfig, analyze
    from sekilden_denkleme.fitting import certify_selection

    config = AnalysisConfig(
        family="auto",
        tolerance=epsilon,
        preference="balanced",
        padding=20,
        evaluation_workers=1,
        certificate_mode="selected",
    )
    start = time.perf_counter()
    result = analyze(path, config)
    elapsed = time.perf_counter() - start
    candidates = copy.deepcopy(result.candidates)
    strict_start = time.perf_counter()
    selected_id = certify_selection(
        candidates, result.reference_boundaries, replace(config, certificate_mode="strict")
    )
    # Kısıtlı problem (min C, E ≤ ε): "daha sade" tercihi, yeniden uydurma olmadan.
    simple = copy.deepcopy(result.candidates)
    simple_id = certify_selection(
        simple, result.reference_boundaries, replace(config, preference="simple")
    )
    simple_strict = copy.deepcopy(result.candidates)
    simple_strict_id = certify_selection(
        simple_strict,
        result.reference_boundaries,
        replace(config, preference="simple", certificate_mode="strict"),
    )
    # Maliyet modeli duyarlılığı: aynı adaylar, mdl_v1 kod uzunluğuyla seçim.
    mdl = copy.deepcopy(result.candidates)
    mdl_id = certify_selection(
        mdl,
        result.reference_boundaries,
        replace(config, preference="simple", certificate_mode="strict"),
        cost_key="mdl_bits",
    )
    return {
        "status": "ok",
        "config": asdict(config),
        "simple_strict_mdl_selected": _brief(next(c for c in mdl if c.id == mdl_id)),
        "selected": _brief(result.selected),
        "strict_selected": _brief(next(c for c in candidates if c.id == selected_id)),
        "simple_selected": _brief(next(c for c in simple if c.id == simple_id)),
        "simple_strict_selected": _brief(
            next(c for c in simple_strict if c.id == simple_strict_id)
        ),
        "analysis_seconds": elapsed,
        "strict_reselection_seconds": time.perf_counter() - strict_start,
        "topology": result.topology,
        "reference_piece_count": sum(len(b.vertices) for b in result.reference_boundaries),
        "candidates": [_brief(c) for c in result.candidates],
        "strict_rejections": [
            {"id": c.id, "certificate": c.metrics.get("certification")}
            for c in candidates
            if c.accepted is False
            and c.metrics.get("certification", {}).get("status") == "undetermined"
        ],
        "provenance": {k: v for k, v in result.provenance.items() if "base64" not in k},
        "normalization": result.normalization,
    }


def run_grid(
    manifest_path: str | Path,
    directory: str | Path,
    *,
    tolerances: tuple[float, ...] = (1, 2, 3, 5),
    workers: int = 4,
    timeout: float = 240,
    ids: list[str] | None = None,
    cancel: Event | None = None,
    progress: Callable[[str], None] | None = None,
    source_root: str | Path | None = None,
) -> Path:
    """Manifestteki her görsel × tolerans çiftini yalıtılmış süreçte çalıştırır.

    workers 1..8 süreç, timeout her işin başlatma dahil saniye sınırıdır.
    Tamamlanmış ve aynı parmak izli işler tekrar çalıştırılmaz. İptalde yeni
    işler başlamaz, çalışanlar kapanır; doğrulanmış ara dosyalar korunur.
    """
    from sekilden_denkleme.fitting import AnalysisCancelled

    if (
        not 1 <= workers <= 8
        or not math.isfinite(timeout)
        or timeout <= 0
        or not tolerances
        or any(not 0 < e <= 50 for e in tolerances)
    ):
        raise ValueError("Tarama işçi, süre veya tolerans ayarı geçersiz.")
    manifest_path, directory = Path(manifest_path).resolve(), Path(directory).resolve()
    source_root = (
        Path(source_root).resolve() if source_root else Path(__file__).resolve().parents[1]
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf8"))
    assets = [a for a in manifest["assets"] if ids is None or a["id"] in ids]
    if any(
        not isinstance(a["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", a["id"])
        for a in assets
    ):
        raise ValueError("Tarama girdi kimliği yalnız harf, rakam, alt çizgi ve tire içerebilir.")
    if len({a["id"] for a in assets}) != len(assets) or len(set(tolerances)) != len(tolerances):
        raise ValueError("Tarama girdi kimlikleri ve toleransları benzersiz olmalıdır.")
    if not assets or (ids and len(assets) != len(set(ids))):
        raise ValueError("Manifestte istenen girdi bulunamadı.")
    paths = {}
    for asset in assets:
        path = (manifest_path.parent / asset["png_path"]).resolve()
        if not path.is_relative_to(manifest_path.parent):
            raise ValueError("Girdi manifest klasörü dışında.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256_png"]:
            raise ValueError(f"Girdi SHA-256 uyuşmuyor: {asset['id']}")
        paths[asset["id"]] = path
    setup = {
        "experiment_schema": "1.0",
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "source_sha256": source_digest(source_root),
        "tolerances": list(tolerances),
        "ids": [a["id"] for a in assets],
        "workers": workers,
        "timeout_seconds": timeout,
        "config": "auto/balanced/selected then strict reselection; padding20; deterministic; one evaluation worker",
        "python": sys.version,
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "blas_threads_per_process": 1,
    }
    fingerprint = hashlib.sha256(json.dumps(setup, sort_keys=True).encode()).hexdigest()
    setup["fingerprint"] = fingerprint
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "cases").mkdir(exist_ok=True)
    metadata = directory / "experiment.json"
    if (
        metadata.exists()
        and json.loads(metadata.read_text(encoding="utf8"))["fingerprint"] != fingerprint
    ):
        raise ValueError(
            "Önceki taramanın kod/ortam/ayar parmak izi farklı; yeni sonuç klasörü seçin."
        )
    _atomic_json(metadata, setup)
    tasks = [(a, e) for a in assets for e in tolerances]
    env = dict(
        os.environ,
        PYTHONPATH=str(source_root),
        PYTHONUTF8="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        OMP_NUM_THREADS="1",
        NUMEXPR_NUM_THREADS="1",
    )

    def execute(asset: dict, epsilon: float) -> dict:
        """Süre/iptal denetimiyle çocuğu bekler; başarısızlığı ölçüm gibi sunmaz."""
        destination = directory / "cases" / f"{asset['id']}_e{epsilon:g}.json"
        if destination.exists():
            row = json.loads(destination.read_text(encoding="utf8"))
            if row.get("fingerprint") != fingerprint:
                raise ValueError("Ara sonuç parmak izi farklı.")
            return row
        if cancel and cancel.is_set():
            raise AnalysisCancelled("Tarama iptal edildi; tamamlanan ölçümler korunuyor.")
        started = time.perf_counter()
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            str(paths[asset["id"]]),
            "--epsilon",
            str(epsilon),
            "--source-root",
            str(source_root),
        ]
        child = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            encoding="utf8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        row = None
        try:
            while True:
                if cancel and cancel.is_set():
                    raise AnalysisCancelled("Tarama iptal edildi; tamamlanan ölçümler korunuyor.")
                try:
                    stdout, stderr = child.communicate(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    if time.perf_counter() - started > timeout:
                        child.kill()
                        child.communicate()
                        row = {"status": "timeout", "error": f"{timeout:g} s süreç sınırı aşıldı."}
                        break
            if child.returncode == 0:
                try:
                    row = json.loads(stdout)
                except json.JSONDecodeError:
                    row = {
                        "status": "error",
                        "error": "Çocuk süreç geçerli JSON üretmedi: " + stdout[-2000:],
                    }
            elif row is None:
                row = {"status": "error", "error": stderr[-6000:] or stdout[-6000:]}
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate()
        row.update(
            id=asset["id"],
            source=asset["source"],
            epsilon=epsilon,
            fingerprint=fingerprint,
            job_wall_seconds=time.perf_counter() - started,
            input_sha256=asset["sha256_png"],
        )
        _atomic_json(destination, row)
        return row

    started = time.perf_counter()
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(execute, a, e) for a, e in tasks]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            if progress:
                progress(
                    f"{len(rows)}/{len(tasks)} · {row['id']} · ε={row['epsilon']:g} · {row['status']} · {row['job_wall_seconds']:.2f} s"
                )
    rows.sort(key=lambda r: (r["id"], r["epsilon"]))
    _atomic_json(
        directory / "results.json",
        {
            "experiment": setup,
            "invocation_wall_seconds": time.perf_counter() - started,
            "completed_count": len(rows),
            "status_counts": dict(Counter(r["status"] for r in rows)),
            "records": rows,
        },
    )
    return directory / "results.json"


def main() -> None:
    """Masaüstüyle ortak taramayı veya yalıtılmış tek analiz çalışanını açar."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path)
    parser.add_argument("directory", nargs="?", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--ids", nargs="+")
    parser.add_argument("--tolerances", type=float, nargs="+", default=[1, 2, 3, 5])
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--epsilon", type=float)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    if args.source_root:
        sys.path.insert(0, str(args.source_root.resolve()))
    if args.worker:
        print(json.dumps(_worker(args.worker, args.epsilon), ensure_ascii=False, allow_nan=False))
    elif args.manifest and args.directory:
        print(
            run_grid(
                args.manifest,
                args.directory,
                workers=args.workers,
                timeout=args.timeout,
                ids=args.ids,
                tolerances=tuple(args.tolerances),
                source_root=args.source_root,
                progress=lambda s: print(s, flush=True),
            )
        )
    else:
        parser.error("Manifest ve sonuç klasörü gereklidir.")


if __name__ == "__main__":
    main()
