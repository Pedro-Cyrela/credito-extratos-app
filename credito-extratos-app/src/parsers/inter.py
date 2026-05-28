from __future__ import annotations

import logging
import re

import pandas as pd

from ..utils import extract_amount_matches, fold_text, normalize_text
from .base import build_record, empty_transactions_df, finalize_records

logger = logging.getLogger(__name__)


INTER_DAY_HEADER_PATTERN = re.compile(
    r"^(?P<day>\d{1,2})\s+de\s+(?P<month>[A-Za-zÀ-ÿçÇ]+)\s+de\s+(?P<year>\d{4})\s+Saldo do dia:\s+.+$",
    flags=re.IGNORECASE,
)

INTER_MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


def _parse_day_header(line: str) -> pd.Timestamp | None:
    match = INTER_DAY_HEADER_PATTERN.match(line)
    if not match:
        return None

    month = INTER_MONTHS.get(fold_text(match.group("month")))
    if not month:
        return None

    try:
        return pd.Timestamp(
            year=int(match.group("year")),
            month=month,
            day=int(match.group("day")),
        ).normalize()
    except ValueError:
        return None


def _is_noise_line(line: str) -> bool:
    folded = fold_text(line)
    return (
        not folded
        or folded.startswith("solicitado em:")
        or folded.startswith("cpf/cnpj:")
        or folded.startswith("periodo:")
        or folded.startswith("saldo total ")
        or folded.startswith("r$ ")
        or folded.startswith("(bloqueado + disponivel)")
        or folded == "valor saldo por transacao"
        or folded == "fale com a gente"
        or folded.startswith("sac:")
        or folded.startswith("ouvidoria:")
        or folded.startswith("deficiencia de fala")
    )


def _parse_transaction_line(
    line: str,
    current_date: pd.Timestamp,
    source_file: str,
) -> dict | None:
    amount_matches = extract_amount_matches(line)
    if len(amount_matches) < 2:
        return None

    amount_match = amount_matches[-2]
    desc = normalize_text(line[: amount_match.start]).strip()
    if not desc:
        return None

    amount = float(amount_match.value)
    detected_as_credit = amount_match.explicit_credit or (
        amount > 0 and not amount_match.explicit_debit
    )
    detected_as_debit = amount_match.explicit_debit or amount < 0

    return build_record(
        dt=current_date,
        desc=desc,
        amount=amount,
        raw_amount_text=amount_match.text,
        detected_as_credit=detected_as_credit,
        detected_as_debit=detected_as_debit,
        source_file=source_file,
    )


class InterParser:
    name = "inter"

    def matches(self, text_pages: list[str]) -> bool:
        sample = "\n".join(text_pages[:2])
        folded = fold_text(sample)
        return (
            "instituicao: banco inter" in folded
            and "saldo por transacao" in folded
            and "saldo do dia:" in folded
        )

    def parse(
        self,
        text_pages: list[str],
        source_file: str,
        word_pages: list[list[dict]] | None = None,
    ) -> pd.DataFrame:
        if not self.matches(text_pages):
            return empty_transactions_df()

        current_date: pd.Timestamp | None = None
        rows: list[dict] = []

        for page_text in text_pages:
            for raw_line in page_text.splitlines():
                line = normalize_text(raw_line)
                if not line or _is_noise_line(line):
                    continue

                day_header = _parse_day_header(line)
                if day_header is not None:
                    current_date = day_header
                    continue

                if current_date is None:
                    continue

                record = _parse_transaction_line(line, current_date, source_file)
                if record:
                    rows.append(record)

        return finalize_records(rows)
