from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

ASSETS = Path(__file__).parent / "assets"

SCALE_MIN = 0.6
SCALE_MAX = 1.6
SCALE_STEP = 1.03
HINT_SPAN = 3
MAX_PEAKS_PER_SCALE = 40


class TemplateError(ValueError):
    pass


@dataclass(frozen=True)
class Match:
    x: int
    y: int
    w: int
    h: int
    score: float

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2


def _all_scales() -> list[float]:
    scales = []
    s = SCALE_MIN
    while s <= SCALE_MAX:
        scales.append(round(s, 4))
        s *= SCALE_STEP
    return scales


SCALES = _all_scales()


def _background(gray: np.ndarray) -> int:
    return int(np.bincount(gray.ravel(), minlength=256).argmax())


def _ink_box(gray: np.ndarray, tol: int = 25) -> tuple[int, int, int, int]:
    """Bounding box (x, y, w, h) of the largest run of ink on a flat background."""
    bg = _background(gray)
    ink = (np.abs(gray.astype(np.int16) - bg) > tol).astype(np.uint8)
    if not ink.any():
        raise TemplateError("image has no visible content")
    height = gray.shape[0]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(5, height // 2), 1))
    merged = cv2.dilate(ink, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(merged)
    best = max(range(1, count), key=lambda i: stats[i, cv2.CC_STAT_AREA])
    ys, xs = np.where((labels == best) & (ink > 0))
    return int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)


def _signature(bgr: np.ndarray) -> float:
    """Blue minus red, averaged over the patch. Separates blue labels from grey ones."""
    return float(bgr[:, :, 0].mean()) - float(bgr[:, :, 2].mean())


class Template:
    """The text label of a button, cut out of a screenshot of the whole button.

    Matching only the label keeps it working when the button is wider or
    narrower than the one in the screenshot, which happens with card layout.
    """

    def __init__(self, gray: np.ndarray, signature: float, name: str = "template"):
        self.gray = gray
        self.signature = signature
        self.name = name

    @classmethod
    def from_button_image(cls, bgr: np.ndarray, name: str = "template") -> "Template":
        if bgr is None or bgr.ndim != 3 or min(bgr.shape[:2]) < 16:
            raise TemplateError("image is too small to be a button screenshot")
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        x, y, w, h = _ink_box(gray)
        pill = bgr[y : y + h, x : x + w]
        inset_y = max(3, round(0.18 * h))
        inset_x = max(3, round(0.05 * w))
        inner = pill[inset_y : h - inset_y, inset_x : w - inset_x]
        if inner.size == 0:
            raise TemplateError("button screenshot is too small")
        inner_gray = cv2.cvtColor(inner, cv2.COLOR_BGR2GRAY)
        tx, ty, tw, th = _ink_box(inner_gray)
        pad = 2
        y0, y1 = max(0, ty - pad), min(inner.shape[0], ty + th + pad)
        x0, x1 = max(0, tx - pad), min(inner.shape[1], tx + tw + pad)
        core = inner[y0:y1, x0:x1]
        return cls(cv2.cvtColor(core, cv2.COLOR_BGR2GRAY), _signature(core), name)

    @classmethod
    def from_file(cls, path: str | Path) -> "Template":
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise TemplateError(f"cannot read image: {path}")
        return cls.from_button_image(image, Path(path).name)


def default_templates() -> tuple[Template, Template]:
    return (
        Template.from_file(ASSETS / "connect_button.png"),
        Template.from_file(ASSETS / "send_button.png"),
    )


def _resize(gray: np.ndarray, scale: float) -> np.ndarray:
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    return cv2.resize(gray, None, fx=scale, fy=scale, interpolation=interpolation)


def _overlap(a: Match, b: Match) -> float:
    ix = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    iy = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    if ix <= 0 or iy <= 0:
        return 0.0
    return ix * iy / min(a.w * a.h, b.w * b.h)


def order_top_to_bottom(matches: list[Match]) -> list[Match]:
    """Rows from the top, left to right inside a row."""
    ordered: list[Match] = []
    pending = sorted(matches, key=lambda m: (m.y, m.x))
    while pending:
        first = pending[0]
        row = [m for m in pending if m.y - first.y <= max(4, first.h // 2)]
        ordered.extend(sorted(row, key=lambda m: m.x))
        pending = [m for m in pending if m not in row]
    return ordered


class Finder:
    """Multi-scale template search. Remembers the zoom that last worked."""

    def __init__(self) -> None:
        self._hint: dict[int, float] = {}

    def _scales_for(self, template: Template) -> list[float]:
        hint = self._hint.get(id(template))
        if hint is None:
            return SCALES
        index = min(range(len(SCALES)), key=lambda i: abs(SCALES[i] - hint))
        return SCALES[max(0, index - HINT_SPAN) : index + HINT_SPAN + 1]

    def _search(self, gray, bgr, template, threshold, scales) -> list[Match]:
        found: list[Match] = []
        frame_h, frame_w = gray.shape
        for scale in scales:
            tpl = _resize(template.gray, scale)
            th, tw = tpl.shape
            if th < 6 or tw < 6 or th >= frame_h or tw >= frame_w:
                continue
            result = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
            result[~np.isfinite(result)] = 0
            for _ in range(MAX_PEAKS_PER_SCALE):
                _, peak, _, (px, py) = cv2.minMaxLoc(result)
                if peak < threshold:
                    break
                found.append(Match(px, py, tw, th, float(peak)))
                result[max(0, py - th // 2) : py + th // 2 + 1, max(0, px - tw // 2) : px + tw // 2 + 1] = -1
        found.sort(key=lambda m: -m.score)
        kept: list[Match] = []
        for candidate in found:
            if any(_overlap(candidate, k) > 0.4 for k in kept):
                continue
            if not self._color_ok(bgr, candidate, template):
                continue
            kept.append(candidate)
        return kept

    @staticmethod
    def _color_ok(bgr: np.ndarray, m: Match, template: Template) -> bool:
        patch = bgr[m.y : m.y + m.h, m.x : m.x + m.w]
        if patch.size == 0:
            return False
        return abs(_signature(patch) - template.signature) <= max(25.0, 0.5 * abs(template.signature))

    def find(self, image: np.ndarray, template: Template, threshold: float) -> list[Match]:
        """All matches, ordered from the top of the image down."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        matches = self._search(gray, image, template, threshold, self._scales_for(template))
        if not matches and id(template) in self._hint:
            matches = self._search(gray, image, template, threshold, SCALES)
        if matches:
            best = max(matches, key=lambda m: m.score)
            self._hint[id(template)] = best.h / template.gray.shape[0]
        return order_top_to_bottom(matches)
