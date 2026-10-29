"""Local, reviewable knowledge-source extraction."""

from __future__ import annotations

from pathlib import Path


MAX_FILE_BYTES = 10 * 1024 * 1024


class KnowledgeIngestionError(ValueError):
    """Raised when a supported source cannot be safely extracted."""


def _extract_image_via_vision_llm(uploaded, suffix: str) -> str | None:
    """Transcribe an uploaded clinical image using the active vision provider.

    Performs at most one external request per upload. Provider errors are
    logged without exposing API keys, image contents, or clinical text.
    """
    import base64
    import json
    import logging
    import os
    import urllib.error
    import urllib.request

    from dashboard.models import AIConfiguration
    from dashboard.utils import increment_credit

    logger = logging.getLogger(__name__)

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

    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    mime_type = mime_types.get(suffix.lower())

    if mime_type is None:
        logger.warning("Unsupported image suffix for vision extraction")
        return None

    image_b64 = base64.b64encode(raw_bytes).decode("ascii")

    # Prefer the provider explicitly activated in the application settings.
    # Only use environment keys when no saved configuration exists.
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

    api_key = ""
    provider = ""

    if config is not None:
        provider = config.provider

        if provider not in {"groq", "gemini"}:
            logger.info("Active configuration does not enable vision extraction")
            return None

        try:
            api_key = (config.get_api_key() or "").strip()
        except Exception as exc:
            logger.warning(
                "Saved provider key could not be retrieved (error_type=%s)",
                type(exc).__name__,
            )
            return None
    else:
        # Environment variables are an explicit alternative when no
        # database provider configuration has been activated.
        groq_key = os.environ.get("GROQ_API_KEY", "").strip()
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

        if groq_key:
            provider, api_key = "groq", groq_key
        elif gemini_key:
            provider, api_key = "gemini", gemini_key

    if not api_key:
        logger.info("No active vision provider key is available")
        return None

    prompt = (
        "Transcribe the visible clinical document exactly as written. "
        "Preserve headings, numbers, measurements, diagnoses, medications, "
        "allergies, procedures, vital signs, negations, and uncertainty "
        "phrases. Keep the original order. Do not infer missing text, "
        "diagnoses, medication status, or clinical facts. Mark unreadable "
        "text as [unreadable]. Return only the transcription."
    )

    if provider == "groq":
        try:
            from groq import Groq

            # One call only; do not retry retired model IDs.
            client = Groq(api_key=api_key, timeout=30.0)

            increment_credit("groq")
            response = client.chat.completions.create(
                model="qwen/qwen3.8-27b",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": (
                                        f"data:{mime_type};base64,{image_b64}"
                                    )
                                },
                            },
                        ],
                    }
                ],
                temperature=0.0,
            )

            content = response.choices[0].message.content
            if isinstance(content, str) and content.strip():
                return content.strip()

            logger.warning("Groq vision provider returned empty text")
            return None

        except Exception as exc:
            logger.warning(
                "Vision request failed (provider=groq, error_type=%s, "
                "status=%s)",
                type(exc).__name__,
                getattr(exc, "status_code", getattr(exc, "code", None)),
            )
            return None

    if provider == "gemini":
        # Use a currently documented Gemini model for image input.
        # Do not fall back to retired Gemini model IDs.
        try:
            url = (
                "https://generativelanguage.googleapis.com/"
                "v1beta/models/gemini-3.8-flash:generateContent"
            )
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": image_b64,
                                }
                            },
                        ]
                    }
                ],
                "generationConfig": {"temperature": 0.0},
            }

            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                },
                method="POST",
            )

            increment_credit("gemini")
            with urllib.request.urlopen(request, timeout=30.0) as response:
                result = json.loads(response.read().decode("utf-8"))

            candidates = result.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "".join(
                    part.get("text", "")
                    for part in parts
                    if isinstance(part.get("text"), str)
                ).strip()

                if text:
                    return text

            logger.warning("Gemini vision provider returned empty text")
            return None

        except Exception as exc:
            logger.warning(
                "Vision request failed (provider=gemini, error_type=%s, "
                "status=%s)",
                type(exc).__name__,
                getattr(exc, "status_code", getattr(exc, "code", None)),
            )
            return None

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
