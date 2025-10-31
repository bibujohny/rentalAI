import os
from typing import Optional

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None

try:
    from pdf2image import convert_from_path
except Exception:  # pragma: no cover
    convert_from_path = None


def ocr_pdf_to_text(path: str) -> str:
    """OCR a scanned PDF into text using pdf2image + Tesseract. Requires system packages:
    - poppler-utils (for pdftoppm)
    - tesseract-ocr
    Returns empty string on failure or if dependencies are missing.
    """
    if convert_from_path is None or pytesseract is None:
        return ""
    try:
        pages = convert_from_path(path, dpi=200)  # lower DPI for speed
        text_parts = []
        for img in pages:
            txt = pytesseract.image_to_string(img) or ""
            text_parts.append(txt)
        return "\n".join(text_parts)
    except Exception:
        return ""
