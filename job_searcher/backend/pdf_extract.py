"""Extracts plain text from an uploaded resume (PDF or plain text)."""
from __future__ import annotations

import io

from pypdf import PdfReader


def extract_text(filename: str, content: bytes) -> str:
    name = (filename or "").lower()

    if name.endswith(".pdf") or content[:4] == b"%PDF":
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages).strip()
        if not text:
            raise ValueError(
                "Could not extract any text from this PDF. It may be a scanned image - "
                "try pasting the resume text instead."
            )
        return text

    # Treat anything else (.txt, .md, or no extension) as plain text
    try:
        return content.decode("utf-8").strip()
    except UnicodeDecodeError as e:
        raise ValueError("Unsupported file type. Upload a PDF or plain-text resume.") from e
