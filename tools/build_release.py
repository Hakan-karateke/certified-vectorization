"""Yayına hazır, gereksiz dosyalardan arındırılmış depo klasörünü oluşturur.

Çalışma deposuna dokunmaz; yalnızca seçilen dosyaları hedef klasöre kopyalar ve
lisans, atıf ve Zenodo üst verisi dosyalarını yazar. Hedef klasör varsa önce
silinir (yalnızca bu betiğin daha önce oluşturduğu klasör kabul edilir).

Kullanım (depo kökünden):
    python tools/build_release.py D:/Dev/Personal/certified-vectorization
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = "3.0.0"
AUTHOR = "Hakan KARATEKE"
YEAR = "2026"
MARKER = ".release-built-by-tools-build_release"

# Kopyalanacak üst düzey dosya ve klasörler (depo köküne göre).
TOP = [
    "pyproject.toml",
    "requirements-cad-tested.txt",
    "baslat_windows.cmd",
    "kur_windows.cmd",
    "kur_cad_windows.cmd",
    "src",
    "tests",
    "docs",
    "tools",
]
EXAMPLE_SCRIPTS = [
    "optimality_gap.py",
    "line_arc_optimum.py",
    "line_arc_sensitivity.py",
    "summarize_sweep.py",
    "compare_potrace.py",
    "certify_potrace.py",
    "certify_svg.py",
    "audit_published_results.py",
    "native_inputs.py",
    "scan_degradation.py",
    "real_scans.py",
    "prepare_icon_dataset.cjs",
    "run_all_experiments.sh",
    "compiled_kernel/ArcKernel.cs",
    "compiled_kernel/run.ps1",
    "compiled_kernel/compare.py",
]
# Sonuç klasörleri: (kaynak, hedef). Yalnızca 3.0 koşuları ve çözünürlükten bağımsız deneyler.
RESULTS = [
    ("examples/icon_dataset/manifest.json", "examples/icon_dataset/manifest.json"),
    ("examples/icon_dataset/sample200.json", "examples/icon_dataset/sample200.json"),
    ("examples/icon_dataset/contact_icons_3.0.json", "examples/icon_dataset/contact_icons.json"),
    ("examples/icon_dataset/png", "examples/icon_dataset/png"),
    ("examples/icon_dataset/optimality_gap_3.0", "examples/icon_dataset/optimality_gap"),
    ("examples/icon_dataset/pipeline_sweep_3.0", "examples/icon_dataset/pipeline_sweep"),
    ("examples/icon_dataset/line_arc_optimum_3.0", "examples/icon_dataset/line_arc_optimum"),
    (
        "examples/icon_dataset/line_arc_sensitivity_3.0",
        "examples/icon_dataset/line_arc_sensitivity",
    ),
    ("examples/icon_dataset/clearance_contacts_3.0", "examples/icon_dataset/clearance_contacts"),
    ("examples/icon_dataset/clearance_sample_3.0", "examples/icon_dataset/clearance_sample"),
    # Yeniden örnekleme sayımı yerel maske ile eski 1000 birimlik düzlemi karşılaştırır.
    ("examples/icon_dataset/resampling_topology", "examples/icon_dataset/resampling_topology"),
    ("examples/icon_dataset/potrace_comparison_3.0", "examples/icon_dataset/potrace_comparison"),
    ("examples/icon_dataset/potrace_certified_3.0", "examples/icon_dataset/potrace_certified"),
    ("examples/compiled_kernel/results", "examples/compiled_kernel/results"),
    ("examples/native_inputs", "examples/native_inputs"),
    ("examples/real_scans/results", "examples/real_scans/results"),
]
# Testlerin okuduğu örnek dosyalar (yalnızca gerekli olanlar).
FIXTURES = [
    "examples/square.png",
    "examples/validation/dataset",
    "examples/complex_inputs/png/fa_snowflake.png",
    "examples/certified_extensions/circle/model.json",
    "examples/certified_extensions/ellipse/model.json",
    "examples/certified_extensions/ring/model.json",
    "examples/certified_extensions/spline/model.json",
    "examples/arc_stress/illustrations/corner_curve/model.json",
    "examples/arc_stress/illustrations/rounded_rectangle/model.json",
    "examples/cad_validation/circle",
    "examples/cad_validation/ring",
    "examples/cad_validation/components",
    "examples/cad_validation/spline",
    "examples/cad_product_validation",
]
PAPER = ["main.tex", "main.pdf", "references.bib", "make_figures.py", "figures"]
SKIP_NAMES = {"__pycache__", ".pytest_cache", ".ruff_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".aux", ".log", ".out", ".bbl", ".blg", ".toc", ".synctex.gz"}

MIT = f"""MIT License

