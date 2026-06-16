from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from .utils import normalize_text

logger = logging.getLogger(__name__)

DEFAULT_OCR_ZOOM = 2.5
LINE_Y_TOLERANCE = 4.0


class OCRUnavailableError(RuntimeError):
    """Raised when OCR fallback dependencies are not installed."""


@dataclass(frozen=True)
class OCRResult:
    text_pages: list[str]
    word_pages: list[list[dict[str, Any]]]
    line_count: int
    average_score: float | None


def _load_fitz():
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:
        raise OCRUnavailableError(
            "PyMuPDF nao esta instalado. Instale `PyMuPDF` para habilitar OCR."
        ) from exc
    return fitz


def _load_numpy():
    try:
        import numpy as np  # type: ignore[import-not-found]
    except ImportError as exc:
        raise OCRUnavailableError(
            "numpy nao esta instalado. Instale `numpy` para habilitar OCR."
        ) from exc
    return np


@lru_cache(maxsize=1)
def _get_ocr_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]
    except ImportError as exc:
        raise OCRUnavailableError(
            "rapidocr-onnxruntime nao esta instalado. Instale `rapidocr-onnxruntime` para habilitar OCR."
        ) from exc
    return RapidOCR()


def _clean_ocr_text(value: object) -> str:
    text = normalize_text(value)
    text = re.sub(r"^[\s:;,.\-|]+", "", text)
    text = re.sub(r"[\s:;,.\-|]+$", "", text)
    return normalize_text(text)


def _render_page_to_array(page, zoom: float):
    fitz = _load_fitz()
    np = _load_numpy()
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)


def _extract_box(points: object, zoom: float) -> tuple[float, float, float, float] | None:
    try:
        coordinates = [(float(point[0]) / zoom, float(point[1]) / zoom) for point in points]  # type: ignore[index]
    except Exception:
        return None

    if not coordinates:
        return None

    xs = [point[0] for point in coordinates]
    ys = [point[1] for point in coordinates]
    return min(xs), min(ys), max(xs), max(ys)


def _ocr_item_to_word(item: Sequence[object], zoom: float) -> dict[str, Any] | None:
    if len(item) < 2:
        return None

    box = _extract_box(item[0], zoom)
    if box is None:
        return None

    text = _clean_ocr_text(item[1])
    if not text:
        return None

    score = None
    if len(item) >= 3:
        try:
            score = float(item[2])
        except Exception:
            score = None

    x0, top, x1, bottom = box
    return {
        "text": text,
        "x0": x0,
        "x1": x1,
        "top": top,
        "bottom": bottom,
        "source": "ocr",
        "confidence": score,
    }


def _group_words_by_line(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []

    for word in sorted(words, key=lambda item: (float(item.get("top", 0)), float(item.get("x0", 0)))):
        top = float(word.get("top", 0))
        if not rows:
            rows.append([word])
            continue

        current_top = sum(float(item.get("top", 0)) for item in rows[-1]) / len(rows[-1])
        if abs(top - current_top) <= LINE_Y_TOLERANCE:
            rows[-1].append(word)
            continue

        rows.append([word])

    return rows


def _line_text(words: list[dict[str, Any]]) -> str:
    parts = [
        _clean_ocr_text(word.get("text", ""))
        for word in sorted(words, key=lambda item: float(item.get("x0", 0)))
    ]
    return normalize_text(" ".join(part for part in parts if part))


def _extract_page_words(page, ocr, zoom: float) -> list[dict[str, Any]]:
    image = _render_page_to_array(page, zoom)
    result, _ = ocr(image)
    if not result:
        return []

    words: list[dict[str, Any]] = []
    for item in result:
        if not isinstance(item, Sequence):
            continue
        word = _ocr_item_to_word(item, zoom)
        if word is not None:
            words.append(word)
    return words


def transcribe_pdf_images(
    file_bytes: bytes,
    *,
    zoom: float = DEFAULT_OCR_ZOOM,
    max_pages: int | None = None,
) -> OCRResult:
    """Run OCR over PDF pages and return text/word structures compatible with parsers."""
    fitz = _load_fitz()
    ocr = _get_ocr_engine()

    text_pages: list[str] = []
    word_pages: list[list[dict[str, Any]]] = []
    scores: list[float] = []
    line_count = 0

    with fitz.open(stream=file_bytes, filetype="pdf") as document:
        pages_to_process = document.page_count
        if max_pages is not None and max_pages > 0:
            pages_to_process = min(pages_to_process, max_pages)

        for page_index in range(pages_to_process):
            page = document[page_index]
            words = _extract_page_words(page, ocr, zoom)
            lines = [_line_text(row) for row in _group_words_by_line(words)]
            lines = [line for line in lines if line]

            for word in words:
                confidence = word.get("confidence")
                if confidence is not None:
                    scores.append(float(confidence))

            text_pages.append("\n".join(lines))
            word_pages.append(words)
            line_count += len(lines)

    average_score = round(sum(scores) / len(scores), 4) if scores else None
    logger.info(
        "OCR concluido | paginas=%d | linhas=%d | score_medio=%s",
        len(text_pages),
        line_count,
        average_score if average_score is not None else "indefinido",
    )
    return OCRResult(
        text_pages=text_pages,
        word_pages=word_pages,
        line_count=line_count,
        average_score=average_score,
    )
