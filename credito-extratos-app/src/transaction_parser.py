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
    fold_text,
    infer_counterparty,
    month_label,
    normalize_text,
    parse_brl_number,
    parse_date,
)


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "column_aliases.json"
ALIASES = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
DATE_PREFIX_PATTERN = re.compile(r"^(?P<data>\d{2}[/-]\d{2}[/-]\d{2,4})\b")
US_AMOUNT_TOKEN = r"[-+]?\$?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}"
FOREIGN_DEPOSIT_ROW_PATTERN = re.compile(
    rf"^(?P<date>\d{{2}}/\d{{2}}/\d{{2}})\s+(?P<description>.+?)\s+(?P<amount>{US_AMOUNT_TOKEN})$",
    flags=re.IGNORECASE,
)
BRADESCO_ROW_PATTERN = re.compile(
    r"^(?:(?P<date>\d{2}/\d{2}/\d{4})\s+)?(?P<body>.*?)\s+"
    r"(?P<amount>-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2})\s+"
    r"(?P<balance>-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2})$"
)
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

FOREIGN_DEPOSIT_HEADINGS = {
    "deposits and other additions",
    "deposits and other additions - continued",
}


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


def _looks_like_foreign_deposit_statement(text_pages: list[str]) -> bool:
    sample = "\n".join(text_pages[:4])
    folded = fold_text(sample)
    return "deposits and other additions" in folded and "date description amount" in folded


def _is_foreign_deposit_heading(line: str) -> bool:
    return fold_text(line) in FOREIGN_DEPOSIT_HEADINGS


def _is_foreign_deposit_stop_line(line: str) -> bool:
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


def _foreign_deposit_partials_to_df(transactions: list[dict], source_file: str) -> pd.DataFrame:
    rows: list[dict] = []
    for transaction in transactions:
        desc = normalize_text(" ".join(transaction["desc_parts"]))
        if not desc:
            continue

        rows.append(
            _build_record(
                dt=transaction["dt"],
                desc=desc,
                amount=transaction["amount"],
                raw_amount_text=transaction["raw_amount_text"],
                detected_as_credit=True,
                detected_as_debit=False,
                source_file=source_file,
            )
        )

    if not rows:
        return _empty_transactions_df()

    result = pd.DataFrame(rows)
    result["data"] = pd.to_datetime(result["data"], errors="coerce")
    return result.sort_values(["data", "descricao"]).reset_index(drop=True)


def _parse_foreign_deposit_transactions(text_pages: list[str], source_file: str) -> pd.DataFrame:
    if not _looks_like_foreign_deposit_statement(text_pages):
        return _empty_transactions_df()

    transactions: list[dict] = []

    for page_text in text_pages:
        in_deposit_section = False

        for raw_line in page_text.splitlines():
            line = normalize_text(raw_line)
            if not line:
                continue

            if _is_foreign_deposit_heading(line):
                in_deposit_section = True
                continue

            if not in_deposit_section:
                continue

            if fold_text(line) == "date description amount":
                continue

            if _is_foreign_deposit_stop_line(line):
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

    return _foreign_deposit_partials_to_df(transactions, source_file)


def _looks_like_bradesco_statement(text_pages: list[str]) -> bool:
    sample = "\n".join(text_pages[:3])
    folded = fold_text(sample)
    return "bradesco celular" in folded and "data historico docto" in folded


def _iter_bradesco_table_lines(text_pages: list[str]) -> list[str]:
    lines: list[str] = []

    for page_text in text_pages:
        in_table = False
        for raw_line in page_text.splitlines():
            line = normalize_text(raw_line)
            if not line:
                continue

            folded = fold_text(line)
            if not in_table:
                if folded.startswith("data historico docto"):
                    in_table = True
                continue

            if folded.startswith("total "):
                break

            lines.append(line)

    return lines


def _parse_bradesco_numeric_line(line: str) -> dict | None:
    match = BRADESCO_ROW_PATTERN.match(line)
    if not match:
        return None

    amount = parse_brl_number(match.group("amount"))
    balance = parse_brl_number(match.group("balance"))
    if amount is None or balance is None:
        return None

    return {
        "date": match.group("date"),
        "body": normalize_text(match.group("body")),
        "amount": abs(float(amount)),
        "amount_text": match.group("amount"),
        "balance": float(balance),
    }


