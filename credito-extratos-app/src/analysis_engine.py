from __future__ import annotations

import pandas as pd

from .exclusion_rules import apply_exclusion_rules
from .header_parser import HeaderInfo, parse_header
from .monthly_summary import build_monthly_summary, calculate_global_metrics
from .pdf_reader import read_pdf
from .table_extractor import tables_to_dataframes
from .transaction_parser import deduplicate_transactions, parse_transaction_tables, parse_transactions_from_text
from .utils import split_user_terms


def analyze_uploaded_files(uploaded_files, custom_terms_raw: str, custom_names_raw: str, flexible_names: bool = True) -> dict:
    headers: list[dict] = []
    transaction_frames: list[pd.DataFrame] = []

    custom_terms = split_user_terms(custom_terms_raw)
    custom_names = split_user_terms(custom_names_raw)

    for file in uploaded_files:
        pdf_doc = read_pdf(file)
        header = parse_header(pdf_doc.text_pages)
        headers.append(
            {
                "arquivo": pdf_doc.filename,
                "banco": header.bank_name,
                "titular": header.account_holder,
                "conta": header.account_number,
                "agencia": header.agency,
                "periodo": header.statement_period,
            }
        )

        table_dfs = tables_to_dataframes(pdf_doc.tables)
        parsed_from_tables = parse_transaction_tables(table_dfs, pdf_doc.filename)
        parsed_from_text = parse_transactions_from_text(pdf_doc.text_pages, pdf_doc.filename)
        combined = pd.concat([parsed_from_tables, parsed_from_text], ignore_index=True)
        combined = deduplicate_transactions(combined)

        transaction_frames.append(combined)

    transactions_df = pd.concat(transaction_frames, ignore_index=True) if transaction_frames else pd.DataFrame()
    transactions_df = deduplicate_transactions(transactions_df)
    final_df = apply_exclusion_rules(transactions_df, custom_terms, custom_names, flexible_names=flexible_names)

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
    }
