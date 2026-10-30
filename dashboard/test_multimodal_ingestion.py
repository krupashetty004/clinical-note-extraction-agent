"""Synthetic tests for scanned-PDF OCR and gated audio transcription."""
from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from dashboard.forms import KnowledgeDocumentForm
from dashboard.knowledge_ingestion import (
    AUDIO_TRANSCRIPTION_MODEL,
    KnowledgeIngestionError,
    extract_uploaded_source,
)
from dashboard.provider_config import ai_configuration_fingerprint


class MultimodalIngestionTests(SimpleTestCase):
    def _configure_active_groq(self, config_class):
        config = MagicMock()
        config.provider = "groq"
        config.model = "qwen/qwen3.8-27b"
        config.temperature = 0.0
        config.max_tokens = 2048
        config.get_api_key.return_value = "synthetic-audio-test-key"
        config.last_test_status = "passed"
        config.tested_fingerprint = ai_configuration_fingerprint(
            config,
            api_key="synthetic-audio-test-key",
        )
        (
            config_class.objects.filter.return_value
            .order_by.return_value
            .first.return_value
        ) = config
        return config

    @staticmethod
    def _audio_upload():
        return SimpleUploadedFile(
            "synthetic-dictation.wav",
            b"synthetic-audio-bytes",
            content_type="audio/wav",
        )

    @staticmethod
    def _pdf_upload():
        return SimpleUploadedFile(
            "synthetic-scanned-note.pdf",
            b"%PDF-1.7 synthetic fixture",
            content_type="application/pdf",
        )

    @override_settings(GROQ_PROVIDER_ENABLED=True, EXTERNAL_CLINICAL_DATA_APPROVED=True)
    @patch("dashboard.knowledge_ingestion._render_pdf_page_png", return_value=BytesIO(b"synthetic png"))
    @patch("PIL.Image.open")
    @patch("pytesseract.image_to_string", return_value="Assessment: hypertension.")
    @patch("pypdf.PdfReader")
    @patch("pypdfium2.PdfDocument")
    def test_scanned_pdf_uses_local_tesseract_and_requires_review(
        self,
        pdf_document_class,
        pdf_reader_class,
        tesseract_call,
        image_open,
        _render_page,
    ):
        reader_page = MagicMock()
        reader_page.extract_text.return_value = ""
        pdf_reader_class.return_value.pages = [reader_page]

        pdf_page = MagicMock()
        pdf_document_class.return_value.__len__.return_value = 1
        pdf_document_class.return_value.__getitem__.return_value = pdf_page

        image = MagicMock()
        image_open.return_value.__enter__.return_value = image

        text, source_type, status = extract_uploaded_source(self._pdf_upload())

        self.assertIn("Assessment: hypertension.", text)
        self.assertEqual(source_type, "pdf")
        self.assertEqual(status, "needs_review")
        tesseract_call.assert_called_once_with(image)
        pdf_document_class.assert_called_once()

    @override_settings(GROQ_PROVIDER_ENABLED=False, EXTERNAL_CLINICAL_DATA_APPROVED=False)
    @patch("dashboard.knowledge_ingestion._render_pdf_page_png", return_value=BytesIO(b"synthetic png"))
    @patch("PIL.Image.open")
    @patch("pytesseract.image_to_string", return_value="")
    @patch("dashboard.knowledge_ingestion._extract_image_via_vision_llm", return_value=None)
    @patch("pypdf.PdfReader")
    @patch("pypdfium2.PdfDocument")
    def test_scanned_pdf_without_available_ocr_is_rejected_not_replaced_by_placeholder(
        self,
        pdf_document_class,
        _pdf_reader_class,
        _vision,
        _tesseract,
        image_open,
        _render_page,
    ):
        reader_page = MagicMock()
        reader_page.extract_text.return_value = ""
        _pdf_reader_class.return_value.pages = [reader_page]
        pdf_document_class.return_value.__len__.return_value = 1
        image_open.return_value.__enter__.return_value = MagicMock()

        with self.assertRaisesRegex(KnowledgeIngestionError, "Scanned PDF page 1"):
            extract_uploaded_source(self._pdf_upload())

    @override_settings(GROQ_PROVIDER_ENABLED=True, EXTERNAL_CLINICAL_DATA_APPROVED=True)
    @patch("dashboard.models.AIConfiguration")
    @patch("groq.Groq")
    @patch("dashboard.utils.increment_credit")
    def test_audio_uses_approved_tested_credential_and_whisper_transcription(
        self,
        increment_credit,
        groq_class,
        config_class,
    ):
        self._configure_active_groq(config_class)
        expected = (
            "Assessment: possible pneumonia. "
            "Start amoxicillin 500 mg three times daily."
        )
        groq_class.return_value.audio.transcriptions.create.return_value.text = expected

        text, source_type, status = extract_uploaded_source(self._audio_upload())

        self.assertEqual(text, expected)
        self.assertEqual(source_type, "audio")
        self.assertEqual(status, "needs_review")
        groq_class.assert_called_once_with(
            api_key="synthetic-audio-test-key",
            timeout=60.0,
            max_retries=0,
        )
        request = (
            groq_class.return_value.audio.transcriptions.create.call_args.kwargs
        )
        self.assertEqual(request["model"], AUDIO_TRANSCRIPTION_MODEL)
        self.assertEqual(request["response_format"], "json")
        self.assertEqual(request["temperature"], 0.0)
        self.assertEqual(request["file"][0], "synthetic-dictation.wav")
        self.assertEqual(request["file"][1], b"synthetic-audio-bytes")
        self.assertIn("Do not infer", request["prompt"])
        increment_credit.assert_called_once_with("groq")

    @override_settings(GROQ_PROVIDER_ENABLED=True, EXTERNAL_CLINICAL_DATA_APPROVED=False)
    @patch("dashboard.models.AIConfiguration")
    @patch("groq.Groq")
    def test_audio_is_blocked_before_configuration_lookup_without_data_approval(
        self,
        groq_class,
        config_class,
    ):
        with self.assertRaisesRegex(KnowledgeIngestionError, "Audio transcription is unavailable"):
            extract_uploaded_source(self._audio_upload())

        config_class.objects.filter.assert_not_called()
        groq_class.assert_not_called()

    @override_settings(GROQ_PROVIDER_ENABLED=True, EXTERNAL_CLINICAL_DATA_APPROVED=True)
    @patch("dashboard.models.AIConfiguration")
    @patch("groq.Groq")
    def test_audio_requires_matching_successful_provider_configuration_test(
        self,
        groq_class,
        config_class,
    ):
        config = self._configure_active_groq(config_class)
        config.tested_fingerprint = "0" * 64

        with self.assertRaisesRegex(KnowledgeIngestionError, "Audio transcription is unavailable"):
            extract_uploaded_source(self._audio_upload())

        groq_class.assert_not_called()

    def test_knowledge_document_form_accepts_audio_for_review_ingestion(self):
        audio = SimpleUploadedFile(
            "synthetic-dictation.wav",
            b"RIFF" + bytes([0, 0, 0, 0]) + b"WAVE" + b"data",
            content_type="audio/wav",
        )
        form = KnowledgeDocumentForm(
            data={
                "title": "Synthetic audio reference",
                "summary": "Synthetic test fixture",
                "content": "",
                "priority": "0",
                "is_active": "",
            },
            files={"source_file": audio},
        )

        self.assertTrue(form.is_valid(), form.errors.as_text())
        self.assertEqual(
            form.cleaned_data["source_file"].name,
            "synthetic-dictation.wav",
        )

    def test_knowledge_document_form_rejects_invalid_audio_signature(self):
        audio = SimpleUploadedFile(
            "synthetic-dictation.wav",
            b"not-a-wave-file",
            content_type="audio/wav",
        )
        form = KnowledgeDocumentForm(
            data={
                "title": "Invalid audio fixture",
                "summary": "",
                "content": "",
                "priority": "0",
                "is_active": "",
            },
            files={"source_file": audio},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("valid WAV audio file", str(form.errors))

    def test_uploaded_files_over_ten_megabytes_are_rejected(self):
        upload = SimpleUploadedFile(
            "too-large.txt",
            b"x" * (10 * 1024 * 1024 + 1),
            content_type="text/plain",
        )
        with self.assertRaisesRegex(KnowledgeIngestionError, "10 MB or smaller"):
            extract_uploaded_source(upload)
