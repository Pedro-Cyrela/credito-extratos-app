from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

import pandas as pd

from ..credit_classifier import classify_by_score, score_transaction
from ..utils import infer_counterparty, month_label

logger = logging.getLogger(__name__)


TRANSACTION_COLUMNS = [
    "data",
    "mes_ref",
    "descricao",
    "origem_identificada",
    "valor",
    "tipo_inferido",
    "status_inicial",
    "motivo_inicial",
    "score",
    "arquivo_origem",
]


PT_MONTHS = {
    "JAN": 1,
    "FEV": 2,
    "MAR": 3,
    "ABR": 4,
    "MAI": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SET": 9,
    "OUT": 10,
    "NOV": 11,
    "DEZ": 12,
}


def empty_transactions_df() -> pd.DataFrame:
    return pd.DataFrame(columns=TRANSACTION_COLUMNS)


def build_record(
    dt: pd.Timestamp,
    desc: str,
    amount: float,
    raw_amount_text: str,
    detected_as_credit: bool,
    detected_as_debit: bool,
    source_file: str,
) -> dict:
    has_plus_sign = "+" in raw_amount_text
    has_minus_sign = "-" in raw_amount_text

    score = score_transaction(
        description=desc,
        amount=amount,
        detected_as_credit=detected_as_credit,
        detected_as_debit=detected_as_debit,
        has_plus_sign=has_plus_sign,
        has_minus_sign=has_minus_sign,
    )
    classification = classify_by_score(score)

    return {
        "data": dt.normalize(),
        "mes_ref": month_label(dt),
        "descricao": desc,
        "origem_identificada": infer_counterparty(desc),
        "valor": abs(amount) if classification.status != "desconsiderado" and amount > 0 else amount,
        "tipo_inferido": "credito" if amount > 0 else "debito",
        "status_inicial": classification.status,
        "motivo_inicial": classification.reason,
        "score": classification.score,
        "arquivo_origem": source_file,
    }


def finalize_records(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return empty_transactions_df()
    result = pd.DataFrame(rows)
    result["data"] = pd.to_datetime(result["data"], errors="coerce")
    return result.sort_values(["data", "descricao"]).reset_index(drop=True)


@runtime_checkable
class BankParser(Protocol):
    """Contract for a bank-specific statement parser.

    A parser is autocontained: it owns its detection (``matches``) and its
    extraction logic (``parse``). The registry calls them in order until one
    matches.
    """

    name: str

    def matches(self, text_pages: list[str]) -> bool: ...

    def parse(
        self,
        text_pages: list[str],
        source_file: str,
        word_pages: list[list[dict]] | None = None,
    ) -> pd.DataFrame: ...
