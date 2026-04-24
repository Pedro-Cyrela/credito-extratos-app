from __future__ import annotations

import re
from dataclasses import dataclass

from .utils import fold_text, normalize_text


@dataclass
class HeaderInfo:
    bank_name: str = ""
    account_holder: str = ""
    account_number: str = ""
    agency: str = ""
    statement_period: str = ""


BANK_PATTERNS = [
    "bank of america",
    "itaú",
    "itau",
    "bradesco",
    "santander",
    "caixa",
    "banco do brasil",
    "nubank",
    "inter",
    "sicredi",
    "sicoob",
    "picpay",
    "mercado pago",
    "c6",
    "btg",
    "original",
]
BANK_DISPLAY_NAMES = {
    "bank of america": "Bank of America",
    "bradesco": "Bradesco",
    "nubank": "Nubank",
    "banco do brasil": "Banco do Brasil",
}
CPF_PATTERN = r"\d{3}\.\d{3}\.\d{3}-\d{2}"


def parse_header(text_pages: list[str]) -> HeaderInfo:
    first_page = text_pages[0] if text_pages else ""
    header_text = "\n".join(text_pages[:2])

    info = HeaderInfo()
    info.bank_name = _detect_bank(header_text, first_page)
    info.account_holder = _extract_holder(header_text or first_page)
    info.agency = _extract_agency(header_text or first_page)
    info.account_number = _extract_account(header_text or first_page)
    info.statement_period = _extract_period(header_text or first_page)

    return info


def _detect_bank(header_text: str, first_page: str) -> str:
    first_page_lower = first_page.lower()
    header_lower = header_text.lower()

    if "nubank.com.br" in header_lower or "movimentações" in header_lower:
        return "Nubank"

    for bank in BANK_PATTERNS:
        if bank in first_page_lower:
            return BANK_DISPLAY_NAMES.get(bank, bank.title())
    return ""


def _extract_holder(header_text: str) -> str:
    holder_patterns = [
        r"(?:titular|cliente|nome)\s*[:\-]\s*([^\n\r]{5,})",
        r"^([A-Z][A-Z\s\.]{5,})\s+bankofamerica\.com\b",
        r"(?:titular|cliente|nome)\s*[:\-]\s*([A-ZÀ-ÿ][A-ZÀ-ÿ\s\.]{5,})",
        rf"([A-ZÀ-Ý][A-ZÀ-Ý\s]{{5,}}?)\s+({CPF_PATTERN})",
        rf"({CPF_PATTERN})\s+([A-ZÀ-Ý][A-ZÀ-Ý\s]{{5,}})",
        r"^([A-ZÀ-Ý][A-ZÀ-Ý\s]{8,})$",
    ]

    for pattern in holder_patterns:
        match = re.search(pattern, header_text, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            continue

        groups = [normalize_text(group) for group in match.groups() if group]
        candidate = next(
            (
                group
                for group in groups
                if re.search(r"[A-Za-zÀ-ÿ]", group) and not re.fullmatch(CPF_PATTERN, group)
            ),
            "",
        )

        if _looks_like_person_name(candidate):
            return candidate

    return ""


def _extract_agency(header_text: str) -> str:
    agency_patterns = [
        r"(?:agencia|agência)\s*[:\-]?\s*(\d{3,6})",
        r"(?:agencia|agência)\s+(\d{3,6})",
    ]

    for pattern in agency_patterns:
        match = re.search(pattern, header_text, flags=re.IGNORECASE)
        if match:
            return normalize_text(match.group(1))

    return ""


def _extract_account(header_text: str) -> str:
    account_patterns = [
        r"account\s*(?:number|#)\s*[:#]?\s*([\d\s\-]+)",
        r"(?:conta(?: corrente)?|cc)\s*[:\-]?\s*([\d\.\-xX/]+)",
        r"(?:agencia|agência)\s*[:\-]?\s*\d{3,6}\s+(?:conta(?: corrente)?|cc)\s*[:\-]?\s*([\d\.\-xX/]+)",
    ]

    for pattern in account_patterns:
        match = re.search(pattern, header_text, flags=re.IGNORECASE)
        if match:
            return normalize_text(match.group(1))

    return ""


def _extract_period(header_text: str) -> str:
    folded = fold_text(header_text)
    bradesco_match = re.search(
        r"movimentacao entre\s*:\s*(\d{2}/\d{2}/\d{4}\s+e\s+\d{2}/\d{2}/\d{4})",
        folded,
    )
    if bradesco_match:
        return normalize_text(bradesco_match.group(1))

    foreign_match = re.search(
        r"\bfor\s+([A-Za-z]+\s+\d{1,2},\s+\d{4}\s+to\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})",
        header_text,
        flags=re.IGNORECASE,
    )
    if foreign_match:
        return normalize_text(foreign_match.group(1))

    period_pattern = r"(?:periodo|período|extrato de)\s*[:\-]?\s*([0-9/\saAaté\-]+)"
    match = re.search(period_pattern, header_text, flags=re.IGNORECASE)
    if match:
        return normalize_text(match.group(1))
    return ""


def _looks_like_person_name(value: str) -> bool:
    candidate = normalize_text(value)
    if not candidate:
        return False

    tokens = [token for token in candidate.split() if len(token) >= 2]
    if len(tokens) < 2:
        return False

    forbidden_terms = {
        "banco",
        "bank",
        "bradesco",
        "celular",
        "itau",
        "itaú",
        "agencia",
        "agência",
        "conta",
        "extrato",
        "periodo",
        "período",
    }

    lowered_tokens = {token.lower() for token in tokens}
    if lowered_tokens & forbidden_terms:
        return False

    alpha_ratio = sum(char.isalpha() or char.isspace() for char in candidate) / max(len(candidate), 1)
    return alpha_ratio >= 0.75
