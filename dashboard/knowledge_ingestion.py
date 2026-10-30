"""Local, reviewable knowledge-source extraction."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path


MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_SCANNED_PDF_PAGES = 10
PDF_RENDER_SCALE = 2.0
AUDIO_TRANSCRIPTION_MODEL = "whisper-large-v3-turbo"


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

def _extract_image_with_local_ocr(image) -> str | None:
    """Run Tesseract locally; absence or failure is represented as no result."""
    try:
        import pytesseract

        text = pytesseract.image_to_string(image)
        cleaned = text.strip() if isinstance(text, str) else ""
        return cleaned or None
    except Exception:
        return None


def _transcribe_audio_via_groq(uploaded, suffix: str) -> str | None:
    """Transcribe audio only with an explicitly approved, tested Groq credential.

    Whisper is a dedicated speech-to-text model; it is separate from the
    active chat/extraction model. No environment-key or Gemini fallback exists.
    """
    import logging

    from django.conf import settings
    from dashboard.models import AIConfiguration
    from dashboard.provider_config import ai_configuration_fingerprint
    from dashboard.utils import increment_credit

    logger = logging.getLogger(__name__)

    if not getattr(settings, "GROQ_PROVIDER_ENABLED", False):
        logger.info("Groq speech transcription is disabled in this environment")
        return None
    if not getattr(settings, "EXTERNAL_CLINICAL_DATA_APPROVED", False):
        logger.info("External clinical-data processing has not been approved")
        return None

    allowed_suffixes = {".wav", ".mp3", ".m4a", ".ogg"}
    if suffix.lower() not in allowed_suffixes:
        return None

    try:
        config = (
            AIConfiguration.objects.filter(is_active=True)
            .order_by("-id")
            .first()
        )
    except Exception as exc:
        logger.warning(
            "Audio configuration lookup failed (error_type=%s)",
            type(exc).__name__,
        )
        return None

    if config is None or config.provider != "groq":
        logger.info("No active Groq configuration is available for transcription")
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
        logger.info("Active Groq configuration has no saved credential")
        return None

    if (
        config.last_test_status != "passed"
        or not config.tested_fingerprint
        or config.tested_fingerprint
        != ai_configuration_fingerprint(config, api_key=api_key)
    ):
        logger.info(
            "Active Groq audio configuration has not passed a matching synthetic test"
        )
        return None

    try:
        uploaded.seek(0)
        raw_bytes = uploaded.read(MAX_FILE_BYTES + 1)
    except Exception as exc:
        logger.warning(
            "Audio upload could not be read (error_type=%s)",
            type(exc).__name__,
        )
        return None
    finally:
        try:
            uploaded.seek(0)
        except Exception:
            pass

    if not raw_bytes or len(raw_bytes) > MAX_FILE_BYTES:
        logger.info("Audio upload is empty or exceeds the configured size limit")
        return None

    prompt = (
        "Transcribe this clinical dictation verbatim in the spoken language. "
        "Preserve medication names, dosages, measurements, negations, uncertainty, "
        "dates, and clinically important wording. Do not infer, summarize, correct, "
        "or add any clinical facts. Mark unintelligible segments as [unintelligible]."
    )

    try:
        from groq import Groq

        client = Groq(api_key=api_key, timeout=60.0, max_retries=0)
        increment_credit("groq")
        response = client.audio.transcriptions.create(
            file=(Path(uploaded.name).name, raw_bytes),
            model=AUDIO_TRANSCRIPTION_MODEL,
            prompt=prompt,
            response_format="json",
            temperature=0.0,
        )
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
        logger.warning("Groq audio transcription returned empty text")
        return None
    except Exception as exc:
        logger.warning(
            "Audio transcription failed (provider=groq, error_type=%s, status=%s)",
            type(exc).__name__,
            getattr(exc, "status_code", getattr(exc, "code", None)),
        )
        return None


def _render_pdf_page_png(pdf_page) -> BytesIO:
    """Render one PDF page to an in-memory PNG using the bundled PDFium runtime."""
    try:
        image = pdf_page.render(scale=PDF_RENDER_SCALE).to_pil()
        image_buffer = BytesIO()
        image.save(image_buffer, format="PNG", optimize=True)
        image_buffer.seek(0)
        return image_buffer
    except Exception as exc:
        raise KnowledgeIngestionError(
            "A scanned PDF page could not be rendered for OCR."
        ) from exc


def extract_uploaded_source(uploaded) -> tuple[str, str, str]:
    """Return extracted text, source type, and review status.

    This function never returns filename/placeholder text as a transcription.
    OCR and speech transcripts are marked needs_review. The calling UI must
    keep them inactive or require the doctor to review them before processing.
    """
    suffix = Path(uploaded.name).suffix.lower()

    try:
        uploaded_size = int(getattr(uploaded, "size", 0) or 0)
    except (TypeError, ValueError):
        uploaded_size = 0
    if uploaded_size > MAX_FILE_BYTES:
        raise KnowledgeIngestionError(
            "Files must be 10 MB or smaller."
        )

    if suffix in {".txt", ".md"}:
        try:
            uploaded.seek(0)
            text = uploaded.read().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise KnowledgeIngestionError(
                "Text files must use UTF-8 encoding."
            ) from exc
        except Exception as exc:
            raise KnowledgeIngestionError(
                "The uploaded text file could not be read."
            ) from exc
        if not text.strip():
            raise KnowledgeIngestionError("The uploaded text file is empty.")
        return text, "text", "extracted"

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise KnowledgeIngestionError(
                "PDF extraction is unavailable because the local PDF reader is not installed."
            ) from exc

        try:
            uploaded.seek(0)
            reader = PdfReader(uploaded)
            page_texts = [
                (page.extract_text() or "").strip()
                for page in reader.pages
            ]
        except Exception as exc:
            raise KnowledgeIngestionError(
                "Failed to parse PDF document."
            ) from exc

        if not page_texts:
            raise KnowledgeIngestionError("The PDF contains no pages.")
        if len(page_texts) > MAX_PDF_PAGES:
            raise KnowledgeIngestionError(
                f"PDFs are limited to {MAX_PDF_PAGES} pages per upload."
            )

        scanned_indexes = [
            index for index, page_text in enumerate(page_texts) if not page_text
        ]
        if not scanned_indexes:
            return (
                "\n\n".join(
                    f"[Page {index + 1}]\n{text}"
                    for index, text in enumerate(page_texts)
                ),
                "pdf",
                "extracted",
            )

        if len(scanned_indexes) > MAX_SCANNED_PDF_PAGES:
            raise KnowledgeIngestionError(
                f"This PDF has {len(scanned_indexes)} scanned pages. "
                f"The current OCR path supports at most {MAX_SCANNED_PDF_PAGES} "
                "scanned pages per upload; split the PDF and upload it in parts."
            )

        try:
            import pypdfium2 as pdfium
        except ImportError as exc:
            raise KnowledgeIngestionError(
                "Scanned-PDF OCR is unavailable because the PDF renderer is not installed."
            ) from exc

        try:
            uploaded.seek(0)
            pdf_bytes = uploaded.read(MAX_FILE_BYTES + 1)
            if len(pdf_bytes) > MAX_FILE_BYTES:
                raise KnowledgeIngestionError("Files must be 10 MB or smaller.")
            pdf_document = pdfium.PdfDocument(pdf_bytes)
        except KnowledgeIngestionError:
            raise
        except Exception as exc:
            raise KnowledgeIngestionError(
                "The scanned PDF could not be opened for OCR."
            ) from exc

        try:
            if len(pdf_document) != len(page_texts):
                raise KnowledgeIngestionError(
                    "The PDF page count changed during OCR preparation."
                )

            for page_index in scanned_indexes:
                page_image = _render_pdf_page_png(pdf_document[page_index])
                try:
                    from PIL import Image

                    with Image.open(page_image) as image:
                        extracted = _extract_image_with_local_ocr(image)
                except Exception:
                    extracted = None

                if not extracted:
                    page_image.seek(0)
                    extracted = _extract_image_via_vision_llm(
                        page_image,
                        ".png",
                    )

                if not extracted:
                    raise KnowledgeIngestionError(
                        f"Scanned PDF page {page_index + 1} could not be transcribed. "
                        "Install local Tesseract OCR or configure an approved, "
                        "successfully tested Groq vision provider. No placeholder "
                        "text was generated."
                    )
                page_texts[page_index] = extracted
        finally:
            try:
                pdf_document.close()
            except Exception:
                pass

        return (
            "\n\n".join(
                f"[Page {index + 1}]\n{text}"
                for index, text in enumerate(page_texts)
            ),
            "pdf",
            "needs_review",
        )

    if suffix in {".png", ".jpg", ".jpeg"}:
        try:
            uploaded.seek(0)
            from PIL import Image

            with Image.open(uploaded) as image:
                text = _extract_image_with_local_ocr(image)
        except Exception:
            text = None
        finally:
            try:
                uploaded.seek(0)
            except Exception:
                pass

        if not text:
            text = _extract_image_via_vision_llm(uploaded, suffix)

        if not text:
            raise KnowledgeIngestionError(
                "No image transcription was produced. Install local Tesseract OCR "
                "or configure an approved, successfully tested Groq vision provider. "
                "No filename placeholder was added to the clinical text."
            )
        return text, "image", "needs_review"

    if suffix in {".wav", ".mp3", ".m4a", ".ogg"}:
        transcript = _transcribe_audio_via_groq(uploaded, suffix)
        if not transcript:
            raise KnowledgeIngestionError(
                "Audio transcription is unavailable. Enable the approved Groq "
                "provider after privacy/security approval and complete a successful "
                "synthetic connection test. No audio placeholder was added to the "
                "clinical text."
            )
        return transcript, "audio", "needs_review"

    raise KnowledgeIngestionError("Unsupported source file type.")
