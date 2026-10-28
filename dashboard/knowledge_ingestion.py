"""Local, reviewable knowledge-source extraction."""

from __future__ import annotations

from pathlib import Path


MAX_FILE_BYTES = 10 * 1024 * 1024


class KnowledgeIngestionError(ValueError):
    """Raised when a supported source cannot be safely extracted."""


def extract_uploaded_source(uploaded) -> tuple[str, str, str]:
    """Return extracted text, source type, and a safe status message."""
    suffix = Path(uploaded.name).suffix.lower()
    if suffix in {".txt", ".md"}:
        try:
            return uploaded.read().decode("utf-8"), "text", "extracted"
        except UnicodeDecodeError as exc:
            raise KnowledgeIngestionError("Text files must use UTF-8 encoding.") from exc

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise KnowledgeIngestionError(
                "PDF extraction is unavailable because the local PDF reader is not installed."
            ) from exc
        reader = PdfReader(uploaded)
        pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"[Page {page_number}]\n{text}")
        if not pages:
            raise KnowledgeIngestionError(
                "This PDF has no selectable text. Local OCR rendering is not installed; review or convert it to text first."
            )
        return "\n\n".join(pages), "pdf", "extracted"

    if suffix in {".png", ".jpg", ".jpeg"}:
        try:
            from PIL import Image
            import pytesseract
        except ImportError as exc:
            raise KnowledgeIngestionError(
                "Image OCR is unavailable because the local OCR packages are not installed."
            ) from exc
        try:
            with Image.open(uploaded) as image:
                text = pytesseract.image_to_string(image).strip()
        except Exception as exc:
            raise KnowledgeIngestionError(
                "Local image OCR failed. Confirm that the Tesseract OCR executable is installed."
            ) from exc
        if not text:
            raise KnowledgeIngestionError("Local OCR found no readable text in the image.")
        return text, "image", "extracted"

    raise KnowledgeIngestionError("Unsupported source file type.")
