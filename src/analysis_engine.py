from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Any

import pandas as pd

from . import get_version_label
from .exclusion_rules import apply_exclusion_rules
from .header_parser import parse_header
from .monthly_summary import build_monthly_summary, calculate_global_metrics
from .pdf_ocr import OCRUnavailableError, transcribe_pdf_images
from .pdf_reader import MIN_SELECTABLE_TEXT_CHARS, PDFDocument, read_pdf
from .table_extractor import tables_to_dataframes
from .transaction_parser import (
    TRANSACTION_COLUMNS,
    deduplicate_transactions,
    detect_foreign_statement,
    parse_transaction_tables,
    parse_transactions_from_text,
)
from .utils import fold_text, normalize_text, split_user_terms

logger = logging.getLogger(__name__)


ERROR_COLUMNS = ["arquivo", "etapa", "erro"]
StatusCallback = Callable[[str], None]


def _build_holder_first_name_rules(holder_names: list[str]) -> list[str]:
    rules: list[str] = []
    seen: set[str] = set()

    for holder in holder_names:
        cleaned = normalize_text(holder)
        first_name = cleaned.split(maxsplit=1)[0] if cleaned else ""
        if not first_name:
            continue

        rule = f"word:{first_name}"
        folded_rule = fold_text(rule)
        if folded_rule not in seen:
            rules.append(rule)
            seen.add(folded_rule)

    return rules


def _ensure_transaction_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS)
    result = df.copy()
    for col in TRANSACTION_COLUMNS:
        if col not in result.columns:
            result[col] = pd.NA
    return result


def _should_ocr_before_header(pdf_doc: PDFDocument) -> bool:
    return (
        not pdf_doc.ocr_used
        and not pdf_doc.ocr_error
        and not pdf_doc.tables
        and pdf_doc.selectable_text_chars < MIN_SELECTABLE_TEXT_CHARS
    )


def _should_try_ocr_after_empty_extraction(
    pdf_doc: PDFDocument,
    parsed_from_tables: pd.DataFrame,
    parsed_from_text: pd.DataFrame,
) -> bool:
    if pdf_doc.ocr_used or pdf_doc.ocr_error:
        return False
    if not parsed_from_tables.empty or not parsed_from_text.empty:
        return False
    if pdf_doc.tables:
        return False
    return (
        pdf_doc.image_count > 0
        or pdf_doc.selectable_text_chars < MIN_SELECTABLE_TEXT_CHARS
        or pdf_doc.selectable_word_count == 0
    )


def _apply_ocr_fallback(
    pdf_doc: PDFDocument,
    reason: str,
    status_callback: StatusCallback | None = None,
) -> PDFDocument:
    if status_callback:
        status_callback(
            f"{pdf_doc.filename}: sem tabela/texto selecionavel suficiente. "
            "Transcrevendo imagem por OCR; isso pode demorar um pouco."
        )

    try:
        ocr_result = transcribe_pdf_images(pdf_doc.file_bytes)
    except OCRUnavailableError as exc:
        logger.warning("OCR indisponivel para %s: %s", pdf_doc.filename, exc)
        return replace(pdf_doc, ocr_reason=reason, ocr_error=str(exc))
    except Exception as exc:
        logger.exception("Falha no OCR de %s", pdf_doc.filename)
        return replace(pdf_doc, ocr_reason=reason, ocr_error=f"{type(exc).__name__}: {exc}")

    return replace(
        pdf_doc,
        text_pages=ocr_result.text_pages,
        word_pages=ocr_result.word_pages,
        ocr_used=True,
        ocr_reason=reason,
        ocr_line_count=ocr_result.line_count,
        ocr_average_score=ocr_result.average_score,
        ocr_error="",
    )


def _append_ocr_error(errors: list[dict], pdf_doc: PDFDocument) -> None:
    if pdf_doc.ocr_error:
        errors.append({"arquivo": pdf_doc.filename, "etapa": "ocr", "erro": pdf_doc.ocr_error})


def _build_header_dict(pdf_doc: PDFDocument, header, foreign_detected: bool) -> dict:
    return {
        "arquivo": pdf_doc.filename,
        "banco": header.bank_name,
        "titular": header.account_holder,
        "conta": header.account_number,
        "agencia": header.agency,
        "periodo": header.statement_period,
        "extrato_estrangeiro_detectado": foreign_detected,
        "ocr_aplicado": pdf_doc.ocr_used,
        "ocr_motivo": pdf_doc.ocr_reason,
        "ocr_linhas": pdf_doc.ocr_line_count,
        "ocr_score_medio": pdf_doc.ocr_average_score,
        "ocr_erro": pdf_doc.ocr_error,
        "texto_selecionavel_chars": pdf_doc.selectable_text_chars,
        "palavras_selecionaveis": pdf_doc.selectable_word_count,
        "tabelas_detectadas": len(pdf_doc.tables),
        "imagens_detectadas": pdf_doc.image_count,
    }


