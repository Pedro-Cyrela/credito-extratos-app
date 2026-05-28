from __future__ import annotations

import logging
import re

import pandas as pd

from ..utils import fold_text, normalize_text, parse_brl_number
from .base import build_record, empty_transactions_df, finalize_records

logger = logging.getLogger(__name__)


C6_MONTH_HEADER_PATTERN = re.compile(
    r"^(?P<month>[A-Za-zÀ-ÿç]+)\s+(?P<year>\d{4})\s+\(\s*(?P<start>\d{2}/\d{2}/\d{4})\s*-\s*(?P<end>\d{2}/\d{2}/\d{4})\s*\)",
    flags=re.IGNORECASE,
)
C6_TRANSACTION_PATTERN = re.compile(
    r"^(?P<posted>\d{2}/\d{2})\s+(?P<booked>\d{2}/\d{2})\s+(?P<kind>.+?)\s+(?P<amount>[+\-]?R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}|[+\-]?R\$\s*\d+,\d{2})$",
    flags=re.IGNORECASE,
)


def _parse_transaction_date(value: str, section_year: int) -> pd.Timestamp | None:
    match = re.fullmatch(r"(?P<day>\d{2})/(?P<month>\d{2})", normalize_text(value))
    if not match:
        return None

    try:
        return pd.Timestamp(
            year=section_year,
            month=int(match.group("month")),
            day=int(match.group("day")),
        ).normalize()
    except ValueError:
        return None


def _is_noise_line(line: str) -> bool:
    folded = fold_text(line)
    return (
        not folded
        or folded in {"data data", "tipo descricao valor", "lancamento contabil"}
        or folded.startswith("saldo do dia")
        or folded == "sem lancamentos no mes"
        or folded.startswith("informacoes sujeitas a alteracao")
        or folded.startswith("atendimento 24 horas")
        or folded.startswith("chat para clientes")
        or folded.startswith("capitais e regioes")
        or folded.startswith("no app do c6 bank")
        or folded.startswith("demais localidades")
        or folded.startswith("abra uma conta para")
        or folded.startswith("sac")
        or folded.startswith("voce e sua empresa")
        or folded.startswith("whatsapp 24 horas")
        or folded.startswith("baixe o app pelo qr code")
        or folded.startswith("ouvidoria")
        or re.fullmatch(r"[\d()\s-]{8,}", folded) is not None
    )


class C6Parser:
    name = "c6"

    def matches(self, text_pages: list[str]) -> bool:
        sample = "\n".join(text_pages[:3])
        folded = fold_text(sample)
        return (
            "extrato exportado no dia" in folded
            and "extrato periodo" in folded
            and "data data tipo descricao valor" in folded
        )

    def parse(
        self,
        text_pages: list[str],
        source_file: str,
        word_pages: list[list[dict]] | None = None,
    ) -> pd.DataFrame:
        if not self.matches(text_pages):
            return empty_transactions_df()

        rows: list[dict] = []
        current_year: int | None = None

        for page_text in text_pages:
            for raw_line in page_text.splitlines():
                line = normalize_text(raw_line)
                if not line:
                    continue

                month_match = C6_MONTH_HEADER_PATTERN.match(line)
                if month_match:
                    current_year = int(month_match.group("year"))
                    continue

                if _is_noise_line(line):
                    continue

                match = C6_TRANSACTION_PATTERN.match(line)
                if not match or current_year is None:
                    continue

                dt = _parse_transaction_date(match.group("posted"), current_year)
                amount = parse_brl_number(match.group("amount"))
                if dt is None or amount is None:
                    continue

                rows.append(
                    build_record(
                        dt=dt,
                        desc=normalize_text(match.group("kind")),
                        amount=float(amount),
                        raw_amount_text=match.group("amount"),
                        detected_as_credit=float(amount) > 0,
                        detected_as_debit=float(amount) < 0,
                        source_file=source_file,
                    )
                )

        return finalize_records(rows)
