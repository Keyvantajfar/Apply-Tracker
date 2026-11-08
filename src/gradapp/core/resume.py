"""Text extraction for uploaded resumes / transcripts (txt, md, pdf, docx)."""
from __future__ import annotations

import io
from typing import Any

try:
    from pypdf import PdfReader
except Exception:  # noqa: BLE001
    PdfReader = None
try:
    from docx import Document
except Exception:  # noqa: BLE001
    Document = None


def extract_text(filename: str, raw: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith((".txt", ".md", ".text", ".csv", ".json")):
        return raw.decode("utf-8-sig", errors="replace").strip()
    if name.endswith(".pdf"):
        if not PdfReader:
            raise ValueError("PDF support needs the 'pypdf' package (pip install -r requirements.txt).")
        reader = PdfReader(io.BytesIO(raw))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        if not text:
            raise ValueError("No text found in this PDF. It may be a scan; paste the text instead.")
        return text
    if name.endswith(".docx"):
        if not Document:
            raise ValueError("DOCX support needs the 'python-docx' package (pip install -r requirements.txt).")
        doc = Document(io.BytesIO(raw))
        parts = [p.text for p in doc.paragraphs]
        for t in doc.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        text = "\n".join(parts).strip()
        if not text:
            raise ValueError("This DOCX has no text.")
        return text
    raise ValueError("Unsupported file type. Use PDF, DOCX, TXT or MD.")