Copyright (c) {YEAR} {AUTHOR}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

THIRD_PARTY = """# Third-party material

## Bootstrap Icons 1.11.3 (examples/icon_dataset/png)

The 2050 bitmaps in `examples/icon_dataset/png` are renderings of the SVG
glyphs of Bootstrap Icons 1.11.3 (https://github.com/twbs/icons), produced by
`examples/prepare_icon_dataset.cjs`. `examples/icon_dataset/manifest.json`
records the archive hash and a SHA-256 digest of every bitmap. Bootstrap Icons
is distributed under the MIT License:

    The MIT License (MIT)

    Copyright (c) 2019-2024 The Bootstrap Authors

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in
    all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
    THE SOFTWARE.

## Font Awesome Free 6.7.2 (examples/complex_inputs/png/fa_snowflake.png)

One test fixture is a rendering of the "snowflake" icon of Font Awesome Free
6.7.2 by Fonticons, Inc. (https://fontawesome.com), whose icons are licensed
under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).

## Material that is referenced but not redistributed

* **MPEG-7 CE-Shape-1 silhouettes** used during development. One test reads
  `examples/complex_inputs/png/mpeg7_deer.png` and is skipped when the file is
  absent; the redistribution terms of that dataset are not stated, so it is
  not included.

* **Scanned documents** used by `examples/real_scans.py` (a 1902 USGS
  topographic sheet, the drawing of U.S. patent 223,898 held by the U.S.
  National Archives, and a Historic American Engineering Record floor plan).
  They are works of U.S. federal agencies. Their URLs on Wikimedia Commons and
  their SHA-256 digests are in `examples/real_scans/results/sources.json`;
  download them into `examples/real_scans/download/` to rerun the experiment.
  The small crops written next to the results are excerpts of these scans.
* **Published results of other methods** audited by
  `examples/audit_published_results.py`: `additional_results.pdf` from the
  PolyFit project page (Dominici et al., SIGGRAPH 2020),
  https://www.cs.ubc.ca/labs/imager/tr/2020/ClipArtVectorization/. Only our
  measurements are included here.
* **Potrace 1.16** (GPL), used unmodified as an external program by
  `examples/compare_potrace.py` and `examples/certify_potrace.py`; obtain it
  from https://potrace.sourceforge.net/.
"""

GITIGNORE = """__pycache__/
*.py[cod]
*.egg-info/
.venv/
.pytest_cache/
.ruff_cache/
build/
dist/
output/
.tmp/
.DS_Store
.release-built-by-tools-build_release
paper/*.aux
paper/*.log
paper/*.out
paper/*.bbl
paper/*.blg
examples/real_scans/download/
examples/external_results/download/
examples/icon_dataset/download/
"""


def _ignore(directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in SKIP_NAMES or any(name.endswith(suffix) for suffix in SKIP_SUFFIXES)
    }


def _copy(source: Path, target: Path, missing: list[str]) -> None:
    if not source.exists():
        missing.append(str(source.relative_to(ROOT)))
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, ignore=_ignore, dirs_exist_ok=True)
    else:
        shutil.copy2(source, target)


