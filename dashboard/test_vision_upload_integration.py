from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from dashboard.forms import ClinicalNoteForm
from dashboard.knowledge_ingestion import extract_uploaded_source


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
        self.assertEqual(status, "extracted")
        mock_vision.assert_called_once()

    @patch(
        "dashboard.forms.extract_uploaded_source",
        return_value=(
            "Assessment: possible musculoskeletal injury causing chest pain.",
            "image",
            "extracted",
        ),
    )
    def test_clinical_note_form_uses_transcribed_image_text(
        self, mock_extract
    ):
        form = ClinicalNoteForm(
            data={"original_text": ""},
            files={"source_file": self.make_image_upload()},
        )

        self.assertTrue(form.is_valid(), form.errors.as_text())
        self.assertIn(
            "possible musculoskeletal injury",
            form.cleaned_data["original_text"],
        )
        mock_extract.assert_called_once()

