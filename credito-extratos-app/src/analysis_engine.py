from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from . import get_version_label
from .exclusion_rules import apply_exclusion_rules
from .header_parser import parse_header
from .monthly_summary import build_monthly_summary, calculate_global_metrics
from .pdf_reader import read_pdf
from .table_extractor import tables_to_dataframes
from .transaction_parser import (
    TRANSACTION_COLUMNS,
    deduplicate_transactions,
    detect_foreign_statement,
    parse_transaction_tables,
    parse_transactions_from_text,
)
from .utils import normalize_text, split_user_terms

logger = logging.getLogger(__name__)


ERROR_COLUMNS = ["arquivo", "etapa", "erro"]


def _ensure_transaction_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS)
    result = df.copy()
    for col in TRANSACTION_COLUMNS:
        if col not in result.columns:
            result[col] = pd.NA
    return result


def _process_single_file(
    file: Any,
    errors: list[dict],
) -> tuple[dict | None, pd.DataFrame, str | None]:
    """Process one uploaded PDF.

    Returns (header_dict_or_None, transactions_df, account_holder_or_None).
    Failures are appended to ``errors`` and the function returns empty data
    so the overall pipeline can continue.
    """
    filename = getattr(file, "name", "<sem nome>")

    try:
        pdf_doc = read_pdf(file)
    except Exception as exc:
        logger.exception("Falha ao ler PDF %s", filename)
        errors.append({"arquivo": filename, "etapa": "leitura_pdf", "erro": f"{type(exc).__name__}: {exc}"})
        return None, _ensure_transaction_schema(pd.DataFrame()), None

    try:
        header = parse_header(pdf_doc.text_pages)
        foreign_detected = detect_foreign_statement(pdf_doc.text_pages)
    except Exception as exc:
        logger.exception("Falha ao interpretar cabecalho de %s", filename)
        errors.append(
            {"arquivo": filename, "etapa": "cabecalho", "erro": f"{type(exc).__name__}: {exc}"}
        )
        return None, _ensure_transaction_schema(pd.DataFrame()), None

    header_dict = {
        "arquivo": pdf_doc.filename,
        "banco": header.bank_name,
        "titular": header.account_holder,
        "conta": header.account_number,
        "agencia": header.agency,
        "periodo": header.statement_period,
        "extrato_estrangeiro_detectado": foreign_detected,
    }

    try:
        table_dfs = tables_to_dataframes(pdf_doc.tables)
        parsed_from_tables = _ensure_transaction_schema(
            parse_transaction_tables(table_dfs, pdf_doc.filename)
        )
        parsed_from_text = _ensure_transaction_schema(
            parse_transactions_from_text(
                pdf_doc.text_pages, pdf_doc.filename, pdf_doc.word_pages
            )
        )
    except Exception as exc:
        logger.exception("Falha ao extrair transacoes de %s", filename)
        errors.append(
            {"arquivo": filename, "etapa": "transacoes", "erro": f"{type(exc).__name__}: {exc}"}
        )
        return header_dict, _ensure_transaction_schema(pd.DataFrame()), header.account_holder or None

    parsed_frames = [df for df in [parsed_from_tables, parsed_from_text] if not df.empty]
    combined = pd.concat(parsed_frames, ignore_index=True) if parsed_frames else pd.DataFrame()
    combined = deduplicate_transactions(combined)

    logger.info(
        "Arquivo processado: %s | banco=%s | linhas_tabela=%d | linhas_texto=%d | total_dedup=%d",
        filename,
        header.bank_name or "indefinido",
        len(parsed_from_tables),
        len(parsed_from_text),
        len(combined),
    )

    return header_dict, combined, header.account_holder or None


def analyze_uploaded_files(
    uploaded_files,
    custom_terms_raw: str,
    custom_names_raw: str,
    flexible_names: bool = True,
    include_holder_in_exclusions: bool = False,
) -> dict:
    headers: list[dict] = []
    transaction_frames: list[pd.DataFrame] = []
    errors: list[dict] = []
    auto_holder_names: list[str] = []

    custom_terms = split_user_terms(custom_terms_raw)
    custom_names = split_user_terms(custom_names_raw)

    logger.info("Iniciando analise: %d arquivo(s)", len(uploaded_files or []))

    for file in uploaded_files or []:
        header_dict, combined, holder = _process_single_file(file, errors)
        if header_dict is not None:
            headers.append(header_dict)
        if holder:
            auto_holder_names.append(holder)
        transaction_frames.append(combined)

    if include_holder_in_exclusions and auto_holder_names:
        existing = {normalize_text(name) for name in custom_names if normalize_text(name)}
        for holder in auto_holder_names:
            cleaned = normalize_text(holder)
            if cleaned and cleaned not in existing:
                custom_names.append(cleaned)
                existing.add(cleaned)

    transactions_df = (
        pd.concat(transaction_frames, ignore_index=True)
        if transaction_frames
        else pd.DataFrame()
    )
    transactions_df = _ensure_transaction_schema(transactions_df)
    transactions_df = deduplicate_transactions(transactions_df)
    final_df = apply_exclusion_rules(
        transactions_df, custom_terms, custom_names, flexible_names=flexible_names
    )
    final_df = _ensure_transaction_schema(final_df)

    summary_df = build_monthly_summary(final_df)
    metrics = calculate_global_metrics(summary_df)

    considered_df = final_df[(final_df["status_final"] == "considerado") & (final_df["valor"] > 0)].copy()
    disregarded_df = final_df[final_df["status_final"] == "desconsiderado"].copy()
    review_df = final_df[final_df["status_final"] == "revisar"].copy()
    header_df = pd.DataFrame(headers)
    errors_df = pd.DataFrame(errors, columns=ERROR_COLUMNS) if errors else pd.DataFrame(columns=ERROR_COLUMNS)

    logger.info(
        "Analise concluida | arquivos_ok=%d | arquivos_com_erro=%d | linhas_totais=%d | consideradas=%d",
        len(headers),
        len(errors_df["arquivo"].unique()) if not errors_df.empty else 0,
        len(final_df),
        len(considered_df),
    )

    return {
        "headers": header_df,
        "transactions": final_df,
        "summary": summary_df,
        "considered": considered_df,
        "disregarded": disregarded_df,
        "review": review_df,
        "errors": errors_df,
        "metrics": metrics,
        "custom_terms": custom_terms,
        "custom_names": custom_names,
        "app_version": get_version_label(),
        "analysis_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "foreign_detected": bool(
            not header_df.empty
            and "extrato_estrangeiro_detectado" in header_df.columns
            and header_df["extrato_estrangeiro_detectado"].fillna(False).astype(bool).any()
        ),
    }
