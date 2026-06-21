from __future__ import annotations

import logging
import re

import pandas as pd

from ..utils import fold_text, normalize_text, parse_brl_number, parse_date
from .base import build_record, empty_transactions_df, finalize_records

logger = logging.getLogger(__name__)

# DD/MM/YYYY Saldo do dia R$ X,XX  — marca início de grupo de data
_DATE_SALDO_PATTERN = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{4})\s+saldo\s+do\s+dia\b",
    flags=re.IGNORECASE,
)

# <descrição> + R$ X,XX  ou  <descrição> - R$ X,XX
_TRANSACTION_PATTERN = re.compile(
    r"^(?P<desc>.+?)\s+(?P<sign>[+\-])\s+R\$\s*(?P<amount>[\d.,]+)\s*$",
    flags=re.IGNORECASE,
)

_NOISE_PREFIXES = (
    "cora scfi",
    "ouvidoria",
    "extrato gerado",
    "agencia:",
    "agencia",
    "cnpj",
    "saldo inicial",
    "saldo final",
    "total de entradas",
    "total de saidas",
    "transacoes",
)


def _is_noise(line: str) -> bool:
    folded = fold_text(line)
    if not folded:
        return True
    # cabeçalho: nome da empresa (linha só com texto sem dígito monetário e curta)
    for prefix in _NOISE_PREFIXES:
        if folded.startswith(prefix):
            return True
    # linha "pag X de Y" no rodapé
    if re.search(r"\bpag\s+\d+\s+de\s+\d+\b", folded):
        return True
    return False


class CoraParser:
    name = "cora"

    def matches(self, text_pages: list[str]) -> bool:
        sample = fold_text("\n".join(text_pages[:3]))
        return "cora scfi" in sample

    def parse(
        self,
        text_pages: list[str],
        source_file: str,
        word_pages: list[list[dict]] | None = None,
    ) -> pd.DataFrame:
        if not self.matches(text_pages):
            return empty_transactions_df()

        rows: list[dict] = []
        current_date: pd.Timestamp | None = None

        for page_text in text_pages:
            for raw_line in page_text.splitlines():
                line = normalize_text(raw_line)
                if not line:
                    continue

                # linha de data-grupo: extrai e propaga data
                date_match = _DATE_SALDO_PATTERN.match(line)
                if date_match:
                    current_date = parse_date(date_match.group("date"))
                    continue

                if _is_noise(line):
                    continue

                if current_date is None:
                    continue

                tx_match = _TRANSACTION_PATTERN.match(line)
                if not tx_match:
                    continue

                raw_amount = tx_match.group("amount")
                amount = parse_brl_number(raw_amount)
                if amount is None:
                    continue

                sign = tx_match.group("sign")
                is_credit = sign == "+"
                is_debit = sign == "-"
                signed_amount = float(amount) if is_credit else -float(amount)
                raw_amount_text = f"{sign} R$ {raw_amount}"

                desc = normalize_text(tx_match.group("desc"))

                rows.append(
                    build_record(
                        dt=current_date,
                        desc=desc,
                        amount=signed_amount,
                        raw_amount_text=raw_amount_text,
                        detected_as_credit=is_credit,
                        detected_as_debit=is_debit,
                        source_file=source_file,
                    )
                )

        return finalize_records(rows)
