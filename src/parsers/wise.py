from __future__ import annotations

import logging
import re

import pandas as pd

from ..utils import extract_amount_matches, fold_text, normalize_text
from .base import build_record, empty_transactions_df, finalize_records

logger = logging.getLogger(__name__)


WISE_PT_MONTHS = {
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
WISE_DATE_LINE_PATTERN = re.compile(
    r"^(?P<day>\d{1,2})\s+de\s+(?P<month>[^\d]+?)\s+de\s+(?P<year>\d{4})\b",
    flags=re.IGNORECASE,
)


def looks_like_wise(text_pages: list[str]) -> bool:
    """Module-level detector reused by detect_foreign_statement()."""
    sample = "\n".join(text_pages[:2])
    folded = fold_text(sample)
    return (
        "wise payments ltd." in folded
        and "extrato em usd" in folded
        and "entrada" in folded
        and "valor" in folded
    )


def _parse_date_line(line: str) -> pd.Timestamp | None:
    match = WISE_DATE_LINE_PATTERN.match(line)
    if not match:
        return None

    month = WISE_PT_MONTHS.get(fold_text(match.group("month")))
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
        or ("entrada" in folded and "valor" in folded and ("descr" in folded or "descri" in folded))
        or folded.startswith("wise payments ltd.")
        or folded.startswith("1st floor, worship square")
        or folded == "london"
        or folded == "united kingdom"
        or folded.startswith("extrato em ")
        or folded.startswith("gerado em:")
        or folded.startswith("titular da conta numero da conta routing number")
        or folded.startswith("swift/bic")
        or folded.startswith("usd em ")
        or folded.startswith("precisa de ajuda?")
        or folded.startswith("a wise payments limited")
        or folded.startswith("reino unido")
        or folded.startswith("house sob o numero")
        or folded.startswith("rio de janeiro")
        or folded == "rj"
        or folded == "brazil"
        or re.fullmatch(r"trwi[a-z0-9]+", folded) is not None
        or re.fullmatch(r"\d{8,}", folded) is not None
        or re.fullmatch(r"ref:[a-f0-9-]+\s+\d+\s*/\s*\d+", folded) is not None
        or re.fullmatch(r".+\[gmt[-+0-9:]+\].*", folded) is not None
    )


def _resolve_amount(line: str) -> tuple[float, str, bool, bool] | None:
    amount_matches = extract_amount_matches(line)
    if len(amount_matches) < 2:
        return None

    amount_match = amount_matches[-2]
    amount = float(amount_match.value)
    detected_as_credit = amount_match.explicit_credit or (
        amount > 0 and not amount_match.explicit_debit
    )
    detected_as_debit = amount_match.explicit_debit or amount < 0
    return amount, amount_match.text, detected_as_credit, detected_as_debit


class WiseParser:
    name = "wise"

    def matches(self, text_pages: list[str]) -> bool:
        return looks_like_wise(text_pages)

    def parse(
        self,
        text_pages: list[str],
        source_file: str,
        word_pages: list[list[dict]] | None = None,
    ) -> pd.DataFrame:
        if not self.matches(text_pages):
            return empty_transactions_df()

        rows: list[dict] = []
        pending_parts: list[str] = []

        for page_text in text_pages:
            for raw_line in page_text.splitlines():
                line = normalize_text(raw_line)
                if _is_noise_line(line):
                    continue

                dt = _parse_date_line(line)
                if dt is not None:
                    if pending_parts:
                        description = normalize_text(" ".join(pending_parts))
                        amount_info = _resolve_amount(description)
                        if amount_info is not None:
                            amount, raw_amount_text, detected_as_credit, detected_as_debit = (
                                amount_info
                            )
                            rows.append(
                                build_record(
                                    dt=dt,
                                    desc=description,
                                    amount=amount,
                                    raw_amount_text=raw_amount_text,
                                    detected_as_credit=detected_as_credit,
                                    detected_as_debit=detected_as_debit,
                                    source_file=source_file,
                                )
                            )
                    pending_parts = []
                    continue

                pending_parts.append(line)

        return finalize_records(rows)
