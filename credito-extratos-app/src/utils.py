from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

import pandas as pd
from unidecode import unidecode


DATE_PATTERNS = [
    r"\b\d{2}/\d{2}/\d{4}\b",
    r"\b\d{2}/\d{2}/\d{2}\b",
    r"\b\d{2}-\d{2}-\d{4}\b",
    r"\b\d{2}-\d{2}-\d{2}\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
]

NUMBER_PATTERN = r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}"
AMOUNT_PATTERN = re.compile(
    rf"""
    (?P<token>
        (?P<prefix_sign>[+\-])?\s*
        (?:R\$\s*)?
        (?P<paren_open>\()?\s*
        (?P<number>{NUMBER_PATTERN})
        \s*(?P<paren_close>\))?
        \s*(?P<suffix_sign>[+\-])?
        \s*(?P<direction>CR|DB|C|D)?
    )
    (?=\s|$)
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True)
class AmountMatch:
    text: str
    value: float
    explicit_credit: bool
    explicit_debit: bool
    start: int
    end: int


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


def extract_amount_matches(value: object) -> list[AmountMatch]:
    if value is None:
        return []

    text = normalize_text(value)
    if not text:
        return []

    matches: list[AmountMatch] = []
    for match in AMOUNT_PATTERN.finditer(text):
        number = match.group("number")
        if not number:
            continue

        numeric_value = float(number.replace(".", "").replace(",", "."))
        prefix_sign = normalize_text(match.group("prefix_sign"))
        suffix_sign = normalize_text(match.group("suffix_sign"))
        direction = normalize_text(match.group("direction")).upper()
        has_parentheses = bool(match.group("paren_open") and match.group("paren_close"))

        explicit_credit = prefix_sign == "+" or suffix_sign == "+" or direction in {"C", "CR"}
        explicit_debit = prefix_sign == "-" or suffix_sign == "-" or direction in {"D", "DB"} or has_parentheses

        signed_value = numeric_value
        if explicit_debit and not explicit_credit:
            signed_value = -numeric_value

        matches.append(
            AmountMatch(
                text=normalize_text(match.group("token")),
                value=signed_value,
                explicit_credit=explicit_credit,
                explicit_debit=explicit_debit,
                start=match.start("token"),
                end=match.end("token"),
            )
        )

    return matches


def parse_brl_number(value: object) -> Optional[float]:
    matches = extract_amount_matches(value)
    if matches:
        return matches[0].value

    if value is None:
        return None
    text = normalize_text(value)
    if not text:
        return None

    text = text.replace("R$", "").replace(" ", "")
    text = text.replace(".", "").replace(",", ".")
    text = text.replace("(", "-").replace(")", "")
    text = text.replace("âˆ’", "-")

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

    known_formats = (
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%Y-%m-%d",
    )

    for fmt in known_formats:
        parsed = pd.to_datetime(text, format=fmt, errors="coerce")
        if not pd.isna(parsed):
            return parsed.normalize()

    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
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
            export_df = df.copy()
            for col in export_df.columns:
                if pd.api.types.is_float_dtype(export_df[col]):
                    export_df[col] = export_df[col].apply(_format_float_ptbr)
            export_df.to_excel(writer, sheet_name=safe_name, index=False)
    buffer.seek(0)
    return buffer.read()


def _format_float_ptbr(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        formatted = f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return ""
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


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
        r"transfer[êe]ncia recebida pelo pix\s+(.*)$",
        r"transfer[êe]ncia enviada pelo pix\s+(.*)$",
        r"(?:pix|ted|doc|transf(?:erencia)?)\s+(?:recebido|recebida)\s+de\s+(.*)$",
        r"(?:pix|ted|doc|transf(?:erencia)?)\s+(?:de|para)\s+(.*)$",
        r"(?:de)\s+([A-ZÀ-ÿ0-9\s\.-]{3,})$",
        r"(?:favorecido|origem)\s*[:\-]\s*(.*)$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = normalize_text(match.group(1))
            candidate = re.split(r"\s+-\s+[•\d]{3,}", candidate, maxsplit=1)[0]
            candidate = re.split(r"\s+-\s+\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", candidate, maxsplit=1)[0]
            return normalize_text(candidate)

    return ""
