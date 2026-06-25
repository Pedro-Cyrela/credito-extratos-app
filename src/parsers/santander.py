"""Parser para o Extrato Consolidado Inteligente do Santander (PF).

Suporta PDFs que cobrem múltiplos meses (ex: jan/fev/mar/abr num único arquivo).
Lida com dois formatos de extração de texto pelo pdfplumber:
  - Espaçado  : palavras separadas normalmente (páginas "limpas")
  - Compactado: palavras coladas sem espaço (páginas com fontes não-padrão)
"""
from __future__ import annotations

import logging
import re

import pandas as pd

from ..utils import fold_text, normalize_text
from .base import build_record, empty_transactions_df, finalize_records

logger = logging.getLogger(__name__)

# ── Regex ────────────────────────────────────────────────────────────────────
# Valor monetário BR: 1.234,56 ou 234,56
_BR_VALUE = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")

# Linha inicia com data DD/MM (com ou sem espaço após)
_DATE_START = re.compile(r"^(\d{1,2})/(\d{2})\s*(.*)", re.DOTALL)

# Cabecalho de mes: "janeiro/2026" etc. O texto e normalizado antes
# da busca para evitar variacoes de acento/encoding em "marco".
_MONTH_YEAR_FOLDED = re.compile(
    r"\b(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|"
    r"setembro|outubro|novembro|dezembro)/(\d{4})",
    re.IGNORECASE,
)

# Linha que contém APENAS dígitos, ponto, vírgula, traço e espaço (linha de valor puro)
_VALUE_ONLY = re.compile(r"^[\-\d\.\,\s]+$")

# Linha com descrição + valor ao final, com saldo opcional depois
# Ex: "PIX ENVIADO Selma Silva 2.890,00-" ou "REMUNERACAO APLIC AUTO - 0,03 30.546,43"
_MIXED_LINE = re.compile(
    r"^(.+?)\s+(\d{1,3}(?:\.\d{3})*,\d{2})([-])?\s*(?:\d{1,3}(?:\.\d{3})*,\d{2})?$"
)

_PT_MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

# ── Seções que encerram a área de transações ─────────────────────────────────
_STOP_SECTIONS = (
    "saldos por periodo",
    "investimentos",
    "creditos contratados",
    "pacote de servicos",
    "programa de relacionamento",
    "limite da conta",
    "renda fixa",
    "cdb / rdb",
    "cdb/rdb",
    "rendimento bruto no periodo",
    "liquidez diaria",
    "aplicacao n",
    "perfil de risco",
)

# ── Prefixos de linhas que devem ser ignoradas ────────────────────────────────
_NOISE_PREFIXES = (
    "pagina:", "extrato_pf", "balp_", "loja:", "*valores",
    "extrato consolidado inteligente", "se voce nao tem", "sevoce",
    "caso voce queira", "para efeito do calculo",
    "caso o saldo devedor", "saldo devedor", "contratado,juros",
    "desconsidere esta", "conheca a nossa",
    "taxa de juros", "juros nao cobrados", "apos o 10", "o iof sempre",
    "nao caia no", "confira nossas", "utilize o cartao", "nunca informe",
    "crie senhas", "ative a autenticacao", "nao utilize redes",
    "nunca anote", "ao pagar um boleto", "nao aceite ajuda",
    "venha conhecer", "vivencie", "confira mais detalhes",
    "oferta sujeita", "para saber mais sobre as regras",
    "consulte sempre a quantidade", "transacoes excedentes",
    "desconfie", "so pague taxas", "atente-se ao visor",
    "sempre peca a sua via", "se quer saber mais dicas",
    "central de atendimento", "ouvidoria", "libras (sac",
    "de segunda", "todos os dias, 24h", "4004", "0800",
    "55 11", "acesse:", "data descricao", "n documento",
    "movimento (rs)", "saldo (rs)", "nome\n", "agencia\n",
    "fale conosco", "prezado", "protect", "informacao e a nossa",
    "sua seguranca e importante",
    "cet (custo efetivo", "para quem quer investir",
    "para quem considera", "o perfil de risco",
    "comparando seu perfil", "carteira atual",
    "perfil api", "balanceado", "conservador",
    "depositos a prazo", "corretora santander",
    "tempo de relacionamento",
    "80.000 a 149.999", "acima de 150.000",
    "valor da mensalidade", "status do debito",
    "dia de debito", "saques", "transf entre contas",
    "retirada no exterior", "ted atm", "ted pessoal",
    "extratos\n", "cheques\n", "outros servicos",
    "avisos impressos", "servico de courier", "aviso por celular",
    "pontuacao atual", "pontuacao anterior", "composicao da pontuacao",
    "produtos\n", "movimentacoes de conta",
)


