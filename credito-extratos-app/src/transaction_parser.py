from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

from .credit_classifier import classify_by_score, score_transaction
from .utils import (
    clean_column_name,
    extract_amount_matches,
    infer_counterparty,
    month_label,
    normalize_text,
    parse_date,
)


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "column_aliases.json"
ALIASES = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
DATE_PREFIX_PATTERN = re.compile(r"^(?P<data>\d{2}[/-]\d{2}[/-]\d{2,4})\b")
NUBANK_DAY_PATTERN = re.compile(
    r"^(?P<day>\d{2})\s+(?P<month>[A-ZÇ]{3})\s+(?P<year>\d{4})\s+Total de entradas\s+\+\s*(?P<amount>.+)$",
    flags=re.IGNORECASE | re.MULTILINE,
)
NUBANK_TOTAL_OUT_PATTERN = re.compile(
    r"^Total de sa[ií]das\s+-\s*(?P<amount>.+)$",
    flags=re.IGNORECASE,
)
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
NUBANK_SKIP_PATTERNS = [
    re.compile(pattern, flags=re.IGNORECASE)
    for pattern in [
        r"^Movimenta[cç][õo]es$",
        r"^Saldo inicial\b",
        r"^Saldo final do per[ií]odo\b",
        r"^Rendimento l[ií]quido\b",
        r"^Tem alguma d[uú]vida\?",
        r"^metropolitanas\)",
        r"^Caso a solu[cç][aã]o fornecida",
        r"^dispon[ií]veis em nubank\.com\.br",
        r"^Extrato gerado dia",
        r"^CPF ",
        r"^\d{6,}-\d{1,2}$",
        r"^\d{2} DE [A-ZÇ]+ DE \d{4} a \d{2} DE [A-ZÇ]+ DE \d{4}\b",
    ]
]


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


def _empty_transactions_df() -> pd.DataFrame:
    return pd.DataFrame(columns=TRANSACTION_COLUMNS)


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


def _resolve_amount(row: pd.Series, mapping: dict[str, str | None]) -> tuple[float | None, str, bool, bool]:
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


def _build_record(
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

            amount, raw_amount_text, detected_as_credit, detected_as_debit = _resolve_amount(row, mapping)
            if amount is None:
                continue

            all_rows.append(
                _build_record(
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
        return _empty_transactions_df()

    result = pd.DataFrame(all_rows)
    result["data"] = pd.to_datetime(result["data"], errors="coerce")
    return result.sort_values(["data", "descricao"]).reset_index(drop=True)


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

    return _build_record(
        dt=dt,
        desc=desc,
        amount=amount,
        raw_amount_text=amount_match.text,
        detected_as_credit=detected_as_credit,
        detected_as_debit=detected_as_debit,
        source_file=source_file,
    )


def _looks_like_nubank_statement(text_pages: list[str]) -> bool:
    sample = "\n".join(text_pages[:3])
    lowered = sample.casefold()
    has_block_headers = bool(NUBANK_DAY_PATTERN.search(sample)) and "total de saídas" in lowered
    has_identity_markers = "movimentações" in lowered or "nubank.com.br" in lowered or "saldo inicial" in lowered
    return has_block_headers and has_identity_markers


def _is_nubank_skip_line(line: str) -> bool:
    return any(pattern.search(line) for pattern in NUBANK_SKIP_PATTERNS)


def _parse_nubank_day(line: str) -> pd.Timestamp | None:
    match = NUBANK_DAY_PATTERN.match(line)
    if not match:
        return None

    month_key = normalize_text(match.group("month")).upper()
    month = PT_MONTHS.get(month_key)
    if not month:
        return None

    return pd.Timestamp(
        year=int(match.group("year")),
        month=month,
        day=int(match.group("day")),
    ).normalize()


def _parse_nubank_transaction_line(
    line: str,
    current_date: pd.Timestamp,
    current_section: str,
    source_file: str,
) -> dict | None:
    amount_matches = extract_amount_matches(line)
    if not amount_matches:
        return None

    amount_match = amount_matches[-1]
    desc = normalize_text(line[:amount_match.start])
    desc = re.sub(r"\s*-\s*$", "", desc).strip()
    if not desc:
        return None

    if current_section == "entradas":
        amount = abs(float(amount_match.value))
        detected_as_credit = True
        detected_as_debit = False
    else:
        amount = -abs(float(amount_match.value))
        detected_as_credit = False
        detected_as_debit = True

    return _build_record(
        dt=current_date,
        desc=desc,
        amount=amount,
        raw_amount_text=amount_match.text,
        detected_as_credit=detected_as_credit,
        detected_as_debit=detected_as_debit,
        source_file=source_file,
    )


def _parse_nubank_transactions(text_pages: list[str], source_file: str) -> pd.DataFrame:
    if not _looks_like_nubank_statement(text_pages):
        return _empty_transactions_df()

    current_date: pd.Timestamp | None = None
    current_section: str | None = None
    rows: list[dict] = []

    for page_text in text_pages:
        for raw_line in page_text.splitlines():
            line = normalize_text(raw_line)
            if not line or _is_nubank_skip_line(line):
                continue

            day_date = _parse_nubank_day(line)
            if day_date is not None:
                current_date = day_date
                current_section = "entradas"
                continue

            if NUBANK_TOTAL_OUT_PATTERN.match(line):
                if current_date is not None:
                    current_section = "saidas"
                continue

            if current_date is None or current_section is None:
                continue

            record = _parse_nubank_transaction_line(
                line=line,
                current_date=current_date,
                current_section=current_section,
                source_file=source_file,
            )
            if record:
                rows.append(record)

    if not rows:
        return _empty_transactions_df()

    result = pd.DataFrame(rows)
    result["data"] = pd.to_datetime(result["data"], errors="coerce")
    return result.sort_values(["data", "descricao"]).reset_index(drop=True)


def parse_transactions_from_text(text_pages: list[str], source_file: str) -> pd.DataFrame:
    generic_rows: list[dict] = []

    for page_text in text_pages:
        for line in _merge_multiline_records(page_text):
            record = _parse_text_line(line, source_file)
            if record:
                generic_rows.append(record)

    frames: list[pd.DataFrame] = []
    if generic_rows:
        generic_df = pd.DataFrame(generic_rows)
        generic_df["data"] = pd.to_datetime(generic_df["data"], errors="coerce")
        frames.append(generic_df)

    nubank_df = _parse_nubank_transactions(text_pages, source_file)
    if not nubank_df.empty:
        frames.append(nubank_df)

    if not frames:
        return _empty_transactions_df()

    result = pd.concat(frames, ignore_index=True)
    return result.sort_values(["data", "descricao"]).reset_index(drop=True)


def deduplicate_transactions(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    deduped = df.drop_duplicates(
        subset=["data", "descricao", "valor", "arquivo_origem"],
        keep="first",
    ).reset_index(drop=True)
    return deduped
