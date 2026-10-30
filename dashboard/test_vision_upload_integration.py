from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from dashboard.forms import ClinicalNoteForm
from dashboard.knowledge_ingestion import (
    KnowledgeIngestionError,
    extract_uploaded_source,
)


class VisionUploadIntegrationTests(SimpleTestCase):
    """Verify vision transcription reaches both upload processing paths."""

    def make_image_upload(self):
        return SimpleUploadedFile(
            "synthetic-clinical-note.png",
            b"synthetic-image-bytes",
            content_type="image/png",
        )

    @patch(
        "dashboard.knowledge_ingestion._extract_image_via_vision_llm",
        return_value=(
            "Assessment: possible musculoskeletal injury causing chest pain."
        ),
    )
    @patch("PIL.Image.open", side_effect=OSError("Synthetic OCR unavailable"))
    def test_image_ingestion_returns_vision_transcription(
        self, _mock_image_open, mock_vision
    ):
        uploaded = self.make_image_upload()

        text, source_type, status = extract_uploaded_source(uploaded)

        self.assertIn("possible musculoskeletal injury", text)
        self.assertEqual(source_type, "image")
        self.assertEqual(status, "needs_review")
        mock_vision.assert_called_once()

    @patch(
        "dashboard.forms.extract_uploaded_source",
        return_value=(
            "Assessment: possible musculoskeletal injury causing chest pain.",
            "image",
            "needs_review",
        ),
    )
    def test_clinical_note_form_uses_transcribed_image_text(
        self, mock_extract
    ):
        form = ClinicalNoteForm(
            data={"original_text": ""},
            files={"source_file": self.make_image_upload()},
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "possible musculoskeletal injury",
            form["original_text"].value(),
        )
        self.assertIn(
            "Review and correct the text in the note editor",
            str(form.errors),
        )
        self.assertEqual(
            form.cleaned_data["original_text"],
            "Assessment: possible musculoskeletal injury causing chest pain.",
        )
        mock_extract.assert_called_once()

    @patch(
        "dashboard.knowledge_ingestion._extract_image_via_vision_llm",
        return_value=None,
    )
    @patch("PIL.Image.open", side_effect=OSError("Synthetic OCR unavailable"))
    def test_unreadable_image_is_rejected_without_placeholder_text(
        self, _mock_image_open, _mock_vision
    ):
        with self.assertRaisesRegex(KnowledgeIngestionError, "No image transcription"):
            extract_uploaded_source(self.make_image_upload())