def _is_noise(folded: str) -> bool:
    if not folded or len(folded) < 2:
        return True
    if folded.startswith("saldo em ") or "saldo anterior" in folded:
        return True
    # Número de agência/conta: "1745 01.000161-4"
    if re.match(r"^\d{4}\s+\d{2}\.\d{6}-\d$", folded):
        return True
    for prefix in _NOISE_PREFIXES:
        if folded.startswith(prefix):
            return True
    return False


def _is_stop_section(folded: str) -> bool:
    return any(folded.startswith(section) for section in _STOP_SECTIONS)


def _is_account_section(folded: str) -> bool:
    return folded == "conta corrente"


def _is_movement_heading(folded: str) -> bool:
    return folded in {"movimentacao", "movimentacoes"}


def _extract_month_year(line: str) -> tuple[int, int] | None:
    match = _MONTH_YEAR_FOLDED.search(fold_text(line))
    if not match:
        return None

    month = _PT_MONTHS.get(match.group(1).lower())
    if month is None:
        return None
    return month, int(match.group(2))


def _infer_line_year(statement_month: int | None, statement_year: int, line_month: int) -> int:
    if statement_month == 1 and line_month == 12:
        return statement_year - 1
    if statement_month == 12 and line_month == 1:
        return statement_year + 1
    return statement_year


def _build_date(
    statement_month: int | None,
    statement_year: int | None,
    day: int,
    line_month: int,
) -> pd.Timestamp | None:
    if statement_year is None:
        return None

    try:
        return pd.Timestamp(
            year=_infer_line_year(statement_month, statement_year, line_month),
            month=line_month,
            day=day,
        ).normalize()
    except ValueError:
        return None


def _parse_value_from_line(line: str) -> tuple[float, bool] | None:
    """Extrai o PRIMEIRO valor monetário da linha e decide se é débito ou crédito.

    - Débito: '-' imediatamente após o valor (ex: '2.125,28-')
    - Crédito: sem '-' após o valor (ex: '50.000,00')
    Retorna (amount_signed, is_debit) ou None.
    """
    m = _BR_VALUE.search(line)
    if not m:
        return None
    raw = m.group()
    try:
        amount = float(raw.replace(".", "").replace(",", "."))
    except ValueError:
        return None
    is_debit = m.end() < len(line) and line[m.end()] == "-"
    return (amount, is_debit)


def _append_transaction(
    transactions: list[dict],
    current_date: pd.Timestamp | None,
    desc_parts: list[str],
    amount: float,
    is_debit: bool,
) -> None:
    cleaned_parts = [normalize_text(part) for part in desc_parts if normalize_text(part)]
    if current_date is None or not cleaned_parts:
        return

    signed = -amount if is_debit else amount
    raw_text = f"{amount:.2f}-" if is_debit else f"{amount:.2f}"
    transactions.append(
        {
            "dt": current_date,
            "desc_parts": cleaned_parts,
            "amount": signed,
            "raw_amount_text": raw_text,
            "detected_as_credit": not is_debit,
            "detected_as_debit": is_debit,
        }
    )


def _append_detail(
    transactions: list[dict],
    pending_desc: list[str],
    current_date: pd.Timestamp | None,
    detail: str,
) -> None:
    clean = normalize_text(detail)
    if not clean:
        return

    if transactions and (current_date is None or transactions[-1]["dt"] == current_date):
        transactions[-1]["desc_parts"].append(clean)
        return

    if current_date is not None:
        pending_desc.append(clean)


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


