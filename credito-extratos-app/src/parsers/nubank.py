from __future__ import annotations

import logging
import re

import pandas as pd

from ..utils import extract_amount_matches, fold_text, normalize_text
from .base import (
    PT_MONTHS,
    build_record,
    empty_transactions_df,
    finalize_records,
)

logger = logging.getLogger(__name__)


NUBANK_DAY_SECTION_PATTERN = re.compile(
    r"^(?P<day>\d{2})\s+(?P<month>[A-ZÃ‡]{3})\s+(?P<year>\d{4})\s+Total de\s+"
    r"(?P<section>entradas|sa[iÃ­]das)\s+[+\-]\s*(?P<amount>.+)$",
    flags=re.IGNORECASE | re.MULTILINE,
)
NUBANK_DAY_PATTERN = re.compile(
    r"^(?P<day>\d{2})\s+(?P<month>[A-ZÇ]{3})\s+(?P<year>\d{4})\s+Total de entradas\s+\+\s*(?P<amount>.+)$",
    flags=re.IGNORECASE | re.MULTILINE,
)
NUBANK_STANDALONE_DAY_PATTERN = re.compile(
    r"^(?P<day>\d{2})\s+(?P<month>[A-ZÇ]{3})\s+(?P<year>\d{4})$",
    flags=re.IGNORECASE,
)
NUBANK_TOTAL_IN_PATTERN = re.compile(
    r"^Total de entradas\s+\+\s*(?P<amount>.+)$",
    flags=re.IGNORECASE,
)
NUBANK_TOTAL_OUT_PATTERN = re.compile(
    r"^Total de sa[ií]das\s+-\s*(?P<amount>.+)$",
    flags=re.IGNORECASE,
)
NUBANK_SKIP_PATTERNS = [
    re.compile(pattern, flags=re.IGNORECASE)
    for pattern in [
        r"^Movimenta[cç][õo]es$",
        r"^Saldo inicial\b",
        r"^Saldo do dia\b",
        r"^Saldo final do per[ií]odo\b",
        r"^Rendimento l[ií]quido\b",
        r"^Tem alguma d[uú]vida\?",
        r"^metropolitanas\)",
        r"^Caso a solu[cç][aã]o fornecida",
        r"^dispon[ií]veis em nubank\.com\.br",
        r"^Extrato gerado dia",
        r"^CPF ",
        r"^\d{6,}-\d{1,2}$",
        r"^\d{2} DE [A-ZÇ]+ DE \d{4} a \d{2} DE [A-ZÇ]+ DE \d{4}\b",
    ]
]


def _is_skip_line(line: str) -> bool:
    return any(pattern.search(line) for pattern in NUBANK_SKIP_PATTERNS)


def _parse_day(line: str) -> pd.Timestamp | None:
    match = NUBANK_DAY_PATTERN.match(line)
    if not match:
        return None

    month_key = normalize_text(match.group("month")).upper()
    month = PT_MONTHS.get(month_key)
    if not month:
        return None

    return pd.Timestamp(
        year=int(match.group("year")),
        month=month,
        day=int(match.group("day")),
    ).normalize()


