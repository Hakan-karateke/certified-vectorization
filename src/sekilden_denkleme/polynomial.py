"""Sınır örneklerine SVD ile sıfır olmayan örtük polinom uydurur."""

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import svd

from .models import PolynomialFit


def fit_polynomial(
    points: NDArray[np.float64], degree: int, plane: float = 1000.0
) -> PolynomialFit:
    """F(u,v)=sum(c_ij u^i v^j)=0 polinomunun katsayılarını hesaplar.

    Args:
        points: (N, 2) koordinat dizisi; x ve y 0..plane düzlemindedir.
        degree: Toplam derece üst sınırı; 2..12.
        plane: Çalışma düzleminin kenarı; normalizasyon yarısına göre yapılır.

    Returns:
        ||c||₂=1 koşuluyla ||A c||₂'yi en aza indiren katsayılar ve tanı ölçümleri.
        u=(x-h)/h ve v=(y-h)/h, h=plane/2 kullanılır. Küçük artık, doğru sıfır
        kümesini garanti etmez; fazladan dallar ve tekillikler oluşabilir.

    Raises:
        ValueError: Noktalar sonlu değilse, biçim yanlışsa veya örnek sayısı yetersizse.
    """
    points = np.asarray(points, dtype=float)
    if not isinstance(degree, int) or not 2 <= degree <= 12:
        raise ValueError("Polinom derecesi 2..12 arasında olmalıdır.")
    powers = [(i, total - i) for total in range(degree + 1) for i in range(total + 1)]
    if (
        points.ndim != 2
        or points.shape[1] != 2
        or len(points) < len(powers)
        or not np.isfinite(points).all()
    ):
        raise ValueError("Polinom için yeterli sayıda sonlu (x,y) örneği gereklidir.")
    half = plane / 2
    u, v = ((points - half) / half).T
    matrix = np.column_stack([u**i * v**j for i, j in powers])
    _, singular_values, vh = svd(matrix, full_matrices=False, lapack_driver="gesvd")
    coefficients = vh[-1]
    # SVD'nin işaret belirsizliği, en büyük katsayı pozitif yapılarak giderilir.
    coefficients *= 1 if coefficients[np.argmax(np.abs(coefficients))] >= 0 else -1
    residual = matrix @ coefficients
    du = np.zeros_like(u)
    dv = np.zeros_like(v)
    for coefficient, (i, j) in zip(coefficients, powers, strict=True):
        if i:
            du += coefficient * i * u ** (i - 1) * v**j
        if j:
            dv += coefficient * j * u**i * v ** (j - 1)
    gradient = np.hypot(du, dv) / half
    # Tekil gradyanlarda mesafe yaklaşımı tanımsızdır; küçük bir sayıya bölünmez.
    valid = gradient > 1e-12
    distance = float(np.sqrt(np.mean((residual / gradient) ** 2))) if valid.all() else None
    smallest = singular_values[-1]
    condition = (
        float(singular_values[0] / smallest)
        if smallest > np.finfo(float).eps * singular_values[0]
        else None
    )
    return PolynomialFit(
        degree,
        [(i, j, float(c)) for (i, j), c in zip(powers, coefficients, strict=True)],
        float(np.sqrt(np.mean(residual**2))),
        distance,
        len(points),
        condition,
        {"plane": float(plane)},
    )


def evaluate_polynomial(
    fit: PolynomialFit, x: NDArray[np.float64], y: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Verilen x/y dizilerinde F değerlerini, yayınlama kurallarıyla aynı biçimde döndürür.

    Args:
        fit: Normalize koordinatlardaki polinom katsayıları.
        x: Kartezyen x koordinatları; NumPy broadcasting desteklenir.
        y: Kartezyen y koordinatları.

    Returns:
        x ve y'nin ortak yayınlama biçiminde F(x,y) değerleri.
    """
    half = float(fit.diagnostics.get("plane", 1000.0)) / 2
    u, v = (np.asarray(x) - half) / half, (np.asarray(y) - half) / half
    result = np.zeros(np.broadcast_shapes(u.shape, v.shape))
    for i, j, coefficient in fit.terms:
        result += coefficient * u**i * v**j
    return result


def polynomial_diagnostics(fit: PolynomialFit, boundaries: list) -> dict:
    """501x501 ızgarada sıfır dallarını araştırır; tamlık garantisi üretmez.

    Marching-squares alt piksel dalları kaçırabilir. Bu nedenle polinom otomatik
    kabul edilen sınır modeli değildir; görüntülenen dallar projede saklanır.
    """
    from matplotlib.figure import Figure
    from scipy.spatial import cKDTree

    from .geometry import sample_boundaries

    axis = np.linspace(0, float(fit.diagnostics.get("plane", 1000.0)), 501)
    x, y = np.meshgrid(axis, axis)
    values = evaluate_polynomial(fit, x, y)
    figure = Figure()
    axes = figure.add_subplot()
    contour = axes.contour(x, y, values, levels=[0])
    paths = [p for p in contour.allsegs[0] if len(p) > 1]
    points = np.vstack(paths) if paths else np.empty((0, 2))
    reference = sample_boundaries(boundaries, 8000)
    maximum = None
    rms = None
    if len(points):
        forward = cKDTree(points).query(reference)[0]
        backward = cKDTree(reference).query(points)[0]
        maximum = float(max(forward.max(), backward.max()))
        rms = float(np.sqrt(np.mean(np.r_[forward, backward] ** 2)))
    closed = sum(np.linalg.norm(p[0] - p[-1]) < 1e-6 for p in paths)
    figure.clear()
    return {
        "status": "exploratory_not_admissible",
        "grid_size": [501, 501],
        "grid_spacing": 2.0,
        "zero_paths": [p.tolist() for p in paths],
        "closed_paths_detected": int(closed),
        "open_paths_detected": len(paths) - int(closed),
        "reference_boundary_count": len(boundaries),
        "branch_count_matches_at_grid_resolution": len(paths) == len(boundaries),
        "sampled_point_cloud_distance": maximum,
        "sampled_point_cloud_rms": rms,
        "geometric_error_upper_bound": None,
        "warning": "Izgara ek dalları/kayıp bileşenleri kesin dışlamaz. Cebirsel artık geometrik hata değildir.",
    }
