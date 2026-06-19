from __future__ import annotations

from dataclasses import dataclass

from .utils import fold_text


@dataclass
class ClassificationResult:
    status: str
    reason: str
    score: int


CREDIT_HINTS = [
    "pix recebido",
    "ted recebida",
    "doc recebido",
    "credito",
    "credito em conta",
    "salario",
    "provento",
    "pagamento recebido",
    "deposito",
    "transferencia recebida",
    "ordem de pagamento",
]

DEBIT_HINTS = [
    "pagamento",
    "compra",
    "debito",
    "tarifa",
    "saque",
    "boleto",
    "cartao",
    "transferencia enviada",
    "pix enviado",
    "encargos",
]


def score_transaction(
    description: str,
    amount: float,
    detected_as_credit: bool,
    detected_as_debit: bool,
    has_plus_sign: bool,
    has_minus_sign: bool,
) -> int:
    text = fold_text(description)
    score = 0

    if detected_as_credit:
        score += 6
    if detected_as_debit:
        score -= 6
    if amount > 0:
        score += 3
    if amount < 0:
        score -= 4
    if has_plus_sign:
        score += 2
    if has_minus_sign:
        score -= 2

    if any(hint in text for hint in CREDIT_HINTS):
        score += 4
    if any(hint in text for hint in DEBIT_HINTS):
        score -= 4

    return score


def classify_by_score(score: int) -> ClassificationResult:
    if score >= 5:
        return ClassificationResult("considerado", "Credito inferido pela estrutura da linha.", score)
    if score <= -3:
        return ClassificationResult("desconsiderado", "Linha aparenta debito ou movimento nao elegivel.", score)
    return ClassificationResult("revisar", "Linha ambigua; revisao recomendada.", score)