def _parse_day_section(line: str) -> tuple[pd.Timestamp, str] | None:
    folded_line = fold_text(line)
    match = re.match(
        r"^(?P<day>\d{2})\s+(?P<month>[A-Z]{3})\s+(?P<year>\d{4})\s+total de\s+"
        r"(?P<section>entradas|sa\S*das)\s+[+\-]\s*(?P<amount>.+)$",
        folded_line,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    month_key = normalize_text(match.group("month")).upper()
    month = PT_MONTHS.get(month_key)
    if not month:
        return None

    current_date = pd.Timestamp(
        year=int(match.group("year")),
        month=month,
        day=int(match.group("day")),
    ).normalize()
    section = "entradas" if "entrada" in fold_text(match.group("section")) else "saidas"
    return current_date, section


def _parse_standalone_day(line: str) -> pd.Timestamp | None:
    match = NUBANK_STANDALONE_DAY_PATTERN.match(line)
    if not match:
        return None

    month_key = normalize_text(match.group("month")).upper()
    month = PT_MONTHS.get(month_key)
    if not month:
        return None

    return pd.Timestamp(
        year=int(match.group("year")),
        month=month,
        day=int(match.group("day")),
    ).normalize()


def _normalize_description(desc: str) -> str:
    normalized = normalize_text(desc)
    folded = fold_text(normalized)

    if (
        folded.startswith("valor adicionado na conta por")
        and "valor adicionado para pix no credito" in folded
    ):
        return "Valor adicionado na conta por cartão Valor adicionado para Pix no Crédito"

    return normalized


def _parse_transaction_line(
    line: str,
    current_date: pd.Timestamp,
    current_section: str,
    source_file: str,
) -> dict | None:
    amount_matches = extract_amount_matches(line)
    if not amount_matches:
        return None

    amount_match = amount_matches[-1]
    desc = normalize_text(line[: amount_match.start])
    desc = re.sub(r"\s*-\s*$", "", desc).strip()
    desc = _normalize_description(desc)
    if not desc:
        return None

    folded_desc = fold_text(desc)
    if "recebid" in folded_desc:
        inferred_section = "entradas"
    elif any(token in folded_desc for token in ("enviad", "compra no debito", "pagamento ")):
        inferred_section = "saidas"
    else:
        inferred_section = current_section

    if inferred_section == "entradas":
        amount = abs(float(amount_match.value))
        detected_as_credit = True
        detected_as_debit = False
    else:
        amount = -abs(float(amount_match.value))
        detected_as_credit = False
        detected_as_debit = True

    return build_record(
        dt=current_date,
        desc=desc,
        amount=amount,
        raw_amount_text=amount_match.text,
        detected_as_credit=detected_as_credit,
        detected_as_debit=detected_as_debit,
        source_file=source_file,
    )


class NubankParser:
    name = "nubank"

    def matches(self, text_pages: list[str]) -> bool:
        sample = "\n".join(text_pages[:3])
        lowered = sample.casefold()
        has_block_headers = bool(NUBANK_DAY_PATTERN.search(sample)) and "total de sa" in lowered
        has_identity_markers = (
            "movimenta" in lowered or "nubank.com.br" in lowered or "saldo inicial" in lowered
        )
        return has_block_headers and has_identity_markers

    def parse(
        self,
        text_pages: list[str],
        source_file: str,
        word_pages: list[list[dict]] | None = None,
    ) -> pd.DataFrame:
        if not self.matches(text_pages):
            return empty_transactions_df()

        current_date: pd.Timestamp | None = None
        current_section: str | None = None
        pending_day: pd.Timestamp | None = None
        rows: list[dict] = []

        for page_text in text_pages:
            for raw_line in page_text.splitlines():
                line = normalize_text(raw_line)
                if not line or _is_skip_line(line):
                    continue

                day_section = _parse_day_section(line)
                if day_section is not None:
                    current_date, current_section = day_section
                    pending_day = None
                    continue

                day_date = _parse_day(line)
                if day_date is not None:
                    current_date = day_date
                    current_section = "entradas"
                    pending_day = None
                    continue

                standalone_day = _parse_standalone_day(line)
                if standalone_day is not None:
                    pending_day = standalone_day
                    continue

                if NUBANK_TOTAL_IN_PATTERN.match(line):
                    if pending_day is not None:
                        current_date = pending_day
                        pending_day = None
                        current_section = "entradas"
                        continue
                    if current_date is not None:
                        current_section = "entradas"
                    continue

                if NUBANK_TOTAL_OUT_PATTERN.match(line):
                    if current_date is not None:
                        current_section = "saidas"
                        pending_day = None
                    continue

                if current_date is None or current_section is None:
                    continue

                record = _parse_transaction_line(
                    line=line,
                    current_date=current_date,
                    current_section=current_section,
                    source_file=source_file,
                )
                if record:
                    rows.append(record)

        return finalize_records(rows)
