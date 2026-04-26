from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from .utils import expand_name_tokens, fold_text, normalize_text


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "exclusion_terms_default.json"
DEFAULT_TERMS = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["default_terms"]


def build_exclusion_terms(custom_terms: list[str], custom_names: list[str], flexible_names: bool = True) -> list[str]:
    results = list(DEFAULT_TERMS)

    for term in custom_terms:
        cleaned = normalize_text(term)
        if cleaned:
            results.append(cleaned)

    for name in custom_names:
        cleaned = normalize_text(name)
        if not cleaned:
            continue

        if flexible_names:
            results.extend(expand_name_tokens(cleaned))
        else:
            tokens = expand_name_tokens(cleaned)
            stronger = [token for token in tokens if len(token.split()) >= 2 or len(token) >= len(cleaned) - 2]
            results.extend(stronger or [cleaned])

    unique = sorted({fold_text(term) for term in results if term}, key=len, reverse=True)
    return unique


def _term_matches(description: str, term: str) -> bool:
    if not term:
        return False

    if term.startswith("word:"):
        token = term.split(":", maxsplit=1)[1]
        if not token:
            return False
        escaped = re.escape(token)
        return bool(re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", description))

    escaped = re.escape(term)
    if " " in term:
        return term in description
    if len(term) <= 4:
        return bool(re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", description))
    return bool(re.search(rf"(?<![a-z0-9]){escaped}[a-z0-9]*", description))


def _find_matched_term(description: str, exclusion_terms: list[str]) -> str | None:
    return next((term for term in exclusion_terms if _term_matches(description, term)), None)


def apply_exclusion_rules(
    df: pd.DataFrame,
    custom_terms: list[str],
    custom_names: list[str],
    flexible_names: bool = True,
) -> pd.DataFrame:
    if df.empty:
        result = df.copy()
        for col in ["status_final", "motivo_final", "termo_regra"]:
            result[col] = []
        return result

    exclusion_terms = build_exclusion_terms(custom_terms, custom_names, flexible_names)

    result = df.copy()
    final_status = []
    final_reason = []
    matched_term_col = []

    for _, row in result.iterrows():
        desc = fold_text(row.get("descricao", ""))
        initial_status = row.get("status_inicial", "revisar")
        initial_reason = row.get("motivo_inicial", "")
        matched_term = _find_matched_term(desc, exclusion_terms)
        display_term = (
            matched_term.split(":", maxsplit=1)[1]
            if matched_term and matched_term.startswith("word:")
            else matched_term
        )

        if row.get("tipo_inferido") == "debito":
            status = "desconsiderado"
            reason = "Movimentacao interpretada como debito."
        elif matched_term:
            status = "desconsiderado"
            reason = f"Regra de exclusao acionada por termo: {display_term}."
        elif initial_status == "considerado" and row.get("valor", 0) > 0:
            status = "considerado"
            reason = initial_reason or "Credito aceito pela regra inicial."
        else:
            status = "revisar"
            reason = initial_reason or "Linha ambigua; revisao recomendada."

        final_status.append(status)
        final_reason.append(reason)
        matched_term_col.append(display_term or "")

    result["status_final"] = final_status
    result["motivo_final"] = final_reason
    result["termo_regra"] = matched_term_col
    return result
