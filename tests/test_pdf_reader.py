import io

from src.pdf_reader import _read_uploaded_bytes


class UploadedFileLike(io.BytesIO):
    name = "sample.pdf"


def test_read_uploaded_bytes_uses_full_buffer_even_if_pointer_moved():
    uploaded = UploadedFileLike(b"%PDF-sample-bytes")
    uploaded.read(4)

    result = _read_uploaded_bytes(uploaded)

    assert result == b"%PDF-sample-bytes"
