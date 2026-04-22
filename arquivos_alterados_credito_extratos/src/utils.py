from __future__ import annotations

import io
import re
import unicodedata
from datetime import datetime
from typing import Iterable, Optional

import pandas as pd
from unidecode import unidecode


DATE_PATTERNS = [
    r"\b\d{2}/\d{2}/\d{4}\b",
    r"\b\d{2}/\d{2}/\d{2}\b",
    r"\b\d{2}-\d{2}-\d{4}\b",
]


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def fold_text(value: object) -> str:
    return unidecode(normalize_text(value)).lower()


def remove_accents(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn"
    )


def clean_column_name(name: object) -> str:
    text = fold_text(name)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def parse_brl_number(value: object) -> Optional[float]:
    if value is None:
        return None
    text = normalize_text(value)
    if not text:
        return None

    text = text.replace("R$", "").replace(" ", "")
    text = text.replace(".", "").replace(",", ".")
    text = text.replace("(", "-").replace(")", "")
    text = text.replace("−", "-")

    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None

    try:
        return float(match.group(0))
    except ValueError:
        return None


def parse_date(value: object) -> Optional[pd.Timestamp]:
    if value is None:
        return None

    text = normalize_text(value)
    if not text:
        return None

    for dayfirst in (True, False):
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=dayfirst)
        if not pd.isna(parsed):
            return parsed.normalize()

    return None


def find_first_date(text: str) -> Optional[str]:
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def month_label(ts: pd.Timestamp) -> str:
    return ts.strftime("%m/%Y")


def to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, df in sheets.items():
            safe_name = name[:31]
            df.to_excel(writer, sheet_name=safe_name, index=False)
    buffer.seek(0)
    return buffer.read()


def split_user_terms(raw_text: str) -> list[str]:
    if not raw_text:
        return []
    parts = re.split(r"[\n,;]+", raw_text)
    return [normalize_text(p) for p in parts if normalize_text(p)]


def expand_name_tokens(name: str) -> list[str]:
    text = fold_text(name)
    tokens = [t for t in re.split(r"\s+", text) if len(t) >= 3]
    results = set(tokens)

    if tokens:
        first_token = tokens[0]
        results.update(_build_prefix_variants(first_token))

    if len(tokens) >= 2:
        results.add(" ".join(tokens[:2]))
    if len(tokens) >= 3:
        results.add(" ".join(tokens[:3]))
    results.add(text)
    return sorted(results, key=len, reverse=True)



def _build_prefix_variants(token: str) -> set[str]:
    variants = {token}
    if len(token) >= 7:
        variants.add(token[:-1])
    if len(token) >= 8:
        variants.add(token[:-2])
    return {variant for variant in variants if len(variant) >= 5}



def safe_float_sum(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    return float(pd.to_numeric(series, errors="coerce").fillna(0).sum())


def infer_counterparty(description: str) -> str:
    text = normalize_text(description)
    if not text:
        return ""

    patterns = [
        r"(?:pix|ted|doc|transf(?:erencia)?)\s+(?:recebido|recebida|de)\s+(.*)$",
        r"(?:de)\s+([A-ZÀ-ÿ0-9\s\.-]{3,})$",
        r"(?:favorecido|origem)\s*[:\-]\s*(.*)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return normalize_text(match.group(1))

    return ""
