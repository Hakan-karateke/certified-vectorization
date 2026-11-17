"""Yayımlanmış vektörleştirme sonuçlarını girdilerine karşı bağımsız ölçer.

Kaynak: PolyFit (Dominici ve ark., SIGGRAPH 2020) proje sayfasındaki
`additional-results.zip` içindeki `additional_results.pdf`. Her satırda bir
piksel sanatı girdisi (gömülü raster) ve dört yöntemin vektör çıktısı vardır:
Kopf–Lischinski 2011, Potrace (Selinger 2003), Hoshyari ve ark. 2018, PolyFit.
Hiçbir yöntem burada çalıştırılmaz; yazarların yayımladığı çıktılar ölçülür.

Ölçüm raster tabanlıdır ve sertifika değildir:
    1. Her çıktı, bir girdi pikseli 16 alt piksele denk gelecek biçimde ve kenar
       yumuşatma kapalı olarak taranır; renkler girdinin paletine eşlenir.
    2. Çıktı ile girdi arasındaki öteleme ve ölçek bilinmediği için, etiket
       uyuşmasını en büyük yapan hizalama aranır. Bu, yöntemin lehinedir.
    3. Hizalanmış görüntüde: farklı etiketli alan oranı; renk sınıflarının
       sınırları arasındaki iki yönlü Hausdorff uzaklığı (girdi pikseli biriminde,
       1/16 piksel çözünürlükle); ve her renk sınıfının 4-bağlantılı bileşen ve
       delik sayılarının girdiyle aynı olup olmadığı.

Kullanım:
    python examples/audit_published_results.py \
        examples/external_results/download/polyfit_additional/additional_results.pdf \
        examples/external_results/polyfit_audit
"""

import argparse
import io
import json
import statistics
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image
from scipy import ndimage

