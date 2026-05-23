from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

import pdfplumber


@dataclass
class PDFDocument:
    filename: str
    text_pages: list[str]
    tables: list[list[list[str | None]]]
    word_pages: list[list[dict[str, Any]]]


def _read_uploaded_bytes(uploaded_file) -> bytes:
    if hasattr(uploaded_file, "getvalue"):
        data = uploaded_file.getvalue()
        if isinstance(data, bytes):
            return data

    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)

    data = uploaded_file.read()
    return data if isinstance(data, bytes) else bytes(data)


def read_pdf(uploaded_file) -> PDFDocument:
    file_bytes = _read_uploaded_bytes(uploaded_file)
    text_pages: list[str] = []
    tables: list[list[list[str | None]]] = []
    word_pages: list[list[dict[str, Any]]] = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text_pages.append(page.extract_text() or "")
            word_pages.append(page.extract_words(x_tolerance=1, y_tolerance=3) or [])
            extracted_tables = page.extract_tables() or []
            for table in extracted_tables:
                if table:
                    tables.append(table)

    return PDFDocument(
        filename=uploaded_file.name,
        text_pages=text_pages,
        tables=tables,
        word_pages=word_pages,
    )
