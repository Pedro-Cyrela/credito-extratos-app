from __future__ import annotations

import logging
import re

import pandas as pd

from ..utils import fold_text, normalize_text, parse_brl_number, parse_date
from .base import build_record, empty_transactions_df, finalize_records

logger = logging.getLogger(__name__)


BRADESCO_ROW_PATTERN = re.compile(
    r"^(?:(?P<date>\d{2}/\d{2}/\d{4})\s+)?(?P<body>.*?)\s+"
    r"(?P<amount>-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2})\s+"
    r"(?P<balance>-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2})$"
)


def _iter_table_lines(text_pages: list[str]) -> list[str]:
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


def _parse_numeric_line(line: str) -> dict | None:
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


def _parse_opening_balance_line(line: str) -> dict | None:
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


def _clean_description_body(value: str) -> str:
    text = normalize_text(value)
    text = re.sub(r"(?:^|\s)\d{1,10}$", "", text).strip()
    return text


def _is_detail_line(line: str) -> bool:
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


def _infer_sign(
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
                detected_as_credit=transaction["detected_as_credit"],
                detected_as_debit=transaction["detected_as_debit"],
                source_file=source_file,
            )
        )
    return finalize_records(rows)


def _words_to_text(words: list[dict]) -> str:
    return normalize_text(
        " ".join(str(word.get("text", "")) for word in sorted(words, key=lambda w: float(w.get("x0", 0))))
    )


def _group_words_by_line(words: list[dict]) -> list[list[dict]]:
    grouped_rows: list[list[dict]] = []

    for word in sorted(words, key=lambda w: (float(w.get("top", 0)), float(w.get("x0", 0)))):
        top = float(word.get("top", 0))
        if not grouped_rows:
            grouped_rows.append([word])
            continue

        current_top = sum(float(item.get("top", 0)) for item in grouped_rows[-1]) / len(
            grouped_rows[-1]
        )
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


def _build_word_rows(word_pages: list[list[dict]]) -> list[dict]:
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

            rows.append(
                {
                    "text": text,
                    "date": _words_to_text(_words_in_x_range(line_words, 0, 100)),
                    "history": _words_to_text(_words_in_x_range(line_words, 100, 295)),
                    "credit": _words_to_text(_words_in_x_range(line_words, 365, 440)),
                    "debit": _words_to_text(_words_in_x_range(line_words, 440, 505)),
                    "balance": _words_to_text(_words_in_x_range(line_words, 505, None)),
                }
            )

    return rows


def _parse_word_amount(row: dict) -> tuple[float, str, bool, bool] | None:
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


def _parse_from_words(word_pages: list[list[dict]], source_file: str) -> pd.DataFrame:
    if not word_pages:
        return empty_transactions_df()

    rows = _build_word_rows(word_pages)
    transactions: list[dict] = []
    pending_description: list[str] = []
    current_date: pd.Timestamp | None = None

    for index, row in enumerate(rows):
        row_date = parse_date(row.get("date"))
        if row_date is not None:
            current_date = row_date

        amount_info = _parse_word_amount(row)
        history = normalize_text(row.get("history"))

        if amount_info is None:
            if "cod. lanc" in fold_text(history):
                pending_description.clear()
                continue

            if history:
                next_row = rows[index + 1] if index + 1 < len(rows) else {}
                next_is_numeric = _parse_word_amount(next_row) is not None
                if transactions and (_is_detail_line(history) or not next_is_numeric):
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

    return _partials_to_df(transactions, source_file)


class BradescoParser:
    name = "bradesco"

    def matches(self, text_pages: list[str]) -> bool:
        sample = "\n".join(text_pages[:3])
        folded = fold_text(sample)
        return "bradesco celular" in folded and "data historico docto" in folded

    def parse(
        self,
        text_pages: list[str],
        source_file: str,
        word_pages: list[list[dict]] | None = None,
    ) -> pd.DataFrame:
        if not self.matches(text_pages):
            return empty_transactions_df()

        word_result = _parse_from_words(word_pages or [], source_file)
        if not word_result.empty:
            return word_result

        lines = _iter_table_lines(text_pages)
        transactions: list[dict] = []
        pending_description: list[str] = []
        current_date: pd.Timestamp | None = None
        previous_balance: float | None = None

        for index, line in enumerate(lines):
            parsed = _parse_numeric_line(line)

            if parsed is None:
                opening_balance = _parse_opening_balance_line(line)
                if opening_balance is not None:
                    current_date = parse_date(opening_balance["date"])
                    previous_balance = opening_balance["balance"]
                    pending_description.clear()
                    continue

                next_line = lines[index + 1] if index + 1 < len(lines) else ""
                next_is_numeric = _parse_numeric_line(next_line) is not None
                if transactions and (_is_detail_line(line) or not next_is_numeric):
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

            body_description = _clean_description_body(parsed["body"])
            desc_parts = [*pending_description]
            if body_description:
                desc_parts.append(body_description)
            pending_description = []

            description = normalize_text(" ".join(desc_parts))
            if not description:
                previous_balance = parsed["balance"]
                continue

            signed_amount, detected_as_credit, detected_as_debit = _infer_sign(
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

        return _partials_to_df(transactions, source_file)