METHODS = ("kopf_lischinski_2011", "potrace", "hoshyari_2018", "polyfit_2020")
SUB = 16
SCALES = tuple(round(0.70 + 0.02 * k, 2) for k in range(26))  # kaba arama; sonra ±0,01
ALIGNED = 0.85  # bundan düşük etiket uyuşması hizalama başarısızlığı sayılır
# Sütun sınırları (PDF noktası); girdi her sayfada x = 31..145 aralığındadır.
CUTS = (246.5, 372.0, 478.5, 612.0)
SPECK = (SUB // 2) ** 2  # çeyrek piksel kareden küçük artıklar tarama çatlağı sayılır
CROSS = ndimage.generate_binary_structure(2, 1)


def _labels(rgb: np.ndarray, palette: np.ndarray) -> np.ndarray:
    distance = ((rgb[:, :, None, :].astype(int) - palette[None, None, :, :].astype(int)) ** 2).sum(
        3
    )
    return distance.argmin(2).astype(np.int16)


def _boundary(labels: np.ndarray) -> np.ndarray:
    edge = np.zeros(labels.shape, dtype=bool)
    edge[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    edge[:, :-1] |= labels[:, 1:] != labels[:, :-1]
    edge[1:, :] |= labels[1:, :] != labels[:-1, :]
    edge[:-1, :] |= labels[1:, :] != labels[:-1, :]
    return edge


def _topology(labels: np.ndarray, classes: int) -> list[tuple[int, int]]:
    result = []
    for k in range(classes):
        mask = labels == k
        _, components = ndimage.label(mask, CROSS)
        outside, count = ndimage.label(~mask, CROSS)
        border = np.unique(np.concatenate([outside[0], outside[-1], outside[:, 0], outside[:, -1]]))
        holes = count - len(border[border > 0])
        result.append((int(components), int(holes)))
    return result


def _clean(labels: np.ndarray, classes: int) -> np.ndarray:
    """SPECK'ten küçük bileşenleri en yakın büyük bölgenin etiketiyle doldurur."""
    small = np.zeros(labels.shape, dtype=bool)
    for k in range(classes):
        parts, count = ndimage.label(labels == k, CROSS)
        if count:
            sizes = np.bincount(parts.ravel())[1:]
            small |= np.isin(parts, np.flatnonzero(sizes < SPECK) + 1)
    if not small.any() or small.all():
        return labels
    index = ndimage.distance_transform_edt(small, return_distances=False, return_indices=True)
    return labels[index[0], index[1]]


def _align(cell: np.ndarray, source: np.ndarray) -> tuple[float, np.ndarray, np.ndarray, float]:
    """En iyi (ölçek, öteleme) hizalamasını bulur; (uyuşma, girdi, çıktı kırpımı, ölçek) döner."""

    def search(scale: float, best: tuple) -> tuple:
        size = (round(source.shape[1] * SUB * scale), round(source.shape[0] * SUB * scale))
        up = np.asarray(Image.fromarray(source).resize(size, Image.Resampling.NEAREST))
        h, w = up.shape
        if h > cell.shape[0] or w > cell.shape[1]:
            return best
        coarse = max(
            (
                (float((cell[y : y + h : 4, x : x + w : 4] == up[::4, ::4]).mean()), y, x)
                for y in range(0, cell.shape[0] - h + 1, 8)
                for x in range(0, cell.shape[1] - w + 1, 8)
            ),
            default=None,
        )
        if coarse is None:
            return best
        _, y0, x0 = coarse
        for y in range(max(0, y0 - 8), min(cell.shape[0] - h, y0 + 8) + 1, 2):
            for x in range(max(0, x0 - 8), min(cell.shape[1] - w, x0 + 8) + 1, 2):
                crop = cell[y : y + h, x : x + w]
                score = float((crop == up).mean())
                if score > best[0]:
                    best = (score, up, crop, scale)
        return best

    best = (-1.0, None, None, 1.0)
    for scale in SCALES:
        best = search(scale, best)
    for scale in (round(best[3] - 0.01, 2), round(best[3] + 0.01, 2)):
        best = search(scale, best)
    return best


def measure(source: np.ndarray, cell: np.ndarray, classes: int) -> dict:
    agreement, reference, model, scale = _align(cell, source)
    if reference is None or agreement < ALIGNED:
        return {"status": "alignment_failed", "agreement": max(agreement, 0.0)}
    unit = SUB * scale
    model = _clean(model, classes)
    edge_reference, edge_model = _boundary(reference), _boundary(model)
    # Kesitin kenarındaki bir piksellik şerit dışarıda bırakılır: çerçeve çizgileri ve
    # komşu hücreler orada sınır gibi görünür.
    margin = int(round(unit))
    for edge in (edge_reference, edge_model):
        edge[:margin] = edge[-margin:] = False
        edge[:, :margin] = edge[:, -margin:] = False
    if edge_model.any() and edge_reference.any():
        to_reference = ndimage.distance_transform_edt(~edge_reference)
        to_model = ndimage.distance_transform_edt(~edge_model)
        hausdorff = max(to_reference[edge_model].max(), to_model[edge_reference].max()) / unit
    else:
        hausdorff = float("inf")
    before, after = _topology(reference, classes), _topology(model, classes)
    return {
        "status": "measured",
        "scale": scale,
        "mismatched_fraction": 1.0 - agreement,
        "boundary_hausdorff_pixels": float(hausdorff),
        "topology_equal": before == after,
        "components_equal": [a[0] for a in before] == [a[0] for a in after],
        "holes_equal": [a[1] for a in before] == [a[1] for a in after],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    options = parser.parse_args()
    pymupdf.TOOLS.set_aa_level(0)
    document = pymupdf.open(options.pdf)
    records = []
    for page in document:
        images = []
        for image in page.get_images(full=True):
            rects = page.get_image_rects(image[0])
            if rects:
                images.append((rects[0], image[0]))
        images.sort(key=lambda pair: pair[0].y0)
        for row, (rect, xref) in enumerate(images):
            pixmap = pymupdf.Pixmap(document, xref)
            if pixmap.alpha or pixmap.colorspace.n != 3:
                pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap, 0) if not pixmap.alpha else pixmap
            picture = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGBA")
            white = Image.new("RGBA", picture.size, "white")
            rgb = np.asarray(Image.alpha_composite(white, picture).convert("RGB"))
            palette = np.unique(np.vstack([rgb.reshape(-1, 3), [[255, 255, 255]]]), axis=0)
            source = _labels(rgb, palette)
            point = rect.width / rgb.shape[1]
            top, bottom = rect.y0 - 2.5 * point, rect.y1 + 2.5 * point
            record = {
                "index": len(records),
                "page": page.number,
                "row": row,
                "size": list(rgb.shape[:2]),
                "colours": len(palette),
            }
            zoom = SUB / point
            left = rect.x1 + 0.5 * point
            for method, right in zip(METHODS, CUTS, strict=True):
                clip = pymupdf.Rect(left, top, right, bottom)
                shot = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
                cell = np.frombuffer(shot.samples, dtype=np.uint8).reshape(shot.h, shot.w, 3)
                record[method] = measure(source, _labels(cell, palette), len(palette))
                left = right
            records.append(record)
            print(json.dumps(record), flush=True)
    options.output.mkdir(parents=True, exist_ok=True)
    (options.output / "results.json").write_text(json.dumps(records, indent=1), encoding="utf-8")
    summary = {"inputs": len(records), "source": options.pdf.name, "subpixels": SUB}
    for method in METHODS:
        rows = [r[method] for r in records if r.get(method, {}).get("status") == "measured"]
        distances = sorted(r["boundary_hausdorff_pixels"] for r in rows)
        summary[method] = {
            "measured": len(rows),
            "alignment_failed": sum(
                r.get(method, {}).get("status") == "alignment_failed" for r in records
            ),
            "median_mismatched_fraction": statistics.median(r["mismatched_fraction"] for r in rows),
            "median_boundary_hausdorff_pixels": statistics.median(distances),
            "p90_boundary_hausdorff_pixels": distances[int(0.9 * (len(distances) - 1))],
            "max_boundary_hausdorff_pixels": distances[-1],
            "within_half_pixel": sum(d <= 0.5 for d in distances),
            "within_one_pixel": sum(d <= 1.0 for d in distances),
            "topology_equal": sum(r["topology_equal"] for r in rows),
            "components_equal": sum(r["components_equal"] for r in rows),
            "holes_equal": sum(r["holes_equal"] for r in rows),
        }
    (options.output / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
