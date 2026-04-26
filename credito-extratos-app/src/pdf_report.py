from __future__ import annotations

from datetime import datetime

import pandas as pd

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


def _dual_value_text(value: float, currency: str, fx_quote: FxQuote | None) -> str:
    if not fx_quote or currency == "BRL":
        return _money(value, currency)
    brl_value = float(value) * float(fx_quote.rate_brl_per_unit)
    return f"{_money(value, currency)} | {_brl(brl_value)}"


def build_pdf_report(
    *,
    headers_df: pd.DataFrame,
    metrics: dict,
    considered_df: pd.DataFrame,
    display_currency: str,
    fx_quote: FxQuote | None,
) -> bytes:
    from fpdf import FPDF  # lazy import to avoid breaking the app if deps aren't installed

    class ReportPdf(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 14)
            self.cell(0, 8, "Relatório — Análise de Crédito por Extratos", new_x="LMARGIN", new_y="NEXT")
            self.set_font("Helvetica", "", 9)
            self.set_text_color(90, 90, 90)
            self.cell(0, 5, datetime.now().strftime("%d/%m/%Y %H:%M"), new_x="LMARGIN", new_y="NEXT")
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

    holders = []
    if not headers_df.empty and "titular" in headers_df.columns:
        holders = [h for h in headers_df["titular"].fillna("").astype(str).tolist() if h.strip()]
    holders = sorted(set(holders))

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Resumo", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(220, 220, 220)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)

    if holders:
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, f"Titular: {', '.join(holders[:3])}" + ("…" if len(holders) > 3 else ""))
        pdf.ln(1)

    if fx_quote and display_currency != "BRL":
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(
            0,
            5,
            "Cotação PTAX venda ({}): 1 {} = {}".format(
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

    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, f"Renda média mensal: {_dual_value_text(renda, display_currency, fx_quote)}")
    pdf.multi_cell(0, 6, f"Meses analisados: {meses}")
    pdf.multi_cell(0, 6, f"Total considerado: {_dual_value_text(total, display_currency, fx_quote)}")
    pdf.multi_cell(0, 6, f"Qtd. créditos considerados: {qtd}")

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Créditos considerados", new_x="LMARGIN", new_y="NEXT")
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
        pdf.cell(w_date, 7, "Data", border=1, fill=True)
        pdf.cell(w_desc, 7, "Descrição", border=1, fill=True)
        pdf.cell(w_val, 7, "Valor", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)

    header_row()
    for _, row in table_df.iterrows():
        date_txt = _format_date(row.get("data"))
        desc_txt = str(row.get("descricao") or "").strip()
        value_num = row.get("valor")
        try:
            value_float = float(value_num)
        except Exception:
            value_float = 0.0
        value_txt = _dual_value_text(value_float, display_currency, fx_quote)

        y0 = pdf.get_y()
        pdf.multi_cell(w_date, 5, date_txt, border=1)
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
