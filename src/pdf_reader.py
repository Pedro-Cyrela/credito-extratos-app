from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any

import pdfplumber

logger = logging.getLogger(__name__)


@dataclass
class PDFDocument:
    filename: str
    file_bytes: bytes
    text_pages: list[str]
    tables: list[list[list[str | None]]]
    word_pages: list[list[dict[str, Any]]]
    page_count: int
    selectable_text_chars: int
    selectable_word_count: int
    image_count: int
    ocr_used: bool = False
    ocr_reason: str = ""
    ocr_line_count: int = 0
    ocr_average_score: float | None = None
    ocr_error: str = ""


@dataclass(frozen=True)
class PDFContentStats:
    filename: str
    page_count: int
    selectable_text_chars: int
    selectable_word_count: int
    selectable_table_count: int
    image_count: int

    @property
    def has_selectable_table_text(self) -> bool:
        return self.selectable_table_count > 0

    @property
    def is_ocr_candidate(self) -> bool:
        return self.selectable_table_count == 0 and (
            (self.image_count > 0 and self.selectable_text_chars < IMAGE_OCR_CANDIDATE_TEXT_CHARS)
            or self.selectable_text_chars < MIN_SELECTABLE_TEXT_CHARS
            or self.selectable_word_count == 0
        )


MIN_SELECTABLE_TEXT_CHARS = 80
IMAGE_OCR_CANDIDATE_TEXT_CHARS = 500


def _read_uploaded_bytes(uploaded_file) -> bytes:
    if hasattr(uploaded_file, "getvalue"):
        data = uploaded_file.getvalue()
        if isinstance(data, bytes):
            return data

    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)

    data = uploaded_file.read()
    return data if isinstance(data, bytes) else bytes(data)


def _count_meaningful_chars(text_pages: list[str]) -> int:
    return sum(1 for text in text_pages for char in text if char.isalnum())


def _filename(uploaded_file) -> str:
    return str(getattr(uploaded_file, "name", "<sem nome>"))


def _extract_pdf_document(file_bytes: bytes, filename: str) -> PDFDocument:
    text_pages: list[str] = []
    tables: list[list[list[str | None]]] = []
    word_pages: list[list[dict[str, Any]]] = []
    image_count = 0

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text_pages.append(page.extract_text() or "")
            page_words = page.extract_words(x_tolerance=1, y_tolerance=3) or []
            word_pages.append(page_words)
            image_count += len(page.images or [])
            extracted_tables = page.extract_tables() or []
            for table in extracted_tables:
                if table:
                    tables.append(table)

    selectable_text_chars = _count_meaningful_chars(text_pages)
    selectable_word_count = sum(len(page_words) for page_words in word_pages)

    return PDFDocument(
        filename=filename,
        file_bytes=file_bytes,
        text_pages=text_pages,
        tables=tables,
        word_pages=word_pages,
        page_count=len(text_pages),
        selectable_text_chars=selectable_text_chars,
        selectable_word_count=selectable_word_count,
        image_count=image_count,
    )


def inspect_pdf_content(uploaded_file) -> PDFContentStats:
    file_bytes = _read_uploaded_bytes(uploaded_file)
    return inspect_pdf_bytes(file_bytes, _filename(uploaded_file))


def inspect_pdf_bytes(file_bytes: bytes, filename: str = "<sem nome>") -> PDFContentStats:
    doc = _extract_pdf_document(file_bytes, filename)
    return PDFContentStats(
        filename=doc.filename,
        page_count=doc.page_count,
        selectable_text_chars=doc.selectable_text_chars,
        selectable_word_count=doc.selectable_word_count,
        selectable_table_count=len(doc.tables),
        image_count=doc.image_count,
    )


def read_pdf(uploaded_file) -> PDFDocument:
    file_bytes = _read_uploaded_bytes(uploaded_file)
    pdf_doc = _extract_pdf_document(file_bytes, _filename(uploaded_file))

    logger.info(
        "PDF lido: %s | paginas=%d | tabelas=%d | chars_texto=%d | palavras=%d | imagens=%d",
        pdf_doc.filename,
        pdf_doc.page_count,
        len(pdf_doc.tables),
        pdf_doc.selectable_text_chars,
        pdf_doc.selectable_word_count,
        pdf_doc.image_count,
    )

    return pdf_doc
