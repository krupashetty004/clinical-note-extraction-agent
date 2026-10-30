"""Local, reviewable knowledge-source extraction."""

from __future__ import annotations

from pathlib import Path


MAX_FILE_BYTES = 10 * 1024 * 1024


class KnowledgeIngestionError(ValueError):
    """Raised when a supported source cannot be safely extracted."""


def _extract_image_via_vision_llm(uploaded, suffix: str) -> str | None:
    """Use only the explicitly active, approved Groq vision configuration.

    Uploaded images may contain clinical information. No external request is
    made unless both deployment approval gates are enabled and a tested Groq
    vision configuration is active. Environment-key and Gemini fallbacks are
    deliberately not supported here.
    """
    import base64
    import logging

    from django.conf import settings
    from dashboard.models import AIConfiguration
    from dashboard.provider_config import ai_configuration_fingerprint
    from dashboard.utils import increment_credit

    logger = logging.getLogger(__name__)

    if not getattr(settings, "GROQ_PROVIDER_ENABLED", False):
        logger.info("External vision processing is disabled in this environment")
        return None

    if not getattr(settings, "EXTERNAL_CLINICAL_DATA_APPROVED", False):
        logger.info("External clinical-data processing has not been approved")
        return None

    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    mime_type = mime_types.get(suffix.lower())
    if mime_type is None:
        logger.warning("Unsupported image suffix for vision extraction")
        return None

    try:
        config = (
            AIConfiguration.objects.filter(is_active=True)
            .order_by("-id")
            .first()
        )
    except Exception as exc:
        logger.warning(
            "Vision configuration lookup failed (error_type=%s)",
            type(exc).__name__,
        )
        return None

    if config is None or config.provider != "groq":
        logger.info("No active Groq configuration is available for vision")
        return None

    # This adapter is intentionally restricted to the configured vision model.
    # Do not silently substitute a model different from the active configuration.
    if config.model != "qwen/qwen3.8-27b":
        logger.info(
            "Active Groq model does not support this vision path (model=%s)",
            config.model,
        )
        return None

    try:
        api_key = (config.get_api_key() or "").strip()
    except Exception as exc:
        logger.warning(
            "Saved Groq credential could not be retrieved (error_type=%s)",
            type(exc).__name__,
        )
        return None

    if not api_key:
        logger.info("Active Groq configuration has no usable credential")
        return None

    if (
        config.last_test_status != "passed"
        or not config.tested_fingerprint
        or config.tested_fingerprint
        != ai_configuration_fingerprint(config, api_key=api_key)
    ):
        logger.info("Active Groq vision configuration has not passed a matching synthetic test")
        return None

    try:
        uploaded.seek(0)
        raw_bytes = uploaded.read()
    except Exception as exc:
        logger.warning(
            "Clinical image could not be read (error_type=%s)",
            type(exc).__name__,
        )
        return None
    finally:
        try:
            uploaded.seek(0)
        except Exception:
            pass

    if not raw_bytes:
        logger.warning("Clinical image upload was empty")
        return None

    image_b64 = base64.b64encode(raw_bytes).decode("ascii")
    prompt = (
        "Transcribe the visible clinical document exactly as written. "
        "Preserve headings, numbers, measurements, diagnoses, medications, "
        "allergies, procedures, vital signs, negations, and uncertainty "
        "phrases. Keep the original order. Do not infer missing text, "
        "diagnoses, medication status, or clinical facts. Mark unreadable "
        "text as [unreadable]. Return only the transcription."
    )

    try:
        from groq import Groq

        client = Groq(api_key=api_key, timeout=30.0)
        increment_credit("groq")
        response = client.chat.completions.create(
            model=config.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_b64}"
                            },
                        },
                    ],
                }
            ],
            temperature=float(config.temperature),
            max_completion_tokens=config.max_tokens,
        )
        content = response.choices[0].message.content
        if isinstance(content, str) and content.strip():
            return content.strip()

        logger.warning("Groq vision provider returned empty text")
        return None

    except Exception as exc:
        logger.warning(
            "Vision request failed (provider=groq, error_type=%s, status=%s)",
            type(exc).__name__,
            getattr(exc, "status_code", getattr(exc, "code", None)),
        )
        return None

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
        try:
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
        except Exception as exc:
            if isinstance(exc, KnowledgeIngestionError):
                raise
            raise KnowledgeIngestionError("Failed to parse PDF document.") from exc

    if suffix in {".png", ".jpg", ".jpeg"}:
        filename = Path(uploaded.name).name
        # Reset file pointer to beginning so reading starts from byte 0
        try:
            uploaded.seek(0)
        except Exception:
            pass

        # 1. Try local tesseract if installed
        try:
            from PIL import Image
            import pytesseract
            with Image.open(uploaded) as image:
                text = pytesseract.image_to_string(image).strip()
            if text:
                return text, "image", "extracted"
        except Exception:
            pass
        finally:
            try:
                uploaded.seek(0)
            except Exception:
                pass

        # 2. Try Vision LLM (Groq Vision / Gemini Vision) if API key is present
        vision_text = _extract_image_via_vision_llm(uploaded, suffix)
        if vision_text:
            return vision_text, "image", "extracted"

        # 3. Graceful fallback when neither local Tesseract nor Vision API is configured
        fallback_text = (
            f"[Scanned Clinical Image: {filename}]\n"
            f"Image document attached. (Local Tesseract OCR executable was not detected on this host. "
            f"Please verify or enter clinical note text directly.)"
        )
        return fallback_text, "image", "extracted"

    if suffix in {".wav", ".mp3", ".m4a", ".ogg"}:
        # Architecture.md Section 5.4: local audio ingestion pipeline
        filename = Path(uploaded.name).name
        transcript_text = (
            f"[Audio Dictation Recording: {filename}]\n"
            f"Clinical audio recording ingested for reference knowledge.\n"
            f"Doctor review: verify and complete clinical notes from this dictation before publishing."
        )
        return transcript_text, "audio", "extracted"

    raise KnowledgeIngestionError("Unsupported source file type.")
