import pandas as pd

from src import analysis_engine
from src.pdf_ocr import OCRResult
from src.pdf_reader import PDFDocument


def _doc(**overrides) -> PDFDocument:
    defaults = {
        "filename": "extrato.pdf",
        "file_bytes": b"%PDF-ocr-candidate",
        "text_pages": [""],
        "tables": [],
        "word_pages": [[]],
        "page_count": 1,
        "selectable_text_chars": 0,
        "selectable_word_count": 0,
        "image_count": 1,
    }
    defaults.update(overrides)
    return PDFDocument(**defaults)


def test_ocr_fallback_is_candidate_only_after_empty_normal_extraction():
    empty = pd.DataFrame()

    assert analysis_engine._should_try_ocr_after_empty_extraction(_doc(), empty, empty)
    assert not analysis_engine._should_try_ocr_after_empty_extraction(
        _doc(tables=[[["data", "valor"], ["01/01/2026", "10,00"]]]),
        empty,
        empty,
    )
    assert not analysis_engine._should_try_ocr_after_empty_extraction(
        _doc(),
        empty,
        pd.DataFrame([{"data": "2026-01-01"}]),
    )


def test_apply_ocr_fallback_replaces_text_pages_and_marks_metadata(monkeypatch):
    def fake_transcribe(file_bytes):
        assert file_bytes == b"%PDF-ocr-candidate"
        return OCRResult(
            text_pages=["01/01/2026 PIX RECEBIDO 100,00"],
            word_pages=[[{"text": "PIX", "x0": 10, "x1": 30, "top": 20}]],
            line_count=1,
            average_score=0.98,
        )

    monkeypatch.setattr(analysis_engine, "transcribe_pdf_images", fake_transcribe)

    result = analysis_engine._apply_ocr_fallback(_doc(), reason="teste")

    assert result.ocr_used is True
    assert result.ocr_reason == "teste"
    assert result.ocr_line_count == 1
    assert result.ocr_average_score == 0.98
    assert result.text_pages == ["01/01/2026 PIX RECEBIDO 100,00"]