def _parse_bradesco_opening_balance_line(line: str) -> dict | None:
    match = re.match(
        r"^(?P<date>\d{2}/\d{2}/\d{4})\s+COD\.\s*LANC\.\s+\d+\s+"
        r"(?P<balance>-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2})$",
        line,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    balance = parse_brl_number(match.group("balance"))
    if balance is None:
        return None

    return {"date": match.group("date"), "balance": float(balance)}


def _clean_bradesco_description_body(value: str) -> str:
    text = normalize_text(value)
    text = re.sub(r"(?:^|\s)\d{1,10}$", "", text).strip()
    return text


def _is_bradesco_detail_line(line: str) -> bool:
    folded = fold_text(line)
    detail_prefixes = (
        "rem:",
        "des:",
        "bradesco ",
        "plus di",
        "max di",
        "cesta ",
        "cgmp",
    )
    return folded.startswith(detail_prefixes) or folded.startswith("'") or folded.startswith('"')


def _infer_bradesco_sign(
    previous_balance: float | None,
    balance: float,
    amount: float,
    description: str,
) -> tuple[float, bool, bool]:
    if previous_balance is not None:
        credit_delta = abs((previous_balance + amount) - balance)
        debit_delta = abs((previous_balance - amount) - balance)
        if min(credit_delta, debit_delta) <= 0.05:
            if credit_delta <= debit_delta:
                return amount, True, False
            return -amount, False, True

    folded = fold_text(description)
    if " rem:" in folded or folded.startswith("rem:"):
        return amount, True, False
    if " des:" in folded or folded.startswith("des:"):
        return -amount, False, True

    credit_terms = ("resgate", "recebimento", "inss", "pix celular")
    debit_terms = (
        "aplicacao",
        "pagto",
        "debito",
        "gastos",
        "conta de",
        "tarifa",
        "iof",
    )
    if any(term in folded for term in credit_terms):
        return amount, True, False
    if any(term in folded for term in debit_terms):
        return -amount, False, True

    return amount, True, False


def _bradesco_partials_to_df(transactions: list[dict], source_file: str) -> pd.DataFrame:
    rows: list[dict] = []

    for transaction in transactions:
        desc = normalize_text(" ".join(transaction["desc_parts"]))
        if not desc:
            continue

        rows.append(
            _build_record(
                dt=transaction["dt"],
                desc=desc,
                amount=transaction["amount"],
                raw_amount_text=transaction["raw_amount_text"],
                detected_as_credit=transaction["detected_as_credit"],
                detected_as_debit=transaction["detected_as_debit"],
                source_file=source_file,
            )
        )

    if not rows:
        return _empty_transactions_df()

    result = pd.DataFrame(rows)
    result["data"] = pd.to_datetime(result["data"], errors="coerce")
    return result.sort_values(["data", "descricao"]).reset_index(drop=True)


def _words_to_text(words: list[dict]) -> str:
    return normalize_text(" ".join(str(word.get("text", "")) for word in sorted(words, key=lambda w: float(w.get("x0", 0)))))


def _group_words_by_line(words: list[dict]) -> list[list[dict]]:
    grouped_rows: list[list[dict]] = []

    for word in sorted(words, key=lambda w: (float(w.get("top", 0)), float(w.get("x0", 0)))):
        top = float(word.get("top", 0))
        if not grouped_rows:
            grouped_rows.append([word])
            continue

        current_top = sum(float(item.get("top", 0)) for item in grouped_rows[-1]) / len(grouped_rows[-1])
        if abs(top - current_top) <= 2.2:
            grouped_rows[-1].append(word)
        else:
            grouped_rows.append([word])

    return grouped_rows


def _words_in_x_range(words: list[dict], x_start: float, x_end: float | None) -> list[dict]:
    selected: list[dict] = []
    for word in words:
        x0 = float(word.get("x0", 0))
        x1 = float(word.get("x1", x0))
        center = (x0 + x1) / 2
        if center < x_start:
            continue
        if x_end is not None and center >= x_end:
            continue
        selected.append(word)
    return selected


def _build_bradesco_word_rows(word_pages: list[list[dict]]) -> list[dict]:
    rows: list[dict] = []

    for page_words in word_pages:
        in_table = False
        for line_words in _group_words_by_line(page_words):
            text = _words_to_text(line_words)
            folded = fold_text(text)

            if not in_table:
                if folded.startswith("data historico docto"):
                    in_table = True
                continue

            if folded.startswith("total "):
                break

            row = {
                "text": text,
                "date": _words_to_text(_words_in_x_range(line_words, 0, 100)),
                "history": _words_to_text(_words_in_x_range(line_words, 100, 295)),
                "credit": _words_to_text(_words_in_x_range(line_words, 365, 440)),
                "debit": _words_to_text(_words_in_x_range(line_words, 440, 505)),
                "balance": _words_to_text(_words_in_x_range(line_words, 505, None)),
            }
            rows.append(row)

    return rows


def _parse_bradesco_word_amount(row: dict) -> tuple[float, str, bool, bool] | None:
    credit = parse_brl_number(row.get("credit"))
    debit = parse_brl_number(row.get("debit"))
    balance = parse_brl_number(row.get("balance"))
    if balance is None:
        return None

    if credit is not None and abs(float(credit)) > 0:
        return abs(float(credit)), normalize_text(row.get("credit")), True, False

    if debit is not None and abs(float(debit)) > 0:
        return -abs(float(debit)), normalize_text(row.get("debit")), False, True

    return None


def _parse_bradesco_transactions_from_words(word_pages: list[list[dict]], source_file: str) -> pd.DataFrame:
    if not word_pages:
        return _empty_transactions_df()

    rows = _build_bradesco_word_rows(word_pages)
    transactions: list[dict] = []
    pending_description: list[str] = []
    current_date: pd.Timestamp | None = None

    for index, row in enumerate(rows):
        row_date = parse_date(row.get("date"))
        if row_date is not None:
            current_date = row_date

        amount_info = _parse_bradesco_word_amount(row)
        history = normalize_text(row.get("history"))

        if amount_info is None:
            if "cod. lanc" in fold_text(history):
                pending_description.clear()
                continue

            if history:
                next_row = rows[index + 1] if index + 1 < len(rows) else {}
                next_is_numeric = _parse_bradesco_word_amount(next_row) is not None
                if transactions and (_is_bradesco_detail_line(history) or not next_is_numeric):
                    transactions[-1]["desc_parts"].append(history)
                else:
                    pending_description.append(history)
            continue

        if current_date is None:
            pending_description.clear()
            continue

        signed_amount, raw_amount_text, detected_as_credit, detected_as_debit = amount_info
        desc_parts = [*pending_description]
        if history:
            desc_parts.append(history)
        pending_description = []

        description = normalize_text(" ".join(desc_parts))
        if not description:
            continue

        transactions.append(
            {
                "dt": current_date,
                "desc_parts": desc_parts,
                "amount": signed_amount,
                "raw_amount_text": raw_amount_text,
                "detected_as_credit": detected_as_credit,
                "detected_as_debit": detected_as_debit,
            }
        )

    return _bradesco_partials_to_df(transactions, source_file)


def _parse_bradesco_transactions(
    text_pages: list[str],
    source_file: str,
    word_pages: list[list[dict]] | None = None,
) -> pd.DataFrame:
    if not _looks_like_bradesco_statement(text_pages):
        return _empty_transactions_df()

    word_result = _parse_bradesco_transactions_from_words(word_pages or [], source_file)
    if not word_result.empty:
        return word_result

    lines = _iter_bradesco_table_lines(text_pages)
    transactions: list[dict] = []
    pending_description: list[str] = []
    current_date: pd.Timestamp | None = None
    previous_balance: float | None = None

    for index, line in enumerate(lines):
        parsed = _parse_bradesco_numeric_line(line)

        if parsed is None:
            opening_balance = _parse_bradesco_opening_balance_line(line)
            if opening_balance is not None:
                current_date = parse_date(opening_balance["date"])
                previous_balance = opening_balance["balance"]
                pending_description.clear()
                continue

            next_line = lines[index + 1] if index + 1 < len(lines) else ""
            next_is_numeric = _parse_bradesco_numeric_line(next_line) is not None
            if transactions and (_is_bradesco_detail_line(line) or not next_is_numeric):
                transactions[-1]["desc_parts"].append(line)
            else:
                pending_description.append(line)
            continue

        if parsed["date"]:
            current_date = parse_date(parsed["date"])

        if current_date is None:
            pending_description.clear()
            previous_balance = parsed["balance"]
            continue

        amount = parsed["amount"]
        if amount == 0:
            pending_description.clear()
            previous_balance = parsed["balance"]
            continue

        body_description = _clean_bradesco_description_body(parsed["body"])
        desc_parts = [*pending_description]
        if body_description:
            desc_parts.append(body_description)
        pending_description = []

        description = normalize_text(" ".join(desc_parts))
        if not description:
            previous_balance = parsed["balance"]
            continue

        signed_amount, detected_as_credit, detected_as_debit = _infer_bradesco_sign(
            previous_balance=previous_balance,
            balance=parsed["balance"],
            amount=amount,
            description=description,
        )

        transactions.append(
            {
                "dt": current_date,
                "desc_parts": desc_parts,
                "amount": signed_amount,
                "raw_amount_text": parsed["amount_text"],
                "detected_as_credit": detected_as_credit,
                "detected_as_debit": detected_as_debit,
            }
        )
        previous_balance = parsed["balance"]

    return _bradesco_partials_to_df(transactions, source_file)


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


def parse_transactions_from_text(
    text_pages: list[str],
    source_file: str,
    word_pages: list[list[dict]] | None = None,
) -> pd.DataFrame:
    bradesco_df = _parse_bradesco_transactions(text_pages, source_file, word_pages=word_pages)
    if not bradesco_df.empty:
        return bradesco_df

    foreign_deposits_df = _parse_foreign_deposit_transactions(text_pages, source_file)
    if not foreign_deposits_df.empty:
        return foreign_deposits_df

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
