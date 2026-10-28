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
        working_path = Path(__file__).resolve().parents[1] / ".annotation_working_queue.jsonl"
        if working_path.exists():
            working_path.unlink()

    def test_annotation_queue_renders_100_note_queue(self):
        response = self.client.get(reverse("dashboard:annotation_queue"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Local annotation queue")
        self.assertContains(response, "100-note queue")
        self.assertContains(response, "mtsamples-00176-9fefeb9804915464")
        self.assertContains(response, "Surgery")
        self.assertContains(response, "mtsamples-03094-ab40536e8afb16bc")

    def test_annotation_queue_uses_original_template_records(self):
        response = self.client.get(reverse("dashboard:annotation_queue"))
        queue = response.context["queue"]
        self.assertEqual(len(queue), 100)
        self.assertEqual(queue[0]["record_id"], "mtsamples-00176-9fefeb9804915464")
        self.assertEqual(queue[0]["source_dataset"], "kaggle:tboyle10/medicaltranscriptions")
        self.assertTrue(queue[0]["note_text"].startswith("PREOPERATIVE DIAGNOSES:"))
        self.assertEqual(queue[-1]["record_id"], "mtsamples-03094-ab40536e8afb16bc")
        self.assertEqual(queue[-1]["specialty"], "IME-QME-Work Comp etc.")

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
