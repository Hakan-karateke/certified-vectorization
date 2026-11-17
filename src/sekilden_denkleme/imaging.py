"""Görseli sabit boyutlu bir ikili piksel düzlemine dönüştürür."""

from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps

CANVAS_SIZE = 1000


def normalize_image(
    path: str | Path | BinaryIO, threshold: int, padding: int, working_size: int | None = None
) -> tuple[NDArray[np.bool_], dict[str, Any]]:
    """Siyah şekli beyaz kare bir çalışma düzlemine yerleştirir.

    working_size verilmezse (varsayılan) görsel yeniden örneklenmez: düzlemin
    kenarı max(genişlik, yükseklik) + 2·padding pikseldir, ölçek tam 1'dir ve bir
    çalışma birimi bir kaynak pikselidir. working_size verilirse (eski davranış,
    örneğin 1000) şekil en-boy oranı korunarak o kenara ölçeklenir; bu durumda
    garantiler yeniden örneklenmiş ikili görsele aittir.

    Args:
        path: Pillow'un açabildiği bir raster görselin dosya yolu.
        threshold: 0..254 gri eşik; eşit veya düşük değerler şekle dahildir.
        padding: Her kenarda bırakılacak en az piksel boşluğu.

    Returns:
        True değerleri siyah pikseller olan maske ve dönüşüm metaverisi.

    Raises:
        ValueError: Görsel animasyonluysa veya eşikleme sonucunda şekil kalmazsa.
        OSError: Dosya okunamazsa veya desteklenmeyen biçimdeyse.
    """
    with Image.open(path) as source:
        if getattr(source, "n_frames", 1) != 1:
            raise ValueError("Tek kareli bir görsel kullanın; animasyon desteklenmiyor.")
        raw_size = list(source.size)
        exif_orientation = int(source.getexif().get(274, 1))
        oriented = ImageOps.exif_transpose(source).convert("RGBA")
        # Saydam bölgeler siyaha dönüşmesin; önce beyaz zeminle birleştirilir.
        white = Image.new("RGBA", oriented.size, "white")
        gray = Image.alpha_composite(white, oriented).convert("L")
        width, height = gray.size
        binary = Image.fromarray(np.where(np.asarray(gray) <= threshold, 0, 255).astype("uint8"))
        if working_size:
            side = int(working_size)
            scale = (side - 2 * padding) / max(width, height)
            new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
            # Önce ikili sınıflandırma, ardından nearest: yeni gri tonlar üretilmez.
            resized = binary.resize(new_size, Image.Resampling.NEAREST)
        else:
            side = max(width, height) + 2 * padding
            new_size = (width, height)
            resized = binary
        offset = ((side - new_size[0]) // 2, (side - new_size[1]) // 2)
        canvas = Image.new("L", (side, side), 255)
        canvas.paste(resized, offset)
        mask = np.asarray(canvas) == 0
    if not mask.any():
        raise ValueError("Eşikleme ve ölçekleme sonrası siyah piksel bulunamadı.")
    metadata = {
        "raw_source_size": raw_size,
        "exif_orientation": exif_orientation,
        "exif_applied": exif_orientation != 1,
        "source_size": [width, height],
        "canvas_size": [side, side],
        "resized_size": list(new_size),
        "scale_x": new_size[0] / width,
        "scale_y": new_size[1] / height,
        "offset_top_left": list(offset),
        "coordinate_domain": [0, side],
        "coordinate_convention": f"x sağa, y yukarı; piksel (r,c) = [c,c+1] × [{side - 1}-r,{side}-r]",
        "foreground_pixels": int(mask.sum()),
        "resampling": "threshold_then_nearest" if working_size else "none",
        "threshold_method": "global_inclusive",
        "threshold": threshold,
        "pixel_geometry": "unit_square_edges",
        "source_transform_applies_to": "EXIF-oriented continuous pixel edges",
        "source_to_working": [
            [new_size[0] / width, 0, offset[0]],
            [0, -new_size[1] / height, side - offset[1]],
            [0, 0, 1],
        ],
        "working_to_source": [
            [width / new_size[0], 0, -offset[0] * width / new_size[0]],
            [0, -height / new_size[1], (side - offset[1]) * height / new_size[1]],
            [0, 0, 1],
        ],
    }
    return mask, metadata
