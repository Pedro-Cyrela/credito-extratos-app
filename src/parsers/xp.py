from __future__ import annotations

import re

import pandas as pd

from ..utils import extract_amount_matches, fold_text, normalize_text, parse_date
from .base import build_record, finalize_records

XP_TRANSACTION_PATTERN = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{2,4})\s+"
    r"(?P<time>(?:\u00e0s|as)\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<body>.+)$",
    flags=re.IGNORECASE,
)


class XPContaDigitalParser:
    name = "xp_conta_digital"

    def matches(self, text_pages: list[str]) -> bool:
        header = fold_text("\n".join(text_pages[:2]))
        return (
            "conta digital xp" in header
            and "banco xp s.a" in header
            and "data descricao valor saldo" in header
        )

    def parse(
        self,
        text_pages: list[str],
        source_file: str,
        word_pages: list[list[dict]] | None = None,
    ) -> pd.DataFrame:
        del word_pages
        rows: list[dict] = []

        for page_text in text_pages:
            for raw_line in page_text.splitlines():
                line = normalize_text(raw_line)
                match = XP_TRANSACTION_PATTERN.match(line)
                if not match:
                    continue

                dt = parse_date(match.group("date"))
                if dt is None:
                    continue

                body = normalize_text(match.group("body"))
                amount_matches = extract_amount_matches(body)
                if len(amount_matches) < 2:
                    continue

                transaction_amount = amount_matches[-2]
                description = normalize_text(body[: transaction_amount.start])
                if not description:
                    description = "Movimentacao sem descricao"

                description = f"{normalize_text(match.group('time'))} {description}"
                amount = float(transaction_amount.value)
                rows.append(
                    build_record(
                        dt=dt,
                        desc=description,
                        amount=amount,
                        raw_amount_text=transaction_amount.text,
                        detected_as_credit=transaction_amount.explicit_credit
                        or (amount > 0 and not transaction_amount.explicit_debit),
                        detected_as_debit=transaction_amount.explicit_debit or amount < 0,
                        source_file=source_file,
                    )
                )

        return finalize_records(rows)
