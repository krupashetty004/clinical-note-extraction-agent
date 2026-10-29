import os
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from dashboard.knowledge_ingestion import _extract_image_via_vision_llm


class VisionIngestionTests(SimpleTestCase):
    """Tests image transcription without external API calls."""

    def configure_active_groq(self, config_class):
        config = MagicMock()
        config.provider = "groq"
        config.get_api_key.return_value = "unit-test-key"

        (
            config_class.objects.filter.return_value
            .order_by.return_value
            .first.return_value
        ) = config

        return config

    def test_groq_vision_returns_transcribed_text_in_one_request(self):
        expected_text = (
            "Assessment: possible musculoskeletal injury causing chest pain."
        )

        with (
            patch("dashboard.models.AIConfiguration") as config_class,
            patch("groq.Groq") as groq_class,
            patch("dashboard.utils.increment_credit") as credit_counter,
        ):
            self.configure_active_groq(config_class)

            response = MagicMock()
            response.choices[0].message.content = expected_text
            groq_class.return_value.chat.completions.create.return_value = response

            uploaded = SimpleUploadedFile(
                "synthetic.png",
                b"synthetic-image-bytes",
                content_type="image/png",
            )

            result = _extract_image_via_vision_llm(uploaded, ".png")

            self.assertEqual(result, expected_text)
            groq_class.assert_called_once_with(
                api_key="unit-test-key",
                timeout=30.0,
            )
            groq_class.return_value.chat.completions.create.assert_called_once()
            credit_counter.assert_called_once_with("groq")

            request = (
                groq_class.return_value.chat.completions.create.call_args.kwargs
            )
            image_url = request["messages"][0]["content"][1]["image_url"]["url"]
            self.assertTrue(image_url.startswith("data:image/png;base64,"))
            self.assertEqual(request["model"], "qwen/qwen3.8-27b")

    def test_missing_configuration_does_not_call_provider(self):
        with (
            patch.dict(
                os.environ,
                {"GROQ_API_KEY": "", "GEMINI_API_KEY": ""},
            ),
            patch("dashboard.models.AIConfiguration") as config_class,
            patch("groq.Groq") as groq_class,
            patch("dashboard.utils.increment_credit") as credit_counter,
        ):
            (
                config_class.objects.filter.return_value
                .order_by.return_value
                .first.return_value
            ) = None

            uploaded = SimpleUploadedFile(
                "synthetic.png",
                b"synthetic-image-bytes",
                content_type="image/png",
            )

            result = _extract_image_via_vision_llm(uploaded, ".png")

            self.assertIsNone(result)
            groq_class.assert_not_called()
            credit_counter.assert_not_called()

    def test_provider_failure_does_not_retry(self):
        with (
            patch("dashboard.models.AIConfiguration") as config_class,
            patch("groq.Groq") as groq_class,
            patch("dashboard.utils.increment_credit") as credit_counter,
        ):
            self.configure_active_groq(config_class)

            groq_class.return_value.chat.completions.create.side_effect = (
                RuntimeError("synthetic provider failure")
            )

            uploaded = SimpleUploadedFile(
                "synthetic.png",
                b"synthetic-image-bytes",
                content_type="image/png",
            )

            result = _extract_image_via_vision_llm(uploaded, ".png")

            self.assertIsNone(result)
            groq_class.return_value.chat.completions.create.assert_called_once()
            credit_counter.assert_called_once_with("groq")
