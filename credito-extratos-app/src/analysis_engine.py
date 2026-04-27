from __future__ import annotations

import pandas as pd

from .exclusion_rules import apply_exclusion_rules
from .header_parser import HeaderInfo, parse_header
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


def _ensure_transaction_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS)
    result = df.copy()
    for col in TRANSACTION_COLUMNS:
        if col not in result.columns:
            result[col] = pd.NA
    return result


def analyze_uploaded_files(
    uploaded_files,
    custom_terms_raw: str,
    custom_names_raw: str,
    flexible_names: bool = True,
    include_holder_in_exclusions: bool = False,
) -> dict:
    headers: list[dict] = []
    transaction_frames: list[pd.DataFrame] = []

    custom_terms = split_user_terms(custom_terms_raw)
    custom_names = split_user_terms(custom_names_raw)
    auto_holder_names: list[str] = []

    for file in uploaded_files:
        pdf_doc = read_pdf(file)
        header = parse_header(pdf_doc.text_pages)
        foreign_detected = detect_foreign_statement(pdf_doc.text_pages)
        if header.account_holder:
            auto_holder_names.append(header.account_holder)
        headers.append(
            {
                "arquivo": pdf_doc.filename,
                "banco": header.bank_name,
                "titular": header.account_holder,
                "conta": header.account_number,
                "agencia": header.agency,
                "periodo": header.statement_period,
                "extrato_estrangeiro_detectado": foreign_detected,
            }
        )

        table_dfs = tables_to_dataframes(pdf_doc.tables)
        parsed_from_tables = _ensure_transaction_schema(parse_transaction_tables(table_dfs, pdf_doc.filename))
        parsed_from_text = _ensure_transaction_schema(
            parse_transactions_from_text(pdf_doc.text_pages, pdf_doc.filename, pdf_doc.word_pages)
        )
        parsed_frames = [df for df in [parsed_from_tables, parsed_from_text] if not df.empty]
        combined = pd.concat(parsed_frames, ignore_index=True) if parsed_frames else pd.DataFrame()
        combined = deduplicate_transactions(combined)

        transaction_frames.append(combined)

    if include_holder_in_exclusions and auto_holder_names:
        existing = {normalize_text(name) for name in custom_names if normalize_text(name)}
        for holder in auto_holder_names:
            cleaned = normalize_text(holder)
            if cleaned and cleaned not in existing:
                custom_names.append(cleaned)
                existing.add(cleaned)

    transactions_df = pd.concat(transaction_frames, ignore_index=True) if transaction_frames else pd.DataFrame()
    transactions_df = _ensure_transaction_schema(transactions_df)
    transactions_df = deduplicate_transactions(transactions_df)
    final_df = apply_exclusion_rules(transactions_df, custom_terms, custom_names, flexible_names=flexible_names)
    final_df = _ensure_transaction_schema(final_df)

    summary_df = build_monthly_summary(final_df)
    metrics = calculate_global_metrics(summary_df)

    considered_df = final_df[(final_df["status_final"] == "considerado") & (final_df["valor"] > 0)].copy()
    disregarded_df = final_df[final_df["status_final"] == "desconsiderado"].copy()
    review_df = final_df[final_df["status_final"] == "revisar"].copy()
    header_df = pd.DataFrame(headers)

    return {
        "headers": header_df,
        "transactions": final_df,
        "summary": summary_df,
        "considered": considered_df,
        "disregarded": disregarded_df,
        "review": review_df,
        "metrics": metrics,
        "custom_terms": custom_terms,
        "custom_names": custom_names,
        "foreign_detected": bool(
            not header_df.empty
            and "extrato_estrangeiro_detectado" in header_df.columns
            and header_df["extrato_estrangeiro_detectado"].fillna(False).astype(bool).any()
        ),
    }
