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
            "".join(json.dumps(record) + "\n" for record in synthetic_records),
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
        self.assertNotIn("local_annotation_queue", self.client.session)
        self.assertNotIn(note_text, json.dumps(dict(self.client.session.items())))
        queue = [
            json.loads(line)
            for line in self.working_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
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
                self.assertNotIn("local_annotation_queue", self.client.session)
                response = self.client.get(reverse("dashboard:annotation_queue"))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(any(item["record_id"] == note_id for item in response.context["queue"]))

    def test_post_cannot_change_source_note_or_provenance(self):
        note = self.client.get(reverse("dashboard:annotation_queue")).context["queue"][0]
        original_text = note["note_text"]
        payload = {
            "record_id": note["record_id"],
            "specialty": "Tampered specialty",
            "note_text": "Tampered source note",
            "source_dataset": "tampered:source",
            "source_url": "https://example.invalid/tampered",
            "source_row_number": 999,
            "source_keywords": "tampered",
            "diagnoses": "[]",
            "procedures": "[]",
            "medications": "[]",
            "allergies": "[]",
            "vital_signs": "[]",
            "icd10_cm_codes": "[]",
            "annotator_id": "synthetic-reviewer",
            "action": "save",
        }
        self.client.post(
            reverse("dashboard:annotation_detail", kwargs={"record_id": note["record_id"]}),
            payload,
        )

        saved = [
            json.loads(line)
            for line in self.working_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ][0]
        self.assertEqual(saved["note_text"], original_text)
        self.assertEqual(saved["specialty"], note["specialty"])
        self.assertEqual(saved["source_dataset"], note["source_dataset"])
        self.assertEqual(saved["source_row_number"], note["source_row_number"])
        self.assertEqual(saved["source_keywords"], note["source_keywords"])


    def test_missing_local_queue_shows_setup_message(self):
        self.template_path.unlink()
        response = self.client.get(reverse("dashboard:annotation_queue"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No local annotation queue is prepared")
        self.assertNotContains(response, "mtsamples-")

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

    def _setup_mtsamples_records(self):
        records = [
            {
                "record_id": "mtsamples-01488-56a93dbe88bfa068",
                "specialty": "Orthopedic",
                "note_text": "Patient with left foot pain and swelling noted.",
                "source_dataset": "synthetic:mirai-test",
                "source_url": "https://example.invalid/mirai-synthetic-dataset",
                "source_row_number": 1,
                "source_keywords": "swelling",
                "annotation_complete": True,
                "adjudication_status": "adjudicated",
                "conflict_status": "not_applicable",
                "conflict_notes": "",
                "reviewer_decision": "accepted",
                "reviewer_comment": "Approved",
                "gold_annotations": {
                    "diagnoses": [],
                    "procedures": [],
                    "medications": [],
                    "allergies": [],
                    "vital_signs": [],
                    "icd10_cm_codes": [],
                },
            },
            {
                "record_id": "mtsamples-00176-9fefeb9804915464",
                "specialty": "Podiatry",
                "note_text": "Degenerative joint disease and bunionectomy evaluation.",
                "source_dataset": "synthetic:mirai-test",
                "source_url": "https://example.invalid/mirai-synthetic-dataset",
                "source_row_number": 2,
                "source_keywords": "joint disease",
                "annotation_complete": True,
                "adjudication_status": "adjudicated",
                "conflict_status": "not_applicable",
                "conflict_notes": "",
                "reviewer_decision": "accepted",
                "reviewer_comment": "Approved",
                "gold_annotations": {
                    "diagnoses": [],
                    "procedures": [],
                    "medications": [],
                    "allergies": [],
                    "vital_signs": [],
                    "icd10_cm_codes": [],
                },
            },
            {
                "record_id": "mtsamples-03094-ab40536e8afb16bc",
                "specialty": "General Medicine",
                "note_text": "Follow up visit for hypertension and routine assessment.",
                "source_dataset": "synthetic:mirai-test",
                "source_url": "https://example.invalid/mirai-synthetic-dataset",
                "source_row_number": 3,
                "source_keywords": "hypertension",
                "annotation_complete": True,
                "adjudication_status": "adjudicated",
                "conflict_status": "not_applicable",
                "conflict_notes": "",
                "reviewer_decision": "accepted",
                "reviewer_comment": "Approved",
                "gold_annotations": {
                    "diagnoses": [],
                    "procedures": [],
                    "medications": [],
                    "allergies": [],
                    "vital_signs": [],
                    "icd10_cm_codes": [],
                },
            },
        ]
        self.template_path.write_text(
            "".join(json.dumps(r) + "\n" for r in records),
            encoding="utf-8",
        )
        if self.working_path.exists():
            self.working_path.unlink()
        self.client.session.clear()
        self.client.session.save()

    def test_dropdown_options_present_on_different_records(self):
        """Dropdown options are present on annotation pages for different records."""
        self._setup_mtsamples_records()
        sample_ids = [
            "mtsamples-01488-56a93dbe88bfa068",
            "mtsamples-00176-9fefeb9804915464",
            "mtsamples-03094-ab40536e8afb16bc",
        ]
        for record_id in sample_ids:
            response = self.client.get(
                reverse("dashboard:annotation_detail", kwargs={"record_id": record_id})
            )
            self.assertEqual(response.status_code, 200)
            content = response.content.decode("utf-8")
            self.assertIn('name="adjudication_status"', content)
            self.assertIn('name="conflict_status"', content)
            self.assertIn('name="reviewer_decision"', content)
            # Check option values are rendered
            self.assertIn('value="not_required"', content)
            self.assertIn('value="adjudicated"', content)
            self.assertIn('value="needs_rework"', content)
            self.assertIn('value="not_reviewed"', content)
            self.assertIn('value="not_applicable"', content)
            self.assertIn('value="resolved"', content)
            self.assertIn('value="pending"', content)
            self.assertIn('value="accepted"', content)
            self.assertIn('value="rejected"', content)

    def test_intended_dropdowns_have_expected_choices(self):
        """Each intended dropdown has its expected choices and displays saved initial value."""
        self._setup_mtsamples_records()
        response = self.client.get(
            reverse("dashboard:annotation_detail", kwargs={"record_id": "mtsamples-01488-56a93dbe88bfa068"})
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        # Expected choices
        self.assertEqual(
            [c[0] for c in form.fields["adjudication_status"].choices],
            ["not_required", "adjudicated", "needs_rework"],
        )
        self.assertEqual(
            [c[0] for c in form.fields["conflict_status"].choices],
            ["not_reviewed", "not_applicable", "resolved"],
        )
        self.assertEqual(
            [c[0] for c in form.fields["reviewer_decision"].choices],
            ["pending", "accepted", "rejected"],
        )
        # Check initial values match template gold record
        self.assertEqual(form.initial["adjudication_status"], "adjudicated")
        self.assertEqual(form.initial["conflict_status"], "not_applicable")
        self.assertEqual(form.initial["reviewer_decision"], "accepted")

    def test_valid_dropdown_selection_submits_and_persists_after_reload(self):
        """A valid selection can be submitted and persists after reload."""
        self._setup_mtsamples_records()
        record_id = "mtsamples-01488-56a93dbe88bfa068"
        get_resp = self.client.get(
            reverse("dashboard:annotation_detail", kwargs={"record_id": record_id})
        )
        record = get_resp.context["record"]
        payload = {
            "record_id": record_id,
            "specialty": record["specialty"],
            "note_text": record["note_text"],
            "source_dataset": record["source_dataset"],
            "source_url": record["source_url"],
            "source_row_number": record["source_row_number"],
            "source_keywords": record.get("source_keywords", ""),
            "diagnoses": json.dumps(record["gold_annotations"]["diagnoses"]),
            "procedures": json.dumps(record["gold_annotations"]["procedures"]),
            "medications": json.dumps(record["gold_annotations"]["medications"]),
            "allergies": json.dumps(record["gold_annotations"]["allergies"]),
            "vital_signs": json.dumps(record["gold_annotations"]["vital_signs"]),
            "icd10_cm_codes": json.dumps(record["gold_annotations"]["icd10_cm_codes"]),
            "annotator_id": "annotator-persistence-test",
            "annotation_complete": "on",
            "adjudication_status": "needs_rework",
            "conflict_status": "resolved",
            "conflict_notes": "Resolved conflict notes.",
            "reviewer_decision": "rejected",
            "reviewer_comment": "Needs rework.",
            "action": "save",
        }
        post_resp = self.client.post(
            reverse("dashboard:annotation_detail", kwargs={"record_id": record_id}),
            payload,
            follow=True,
        )
        self.assertEqual(post_resp.status_code, 200)
        # Verify persistence in session and rendered form
        reloaded_form = post_resp.context["form"]
        self.assertEqual(reloaded_form.initial["adjudication_status"], "needs_rework")
        self.assertEqual(reloaded_form.initial["conflict_status"], "resolved")
        self.assertEqual(reloaded_form.initial["reviewer_decision"], "rejected")

        # Verify rendered HTML select elements have selected attributes
        content = post_resp.content.decode("utf-8")
        self.assertIn('<option value="needs_rework" selected>Needs rework</option>', content)
        self.assertIn('<option value="resolved" selected>Resolved</option>', content)
        self.assertIn('<option value="rejected" selected>Rejected</option>', content)

    def test_invalid_dropdown_selection_is_rejected(self):
        """Invalid dropdown selections are rejected with validation errors."""
        self._setup_mtsamples_records()
        record_id = "mtsamples-01488-56a93dbe88bfa068"
        get_resp = self.client.get(
            reverse("dashboard:annotation_detail", kwargs={"record_id": record_id})
        )
        record = get_resp.context["record"]
        payload = {
            "record_id": record_id,
            "specialty": record["specialty"],
            "note_text": record["note_text"],
            "source_dataset": record["source_dataset"],
            "source_url": record["source_url"],
            "source_row_number": record["source_row_number"],
            "source_keywords": record.get("source_keywords", ""),
            "diagnoses": "[]",
            "procedures": "[]",
            "medications": "[]",
            "allergies": "[]",
            "vital_signs": "[]",
            "icd10_cm_codes": "[]",
            "annotator_id": "annotator-invalid-test",
            "adjudication_status": "invalid_status_xyz",
            "conflict_status": "bogus_conflict",
            "reviewer_decision": "bad_decision",
            "action": "save",
        }
        post_resp = self.client.post(
            reverse("dashboard:annotation_detail", kwargs={"record_id": record_id}),
            payload,
        )
        self.assertEqual(post_resp.status_code, 200)
        form = post_resp.context["form"]
        self.assertFalse(form.is_valid())
        self.assertIn("adjudication_status", form.errors)
        self.assertIn("conflict_status", form.errors)
        self.assertIn("reviewer_decision", form.errors)
