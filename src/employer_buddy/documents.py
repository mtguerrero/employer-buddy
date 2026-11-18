"""Conversión de archivos recibidos al formato que acepta Claude."""

import io

from docx import Document

from employer_buddy.ai import SourceDocument

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
IMAGES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_BYTES = 20 * 1024 * 1024


class UnsupportedFileError(Exception):
    pass


def docx_text(content: bytes) -> str:
    doc = Document(io.BytesIO(content))
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def to_source(content: bytes, mime_type: str) -> SourceDocument:
    mime = mime_type.split(";")[0].strip().lower()
    if len(content) > MAX_BYTES:
        raise UnsupportedFileError("El archivo pesa más de 20 MB.")
    if mime == PDF or mime in IMAGES:
        return SourceDocument(mime_type=mime, content=content)
    if mime == DOCX:
        return SourceDocument(mime_type="text/plain", text=docx_text(content))
    raise UnsupportedFileError(f"Formato no soportado: {mime or 'desconocido'}")
