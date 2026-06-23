from io import BytesIO

import pandas as pd
from openpyxl import load_workbook

from src.pdf_report import _pdf_text
from src.utils import to_excel_bytes


def test_excel_export_removes_xml_control_characters():
    output = to_excel_bytes({"Dados": pd.DataFrame([{"descricao": "Cliente Te\x00te"}])})

    workbook = load_workbook(BytesIO(output), read_only=True)
    assert workbook["Dados"]["A2"].value == "Cliente Tete"


def test_pdf_text_removes_xml_control_characters():
    assert _pdf_text("Cliente Te\x00te") == "Cliente Tete"