def main() -> None:
    target = Path(sys.argv[1]).resolve()
    if target == ROOT or ROOT in target.parents:
        raise SystemExit("Hedef klasör çalışma deposunun içinde olamaz.")
    if target.exists():
        if not (target / MARKER).exists():
            raise SystemExit(f"{target} bu betiğin oluşturduğu bir klasör değil; silinmedi.")
        shutil.rmtree(target)
    target.mkdir(parents=True)
    (target / MARKER).write_text("generated; safe to delete and rebuild\n", encoding="utf-8")
    missing: list[str] = []
    for name in TOP:
        _copy(ROOT / name, target / name, missing)
    for name in EXAMPLE_SCRIPTS:
        _copy(ROOT / "examples" / name, target / "examples" / name, missing)
    for source, destination in RESULTS:
        _copy(ROOT / source, target / destination, missing)
    for name in FIXTURES:
        _copy(ROOT / name, target / name, missing)
    for name in PAPER:
        _copy(ROOT / "paper" / name, target / "paper" / name, missing)
    # Türkçe uygulama kılavuzu korunur; kök README yayın için İngilizce yazılır.
    guide = (ROOT / "README.md").read_text(encoding="utf-8")
    note = """> **Not (3.0):** Bu belge 2.6 sürümünün Türkçe kullanım kılavuzudur ve geliştirme
> deposundaki örnek klasörlerine bağlantılar içerir; o klasörler bu yayında yoktur.
> Güncel değişiklikler için [release-3.0.md](release-3.0.md) dosyasına bakın. 3.0'dan
> itibaren görsel varsayılan olarak yeniden örneklenmez.

"""
    (target / "docs").mkdir(parents=True, exist_ok=True)
    (target / "docs" / "README.tr.md").write_text(note + guide, encoding="utf-8")
    _copy(ROOT / "tools" / "release" / "README.md", target / "README.md", missing)
    (target / "LICENSE").write_text(MIT, encoding="utf-8")
    (target / "THIRD_PARTY.md").write_text(THIRD_PARTY, encoding="utf-8")
    (target / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    title = (
        "Certified raster-to-vector conversion with provably minimal polygons and line-arc rings"
    )
    (target / "CITATION.cff").write_text(
        "cff-version: 1.2.0\n"
        'message: "If you use this software, please cite it as below."\n'
        f'title: "{title}"\n'
        "type: software\n"
        "authors:\n"
        '  - family-names: "Karateke"\n'
        '    given-names: "Hakan"\n'
        f'version: "{VERSION}"\n'
        'doi: "10.5281/zenodo.24299983"\n'
        'repository-code: "https://github.com/Hakan-karateke/certified-vectorization"\n'
        'license: "MIT"\n'
        "keywords:\n"
        "  - vectorization\n"
        "  - certified computation\n"
        "  - Hausdorff distance\n"
        "  - minimum-link polygon\n"
        "  - circular arcs\n",
        encoding="utf-8",
    )
    zenodo = {
        "title": title,
        "upload_type": "software",
        "version": VERSION,
        "creators": [{"name": "Karateke, Hakan"}],
        "license": "MIT",
        "description": (
            "Implementation, experiment scripts, recorded results and manuscript for certified "
            "raster-to-vector conversion: an independent checker for the Hausdorff error and the "
            "planar topology of a vector model, provably minimal node-restricted polygons and "
            "line-arc rings, and audits of third-party tracers."
        ),
        "keywords": ["vectorization", "certified computation", "Hausdorff distance", "CAD"],
    }
    (target / ".zenodo.json").write_text(json.dumps(zenodo, indent=2), encoding="utf-8")
    files = [p for p in target.rglob("*") if p.is_file()]
    size = sum(p.stat().st_size for p in files)
    print(f"{target}: {len(files)} files, {size / 1e6:.1f} MB")
    largest = sorted(files, key=lambda p: p.stat().st_size, reverse=True)[:8]
    for path in largest:
        print(f"  {path.stat().st_size / 1e6:7.1f} MB  {path.relative_to(target)}")
    if missing:
        print("MISSING (not copied):")
        for name in missing:
            print("  ", name)


if __name__ == "__main__":
    main()
