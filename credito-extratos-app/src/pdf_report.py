from __future__ import annotations

from datetime import datetime

import pandas as pd
from unidecode import unidecode

from .fx_ptax import FxQuote


def _brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _money(value: float, currency: str = "BRL") -> str:
    if currency == "BRL":
        return _brl(value)
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{currency} {formatted}"


def _format_date(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    dt = pd.to_datetime(value, errors="coerce")
    if pd.isna(dt):
        return ""
    return dt.strftime("%d/%m/%Y")


def _pdf_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value)
    text = (
        text.replace("\u2014", "-")  # em dash
        .replace("\u2013", "-")  # en dash
        .replace("\u2212", "-")  # minus sign
        .replace("\u00a0", " ")  # nbsp
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        return unidecode(text)


def _dual_value_text(value: float, currency: str, fx_quote: FxQuote | None) -> str:
    if not fx_quote or currency == "BRL":
        return _money(value, currency)
    brl_value = float(value) * float(fx_quote.rate_brl_per_unit)
    return f"{_money(value, currency)} | {_brl(brl_value)}"


def build_pdf_report(
    *,
    headers_df: pd.DataFrame,
    metrics: dict,
    summary_df: pd.DataFrame | None = None,
    considered_df: pd.DataFrame,
    display_currency: str,
    fx_quote: FxQuote | None,
) -> bytes:
    from fpdf import FPDF  # lazy import to avoid breaking the app if deps aren't installed

    class ReportPdf(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 14)
            self.cell(
                0,
                8,
                _pdf_text("Relatório - Análise de Crédito por Extratos"),
                new_x="LMARGIN",
                new_y="NEXT",
            )
            self.set_font("Helvetica", "", 9)
            self.set_text_color(90, 90, 90)
            self.cell(
                0,
                5,
                _pdf_text(datetime.now().strftime("%d/%m/%Y %H:%M")),
                new_x="LMARGIN",
                new_y="NEXT",
            )
            self.set_text_color(0, 0, 0)
            self.ln(2)

        def footer(self):
            self.set_y(-14)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(120, 120, 120)
            self.cell(0, 8, f"Página {self.page_no()}", align="R")
            self.set_text_color(0, 0, 0)

    pdf = ReportPdf(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    full_w = getattr(pdf, "epw", pdf.w - pdf.l_margin - pdf.r_margin)
    if not full_w or full_w <= 0:
        full_w = pdf.w - pdf.l_margin - pdf.r_margin

    holders = []
    if not headers_df.empty and "titular" in headers_df.columns:
        holders = [h for h in headers_df["titular"].fillna("").astype(str).tolist() if h.strip()]
    holders = sorted(set(holders))

    months: list[str] = []
    if summary_df is not None and not summary_df.empty and "mes_ref" in summary_df.columns:
        months = [str(m).strip() for m in summary_df["mes_ref"].tolist() if str(m).strip()]
    elif "mes_ref" in considered_df.columns:
        months = [str(m).strip() for m in considered_df["mes_ref"].tolist() if str(m).strip()]
    else:
        if "data" in considered_df.columns:
            dt_series = pd.to_datetime(considered_df["data"], errors="coerce")
            months = [d.strftime("%m/%Y") for d in dt_series.dropna().dt.to_pydatetime()]

    months_unique: list[str] = []
    for m in months:
        if m not in months_unique:
            months_unique.append(m)

    def wrap_items(items: list[str], max_width: float) -> list[str]:
        if not items:
            return []
        lines: list[str] = []
        current = ""
        for item in items:
            candidate = item if not current else f"{current}, {item}"
            if pdf.get_string_width(_pdf_text(candidate)) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = item
        if current:
            lines.append(current)
        return lines


    def write_kv(label: str, value_lines: list[str] | str):
        lines = value_lines if isinstance(value_lines, list) else [value_lines]
        lines = [line for line in lines if line is not None]

        label_w = 44
        gap = 4
        value_w = full_w - label_w - gap
        if value_w < 60:
            label_w = 34
            value_w = full_w - label_w - gap
        if value_w < 40:
            label_w = 0
            value_w = full_w

        for idx, line in enumerate(lines):
            pdf.set_font("Helvetica", "B" if idx == 0 else "", 10)
            if label_w:
                pdf.cell(label_w, 6, _pdf_text(label) if idx == 0 else "", border=0)
                pdf.cell(gap, 6, "" if idx == 0 else "", border=0)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(value_w, 6, _pdf_text(line), border=0)


    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, _pdf_text("Resumo"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(220, 220, 220)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)

    if holders:
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(
            full_w,
            5,
            _pdf_text(f"Titular: {', '.join(holders[:3])}" + ("..." if len(holders) > 3 else "")),
        )
        pdf.ln(1)

    if fx_quote and display_currency != "BRL":
        write_kv(
            "Cotação PTAX",
            "Venda ({}): 1 {} = {}".format(
                fx_quote.requested_date.strftime("%d/%m/%Y"),
                display_currency,
                _brl(float(fx_quote.rate_brl_per_unit)),
            ),
        )
        pdf.ln(1)

    renda = float(metrics.get("renda_media_mensal") or 0)
    meses = int(metrics.get("meses_analisados") or 0)
    total = float(metrics.get("total_considerado") or 0)
    qtd = int(metrics.get("qtd_creditos") or 0)

    months_line = ", ".join(months_unique) if months_unique else ""
    months_count = len(months_unique) if months_unique else meses
    if months_unique:
        month_lines = wrap_items(months_unique, max_width=full_w - 44 - 4)
        write_kv("Meses", [f"({months_count}) {month_lines[0]}", *month_lines[1:]] if month_lines else f"({months_count})")
    else:
        write_kv("Meses", f"{months_count}")

    write_kv("Renda total", _dual_value_text(total, display_currency, fx_quote))
    write_kv("Renda média", _dual_value_text(renda, display_currency, fx_quote))
    write_kv("Qtd. créditos", str(qtd))

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, _pdf_text("Créditos considerados"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(220, 220, 220)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)

    table_df = considered_df.copy()
    cols = [c for c in ["data", "descricao", "valor"] if c in table_df.columns]
    table_df = table_df[cols].copy() if cols else pd.DataFrame(columns=["data", "descricao", "valor"])
    if "data" in table_df.columns:
        table_df["data"] = pd.to_datetime(table_df["data"], errors="coerce")
        table_df = table_df.sort_values(["data", "descricao"], na_position="last")

    w_date = 24
    w_desc = 115
    w_val = pdf.w - pdf.l_margin - pdf.r_margin - w_date - w_desc

    def header_row():
        pdf.set_fill_color(245, 246, 248)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(w_date, 7, _pdf_text("Data"), border=1, fill=True)
        pdf.cell(w_desc, 7, _pdf_text("Descrição"), border=1, fill=True)
        pdf.cell(w_val, 7, _pdf_text("Valor"), border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)

    header_row()
    for _, row in table_df.iterrows():
        date_txt = _format_date(row.get("data"))
        desc_txt = _pdf_text(str(row.get("descricao") or "").strip())
        value_num = row.get("valor")
        try:
            value_float = float(value_num)
        except Exception:
            value_float = 0.0
        value_txt = _pdf_text(_dual_value_text(value_float, display_currency, fx_quote))

        y0 = pdf.get_y()
        pdf.multi_cell(w_date, 5, _pdf_text(date_txt), border=1)
        h_date = pdf.get_y() - y0
        pdf.set_xy(pdf.l_margin + w_date, y0)
        pdf.multi_cell(w_desc, 5, desc_txt, border=1)
        h_desc = pdf.get_y() - y0
        pdf.set_xy(pdf.l_margin + w_date + w_desc, y0)
        pdf.multi_cell(w_val, 5, value_txt, border=1)
        h_val = pdf.get_y() - y0
        row_h = max(h_date, h_desc, h_val)

        pdf.set_y(y0 + row_h)
        if pdf.get_y() > (pdf.h - pdf.b_margin - 12):
            pdf.add_page()
            header_row()

    output = pdf.output(dest="S")
    if isinstance(output, (bytes, bytearray)):
        return bytes(output)
    return str(output).encode("latin-1")
