"""Extracts plain text from an uploaded resume (PDF or plain text)."""
from __future__ import annotations

import io

from pypdf import PdfReader

# Below this, a pypdf extraction is treated as "no real text" and OCR is tried instead.
# Design-tool exports (Canva, some resume builders) embed fonts without a proper
# Unicode mapping - the PDF renders fine visually but pypdf pulls out only a
# handful of garbage characters per page.
_MIN_DIRECT_TEXT_CHARS = 50
_MAX_OCR_PAGES = 5


def _extract_direct(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def _extract_via_ocr(content: bytes) -> str:
    from pdf2image import convert_from_bytes
    from pytesseract import image_to_string

    images = convert_from_bytes(content, dpi=200, last_page=_MAX_OCR_PAGES)
    pages = [image_to_string(image) for image in images]
    return "\n".join(pages).strip()


def extract_text(filename: str, content: bytes) -> str:
    name = (filename or "").lower()

    if name.endswith(".pdf") or content[:4] == b"%PDF":
        text = _extract_direct(content)

        if len(text) < _MIN_DIRECT_TEXT_CHARS:
            try:
                ocr_text = _extract_via_ocr(content)
            except Exception:
                ocr_text = ""
            if len(ocr_text) > len(text):
                text = ocr_text

        if not text:
            raise ValueError(
                "Could not extract any text from this PDF, even with OCR. "
                "Try pasting the resume text instead."
            )
        return text

    # Treat anything else (.txt, .md, or no extension) as plain text
    try:
        return content.decode("utf-8").strip()
    except UnicodeDecodeError as e:
        raise ValueError("Unsupported file type. Upload a PDF or plain-text resume.") from e
