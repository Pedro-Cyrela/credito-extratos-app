from __future__ import annotations

import logging
import re

import pandas as pd

from ..utils import fold_text, normalize_text, parse_brl_number, parse_date
from .base import build_record, empty_transactions_df, finalize_records

logger = logging.getLogger(__name__)


BB_MAIN_ROW_PATTERN = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<middle>.+?)\s+"
    r"(?P<valor>\d{1,3}(?:\.\d{3})*,\d{2})\s+\((?P<sign>[+-])\)\s*$",
    flags=re.IGNORECASE,
)
BB_DETAIL_ROW_PATTERN = re.compile(r"^\d{2}/\d{2}\s+\d{2}:\d{2}\b")

_BB_KNOWN_CATEGORIES = (
    "recebimento de proventos",
    "compra com cartao",
    "aplicacao poupanca",
    "pagamento de boleto",
    "pagamento conta luz",
    "pgto conta luz",
    "pagamento conta agua",
    "pgto conta agua",
    "pagamento conta gas",
    "pgto conta gas",
    "pgto conta telefone",
    "pix - enviado",
    "pix - recebido",
    "bb rende facil",
    "rende facil",
    "saldo anterior",
)


def _is_category_line(folded_line: str) -> bool:
    if not folded_line:
        return False
    if folded_line.startswith("saldo do dia") or folded_line.startswith("lançamentos"):
        return True
    return folded_line in _BB_KNOWN_CATEGORIES or folded_line.startswith(("pgto ", "pix -"))


def _parse_middle(middle: str) -> tuple[str | None, str | None, str]:
    tokens = [t for t in middle.split() if t]
    lote = tokens[0] if tokens and tokens[0].isdigit() else None
    documento = None
    start = 0
    if lote is not None:
        start = 1
        if len(tokens) > 1 and tokens[1].isdigit():
            documento = tokens[1]
            start = 2
    historico = " ".join(tokens[start:]).strip()
    return lote, documento, historico


class BancoBrasilParser:
    name = "banco_brasil"

    def matches(self, text_pages: list[str]) -> bool:
        sample = "\n".join(text_pages[:2])
        folded = fold_text(sample)
        return (
            "extrato de conta corrente" in folded
            and "lancamentos" in folded
            and "dia lote documento historico valor" in folded
        )

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

        rows: list[dict] = []
        last_index: int | None = None
        pending_prefixes: list[str] = []

        for line in lines:
            folded = fold_text(line)
            if not folded:
                continue

            if (
                folded.startswith("saldo do dia")
                or folded.startswith("lançamentos")
                or folded.startswith("dia lote")
            ):
                continue

            if folded == "rende facil" and last_index is not None:
                rows[last_index]["descricao"] = normalize_text(
                    f"{rows[last_index]['descricao']} {line}"
                )
                continue

            main_match = BB_MAIN_ROW_PATTERN.match(line)
            if main_match:
                _, _, historico = _parse_middle(main_match.group("middle"))
                historico = normalize_text(historico)

                dt = parse_date(main_match.group("date"))
                valor = parse_brl_number(main_match.group("valor"))
                if dt is None or valor is None:
                    last_index = None
                    continue

                sign = main_match.group("sign")
                amount = abs(float(valor)) if sign == "+" else -abs(float(valor))

                desc_parts = [*pending_prefixes]
                pending_prefixes = []
                if historico:
                    desc_parts.append(historico)
                description = normalize_text(" ".join(desc_parts)) or historico
                if fold_text(description).startswith("saldo anterior"):
                    last_index = None
                    continue

                rows.append(
                    build_record(
                        dt=dt,
                        desc=description,
                        amount=amount,
                        raw_amount_text=main_match.group("valor"),
                        detected_as_credit=sign == "+",
                        detected_as_debit=sign == "-",
                        source_file=source_file,
                    )
                )
                last_index = len(rows) - 1
                continue

            if _is_category_line(folded):
                pending_prefixes.append(line)
                continue

            if last_index is not None:
                if BB_DETAIL_ROW_PATTERN.match(line) or any(ch.isalpha() for ch in line):
                    rows[last_index]["descricao"] = normalize_text(
                        f"{rows[last_index]['descricao']} {line}"
                    )

        return finalize_records(rows)
