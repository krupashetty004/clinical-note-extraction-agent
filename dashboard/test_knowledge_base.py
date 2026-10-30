from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from dashboard.models import AIConfiguration, KnowledgeDocument


class KnowledgeBaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.admin = user_model.objects.create_user(
            username="knowledge_admin",
            password="secret123",
        )
        cls.admin.groups.add(Group.objects.get_or_create(name="Administrator")[0])

    def setUp(self):
        self.client.force_login(self.admin)

    def test_admin_can_create_and_search_local_document(self):
        response = self.client.post(
            reverse("dashboard:knowledge_document_new"),
            {
                "title": "Asthma management",
                "summary": "Clinical guidance for moderate asthma.",
                "content": "Use bronchodilator therapy and monitor exacerbation symptoms.",
                "is_active": "on",
                "source_title": "Clinical asthma guideline",
                "source_url": "https://example.com/asthma-guideline",
                "source_quote": "Monitor symptoms and adjust therapy to control exacerbations.",
            },
        )

        self.assertEqual(response.status_code, 302)
        document = KnowledgeDocument.objects.get(title="Asthma management")
        self.assertEqual(document.created_by, self.admin)
        self.assertEqual(document.version_number, 1)
        self.assertTrue(document.is_active)
        self.assertEqual(document.source_citations[0]["title"], "Clinical asthma guideline")

        search = self.client.get(reverse("dashboard:knowledge_base"), {"q": "asthma"})
        self.assertContains(search, "Asthma management")

    def test_admin_can_edit_document_and_deactivate_it(self):
        document = KnowledgeDocument.objects.create(
            title="Diabetes notes",
            summary="Draft material",
            content="Monitor glucose and assess for complications.",
            created_by=self.admin,
            source_citations=[
                {
                    "title": "Diabetes guidance",
                    "url": "https://example.com/diabetes",
                    "quote": "Regular monitoring is recommended.",
                }
            ],
        )

        response = self.client.post(
            reverse("dashboard:knowledge_document_edit", kwargs={"doc_id": document.pk}),
            {
                "title": "Diabetes notes",
                "summary": "Updated clinical guidance.",
                "content": "Monitor glucose and assess for complications, including retinopathy.",
                "is_active": "",
                "source_title": "Diabetes guidance",
                "source_url": "https://example.com/diabetes",
                "source_quote": "Regular monitoring is recommended.",
            },
        )

        self.assertEqual(response.status_code, 302)
        document.refresh_from_db()
        self.assertFalse(document.is_active)
        self.assertEqual(document.version_number, 2)
        self.assertEqual(document.deactivated_by, self.admin)

        detail = self.client.get(reverse("dashboard:knowledge_document_detail", kwargs={"doc_id": document.pk}))
        self.assertContains(detail, "Updated clinical guidance.")

    def test_doctor_can_create_document_with_priority_and_voice_control(self):
        doctor = get_user_model().objects.create_user(
            username="knowledge_doctor",
            password="secret123",
        )
        doctor.groups.add(Group.objects.get_or_create(name="Doctor")[0])
        self.client.force_login(doctor)

        response = self.client.post(
            reverse("dashboard:knowledge_document_new"),
            {
                "title": "Urgent local guidance",
                "summary": "High-priority guidance.",
                "content": "Review this guidance before other documents.",
                "priority": "25",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        document = KnowledgeDocument.objects.get(title="Urgent local guidance")
        self.assertEqual(document.priority, 25)
        form_page = self.client.get(reverse("dashboard:knowledge_document_edit", kwargs={"doc_id": document.pk}))
        self.assertContains(form_page, "data-voice-input")
        self.assertContains(form_page, 'aria-label="Dictate content"')

    def test_priority_sort_is_descending_and_title_sort_is_available(self):
        KnowledgeDocument.objects.create(
            title="Low priority",
            content="Content",
            priority=1,
            created_by=self.admin,
        )
        KnowledgeDocument.objects.create(
            title="High priority",
            content="Content",
            priority=10,
            created_by=self.admin,
        )

        response = self.client.get(
            reverse("dashboard:knowledge_base"),
            {"sort": "priority"},
        )
        documents = list(response.context["documents"])
        self.assertEqual(
            [document.title for document in documents[:2]],
            ["High priority", "Low priority"],
        )
        self.assertContains(
            self.client.get(
                reverse("dashboard:knowledge_base"),
                {"sort": "title"},
            ),
            "Title (A-Z)",
        )

    def test_pdf_upload_extracts_local_text_into_inactive_review_draft(self):
        response = self.client.post(
            reverse("dashboard:knowledge_document_new"),
            {
                "title": "Uploaded guidance",
                "summary": "Imported source",
                "priority": "5",
                "is_active": "on",
                "source_file": SimpleUploadedFile(
                    "guidance.txt",
                    b"Review this extracted guidance before publishing.",
                    content_type="text/plain",
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        document = KnowledgeDocument.objects.get(title="Uploaded guidance")
        self.assertFalse(document.is_active)
        self.assertEqual(document.ingestion_status, "needs_review")
        self.assertEqual(document.source_type, "text")
        self.assertIn("Review this extracted guidance", document.content)
        edit_page = self.client.get(response.url)
        self.assertContains(edit_page, "Review this extracted guidance")

    def test_reviewed_upload_is_published_before_rag_can_retrieve_it(self):
        document = KnowledgeDocument.objects.create(
            title="Uploaded hypertension guidance",
            content="Hypertension management includes appropriate follow-up.",
            ingestion_status="needs_review",
            is_active=False,
            created_by=self.admin,
        )

        response = self.client.post(
            reverse("dashboard:knowledge_document_edit", kwargs={"doc_id": document.pk}),
            {
                "title": document.title,
                "summary": "Reviewed local guidance.",
                "content": document.content,
                "is_active": "on",
                "priority": "2",
                "source_title": "Synthetic guideline",
                "source_url": "https://example.test/guideline",
                "source_quote": "Synthetic quote.",
            },
        )

        self.assertEqual(response.status_code, 302)
        document.refresh_from_db()
        self.assertTrue(document.is_active)
        self.assertEqual(document.ingestion_status, "published")

    def test_unsupported_upload_is_rejected(self):
        response = self.client.post(
            reverse("dashboard:knowledge_document_new"),
            {
                "title": "Unsafe source",
                "summary": "",
                "source_file": SimpleUploadedFile(
                    "source.exe",
                    b"not supported",
                    content_type="application/octet-stream",
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unsupported file type")

    def test_invalid_pdf_signature_is_rejected(self):
        response = self.client.post(
            reverse("dashboard:knowledge_document_new"),
            {
                "title": "Invalid PDF",
                "source_file": SimpleUploadedFile(
                    "source.pdf",
                    b"not a pdf",
                    content_type="application/pdf",
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid PDF")

    def test_settings_shows_remaining_usage_for_draft_configuration(self):
        self.client.post(
            reverse("dashboard:settings"),
            {
                "provider": "synthetic",
                "model": "local-synthetic-v1",
                "temperature": "0",
                "max_tokens": "1024",
                "request_limit": "20",
                "token_limit": "2000",
                "action": "save_draft",
            },
        )
        response = self.client.get(reverse("dashboard:settings"))
        self.assertContains(response, "0 requests used", status_code=200)
        self.assertContains(response, "Requests remaining")

    def test_admin_can_open_ai_settings_and_voice_button_is_icon_based(self):
        settings_page = self.client.get(reverse("dashboard:settings"))
        self.assertEqual(settings_page.status_code, 200)
        self.assertContains(settings_page, "Test connection")

        document = self.client.get(reverse("dashboard:knowledge_document_new"))
        self.assertContains(document, "data-voice-input")
        self.assertContains(document, "composer-icon-button")
        self.assertContains(document, 'aria-label="Attach a file"')
        self.assertNotContains(document, "Start voice input</button>")

    def test_ai_settings_requires_a_passed_test_before_activation(self):
        response = self.client.post(
            reverse("dashboard:settings"),
            {
                "provider": "synthetic",
                "model": "local-synthetic-v1",
                "temperature": "0",
                "max_tokens": "1024",
                "action": "activate",
            },
        )

        self.assertEqual(response.status_code, 200)
        configuration = AIConfiguration.objects.get()
        self.assertFalse(configuration.is_active)
        self.assertContains(response, "Test this configuration successfully before activation.")

    def test_ai_settings_renders_model_options_and_encrypts_entered_api_key(self):
        response = self.client.get(reverse("dashboard:settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="local-synthetic-v1"')
        self.assertContains(response, 'value="openai/gpt-oss-20b"')
        self.assertContains(response, 'value="openai/gpt-oss-120b"')
        self.assertContains(response, 'value="qwen/qwen3.8-27b"')
        self.assertNotContains(response, "llama-3.3-70b-versatile")
        self.assertNotContains(response, "llama-3.2-11b-vision-preview")
        self.assertContains(response, 'name="api_key"')

        self.client.post(
            reverse("dashboard:settings"),
            {
                "provider": "groq",
                "model": "openai/gpt-oss-20b",
                "temperature": "0",
                "max_tokens": "1024",
                "api_key": "gsk-test-secret",
                "action": "save_draft",
            },
        )
        configuration = AIConfiguration.objects.get()
        self.assertTrue(configuration.has_api_key())
        self.assertNotIn("gsk-test-secret", configuration.api_key_encrypted)

    def test_ai_settings_can_test_and_activate_synthetic_configuration(self):
        response = self.client.post(
            reverse("dashboard:settings"),
            {
                "provider": "synthetic",
                "model": "local-synthetic-v1",
                "temperature": "0",
                "max_tokens": "1024",
                "action": "test",
            },
        )

        self.assertEqual(response.status_code, 200)
        configuration = AIConfiguration.objects.get()
        self.assertEqual(configuration.last_test_status, "passed")
        self.assertContains(response, "Synthetic configuration validated locally")

        response = self.client.post(
            reverse("dashboard:settings"),
            {
                "provider": "synthetic",
                "model": "local-synthetic-v1",
                "temperature": "0",
                "max_tokens": "1024",
                "action": "activate",
            },
        )

        self.assertEqual(response.status_code, 200)
        configuration.refresh_from_db()
        self.assertTrue(configuration.is_active)
        self.assertEqual(configuration.activated_by, self.admin)

    @override_settings(GROQ_PROVIDER_ENABLED=True)
    @patch("dashboard.extraction.groq_provider.GroqExtractionProvider")
    def test_groq_connection_test_uses_saved_key_and_model_with_synthetic_input(
        self,
        mock_provider_class,
    ):
        mock_provider = mock_provider_class.return_value
        mock_provider.extract.return_value = {
            "items": [],
            "needs_review": True,
            "review_reasons": ["Synthetic provider test only."],
        }

        response = self.client.post(
            reverse("dashboard:settings"),
            {
                "provider": "groq",
                "model": "openai/gpt-oss-120b",
                "temperature": "0",
                "max_tokens": "1024",
                "api_key": "gsk-synthetic-test-key",
                "action": "test",
            },
        )

        self.assertEqual(response.status_code, 200)
        configuration = AIConfiguration.objects.get()
        self.assertEqual(configuration.last_test_status, "passed")
        self.assertEqual(configuration.model, "openai/gpt-oss-120b")
        self.assertEqual(len(configuration.tested_fingerprint), 64)
        mock_provider_class.assert_called_once_with(
            api_key="gsk-synthetic-test-key",
            model="openai/gpt-oss-120b",
            temperature=0.0,
            max_completion_tokens=1024,
        )
        test_note = mock_provider.extract.call_args.args[0]
        self.assertIn("Synthetic provider connectivity test", test_note)
        self.assertNotIn("AI-PROC-001", test_note)

        activated = self.client.post(
            reverse("dashboard:settings"),
            {
                "provider": "groq",
                "model": "openai/gpt-oss-120b",
                "temperature": "0",
                "max_tokens": "1024",
                "api_key": "********",
                "action": "activate",
            },
        )
        self.assertEqual(activated.status_code, 200)
        configuration.refresh_from_db()
        self.assertTrue(configuration.is_active)
        self.assertEqual(configuration.activated_by, self.admin)

    def test_ai_configuration_cannot_activate_after_tested_values_change(self):
        self.client.post(
            reverse("dashboard:settings"),
            {
                "provider": "synthetic",
                "model": "local-synthetic-v1",
                "temperature": "0",
                "max_tokens": "1024",
                "action": "test",
            },
        )
        configuration = AIConfiguration.objects.get()
        self.assertEqual(configuration.last_test_status, "passed")

        response = self.client.post(
            reverse("dashboard:settings"),
            {
                "provider": "synthetic",
                "model": "local-synthetic-v1",
                "temperature": "0.5",
                "max_tokens": "1024",
                "action": "activate",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configuration values or credentials changed")
        configuration.refresh_from_db()
        self.assertFalse(configuration.is_active)
        self.assertEqual(configuration.last_test_status, "not_tested")
        self.assertEqual(configuration.tested_fingerprint, "")
        self.assertFalse(AIConfiguration.objects.filter(is_active=True).exists())

    def test_ai_settings_does_not_activate_live_provider_without_local_test(self):
        response = self.client.post(
            reverse("dashboard:settings"),
            {
                "provider": "groq",
                "model": "openai/gpt-oss-20b",
                "temperature": "0",
                "max_tokens": "1024",
                "action": "test",
            },
        )

        self.assertEqual(response.status_code, 200)
        configuration = AIConfiguration.objects.get()
        self.assertEqual(configuration.last_test_status, "blocked")
        self.assertFalse(configuration.is_active)
        self.assertContains(response, "Live provider testing is disabled")