class SantanderParser:
    """Parser do Extrato Consolidado Inteligente Santander (conta corrente PF)."""

    name = "santander"

    # ── Detecção ──────────────────────────────────────────────────────────────
    def matches(self, text_pages: list[str]) -> bool:
        sample = fold_text(" ".join(text_pages[:4]))
        return (
            "extrato consolidado inteligente" in sample
            and (
                "movimentacao" in sample
                or "conta corrente" in sample
                or "saldo em" in sample
            )
        )

    # ── Extração ──────────────────────────────────────────────────────────────
    def parse(
        self,
        text_pages: list[str],
        source_file: str,
        word_pages: list[list[dict]] | None = None,
    ) -> pd.DataFrame:
        if not self.matches(text_pages):
            return empty_transactions_df()

        transactions: list[dict] = []
        current_year: int | None = None
        current_month: int | None = None
        current_date: pd.Timestamp | None = None
        in_transactions: bool = False
        pending_desc: list[str] = []
        movement_blocked: bool = False
        in_account_section: bool = False

        for page_text in text_pages:
            for raw_line in page_text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue

                folded = fold_text(line)

                # 1. Cabecalho de mes. Cada mes do PDF comeca em um novo
                # bloco, inclusive quando a linha traz apenas "fevereiro/2026".
                month_year = _extract_month_year(line)
                if month_year is not None:
                    new_month, new_year = month_year
                    same_month = current_month == new_month and current_year == new_year
                    same_open_month = (
                        in_transactions
                        and same_month
                    )
                    current_month, current_year = new_month, new_year
                    if not same_month:
                        current_date = None
                        in_transactions = False
                        pending_desc = []
                        movement_blocked = False
                        in_account_section = False
                    elif not same_open_month:
                        current_date = None
                        pending_desc = []
                    continue

                if _is_account_section(folded):
                    in_account_section = True
                    movement_blocked = False
                    continue

                # ── 2. Início da seção de transações ─────────────────────
                if _is_movement_heading(folded):
                    if movement_blocked and not in_account_section:
                        continue
                    in_transactions = True
                    movement_blocked = False
                    pending_desc = []
                    continue

                # ── 3. Fim da seção de transações ────────────────────────
                if _is_stop_section(folded):
                    # Emite pendente antes de parar
                    pending_desc = []
                    in_transactions = False
                    movement_blocked = True
                    in_account_section = False
                    continue

                if not in_transactions:
                    continue

                # ── 4. Ruído estrutural ──────────────────────────────────
                if _is_noise(folded):
                    continue

                # ── 5. Linha de valor puro (só números/pontuação) ─────────
                if pending_desc and _VALUE_ONLY.match(line) and _BR_VALUE.search(line):
                    result = _parse_value_from_line(line)
                    if result is not None:
                        amount, is_debit = result
                        _append_transaction(
                            transactions, current_date, pending_desc, amount, is_debit
                        )
                        pending_desc = []
                    continue

                # ── 6. Linha que começa com data DD/MM ───────────────────
                date_m = _DATE_START.match(line)
                if date_m and current_year:
                    day = int(date_m.group(1))
                    line_month = int(date_m.group(2))
                    rest = date_m.group(3).strip()
                    if not rest:
                        parsed_date = _build_date(current_month, current_year, day, line_month)
                        if parsed_date is not None:
                            current_date = parsed_date
                        continue

                    # Verifica se o restante da linha já contém um valor
                    rest_vals = list(_BR_VALUE.finditer(rest))
                    if rest_vals:
                        parsed_date = _build_date(current_month, current_year, day, line_month)
                        if parsed_date is None:
                            continue
                        current_date = parsed_date
                        first_v = rest_vals[0]
                        is_debit = first_v.end() < len(rest) and rest[first_v.end()] == "-"
                        try:
                            amount = float(first_v.group().replace(".", "").replace(",", "."))
                        except ValueError:
                            amount = None

                        if amount is not None:
                            desc_text = rest[: first_v.start()].strip()
                            desc_text = re.sub(r"^[-\s]+", "", desc_text)
                            desc_text = re.sub(r"^\d{4,8}\s*", "", desc_text).strip()

                            if desc_text:
                                # Linha completa: data + desc + valor
                                pending_desc = []
                                _append_transaction(
                                    transactions, current_date, [desc_text], amount, is_debit
                                )
                            else:
                                # Só valor na mesma linha da data
                                _append_transaction(
                                    transactions, current_date, pending_desc, amount, is_debit
                                )
                                pending_desc = []
                    else:
                        # Datas sem valor costumam ser detalhes de cartão
                        # ("31/01 Mercado", "09/01 11:43 CARTAO MASTER").
                        parsed_date = _build_date(current_month, current_year, day, line_month)
                        if transactions:
                            _append_detail(transactions, pending_desc, current_date, rest)
                        elif parsed_date is not None:
                            current_date = parsed_date
                            pending_desc = [rest]
                    continue

                # ── 7. Linha mista: descrição + valor ao final ────────────
                mixed_m = _MIXED_LINE.match(line)
                if mixed_m:
                    desc_part = mixed_m.group(1).strip()
                    val_raw = mixed_m.group(2)
                    is_debit = mixed_m.group(3) == "-"
                    try:
                        amount = float(val_raw.replace(".", "").replace(",", "."))
                    except ValueError:
                        amount = None

                    if amount is not None:
                        # Verifica se desc_part é apenas número de documento ou traço
                        is_doc = bool(re.match(r"^[-\d\s]+$", desc_part))
                        if is_doc:
                            _append_transaction(
                                transactions, current_date, pending_desc, amount, is_debit
                            )
                            pending_desc = []
                        else:
                            # Linha com descricao + valor e um novo lancamento;
                            # detalhes posteriores serao anexados a ele.
                            _append_transaction(
                                transactions, current_date, [desc_part], amount, is_debit
                            )
                            pending_desc = []
                    continue

                # ── 8. Linha de descrição pura ────────────────────────────
                if not _BR_VALUE.search(line):
                    clean = re.sub(r"^\d{1,2}/\d{2}\s*", "", line).strip()
                    clean = normalize_text(clean)
                    if clean:
                        _append_detail(transactions, pending_desc, current_date, clean)
                    continue

                # ── 9. Fallback: linha com valor não capturada acima ───────
                result = _parse_value_from_line(line)
                if result is not None and current_date and pending_desc:
                    amount, is_debit = result
                    _append_transaction(
                        transactions, current_date, pending_desc, amount, is_debit
                    )
                    pending_desc = []

        return _partials_to_df(transactions, source_file)
