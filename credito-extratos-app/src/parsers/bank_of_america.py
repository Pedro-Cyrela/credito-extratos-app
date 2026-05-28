from __future__ import annotations

import logging
import re

import pandas as pd

from ..utils import fold_text, normalize_text
from .base import build_record, empty_transactions_df, finalize_records

logger = logging.getLogger(__name__)


US_AMOUNT_TOKEN = r"[-+]?\$?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}"
FOREIGN_DEPOSIT_ROW_PATTERN = re.compile(
    rf"^(?P<date>\d{{2}}/\d{{2}}/\d{{2}})\s+(?P<description>.+?)\s+(?P<amount>{US_AMOUNT_TOKEN})$",
    flags=re.IGNORECASE,
)

FOREIGN_DEPOSIT_HEADINGS = {
    "deposits and other additions",
    "deposits and other additions - continued",
}


def looks_like_foreign_deposit(text_pages: list[str]) -> bool:
    """Module-level detector reused by detect_foreign_statement()."""
    sample = "\n".join(text_pages[:4])
    folded = fold_text(sample)
    return "deposits and other additions" in folded and "date description amount" in folded


def _parse_us_date(value: str) -> pd.Timestamp | None:
    parsed = pd.to_datetime(value, format="%m/%d/%y", errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.normalize()


def _parse_us_amount(value: str) -> float | None:
    text = normalize_text(value).replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _is_heading(line: str) -> bool:
    return fold_text(line) in FOREIGN_DEPOSIT_HEADINGS


def _is_stop_line(line: str) -> bool:
    folded = fold_text(line)
    return (
        folded.startswith("total deposits and other additions")
        or folded.startswith("withdrawals and other subtractions")
        or folded.startswith("checks")
        or folded.startswith("service fees")
        or folded.startswith("daily ledger")
        or folded.startswith("continued on the next page")
        or re.fullmatch(r"page \d+ of \d+", folded) is not None
    )


def _partials_to_df(transactions: list[dict], source_file: str) -> pd.DataFrame:
    rows: list[dict] = []
    for transaction in transactions:
        desc = normalize_text(" ".join(transaction["desc_parts"]))
        if not desc:
            continue

        rows.append(
            build_record(
                dt=transaction["dt"],
                desc=desc,
                amount=transaction["amount"],
                raw_amount_text=transaction["raw_amount_text"],
                detected_as_credit=True,
                detected_as_debit=False,
                source_file=source_file,
            )
        )

    return finalize_records(rows)


class BankOfAmericaParser:
    name = "bank_of_america"

    def matches(self, text_pages: list[str]) -> bool:
        return looks_like_foreign_deposit(text_pages)

    def parse(
        self,
        text_pages: list[str],
        source_file: str,
        word_pages: list[list[dict]] | None = None,
    ) -> pd.DataFrame:
        if not self.matches(text_pages):
            return empty_transactions_df()

        transactions: list[dict] = []

        for page_text in text_pages:
            in_deposit_section = False

            for raw_line in page_text.splitlines():
                line = normalize_text(raw_line)
                if not line:
                    continue

                if _is_heading(line):
                    in_deposit_section = True
                    continue

                if not in_deposit_section:
                    continue

                if fold_text(line) == "date description amount":
                    continue

                if _is_stop_line(line):
                    in_deposit_section = False
                    continue

                match = FOREIGN_DEPOSIT_ROW_PATTERN.match(line)
                if match:
                    dt = _parse_us_date(match.group("date"))
                    amount = _parse_us_amount(match.group("amount"))
                    desc = normalize_text(match.group("description"))
                    if dt is None or amount is None or not desc:
                        continue

                    transactions.append(
                        {
                            "dt": dt,
                            "desc_parts": [desc],
                            "amount": abs(amount),
                            "raw_amount_text": match.group("amount"),
                        }
                    )
                    continue

                if transactions:
                    transactions[-1]["desc_parts"].append(line)

        return _partials_to_df(transactions, source_file)
