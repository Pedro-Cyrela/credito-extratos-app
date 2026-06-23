from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .utils import fold_text, normalize_text

logger = logging.getLogger(__name__)


_BANKS_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "banks.json"


def _load_banks_catalog() -> tuple[list[str], dict[str, str]]:
    """Load banks.json once into (aliases_in_priority_order, alias_to_display).

    Aliases are folded (accent-less, lowercased) so matching against PDF text
    is consistent regardless of how the bank name appears in the document.
    Aliases are sorted by length descending so longer aliases ("banco do
    brasil") win over shorter prefixes ("bb").
    """
    try:
        payload = json.loads(_BANKS_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Falha ao carregar %s; caindo no fallback hardcoded", _BANKS_CONFIG_PATH)
        return [], {}

    aliases: list[tuple[str, str]] = []
    for entry in payload.get("banks", []):
        display = entry.get("display", "")
        for alias in entry.get("aliases", []):
            folded = fold_text(alias)
            if folded:
                aliases.append((folded, display))

    aliases.sort(key=lambda pair: -len(pair[0]))
    return [a for a, _ in aliases], {a: d for a, d in aliases}


_BANK_ALIASES_ORDERED, _BANK_DISPLAY_BY_ALIAS = _load_banks_catalog()


@dataclass
class HeaderInfo:
    bank_name: str = ""
    account_holder: str = ""
    account_number: str = ""
    agency: str = ""
    statement_period: str = ""


# Kept as a thin shim around the catalog for any external callers.
BANK_PATTERNS = list(_BANK_ALIASES_ORDERED)
BANK_DISPLAY_NAMES = dict(_BANK_DISPLAY_BY_ALIAS)
CPF_PATTERN = r"\d{3}\.\d{3}\.\d{3}-\d{2}"
CNPJ_PATTERN = r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"
DOCUMENT_PATTERN = rf"(?:{CPF_PATTERN}|{CNPJ_PATTERN})"
PLAIN_DOCUMENT_PATTERN = r"(?:\d{11}|\d{14})"
SANTANDER_AGENCY_ACCOUNT_PATTERN = re.compile(
    r"^(?P<name>[A-ZÀ-ÿ][A-ZÀ-ÿ ]{5,}?)\s+Ag[eê]ncia\s+e\s+Conta\s*:\s*(?P<agency>\d{3,6})\s*/\s*(?P<account>[\d\.\-xX/]+)\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
XP_AGENCY_ACCOUNT_PATTERN = re.compile(
    r"^(?P<name>.+?)\s+Banco XP S\.?\s*A\.?\s*\|\s*"
    r"Ag\S*ncia\s*:\s*(?P<agency>[\d\-]+)\s*\|\s*"
    r"Conta\s*:\s*(?P<account>[\d\.\-xX/]+)\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)


def parse_header(text_pages: list[str]) -> HeaderInfo:
    first_page = text_pages[0] if text_pages else ""
    header_text = "\n".join(text_pages[:2])

    info = HeaderInfo()
    info.bank_name = _detect_bank(header_text, first_page)

    xp_candidate = XP_AGENCY_ACCOUNT_PATTERN.search(header_text or first_page)
    santander_candidate = SANTANDER_AGENCY_ACCOUNT_PATTERN.search(header_text or first_page)
    if xp_candidate:
        info.account_holder = normalize_text(xp_candidate.group("name"))
        info.agency = normalize_text(xp_candidate.group("agency"))
        info.account_number = normalize_text(xp_candidate.group("account"))
    elif santander_candidate:
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
    folded_header = fold_text(header_text)

    if "bradesco celular" in folded_header:
        return "Bradesco"

    if "nubank.com.br" in folded_header or (
        "movimenta" in folded_header
        and ("total de entradas" in folded_header or re.search(r"\b(cpf|cnpj)\b", folded_header))
        and "conta" in folded_header
    ):
        return "Nubank"

    bb_markers = (
        "extrato de conta corrente" in folded_header
        and "lanc" in folded_header
        and "dia" in folded_header
        and "lote" in folded_header
        and "historico" in folded_header
        and "valor" in folded_header
        and ("(+)" in folded_header or "(-)" in folded_header)
    )
    if bb_markers:
        return "Banco do Brasil"

    santander_markers = (
        "extrato de conta corrente" in folded_header
        and "agencia e conta:" in folded_header
        and "credito (r$)" in folded_header
        and "debito (r$)" in folded_header
        and "saldo (r$)" in folded_header
    )
    if santander_markers:
        return "Santander"

    itau_markers = (
        "extrato conta corrente" in folded_header
        and "lancamentos" in folded_header
        and "periodo de visualizacao" in folded_header
        and "saldo em conta" in folded_header
    )
    if itau_markers:
        return "Itaú"

    folded_first_page = fold_text(first_page)
    short_codes_requiring_context = {"inter", "c6", "btg", "bb"}

    for alias in _BANK_ALIASES_ORDERED:
        if alias in short_codes_requiring_context:
            continue
        if alias in folded_first_page:
            return _BANK_DISPLAY_BY_ALIAS.get(alias, alias.title())

    if re.search(r"\bc6\s+bank\b", folded_header):
        return _BANK_DISPLAY_BY_ALIAS.get("c6", "C6 Bank")
    if re.search(r"\bbanco\s+inter\b", folded_header):
        return _BANK_DISPLAY_BY_ALIAS.get("banco inter", "Inter")
    if re.search(r"\bbtg\b", folded_header) and "btg pactual" in folded_header:
        return _BANK_DISPLAY_BY_ALIAS.get("btg pactual", "BTG Pactual")
    if "cora scfi" in folded_header:
        return _BANK_DISPLAY_BY_ALIAS.get("cora scfi", "Cora")
    return ""


def _extract_holder(header_text: str) -> str:
    lines = [normalize_text(line) for line in header_text.splitlines() if normalize_text(line)]
    header_lines: list[str] = []
    for line in lines:
        if "movimenta" in fold_text(line):
            break
        header_lines.append(line)
    search_lines = header_lines[:6] if header_lines else lines[:6]

    for line in search_lines:
        document_match = re.search(DOCUMENT_PATTERN, line, flags=re.IGNORECASE)
        if not document_match:
            continue
        candidate = _clean_holder_candidate(line[: document_match.start()])
        if _looks_like_holder_name(candidate):
            return candidate

    for index, line in enumerate(search_lines):
        if re.search(rf"^CNPJ\s*{CNPJ_PATTERN}\b", line, flags=re.IGNORECASE) and index > 0:
            candidate = _clean_holder_candidate(search_lines[index - 1])
            if _looks_like_holder_name(candidate):
                return candidate

    for index, line in enumerate(search_lines):
        if fold_text(line).startswith("cpf/cnpj:") and index > 0:
            candidate = _clean_holder_candidate(re.sub(rf"\s+{PLAIN_DOCUMENT_PATTERN}\s*$", "", search_lines[index - 1]))
            if _looks_like_holder_name(candidate):
                return candidate

    first_line = normalize_text(search_lines[0] if search_lines else "")
    inline_name_match = re.match(rf"^(?P<name>.+?)\s+CPF\s*:?\s*{CPF_PATTERN}", first_line, flags=re.IGNORECASE)
    if inline_name_match:
        candidate = _clean_holder_candidate(inline_name_match.group("name"))
        if _looks_like_holder_name(candidate):
            return candidate

    patterns = [
        rf"^(?P<name>[A-ZÀ-ÿ][A-ZÀ-ÿ\s]{{5,}}?)\s+CPF\s*:?\s*{CPF_PATTERN}(?:\s+(?:agencia|agência|conta)\b|$)",
        rf"([A-ZÀ-ÿ][A-ZÀ-ÿ\s]{{5,}}?)\s+\S+\s*({CPF_PATTERN})",
        rf"([A-ZÀ-Ý0-9][A-ZÀ-Ý0-9\s]{{5,}}?)\s+(?:CNPJ\s*)?({CNPJ_PATTERN})",
        rf"({CPF_PATTERN})\s+([A-ZÀ-Ý][A-ZÀ-Ý\s]{{5,}})",
        rf"({CNPJ_PATTERN})\s+([A-ZÀ-Ý0-9][A-ZÀ-Ý0-9\s]{{5,}})",
        r"cliente\s+([^\n\r]{5,})",
        r"(?:titular|cliente|nome)\s*[:\-]\s*([^\n\r]{5,})",
        r"^([A-Z][A-Z\s\.]{5,})\s+bankofamerica\.com\b",
        r"^([A-ZÀ-Ý][A-ZÀ-Ý\s]{8,})$",
    ]

    for pattern in patterns:
        match = re.search(pattern, header_text, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            continue

        groups = [normalize_text(group) for group in match.groups() if group]
        candidate = next(
            (
                _clean_holder_candidate(group)
                for group in groups
                if re.search(r"[A-Za-zÀ-ÿ]", group)
                and not re.fullmatch(CPF_PATTERN, group)
                and not re.fullmatch(CNPJ_PATTERN, group)
            ),
            "",
        )
        if _looks_like_holder_name(candidate):
            return candidate

    return ""


def _clean_holder_candidate(value: str) -> str:
    candidate = normalize_text(value).replace("*", "").strip()
    candidate = re.sub(rf"\b(?:CPF|CNPJ)\s*:?\s*(?:{CPF_PATTERN}|{CNPJ_PATTERN})\b", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\b(?:CPF|CNPJ)\s*:?\s*$", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"^\d{2}\.\d{3}\.\d{3}\s+", "", candidate)
    candidate = re.sub(r"^\d+\s+", "", candidate)
    candidate = re.sub(r"[\s•\-\|]+$", "", candidate)
    return normalize_text(candidate)


def _extract_agency(header_text: str) -> str:
    for source in [header_text, fold_text(header_text)]:
        match = re.search(r"ag\S*ncia\s*[:\-]?\s*([\d\-]{1,10})", source, flags=re.IGNORECASE)
        if match:
            return normalize_text(match.group(1))
    return ""


def _extract_account(header_text: str) -> str:
    for source in [header_text, fold_text(header_text)]:
        match = re.search(r"(?:account\s*(?:number|#)|conta(?: corrente)?|cc)\s*[:\-]?\s*([\d\.\-xX/ ]+)", source, flags=re.IGNORECASE)
        if match:
            return normalize_text(match.group(1))
    return ""


def _extract_period(header_text: str) -> str:
    folded = fold_text(header_text)

    xp_period = re.search(
        r"\bde\s*:\s*(\d{2}/\d{2}/\d{4})\s+ate\s*:\s*(\d{2}/\d{2}/\d{4})",
        folded,
        flags=re.IGNORECASE,
    )
    if xp_period:
        return f"{xp_period.group(1)} a {xp_period.group(2)}"

    patterns = [
        r"movimentacao entre\s*:\s*(\d{2}/\d{2}/\d{4}\s+e\s+\d{2}/\d{2}/\d{4})",
        r"periodo\s*:\s*(\d{2}/\d{2}/\d{4}\s+a\s+\d{2}/\d{2}/\d{4})",
        r"per\S*odo\s+(\d{2}/\d{2}/\d{4}\s+a\s+\d{2}/\d{2}/\d{4})",
        r"extrato\s+per\S*odo\s*\S*\s*(\d{1,2}\s+de\s+[a-z]+\s+de\s+\d{4}\s+at\S*\s+\d{1,2}\s+de\s+[a-z]+\s+de\s+\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, folded, flags=re.IGNORECASE)
        if match:
            return normalize_text(match.group(1))

    foreign_match = re.search(
        r"\bfor\s+([A-Za-z]+\s+\d{1,2},\s+\d{4}\s+to\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})",
        header_text,
        flags=re.IGNORECASE,
    )
    if foreign_match:
        return normalize_text(foreign_match.group(1))

    return ""


def _looks_like_holder_name(value: str) -> bool:
    candidate = normalize_text(value)
    if not candidate:
        return False

    all_tokens = candidate.split()
    meaningful_tokens = [t for t in all_tokens if len(t) >= 2]
    # Aceita nomes com iniciais (ex: "R J J SERVICOS"): basta ter >= 2 tokens
    # no total e pelo menos 1 token substantivo (len >= 2).
    if len(all_tokens) < 2 or not meaningful_tokens:
        return False
    tokens = meaningful_tokens

    forbidden_terms = {
        "banco",
        "bank",
        "bradesco",
        "celular",
        "itau",
        "agencia",
        "conta",
        "extrato",
        "periodo",
        "movimentacoes",
        "movimentacao",
        "valores",
        "cnpj",
        "cpf",
    }

    lowered_tokens = {fold_text(token) for token in tokens}
    if lowered_tokens & forbidden_terms:
        return False

    alpha_ratio = sum(char.isalpha() or char.isspace() for char in candidate) / max(len(candidate), 1)
    return alpha_ratio >= 0.75
