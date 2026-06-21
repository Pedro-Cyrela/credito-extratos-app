from __future__ import annotations

import logging
import re

import pandas as pd

from ..utils import fold_text, normalize_text, parse_brl_number
from .base import build_record, empty_transactions_df, finalize_records

logger = logging.getLogger(__name__)

# Limites de coluna medidos em coordenada x das palavras extraídas pelo pdfplumber
_DATE_X_MAX = 190
_DESC_X_MIN = 190
_DESC_X_MAX = 355
_CREDIT_X_MIN = 355
_CREDIT_X_MAX = 415
_DEBIT_X_MIN = 415
_DEBIT_X_MAX = 520

_DATE_PATTERN = re.compile(r"^\d{2}/\d{2}$")

# Linhas internas que não representam movimentação real do cliente
_NOISE_PREFIXES = (
    "saldo aplic aut mais",
    "apl aplic aut mais",
    "res aplic aut mais",
    "rend pago aplic aut mais",
    "saldo anterior",
    "saldo em c",
    "saldo final",
    "totalizador",
)

# Prefixos de linha que marcam fim da seção de movimentação
_SECTION_END_PREFIXES = (
    "totalizador de aplic",
    "conta corrente|aplic",
    "conta corrente |aplic",
    "conta corrente|cheque",
    "conta corrente |cheque",
    "conta corrente|pacote",
    "conta corrente |pacote",
    # rodapé repetido em cada página: "... Menu Conta Corrente > Extrato Mensal 428149 ..."
    "conta corrente > extrato",
)


def _words_in_x(words: list[dict], x_min: float, x_max: float) -> list[dict]:
    return [w for w in words if x_min <= w["x0"] < x_max]


def _words_before_x(words: list[dict], x_max: float) -> list[dict]:
    return [w for w in words if w["x0"] < x_max]


def _text_of(words: list[dict]) -> str:
    return normalize_text(" ".join(w["text"] for w in words))


def _group_by_line(words: list[dict], y_tol: int = 4) -> list[list[dict]]:
    """Agrupa palavras em linhas pela coordenada vertical (top)."""
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[list[dict]] = [[sorted_words[0]]]
    for word in sorted_words[1:]:
        if abs(word["top"] - lines[-1][-1]["top"]) <= y_tol:
            lines[-1].append(word)
        else:
            lines.append([word])
    return lines


def _is_table_header(words: list[dict]) -> bool:
    """Retorna True se a linha é o cabeçalho de colunas da movimentação."""
    desc_text = fold_text(_text_of(_words_in_x(words, _DESC_X_MIN, _DESC_X_MAX)))
    credit_text = fold_text(_text_of(_words_in_x(words, _CREDIT_X_MIN, _CREDIT_X_MAX)))
    debit_text = fold_text(_text_of(_words_in_x(words, _DEBIT_X_MIN, _DEBIT_X_MAX)))
    return (
        "descri" in desc_text
        and "entr" in credit_text
        and "sa" in debit_text
    )


def _parse_page_words(
    page_words: list[dict],
    current_date: pd.Timestamp | None,
    source_file: str,
    year: int,
) -> tuple[list[dict], pd.Timestamp | None]:
    """Extrai transações de uma página usando coordenadas de palavra.

    Retorna (lista de registros, data corrente atualizada).
    """
    rows: list[dict] = []
    lines = _group_by_line(page_words)
    in_table = False

    for line_words in lines:
        if not in_table:
            if _is_table_header(line_words):
                in_table = True
            continue

        desc_words = _words_in_x(line_words, _DESC_X_MIN, _DESC_X_MAX)
        date_words = _words_before_x(line_words, _DATE_X_MAX)
        credit_words = _words_in_x(line_words, _CREDIT_X_MIN, _CREDIT_X_MAX)
        debit_words = _words_in_x(line_words, _DEBIT_X_MIN, _DEBIT_X_MAX)

        desc_text = _text_of(desc_words)
        if not desc_text:
            continue

        desc_folded = fold_text(desc_text)

        # Detecta fim da seção de movimentação
        if any(desc_folded.startswith(p) for p in _SECTION_END_PREFIXES):
            break

        # Descarta linhas de ruído interno (saldo Aplic Aut Mais, etc.)
        if any(desc_folded.startswith(p) for p in _NOISE_PREFIXES):
            continue

        # Atualiza data corrente se a linha tem prefixo DD/MM
        for w in date_words:
            if _DATE_PATTERN.match(w["text"]):
                day_str, month_str = w["text"].split("/")
                try:
                    current_date = pd.Timestamp(
                        year=year, month=int(month_str), day=int(day_str)
                    ).normalize()
                except ValueError:
                    pass
                break

        if current_date is None:
            continue

        credit_raw = _text_of(credit_words)
        debit_raw = _text_of(debit_words)

        credit_val = parse_brl_number(credit_raw) if credit_raw else None
        debit_val = parse_brl_number(debit_raw) if debit_raw else None

        # Precisa de pelo menos um valor para ser uma transação
        if credit_val is None and debit_val is None:
            continue

        if credit_val is not None and abs(credit_val) > 0:
            rows.append(
                build_record(
                    dt=current_date,
                    desc=desc_text,
                    amount=abs(float(credit_val)),
                    raw_amount_text=credit_raw,
                    detected_as_credit=True,
                    detected_as_debit=False,
                    source_file=source_file,
                )
            )

        if debit_val is not None and abs(debit_val) > 0:
            rows.append(
                build_record(
                    dt=current_date,
                    desc=desc_text,
                    amount=-abs(float(debit_val)),
                    raw_amount_text=debit_raw,
                    detected_as_credit=False,
                    detected_as_debit=True,
                    source_file=source_file,
                )
            )

    return rows, current_date


def _extract_year(text_pages: list[str]) -> int:
    """Extrai o ano de referência do cabeçalho do extrato."""
    for page in text_pages[:2]:
        match = re.search(r"\b(20\d{2})\b", page)
        if match:
            return int(match.group(1))
    return pd.Timestamp.now().year


class ItauMensalParser:
    name = "itau_mensal"

    def matches(self, text_pages: list[str]) -> bool:
        sample = fold_text("\n".join(text_pages[:2]))
        return (
            "extrato mensal" in sample
            and "entradas" in sample
            and "saidas" in sample
            and ("ag " in sample or "agencia" in sample)
        )

    def parse(
        self,
        text_pages: list[str],
        source_file: str,
        word_pages: list[list[dict]] | None = None,
    ) -> pd.DataFrame:
        if not self.matches(text_pages) or not word_pages:
            return empty_transactions_df()

        year = _extract_year(text_pages)
        all_rows: list[dict] = []
        current_date: pd.Timestamp | None = None

        for page_words in word_pages:
            page_rows, current_date = _parse_page_words(
                page_words, current_date, source_file, year
            )
            all_rows.extend(page_rows)

        return finalize_records(all_rows)
