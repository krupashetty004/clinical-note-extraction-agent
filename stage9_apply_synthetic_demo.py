from __future__ import annotations

"""Safely apply Mirai Labs Stage 9 synthetic-demo integration.

Run from the repository root with:
    python stage9_apply_synthetic_demo.py --check
    python stage9_apply_synthetic_demo.py --apply

The script only edits local project files. It never runs Git write commands,
installs packages, calls network services, or invokes an AI provider.
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


SETTING_BLOCK = '''\n\n# Local synthetic demonstration only. Disabled by default and never enabled\n# when DEBUG is false. This does not configure or call an AI provider.\nSYNTHETIC_DEMO_ENABLED = (\n    DEBUG\n    and os.environ.get("MIRAI_ENABLE_SYNTHETIC_DEMO", "").strip().lower()\n    in {"1", "true", "yes"}\n)\n'''

SYNTHETIC_PROVIDER_SOURCE = '''"""Deterministic, non-clinical providers for local integration testing only.

These providers do not inspect clinical content or call an AI model. They
always return no extracted items and require human review. Never use them for
clinical decisions or as evidence of model quality.
"""


class SyntheticDemoExtractionProvider:
    """Return an intentionally empty result for UI plumbing tests."""

    def extract(self, input_text: str) -> dict:
        if not isinstance(input_text, str):
            raise TypeError("input_text must be a string.")

        return {
            "items": [],
            "needs_review": True,
            "review_reasons": [
                "Synthetic demonstration only: no AI model was called and "
                "no clinical findings were extracted. Review the original "
                "note manually.",
            ],
        }


class SyntheticDemoVerificationProvider:
    """Return a review-required placeholder, not a clinical verification."""

    def verify(self, original_note, extraction, coding) -> dict:
        if not isinstance(original_note, str):
            raise TypeError("original_note must be a string.")

        return {
            "item_checks": [],
            "potential_omissions": [],
            "needs_review": True,
            "review_reasons": [
                "Synthetic demonstration only: independent clinical "
                "verification was not performed.",
            ],
        }
'''

TEST_SOURCE = '''"""Tests for the gated, local synthetic processing demonstration."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dashboard.models import (
    ClinicalNote,
    ClinicalProcessingRun,
    Encounter,
    Patient,
    PatientAccess,
)


class SyntheticDemoViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.doctor = user_model.objects.create_user(
            username="synthetic_demo_doctor",
            password="Synthetic-Demo-Test-Password-712!",
        )
        cls.doctor.groups.add(Group.objects.get(name="Doctor"))

        cls.other_doctor = user_model.objects.create_user(
            username="synthetic_demo_other_doctor",
            password="Synthetic-Demo-Test-Password-813!",
        )
        cls.other_doctor.groups.add(Group.objects.get(name="Doctor"))

        cls.patient = Patient.objects.create(
            identifier="SYN-DEMO-001",
            display_name="Synthetic Demo Patient",
            created_by=cls.doctor,
        )
        PatientAccess.objects.create(
            patient=cls.patient,
            doctor=cls.doctor,
        )
        cls.encounter = Encounter.objects.create(
            patient=cls.patient,
            title="Synthetic demo encounter",
            encounter_date=timezone.now(),
            created_by=cls.doctor,
        )
        cls.note = ClinicalNote.objects.create(
            encounter=cls.encounter,
            version_number=1,
            original_text=(
                "Synthetic test note only. No real clinical data is present."
            ),
            source=ClinicalNote.Source.MANUAL,
            created_by=cls.doctor,
        )

    def setUp(self):
        self.client.force_login(self.doctor)

    @override_settings(SYNTHETIC_DEMO_ENABLED=True)
    def test_post_creates_persisted_demo_run_and_requires_review(self):
        response = self.client.post(
            reverse(
                "dashboard:run_synthetic_processing_demo",
                kwargs={"note_id": self.note.pk},
            ),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        run = ClinicalProcessingRun.objects.get(clinical_note=self.note)
        self.assertEqual(
            run.execution_mode,
            ClinicalProcessingRun.ExecutionMode.SYNTHETIC_DEMO,
        )
        self.assertEqual(run.status, ClinicalProcessingRun.Status.NEEDS_REVIEW)
        self.assertEqual(run.extraction_result["items"], [])
        self.assertTrue(run.extraction_result["needs_review"])
        self.assertTrue(run.verification_result["needs_review"])
        self.assertContains(response, "Synthetic demonstration only")
        self.assertContains(response, "No AI model was called")

    @override_settings(SYNTHETIC_DEMO_ENABLED=False)
    def test_demo_is_disabled_by_default_and_creates_no_run(self):
        response = self.client.post(
            reverse(
                "dashboard:run_synthetic_processing_demo",
                kwargs={"note_id": self.note.pk},
            )
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            ClinicalProcessingRun.objects.filter(clinical_note=self.note).exists()
        )

    @override_settings(SYNTHETIC_DEMO_ENABLED=True)
    def test_demo_endpoint_rejects_get(self):
        response = self.client.get(
            reverse(
                "dashboard:run_synthetic_processing_demo",
                kwargs={"note_id": self.note.pk},
            )
        )
        self.assertEqual(response.status_code, 405)

    @override_settings(SYNTHETIC_DEMO_ENABLED=True)
    def test_doctor_without_patient_access_cannot_run_demo(self):
        self.client.force_login(self.other_doctor)
        response = self.client.post(
            reverse(
                "dashboard:run_synthetic_processing_demo",
                kwargs={"note_id": self.note.pk},
            )
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            ClinicalProcessingRun.objects.filter(clinical_note=self.note).exists()
        )
'''


def require_one(text: str, needle: str, label: str) -> None:
    count = text.count(needle)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} anchor; found {count}.")


def require_count(text: str, needle: str, count_expected: int, label: str) -> None:
    count = text.count(needle)
    if count != count_expected:
        raise RuntimeError(
            f"Expected {count_expected} {label} anchors; found {count}."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="Validate anchors; do not edit files.")
    action.add_argument("--apply", action="store_true", help="Apply the local code changes after validation.")
    args = parser.parse_args()

    root = Path.cwd()
    if not (root / "manage.py").is_file() or not (root / ".git").exists():
        print("ERROR: Run this script from the repository root (manage.py and .git must exist).", file=sys.stderr)
        return 2

    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if branch.returncode != 0:
        print("ERROR: Unable to inspect the current Git branch.", file=sys.stderr)
        return 2
    branch_name = branch.stdout.strip()
    if branch_name != "local/django-foundation":
        print(
            f"ERROR: Expected branch local/django-foundation; found {branch_name!r}. No files changed.",
            file=sys.stderr,
        )
        return 2

    paths = {
        "settings": root / "config" / "settings.py",
        "models": root / "dashboard" / "models.py",
        "service": root / "dashboard" / "extraction" / "processing_service.py",
        "views": root / "dashboard" / "views.py",
        "urls": root / "dashboard" / "urls.py",
        "patient_template": root / "dashboard" / "templates" / "dashboard" / "patient_detail.html",
        "run_template": root / "dashboard" / "templates" / "dashboard" / "processing_run_detail.html",
        "provider_new": root / "dashboard" / "extraction" / "synthetic_demo.py",
        "test_new": root / "dashboard" / "test_synthetic_demo_view.py",
    }
    for key, path in paths.items():
        if key not in {"provider_new", "test_new"} and not path.is_file():
            print(f"ERROR: Required file missing: {path}", file=sys.stderr)
            return 2
    for key in ("provider_new", "test_new"):
        if paths[key].exists():
            print(f"ERROR: Refusing to overwrite existing file: {paths[key]}", file=sys.stderr)
            return 2

    original: dict[str, str] = {
        key: path.read_text(encoding="utf-8")
        for key, path in paths.items()
        if key not in {"provider_new", "test_new"}
    }
    edited = dict(original)

    # Validate all anchors and build all replacement contents in memory first.
    if "SYNTHETIC_DEMO_ENABLED" in edited["settings"]:
        raise RuntimeError("SYNTHETIC_DEMO_ENABLED already exists in settings.py; no files changed.")
    edited["settings"] = edited["settings"].rstrip() + SETTING_BLOCK + "\n"

    if "class ExecutionMode(models.TextChoices)" in edited["models"]:
        raise RuntimeError("ExecutionMode already exists in models.py; no files changed.")
    status_anchor = '''        FAILED = "failed", "Failed"\n'''
    require_one(edited["models"], status_anchor, "processing-run status")
    edited["models"] = edited["models"].replace(
        status_anchor,
        status_anchor + '''\n    class ExecutionMode(models.TextChoices):\n        UNKNOWN = "unknown", "Unknown / legacy"\n        SYNTHETIC_DEMO = "synthetic_demo", "Synthetic demonstration"\n''',
        1,
    )
    run_model_pos = edited["models"].find("class ClinicalProcessingRun(models.Model):")
    if run_model_pos < 0:
        raise RuntimeError("ClinicalProcessingRun class anchor not found; no files changed.")
    model_tail = edited["models"][run_model_pos:]
    require_one(model_tail, "    clinical_note = models.ForeignKey(\n", "processing-run clinical_note field")
    model_tail = model_tail.replace(
        "    clinical_note = models.ForeignKey(\n",
        '''    execution_mode = models.CharField(\n        max_length=24,\n        choices=ExecutionMode.choices,\n        default=ExecutionMode.UNKNOWN,\n    )\n\n    clinical_note = models.ForeignKey(\n''',
        1,
    )
    edited["models"] = edited["models"][:run_model_pos] + model_tail

    signature_anchor = '''    max_verification_attempts: int = 2,\n) -> ClinicalProcessingRun:\n'''
    require_one(edited["service"], signature_anchor, "processing_service signature")
    edited["service"] = edited["service"].replace(
        signature_anchor,
        '''    max_verification_attempts: int = 2,\n    execution_mode: str = ClinicalProcessingRun.ExecutionMode.UNKNOWN,\n) -> ClinicalProcessingRun:\n''',
        1,
    )
    create_anchor = '''    run = ClinicalProcessingRun.objects.create(\n        clinical_note=note,\n        created_by=initiated_by,\n        status=ClinicalProcessingRun.Status.PENDING,\n    )\n'''
    require_one(edited["service"], create_anchor, "processing-run creation")
    edited["service"] = edited["service"].replace(
        create_anchor,
        '''    if execution_mode not in ClinicalProcessingRun.ExecutionMode.values:\n        raise ValueError("execution_mode must be a supported processing mode.")\n\n    run = ClinicalProcessingRun.objects.create(\n        clinical_note=note,\n        created_by=initiated_by,\n        status=ClinicalProcessingRun.Status.PENDING,\n        execution_mode=execution_mode,\n    )\n''',
        1,
    )

    require_one(edited["views"], "from django.core.paginator import Paginator\n", "views paginator import")
    edited["views"] = edited["views"].replace(
        "from django.core.paginator import Paginator\n",
        "from django.conf import settings\nfrom django.core.paginator import Paginator\n",
        1,
    )
    require_one(edited["views"], "import json\n", "views json import")
    edited["views"] = edited["views"].replace(
        "import json\n",
        '''import json\nfrom django.http import Http404\nfrom django.views.decorators.http import require_POST\n\nfrom dashboard.extraction.processing_service import process_clinical_note\nfrom dashboard.extraction.synthetic_demo import (\n    SyntheticDemoExtractionProvider,\n    SyntheticDemoVerificationProvider,\n)\n''',
        1,
    )
    patient_context_anchor = '''            "previous_encounters": previous_encounters,\n'''
    require_one(edited["views"], patient_context_anchor, "patient-detail context")
    edited["views"] = edited["views"].replace(
        patient_context_anchor,
        patient_context_anchor + '''            "synthetic_demo_enabled": (\n                settings.SYNTHETIC_DEMO_ENABLED\n                and request.user.groups.filter(name="Doctor").exists()\n            ),\n''',
        1,
    )
    if "def run_synthetic_processing_demo(" in edited["views"]:
        raise RuntimeError("Synthetic demo view already exists; no files changed.")
    edited["views"] = edited["views"].rstrip() + '''\n\n\n@role_required("Doctor")\n@require_POST\ndef run_synthetic_processing_demo(\n    request: HttpRequest,\n    note_id: int,\n) -> HttpResponse:\n    """Run a gated local plumbing demo; this does not perform AI analysis."""\n    if not settings.SYNTHETIC_DEMO_ENABLED:\n        raise Http404\n\n    authorized_patients = Patient.objects.accessible_to(request.user)\n    note = get_object_or_404(\n        ClinicalNote.objects.filter(encounter__patient__in=authorized_patients),\n        pk=note_id,\n    )\n\n    run = process_clinical_note(\n        note,\n        request.user,\n        extraction_provider=SyntheticDemoExtractionProvider(),\n        verification_provider=SyntheticDemoVerificationProvider(),\n        execution_mode=ClinicalProcessingRun.ExecutionMode.SYNTHETIC_DEMO,\n    )\n    return redirect("dashboard:processing_run_detail", run_id=run.pk)\n'''

    route_anchor = '''    path(\n        "encounters/<int:encounter_id>/notes/new/",\n'''
    require_one(edited["urls"], route_anchor, "clinical note URL route")
    edited["urls"] = edited["urls"].replace(
        route_anchor,
        '''    path(\n        "notes/<int:note_id>/run-synthetic-demo/",\n        views.run_synthetic_processing_demo,\n        name="run_synthetic_processing_demo",\n    ),\n    path(\n        "encounters/<int:encounter_id>/notes/new/",\n''',
        1,
    )

    note_anchor = '''                    <div class="original-note-text">{{ note.original_text }}</div>\n\n                    <div class="processing-run-history mt-3">\n'''
    require_count(edited["patient_template"], note_anchor, 2, "note preview")
    demo_form = '''                    <div class="original-note-text">{{ note.original_text }}</div>\n\n                    {% if synthetic_demo_enabled %}\n                        <form method="post"\n                              action="{% url 'dashboard:run_synthetic_processing_demo' note_id=note.pk %}"\n                              class="mb-3">\n                            {% csrf_token %}\n                            <button type="submit" class="btn btn-outline-warning btn-sm">\n                                Run synthetic demo (no AI)\n                            </button>\n                        </form>\n                    {% endif %}\n\n                    <div class="processing-run-history mt-3">\n'''
    edited["patient_template"] = edited["patient_template"].replace(note_anchor, demo_form)

    run_info_anchor = '''<section class="panel">\n    <h2>Run information</h2>\n'''
    require_one(edited["run_template"], run_info_anchor, "run information template section")
    edited["run_template"] = edited["run_template"].replace(
        run_info_anchor,
        '''{% if run.execution_mode == "synthetic_demo" %}\n<div class="alert alert-warning" role="alert">\n    <strong>Synthetic demonstration only.</strong> No AI model was called,\n    no clinical findings were extracted, and no independent clinical\n    verification was performed. Do not use this output for clinical decisions.\n</div>\n{% elif run.execution_mode == "unknown" %}\n<div class="alert alert-warning" role="alert">\n    Execution mode was not recorded for this run. Do not assume that a real\n    AI model was used or that its output is clinically validated.\n</div>\n{% endif %}\n\n<section class="panel">\n    <h2>Run information</h2>\n''',
        1,
    )
    run_status_anchor = '''        <dt>Status</dt>\n        <dd>{{ run.get_status_display }}</dd>\n'''
    require_one(edited["run_template"], run_status_anchor, "run status template field")
    edited["run_template"] = edited["run_template"].replace(
        run_status_anchor,
        run_status_anchor + '''\n        <dt>Execution mode</dt>\n        <dd>{{ run.get_execution_mode_display }}</dd>\n''',
        1,
    )

    changes = {
        key: value for key, value in edited.items() if value != original[key]
    }
    new_files = {
        "provider_new": SYNTHETIC_PROVIDER_SOURCE,
        "test_new": TEST_SOURCE,
    }

    if args.check:
        print("Preflight passed. No files changed.")
        print(f"Branch: {branch_name}")
        print("Files to modify:")
        for key in changes:
            print(f"  {paths[key]}")
        print("Files to create:")
        for key in new_files:
            print(f"  {paths[key]}")
        print("After applying: run makemigrations, review migration, migrate, and tests.")
        return 0

    backup_dir = Path(tempfile.mkdtemp(prefix="mirai-stage9-backup-"))
    backup_paths: dict[Path, Path] = {}
    created: list[Path] = []
    try:
        for key in changes:
            src = paths[key]
            dst = backup_dir / f"{key}-{src.name}.bak"
            dst.write_bytes(src.read_bytes())
            backup_paths[src] = dst
        for key, content in new_files.items():
            path = paths[key]
            if path.exists():
                raise RuntimeError(f"Refusing to overwrite newly appeared file: {path}")
        for key, content in changes.items():
            paths[key].write_text(content, encoding="utf-8", newline="")
        for key, content in new_files.items():
            paths[key].write_text(content, encoding="utf-8", newline="")
            created.append(paths[key])
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        for src, backup in backup_paths.items():
            src.write_bytes(backup.read_bytes())
        print(f"ERROR: Apply failed; backups restored where available: {backup_dir}", file=sys.stderr)
        raise

    print("Stage 9 source changes applied locally. No Git write commands were run.")
    print(f"Backup copies of modified files: {backup_dir}")
    print("Changed files:")
    for key in changes:
        print(f"  {paths[key]}")
    print("Created files:")
    for key in new_files:
        print(f"  {paths[key]}")
    print("\nNEXT: Review the diff, then run `python manage.py makemigrations dashboard`.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
