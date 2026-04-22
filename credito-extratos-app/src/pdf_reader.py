from __future__ import annotations

import io
from dataclasses import dataclass

import pdfplumber


@dataclass
class PDFDocument:
    filename: str
    text_pages: list[str]
    tables: list[list[list[str | None]]]


def read_pdf(uploaded_file) -> PDFDocument:
    file_bytes = uploaded_file.read()
    text_pages: list[str] = []
    tables: list[list[list[str | None]]] = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text_pages.append(page.extract_text() or "")
            extracted_tables = page.extract_tables() or []
            for table in extracted_tables:
                if table:
                    tables.append(table)

    return PDFDocument(
        filename=uploaded_file.name,
        text_pages=text_pages,
        tables=tables,
    )
