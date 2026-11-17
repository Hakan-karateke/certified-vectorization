"""Komut satırından görsel analizi ve çıktı üretimi."""

import argparse
import sys
from pathlib import Path

from .cad_geometry import CadOptions
from .export import ExportOptions, export_result
from .models import AnalysisConfig
from .pipeline import analyze


def main(argv: list[str] | None = None) -> int:
    """Argümanları işler, analizi çalıştırır; başarıda 0, hatada 2 döndürür.

    Args:
        argv: Program adı hariç argümanlar; None ise sys.argv kullanılır.

    Returns:
        İşletim sistemi çıkış kodu. --help argparse tarafından yönetilir.
    """
    parser = argparse.ArgumentParser(description="Siyah-beyaz şekilden sınır denklemleri üretir.")
    parser.add_argument("image", type=Path, help="Girdi görseli (PNG, JPEG, BMP, TIFF vb.)")
    parser.add_argument("--output", type=Path, default=Path("output"), help="Çıktı klasörü")
    parser.add_argument("--threshold", type=int, default=127, help="Siyah eşiği: 0..254")
    parser.add_argument("--padding", type=int, default=20, help="Tuval kenar boşluğu: 0..499")
    parser.add_argument(
        "--working-size",
        type=int,
        default=0,
        help="0: yerel çözünürlük (1 birim = 1 kaynak pikseli); N: görseli N birimlik düzleme ölçekle",
    )
    parser.add_argument(
        "--tolerance", type=float, default=0, help="Sadeleştirme: 0 kesin; en çok 50"
    )
    parser.add_argument("--degree", type=int, help="İsteğe bağlı yaklaşık polinom derecesi: 2..12")
    parser.add_argument(
        "--family",
        choices=[
            "exact",
            "polygon",
            "auto",
            "mixed",
            "circle",
            "ellipse",
            "bezier",
            "bspline",
            "adaptive",
            "fourier",
            "topology",
            "minlink",
            "linearc",
        ],
        default="polygon",
    )
    parser.add_argument(
        "--preference", choices=["simple", "balanced", "accurate"], default="balanced"
    )
    parser.add_argument("--embed-input", action="store_true")
    parser.add_argument("--search", choices=["deterministic", "annealing"], default="deterministic")
    parser.add_argument("--search-budget", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20261015)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--certificate", choices=["off", "selected", "strict"], default="selected")
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=["json", "txt", "png", "jpeg", "svg", "pdf", "dxf", "step", "iges"],
    )
    parser.add_argument("--cad-unit", choices=["mm", "cm", "m", "in"], default="mm")
    parser.add_argument(
        "--cad-scale",
        type=float,
        default=1.0,
        help="Bir çalışma koordinatının CAD birimindeki uzunluğu",
    )
    parser.add_argument(
        "--cad-tolerance",
        type=float,
        default=0.01,
        help="CAD aktarım toleransı, seçilmiş CAD biriminde",
    )
    parser.add_argument(
        "--cad-approximate",
        action="store_true",
        help="Fourier gibi eğrilerde kontrollü yaklaşımı kabul et",
    )
    args = parser.parse_args(argv)
    try:
        config = AnalysisConfig(
            args.threshold,
            args.padding,
            args.tolerance,
            args.degree,
            family=args.family,
            preference=args.preference,
            embed_input=args.embed_input,
            search_strategy=args.search,
            search_budget=args.search_budget,
            random_seed=args.seed,
            evaluation_workers=args.workers,
            certificate_mode=args.certificate,
            working_size=args.working_size,
        )
        result = analyze(args.image, config)
        options = ExportOptions(
            cad=CadOptions(
                unit=args.cad_unit,
                scale=args.cad_scale,
                tolerance=args.cad_tolerance,
                allow_approximation=args.cad_approximate,
            )
        )
        paths = export_result(result, args.output, formats=args.formats, options=options)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Hata: {error}", file=sys.stderr)
        return 2
    print(f"{result.metrics['boundary_count']} sınır, {result.metrics['exported_segments']} parça.")
    for path in paths:
        print(path.resolve())
    return 0
