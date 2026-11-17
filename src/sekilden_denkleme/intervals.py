"""IEEE-754 dışa yuvarlama ve tam rasyonel dönüşüm için ortak aralık çekirdeği."""

from dataclasses import dataclass
from fractions import Fraction as Q
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Interval:
    """IEEE-754 temel işlemlerini nextafter ile dışa yuvarlayan kapalı aralık."""

    lo: np.ndarray
    hi: np.ndarray

    @classmethod
    def point(cls, value: Any) -> "Interval":
        """Verilen kayıtlı binary64 değerini tam tek nokta aralığı kabul eder."""
        a = np.asarray(value, dtype=float)
        return cls(a, a)

    def __add__(self, other: "Interval") -> "Interval":
        return Interval(
            np.nextafter(self.lo + other.lo, -np.inf), np.nextafter(self.hi + other.hi, np.inf)
        )

    def __neg__(self) -> "Interval":
        return Interval(-self.hi, -self.lo)

    def __sub__(self, other: "Interval") -> "Interval":
        return self + -other

    def __mul__(self, other: "Interval") -> "Interval":
        products = np.stack(
            np.broadcast_arrays(
                self.lo * other.lo, self.lo * other.hi, self.hi * other.lo, self.hi * other.hi
            )
        )
        return Interval(
            np.nextafter(np.min(products, axis=0), -np.inf),
            np.nextafter(np.max(products, axis=0), np.inf),
        )

    def __truediv__(self, other: "Interval") -> "Interval":
        if np.any((other.lo <= 0) & (other.hi >= 0)):
            raise ValueError("Sertifika aralığında sıfıra bölme belirsizliği.")
        reciprocal = Interval(
            np.nextafter(1 / other.hi, -np.inf), np.nextafter(1 / other.lo, np.inf)
        )
        return self * reciprocal

    def clip01(self) -> "Interval":
        """Monoton clip fonksiyonunun aralık uzantısıdır."""
        return Interval(np.clip(self.lo, 0, 1), np.clip(self.hi, 0, 1))


def _coordinate(a: Interval, index: int) -> Interval:
    """Vektör aralığından bir koordinatın kapsamasını çıkarır."""
    return Interval(a.lo[..., index], a.hi[..., index])


def _norm_upper(a: Interval) -> np.ndarray:
    """İki koordinatlı aralık vektörünün Öklid normuna dış üst sınır verir."""
    maximum = np.maximum(np.abs(a.lo), np.abs(a.hi))
    square = Interval.point(maximum) * Interval.point(maximum)
    total = _coordinate(square, 0) + _coordinate(square, 1)
    return np.nextafter(np.sqrt(np.maximum(total.hi, 0)), np.inf)


def _segment_upper(p: Interval, a: Interval, b: Interval) -> np.ndarray:
    """Gerçek p noktasından bir tanık sonlu parçaya uzaklığın aralık üst sınırı."""
    d = b - a
    q = p - a
    squared = _coordinate(d, 0) * _coordinate(d, 0) + _coordinate(d, 1) * _coordinate(d, 1)
    dot = _coordinate(q, 0) * _coordinate(d, 0) + _coordinate(q, 1) * _coordinate(d, 1)
    u = (dot / squared).clip01()
    parameter = Interval(u.lo[..., None], u.hi[..., None])
    return _norm_upper(q - parameter * d)


def _rational_interval(values: list) -> Interval:
    """Rasyonelleri karşılaştırmalı dönüşümle gerçekten kapsayan binary64 aralıklar."""
    exact = np.asarray(values, dtype=object)
    approx = exact.astype(float)
    lo, hi = approx.copy(), approx.copy()
    for index in np.ndindex(exact.shape):
        value = Q(float(approx[index]))
        if value > exact[index]:
            lo[index] = np.nextafter(approx[index], -np.inf)
        if value < exact[index]:
            hi[index] = np.nextafter(approx[index], np.inf)
    return Interval(lo, hi)
