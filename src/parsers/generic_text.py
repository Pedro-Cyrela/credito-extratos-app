from __future__ import annotations

import logging
import re

import pandas as pd

from ..utils import extract_amount_matches, normalize_text, parse_date
from .base import build_record, empty_transactions_df

logger = logging.getLogger(__name__)


DATE_PREFIX_PATTERN = re.compile(r"^(?P<data>\d{2}[/-]\d{2}[/-]\d{2,4})\b")


def _merge_multiline_records(page_text: str) -> list[str]:
    logical_lines: list[str] = []
    current_line = ""

    for raw_line in page_text.splitlines():
        line = normalize_text(raw_line)
        if not line:
            continue

        if DATE_PREFIX_PATTERN.match(line):
            if current_line:
                logical_lines.append(current_line)
            current_line = line
            continue

        if current_line:
            current_line = f"{current_line} {line}".strip()

    if current_line:
        logical_lines.append(current_line)

    return logical_lines


def _parse_text_line(line: str, source_file: str) -> dict | None:
    date_match = DATE_PREFIX_PATTERN.match(line)
    if not date_match:
        return None

    dt = parse_date(date_match.group("data"))
    if dt is None:
        return None

    remainder = normalize_text(line[date_match.end():])
    amount_matches = extract_amount_matches(remainder)
    if not amount_matches:
        return None

    amount_match = amount_matches[-2] if len(amount_matches) >= 2 else amount_matches[-1]
    desc = normalize_text(remainder[:amount_match.start])
    if not desc:
        return None

    amount = float(amount_match.value)
    detected_as_credit = amount_match.explicit_credit or (
        amount > 0 and not amount_match.explicit_debit
    )
    detected_as_debit = amount_match.explicit_debit or amount < 0

    return build_record(
        dt=dt,
        desc=desc,
        amount=amount,
        raw_amount_text=amount_match.text,
        detected_as_credit=detected_as_credit,
        detected_as_debit=detected_as_debit,
        source_file=source_file,
    )


def parse_generic_text(text_pages: list[str], source_file: str) -> pd.DataFrame:
    """Generic fallback parser: extracts rows starting with a date prefix.

    Used when no bank-specific parser matches.
    """
    generic_rows: list[dict] = []

    for page_text in text_pages:
        for line in _merge_multiline_records(page_text):
            record = _parse_text_line(line, source_file)
            if record:
                generic_rows.append(record)

    if not generic_rows:
        return empty_transactions_df()

    result = pd.DataFrame(generic_rows)
    result["data"] = pd.to_datetime(result["data"], errors="coerce")
    return result.sort_values(["data", "descricao"]).reset_index(drop=True)