def _parse_transactions(pdf_doc: PDFDocument) -> tuple[pd.DataFrame, pd.DataFrame]:
    table_dfs = tables_to_dataframes(pdf_doc.tables)
    parsed_from_tables = _ensure_transaction_schema(
        parse_transaction_tables(table_dfs, pdf_doc.filename)
    )
    parsed_from_text = _ensure_transaction_schema(
        parse_transactions_from_text(pdf_doc.text_pages, pdf_doc.filename, pdf_doc.word_pages)
    )
    return parsed_from_tables, parsed_from_text


def _process_single_file(
    file: Any,
    errors: list[dict],
    status_callback: StatusCallback | None = None,
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
        if _should_ocr_before_header(pdf_doc):
            pdf_doc = _apply_ocr_fallback(
                pdf_doc,
                reason="pdf_sem_texto_ou_tabela_selecionavel",
                status_callback=status_callback,
            )
            _append_ocr_error(errors, pdf_doc)
        header = parse_header(pdf_doc.text_pages)
        foreign_detected = detect_foreign_statement(pdf_doc.text_pages)
    except Exception as exc:
        logger.exception("Falha ao interpretar cabecalho de %s", filename)
        errors.append(
            {"arquivo": filename, "etapa": "cabecalho", "erro": f"{type(exc).__name__}: {exc}"}
        )
        return None, _ensure_transaction_schema(pd.DataFrame()), None

    try:
        parsed_from_tables, parsed_from_text = _parse_transactions(pdf_doc)
        if _should_try_ocr_after_empty_extraction(pdf_doc, parsed_from_tables, parsed_from_text):
            pdf_doc = _apply_ocr_fallback(
                pdf_doc,
                reason="sem_movimentacoes_extraidas_e_sem_tabela_selecionavel",
                status_callback=status_callback,
            )
            _append_ocr_error(errors, pdf_doc)
            if pdf_doc.ocr_used:
                header = parse_header(pdf_doc.text_pages)
                foreign_detected = detect_foreign_statement(pdf_doc.text_pages)
                parsed_from_tables, parsed_from_text = _parse_transactions(pdf_doc)
    except Exception as exc:
        logger.exception("Falha ao extrair transacoes de %s", filename)
        errors.append(
            {"arquivo": filename, "etapa": "transacoes", "erro": f"{type(exc).__name__}: {exc}"}
        )
        header_dict = _build_header_dict(pdf_doc, header, foreign_detected)
        return header_dict, _ensure_transaction_schema(pd.DataFrame()), header.account_holder or None

    header_dict = _build_header_dict(pdf_doc, header, foreign_detected)
    parsed_frames = [df for df in [parsed_from_tables, parsed_from_text] if not df.empty]
    combined = pd.concat(parsed_frames, ignore_index=True) if parsed_frames else pd.DataFrame()
    combined = deduplicate_transactions(combined)

    logger.info(
        "Arquivo processado: %s | banco=%s | linhas_tabela=%d | linhas_texto=%d | total_dedup=%d | ocr=%s",
        filename,
        header.bank_name or "indefinido",
        len(parsed_from_tables),
        len(parsed_from_text),
        len(combined),
        "sim" if pdf_doc.ocr_used else "nao",
    )

    return header_dict, combined, header.account_holder or None


def analyze_uploaded_files(
    uploaded_files,
    custom_terms_raw: str,
    custom_names_raw: str,
    include_holder_first_name: bool = False,
    include_holder_in_exclusions: bool = False,
    status_callback: StatusCallback | None = None,
) -> dict:
    headers: list[dict] = []
    transaction_frames: list[pd.DataFrame] = []
    errors: list[dict] = []
    auto_holder_names: list[str] = []

    custom_terms = split_user_terms(custom_terms_raw)
    custom_names = split_user_terms(custom_names_raw)

    logger.info("Iniciando analise: %d arquivo(s)", len(uploaded_files or []))

    for file in uploaded_files or []:
        header_dict, combined, holder = _process_single_file(file, errors, status_callback=status_callback)
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

    rule_terms = list(custom_terms)
    if include_holder_first_name:
        existing_terms = {fold_text(term) for term in rule_terms if normalize_text(term)}
        for first_name_rule in _build_holder_first_name_rules(auto_holder_names):
            if fold_text(first_name_rule) not in existing_terms:
                rule_terms.append(first_name_rule)
                existing_terms.add(fold_text(first_name_rule))

    transactions_df = (
        pd.concat(transaction_frames, ignore_index=True)
        if transaction_frames
        else pd.DataFrame()
    )
    transactions_df = _ensure_transaction_schema(transactions_df)
    transactions_df = deduplicate_transactions(transactions_df)
    final_df = apply_exclusion_rules(transactions_df, rule_terms, custom_names)
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
