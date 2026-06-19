from __future__ import annotations

import logging
import re

import pandas as pd

from ..utils import extract_amount_matches, fold_text, normalize_text, parse_date
from .base import (
    PT_MONTHS,
    build_record,
    empty_transactions_df,
    finalize_records,
)

logger = logging.getLogger(__name__)


EAGLE_DAY_PATTERN = re.compile(
    r"^(?P<day>\d{1,2})\s+(?P<month>[A-ZÇ]{3})\s+(?P<year>\d{4})\b",
    flags=re.IGNORECASE,
)


def _is_noise(folded: str) -> bool:
    return folded.startswith(
        (
            "extrato ",
            "nome ",
            "cnpj ",
            "saldo inicial",
            "total de entradas",
            "total de saidas",
            "saldo final",
            "saldo final disponivel",
            "movimentacoes",
            "o extrato e baseado",
            "extrato gerado em",
            "reclamacoes",
            "cancelamentos",
            "localidades",
            "capitais",
        )
    )


class EagleBrokerParser:
    name = "eagle_broker"

    def matches(self, text_pages: list[str]) -> bool:
        sample = "\n".join(text_pages[:2])
        folded = fold_text(sample)
        return "movimentacoes" in folded and "saldo ao final do dia" in folded and "extrato" in folded

    def parse(
        self,
        text_pages: list[str],
        source_file: str,
        word_pages: list[list[dict]] | None = None,
    ) -> pd.DataFrame:
        if not self.matches(text_pages):
            return empty_transactions_df()

        lines: list[str] = []
        for page_text in text_pages:
            lines.extend(
                [normalize_text(ln) for ln in (page_text or "").splitlines() if normalize_text(ln)]
            )

        current_date: pd.Timestamp | None = None
        rows: list[dict] = []
        last_index: int | None = None

        for line in lines:
            folded = fold_text(line)
            if not folded or _is_noise(folded):
                continue

            if folded.startswith("saldo ao final do dia"):
                last_index = None
                continue

            day_match = EAGLE_DAY_PATTERN.match(line)
            if day_match:
                month_key = normalize_text(day_match.group("month")).upper()
                month = PT_MONTHS.get(month_key)
                if month:
                    current_date = pd.Timestamp(
                        year=int(day_match.group("year")),
                        month=month,
                        day=int(day_match.group("day")),
                    ).normalize()
                else:
                    current_date = parse_date(day_match.group(0))
                remainder = normalize_text(line[day_match.end():])
                last_index = None
                if not remainder:
                    continue

                amount_matches = extract_amount_matches(remainder)
                if amount_matches:
                    amount_match = amount_matches[-1]
                    desc = normalize_text(remainder[: amount_match.start])
                    amount = float(amount_match.value)
                    if "enviado" in folded and amount > 0:
                        amount = -abs(amount)
                    if "recebido" in folded and amount < 0:
                        amount = abs(amount)

                    rows.append(
                        build_record(
                            dt=current_date,
                            desc=desc,
                            amount=amount,
                            raw_amount_text=amount_match.text,
                            detected_as_credit=amount > 0,
                            detected_as_debit=amount < 0,
                            source_file=source_file,
                        )
                    )
                    last_index = len(rows) - 1
                continue

            if current_date is not None:
                amount_matches = extract_amount_matches(line)
                if amount_matches and (
                    "pix" in folded or "recebido" in folded or "enviado" in folded
                ):
                    amount_match = amount_matches[-1]
                    desc = normalize_text(line[: amount_match.start])
                    amount = float(amount_match.value)
                    if "enviado" in folded and amount > 0:
                        amount = -abs(amount)
                    if "recebido" in folded and amount < 0:
                        amount = abs(amount)
                    rows.append(
                        build_record(
                            dt=current_date,
                            desc=desc,
                            amount=amount,
                            raw_amount_text=amount_match.text,
                            detected_as_credit=amount > 0,
                            detected_as_debit=amount < 0,
                            source_file=source_file,
                        )
                    )
                    last_index = len(rows) - 1
                    continue

            if last_index is not None and any(ch.isalpha() for ch in line):
                rows[last_index]["descricao"] = normalize_text(
                    f"{rows[last_index]['descricao']} {line}"
                )

        return finalize_records(rows)
