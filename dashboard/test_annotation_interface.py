import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse


class LocalAnnotationInterfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.doctor = user_model.objects.create_user(
            username="annotation_doctor",
            password="secret123",
        )
        cls.doctor.groups.add(Group.objects.get_or_create(name="Doctor")[0])

    def setUp(self):
        self.client.force_login(self.doctor)
        self.client.session.clear()
        self.client.session.save()

        # Tests use synthetic-only queue data and never depend on the locally
        # downloaded MTSamples dataset or modify a user's working annotation file.
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        temporary_root = Path(self._temporary_directory.name)
        self.template_path = temporary_root / "annotation_template.jsonl"
        self.working_path = temporary_root / ".annotation_working_queue.jsonl"

        synthetic_records = [
            {
                "record_id": "synthetic-annotation-001",
                "specialty": "Synthetic Surgery",
                "note_text": (
                    "Synthetic demo record: the phrase left foot is included "
                    "only to test evidence offsets."
                ),
                "source_dataset": "synthetic:mirai-test",
                "source_url": "https://example.invalid/mirai-synthetic-dataset",
                "source_row_number": 1,
                "source_keywords": "synthetic; left foot",
                "annotation_complete": False,
                "adjudication_status": "not_reviewed",
                "conflict_status": "not_reviewed",
                "conflict_notes": "",
                "gold_annotations": None,
            },
            {
                "record_id": "synthetic-annotation-002",
                "specialty": "Synthetic Internal Medicine",
                "note_text": (
                    "Synthetic assessment example for testing the annotation queue."
                ),
                "source_dataset": "synthetic:mirai-test",
                "source_url": "https://example.invalid/mirai-synthetic-dataset",
                "source_row_number": 2,
                "source_keywords": "synthetic; assessment",
                "annotation_complete": False,
                "adjudication_status": "not_reviewed",
                "conflict_status": "not_reviewed",
                "conflict_notes": "",
                "gold_annotations": None,
            },
        ]
        self.template_path.write_text(
            "".join(json.dumps(record) + "\\n" for record in synthetic_records),
            encoding="utf-8",
        )

        patchers = (
            patch("dashboard.views._annotation_template_path", return_value=self.template_path),
            patch("dashboard.views._annotation_working_path", return_value=self.working_path),
            patch("dashboard.views.ANNOTATION_VALIDATOR.SOURCE_ID", "synthetic:mirai-test"),
            patch(
                "dashboard.views.ANNOTATION_VALIDATOR.SOURCE_URL",
                "https://example.invalid/mirai-synthetic-dataset",
            ),
        )
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_annotation_queue_renders_synthetic_note_queue(self):
        response = self.client.get(reverse("dashboard:annotation_queue"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Local annotation queue")
        self.assertContains(response, "2-note queue")
        self.assertContains(response, "synthetic-annotation-001")
        self.assertContains(response, "Synthetic Surgery")
        self.assertContains(response, "synthetic-annotation-002")

    def test_annotation_queue_uses_original_synthetic_template_records(self):
        response = self.client.get(reverse("dashboard:annotation_queue"))
        queue = response.context["queue"]
        self.assertEqual(len(queue), 2)
        self.assertEqual(queue[0]["record_id"], "synthetic-annotation-001")
        self.assertEqual(queue[0]["source_dataset"], "synthetic:mirai-test")
        self.assertTrue(queue[0]["note_text"].startswith("Synthetic demo record:"))
        self.assertEqual(queue[-1]["record_id"], "synthetic-annotation-002")
        self.assertEqual(queue[-1]["specialty"], "Synthetic Internal Medicine")

    def test_annotation_detail_saves_and_persists_draft(self):
        queue = self.client.get(reverse("dashboard:annotation_queue")).context["queue"]
        note = queue[0]
        note_id = note["record_id"]
        note_text = note["note_text"]
        offset_start = note_text.index("left foot")
        payload = {
            "record_id": note_id,
            "specialty": note["specialty"],
            "note_text": note_text,
            "source_dataset": note["source_dataset"],
            "source_url": note["source_url"],
            "source_row_number": note["source_row_number"],
            "source_keywords": note["source_keywords"],
            "diagnoses": json.dumps([
                {
                    "entity": "left foot",
                    "evidence_text": "left foot",
                    "start_offset": offset_start,
                    "end_offset": offset_start + len("left foot"),
                    "status": "active",
                }
            ]),
            "procedures": "[]",
            "medications": "[]",
            "allergies": "[]",
            "vital_signs": "[]",
            "icd10_cm_codes": json.dumps([
                {"code": "M201", "description": "Hallux rigidus"}
            ]),
            "annotator_id": "annotator-demo",
            "annotation_complete": "on",
            "adjudication_status": "adjudicated",
            "conflict_status": "not_applicable",
            "conflict_notes": "",
            "reviewer_decision": "accepted",
            "reviewer_comment": "Reviewed",
            "action": "save",
        }

        response = self.client.post(
            reverse("dashboard:annotation_detail", kwargs={"record_id": note_id}),
            payload,
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        queue = self.client.session["local_annotation_queue"]
        stored = next(record for record in queue if record["record_id"] == note_id)
        self.assertEqual(stored["specialty"], note["specialty"])
        self.assertTrue(stored["annotation_complete"])
        self.assertEqual(stored["annotator_id"], "annotator-demo")

    def test_draft_saves_to_a_working_jsonl_file(self):
        queue = self.client.get(reverse("dashboard:annotation_queue")).context["queue"]
        note = queue[0]
        note_id = note["record_id"]
        note_text = note["note_text"]
        offset_start = note_text.index("left foot")
        payload = {
            "record_id": note_id,
            "specialty": note["specialty"],
            "note_text": note_text,
            "source_dataset": note["source_dataset"],
            "source_url": note["source_url"],
            "source_row_number": note["source_row_number"],
            "source_keywords": note["source_keywords"],
            "diagnoses": json.dumps([
                {
                    "entity": "left foot",
                    "evidence_text": "left foot",
                    "start_offset": offset_start,
                    "end_offset": offset_start + len("left foot"),
                    "status": "active",
                }
            ]),
            "procedures": "[]",
            "medications": "[]",
            "allergies": "[]",
            "vital_signs": "[]",
            "icd10_cm_codes": json.dumps([
                {"code": "M201", "description": "Hallux rigidus"}
            ]),
            "annotator_id": "annotator-durable",
            "annotation_complete": "on",
            "adjudication_status": "adjudicated",
            "conflict_status": "not_applicable",
            "conflict_notes": "",
            "reviewer_decision": "accepted",
            "reviewer_comment": "Stored",
            "action": "save",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            working_path = Path(tmpdir) / ".annotation_working_queue.jsonl"
            with patch("dashboard.views._annotation_working_path", return_value=working_path):
                self.client.post(
                    reverse("dashboard:annotation_detail", kwargs={"record_id": note_id}),
                    payload,
                )
                self.assertTrue(working_path.exists())
                lines = [json.loads(line) for line in working_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                saved = next(item for item in lines if item["record_id"] == note_id)
                self.assertEqual(saved["annotator_id"], "annotator-durable")
                self.client.session.pop("local_annotation_queue")
                self.client.session.save()
                response = self.client.get(reverse("dashboard:annotation_queue"))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(any(item["record_id"] == note_id for item in response.context["queue"]))

    def test_export_is_blocked_until_valid_gold_record_is_complete(self):
        response = self.client.get(reverse("dashboard:annotation_export"))
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["status"], "blocked")
        self.assertIn("invalid_records", data)

    def test_export_rejects_invalid_completed_record(self):
        queue = self.client.get(reverse("dashboard:annotation_queue")).context["queue"]
        note = queue[0]
        note_id = note["record_id"]
        note_text = note["note_text"]
        offset_start = note_text.index("left foot")
        payload = {
            "record_id": note_id,
            "specialty": note["specialty"],
            "note_text": note_text,
            "source_dataset": note["source_dataset"],
            "source_url": note["source_url"],
            "source_row_number": note["source_row_number"],
            "source_keywords": note["source_keywords"],
            "diagnoses": json.dumps([
                {
                    "entity": "left foot",
                    "evidence_text": "right foot",
                    "start_offset": offset_start,
                    "end_offset": offset_start + len("left foot"),
                    "status": "active",
                }
            ]),
            "procedures": "[]",
            "medications": "[]",
            "allergies": "[]",
            "vital_signs": "[]",
            "icd10_cm_codes": json.dumps([
                {"code": "M201", "description": "Hallux rigidus"}
            ]),
            "annotator_id": "annotator-bad",
            "annotation_complete": "on",
            "adjudication_status": "adjudicated",
            "conflict_status": "not_applicable",
            "conflict_notes": "",
            "reviewer_decision": "accepted",
            "reviewer_comment": "Bad",
            "action": "save",
        }
        self.client.post(
            reverse("dashboard:annotation_detail", kwargs={"record_id": note_id}),
            payload,
        )
        response = self.client.post(reverse("dashboard:annotation_export"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "blocked")

    def test_valid_export_returns_jsonl_payload_for_ready_record(self):
        queue = self.client.get(reverse("dashboard:annotation_queue")).context["queue"]
        note = queue[0]
        note_id = note["record_id"]
        note_text = note["note_text"]
        offset_start = note_text.index("left foot")
        payload = {
            "record_id": note_id,
            "specialty": note["specialty"],
            "note_text": note_text,
            "source_dataset": note["source_dataset"],
            "source_url": note["source_url"],
            "source_row_number": note["source_row_number"],
            "source_keywords": note["source_keywords"],
            "diagnoses": json.dumps([
                {
                    "entity": "left foot",
                    "evidence_text": "left foot",
                    "start_offset": offset_start,
                    "end_offset": offset_start + len("left foot"),
                    "status": "active",
                }
            ]),
            "procedures": "[]",
            "medications": "[]",
            "allergies": "[]",
            "vital_signs": "[]",
            "icd10_cm_codes": json.dumps([
                {"code": "M201", "description": "Hallux rigidus"}
            ]),
            "annotator_id": "annotator-ready",
            "annotation_complete": "on",
            "adjudication_status": "adjudicated",
            "conflict_status": "not_applicable",
            "conflict_notes": "",
            "reviewer_decision": "accepted",
            "reviewer_comment": "Valid",
            "action": "save",
        }
        self.client.post(
            reverse("dashboard:annotation_detail", kwargs={"record_id": note_id}),
            payload,
        )

        response = self.client.post(reverse("dashboard:annotation_export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/jsonl; charset=utf-8")
        content = response.content.decode("utf-8")
        self.assertIn(f'"record_id": "{note_id}"', content)
