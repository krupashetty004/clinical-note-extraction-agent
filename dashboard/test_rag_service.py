from django.contrib.auth import get_user_model
from django.test import TestCase

from dashboard.extraction.rag_service import (
    chunk_text,
    retrieve_knowledge_passages,
    score_passage,
)
from dashboard.models import KnowledgeDocument


class RAGServiceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="rag_author",
            password="secretpassword",
        )

        self.doc1 = KnowledgeDocument.objects.create(
            title="Clinical Practice Guidelines for Hypertension",
            content=(
                "First-line pharmacological treatment of primary essential hypertension "
                "includes thiazide-type diuretics, ACE inhibitors such as lisinopril, "
                "angiotensin receptor blockers, and calcium channel blockers.\n\n"
                "Target blood pressure for most adults is below 130/80 mmHg."
            ),
            priority=3,
            is_active=True,
            created_by=self.user,
        )

        self.doc2 = KnowledgeDocument.objects.create(
            title="Management of Type 2 Diabetes",
            content=(
                "Metformin is the preferred initial pharmacologic agent for the "
                "treatment of type 2 diabetes mellitus in adults.\n\n"
                "Monitor HbA1c every 3 to 6 months."
            ),
            priority=1,
            is_active=True,
            created_by=self.user,
        )

        self.inactive_doc = KnowledgeDocument.objects.create(
            title="Draft Inactive Guidance on Asthma",
            content="Inhaled corticosteroids such as fluticasone are standard controller therapy.",
            priority=5,
            is_active=False,
            created_by=self.user,
        )

    def test_chunking_preserves_paragraphs_and_offsets(self):
        text = "Paragraph one with text.\n\nParagraph two with more details."
        chunks = chunk_text(text)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["chunk_index"], 1)
        self.assertEqual(chunks[0]["text"], "Paragraph one with text.")
        self.assertEqual(text[chunks[0]["start_offset"]:chunks[0]["end_offset"]], "Paragraph one with text.")

    def test_retrieve_knowledge_filters_inactive_documents(self):
        results = retrieve_knowledge_passages("asthma inhaled corticosteroid")
        self.assertEqual(len(results), 0, "Inactive documents must be excluded from RAG retrieval.")

    def test_retrieve_knowledge_returns_relevant_hypertension_guidelines(self):
        results = retrieve_knowledge_passages("hypertension lisinopril treatment")
        self.assertGreater(len(results), 0)
        top = results[0]
        self.assertEqual(top["document_id"], self.doc1.pk)
        self.assertEqual(top["title"], "Clinical Practice Guidelines for Hypertension")
        self.assertIn("lisinopril", top["text"])
        self.assertGreater(top["score"], 0.2)

    def test_retrieve_knowledge_returns_relevant_diabetes_guidelines(self):
        results = retrieve_knowledge_passages("diabetes metformin therapy")
        self.assertGreater(len(results), 0)
        top = results[0]
        self.assertEqual(top["document_id"], self.doc2.pk)
        self.assertIn("Metformin", top["text"])

    def test_retrieval_excludes_active_uploads_waiting_for_review(self):
        pending = KnowledgeDocument.objects.create(
            title="Pending review asthma guidance",
            content="Asthma management includes inhaled corticosteroids and monitoring.",
            ingestion_status="needs_review",
            is_active=True,
            created_by=self.user,
        )

        results = retrieve_knowledge_passages("asthma inhaled corticosteroids")
        self.assertNotIn(pending.pk, {row["document_id"] for row in results})

    def test_retrieval_includes_explicitly_published_documents(self):
        published = KnowledgeDocument.objects.create(
            title="Published COPD guidance",
            content="COPD care includes bronchodilator therapy and pulmonary rehabilitation.",
            ingestion_status="published",
            is_active=True,
            created_by=self.user,
        )

        results = retrieve_knowledge_passages("COPD pulmonary rehabilitation")
        self.assertIn(published.pk, {row["document_id"] for row in results})

    def test_retrieval_rejects_invalid_limits_and_scores(self):
        with self.assertRaises(ValueError):
            retrieve_knowledge_passages("hypertension", top_k=0)
        with self.assertRaises(ValueError):
            retrieve_knowledge_passages("hypertension", min_score=1.5)

