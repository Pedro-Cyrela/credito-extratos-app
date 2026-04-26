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
SANTANDER_AGENCY_ACCOUNT_PATTERN = re.compile(
    r"^(?P<name>[A-ZÀ-ÿ][A-ZÀ-ÿ ]{5,}?)\s+Ag[eê]ncia\s+e\s+Conta\s*:\s*(?P<agency>\d{3,6})\s*/\s*(?P<account>[\d\.\-xX/]+)\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)


def parse_header(text_pages: list[str]) -> HeaderInfo:
    first_page = text_pages[0] if text_pages else ""
    header_text = "\n".join(text_pages[:2])

    info = HeaderInfo()
    info.bank_name = _detect_bank(header_text, first_page)

    santander_candidate = SANTANDER_AGENCY_ACCOUNT_PATTERN.search(header_text or first_page)
    if santander_candidate:
        info.account_holder = normalize_text(santander_candidate.group("name"))
        info.agency = normalize_text(santander_candidate.group("agency"))
        info.account_number = normalize_text(santander_candidate.group("account"))
    else:
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

    bb_markers = (
        "extrato de conta corrente" in header_lower
        and "lançamentos" in header_lower
        and "dia" in header_lower
        and "lote" in header_lower
        and ("histórico" in header_lower or "historico" in header_lower)
        and "valor" in header_lower
        and ("(+)" in header_lower or "(-)" in header_lower)
    )
    if bb_markers:
        return "Banco do Brasil"

    santander_markers = (
        "extrato de conta corrente" in header_lower
        and ("agência e conta:" in header_lower or "agencia e conta:" in header_lower)
        and "crédito (r$)" in header_lower
        and "débito (r$)" in header_lower
        and "saldo (r$)" in header_lower
    )
    if santander_markers:
        return "Santander"

    for bank in BANK_PATTERNS:
        if bank in {"inter", "c6", "btg"}:
            continue
        if bank in first_page_lower:
            return BANK_DISPLAY_NAMES.get(bank, bank.title())

    # Avoid false positive: "inter" appears in "internet" and "intermediacao".
    if re.search(r"\bbanco\s+inter\b", header_lower) or re.search(r"\bc6\s+bank\b", header_lower):
        return "Inter"
    if re.search(r"\bbtg\b", header_lower) and "btg pactual" in header_lower:
        return "BTG"
    return ""


def _extract_holder(header_text: str) -> str:
    holder_patterns = [
        r"cliente\s+([^\n\r]{5,})",
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
            return candidate.replace("*", "").strip()

    return ""


def _extract_agency(header_text: str) -> str:
    agency_patterns = [
        r"(?:agencia|agência)\s*[:\-]?\s*([\d\-]{3,10})",
        r"(?:agencia|agência)\s+([\d\-]{3,10})",
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
    banco_brasil_match = re.search(
        r"per[ií]odo\s*:\s*([0-3]?\d\s+a\s+\d{2}/\d{2}/\d{4})",
        folded,
    )
    if banco_brasil_match:
        return normalize_text(banco_brasil_match.group(1))

    santander_match = re.search(
        r"per[ií]odo\s*:\s*(\d{2}/\d{2}/\d{4}\s+a\s+\d{2}/\d{2}/\d{4})",
        folded,
    )
    if santander_match:
        return normalize_text(santander_match.group(1))

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
