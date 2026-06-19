from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

from ..utils import (
    clean_column_name,
    extract_amount_matches,
    normalize_text,
    parse_date,
)
from .base import build_record, empty_transactions_df, finalize_records

logger = logging.getLogger(__name__)


CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "column_aliases.json"
ALIASES = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _best_column(columns: list[str], group: str, threshold: int = 74) -> str | None:
    alias_list = [clean_column_name(alias) for alias in ALIASES.get(group, [])]
    best_name = None
    best_score = threshold

    for col in columns:
        col_clean = clean_column_name(col)
        if col_clean in alias_list:
            return col
        for alias in alias_list:
            score = fuzz.partial_ratio(col_clean, alias)
            if score >= best_score:
                best_score = score
                best_name = col
    return best_name


def _prepare_candidate_df(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    prepared.columns = [normalize_text(c) or f"col_{i}" for i, c in enumerate(prepared.columns)]
    prepared = prepared.replace({"": pd.NA})
    prepared = prepared.dropna(how="all").copy()
    return prepared


def _date_ratio(series: pd.Series) -> float:
    sample = [value for value in series.dropna().astype(str).head(12).tolist() if normalize_text(value)]
    if not sample:
        return 0.0
    return sum(parse_date(value) is not None for value in sample) / len(sample)


def _amount_ratio(series: pd.Series) -> float:
    sample = [value for value in series.dropna().astype(str).head(12).tolist() if normalize_text(value)]
    if not sample:
        return 0.0
    return sum(bool(extract_amount_matches(value)) for value in sample) / len(sample)


def _text_score(series: pd.Series) -> float:
    sample = [normalize_text(value) for value in series.dropna().astype(str).head(12).tolist()]
    if not sample:
        return 0.0
    alpha_rows = [value for value in sample if re.search(r"[A-Za-zÀ-ÿ]", value)]
    if not alpha_rows:
        return 0.0
    return sum(len(value) for value in alpha_rows) / len(alpha_rows)


def _resolve_columns(df: pd.DataFrame) -> dict[str, str | None]:
    columns = list(df.columns)
    date_col = _best_column(columns, "date")
    desc_col = _best_column(columns, "description")
    credit_col = _best_column(columns, "credit")
    debit_col = _best_column(columns, "debit")
    value_col = _best_column(columns, "value")
    balance_col = _best_column(columns, "balance")

    if not date_col:
        date_scores = {column: _date_ratio(df[column]) for column in columns}
        date_col = max(date_scores, key=date_scores.get) if date_scores else None
        if date_col and date_scores[date_col] < 0.45:
            date_col = None

    if not desc_col:
        text_scores = {
            column: _text_score(df[column])
            for column in columns
            if column != date_col and _amount_ratio(df[column]) < 0.7
        }
        desc_col = max(text_scores, key=text_scores.get) if text_scores else None

    numeric_candidates = [
        column
        for column in columns
        if column not in {date_col, desc_col} and _amount_ratio(df[column]) >= 0.45
    ]

    if not value_col and len(numeric_candidates) == 1:
        value_col = numeric_candidates[0]

    if not balance_col and len(numeric_candidates) >= 2:
        balance_col = numeric_candidates[-1]

    if not value_col and len(numeric_candidates) >= 2:
        non_balance_candidates = [column for column in numeric_candidates if column != balance_col]
        value_col = non_balance_candidates[0] if non_balance_candidates else numeric_candidates[0]

    return {
        "date": date_col,
        "description": desc_col,
        "credit": credit_col,
        "debit": debit_col,
        "value": value_col,
        "balance": balance_col,
    }


def _select_amount_match(cell_value: object):
    matches = extract_amount_matches(cell_value)
    return matches[0] if matches else None


def _resolve_amount(
    row: pd.Series, mapping: dict[str, str | None]
) -> tuple[float | None, str, bool, bool]:
    credit_match = _select_amount_match(row.get(mapping["credit"])) if mapping["credit"] else None
    debit_match = _select_amount_match(row.get(mapping["debit"])) if mapping["debit"] else None
    generic_match = _select_amount_match(row.get(mapping["value"])) if mapping["value"] else None

    if credit_match and abs(credit_match.value) > 0:
        return abs(float(credit_match.value)), credit_match.text, True, False

    if debit_match and abs(debit_match.value) > 0:
        return -abs(float(debit_match.value)), debit_match.text, False, True

    if generic_match and abs(generic_match.value) > 0:
        detected_as_credit = generic_match.explicit_credit or (
            generic_match.value > 0 and not generic_match.explicit_debit
        )
        detected_as_debit = generic_match.explicit_debit or generic_match.value < 0
        amount = float(generic_match.value)
        if detected_as_debit and amount > 0:
            amount = -amount
        if detected_as_credit and amount < 0:
            amount = abs(amount)
        return amount, generic_match.text, detected_as_credit, detected_as_debit

    return None, "", False, False


def parse_transaction_tables(dataframes: list[pd.DataFrame], source_file: str) -> pd.DataFrame:
    all_rows: list[dict] = []

    for raw_df in dataframes:
        df = _prepare_candidate_df(raw_df)
        if df.empty:
            continue

        mapping = _resolve_columns(df)
        date_col = mapping["date"]
        desc_col = mapping["description"]
        if not date_col or not desc_col:
            continue

        for _, row in df.iterrows():
            dt = parse_date(row.get(date_col))
            desc = normalize_text(row.get(desc_col))
            if dt is None or not desc:
                continue

            amount, raw_amount_text, detected_as_credit, detected_as_debit = _resolve_amount(
                row, mapping
            )
            if amount is None:
                continue

            all_rows.append(
                build_record(
                    dt=dt,
                    desc=desc,
                    amount=amount,
                    raw_amount_text=raw_amount_text,
                    detected_as_credit=detected_as_credit,
                    detected_as_debit=detected_as_debit,
                    source_file=source_file,
                )
            )

    if not all_rows:
        return empty_transactions_df()

    return finalize_records(all_rows)
