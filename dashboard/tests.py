from datetime import datetime, timezone as datetime_timezone
from django.db import IntegrityError, transaction
from datetime import timedelta
from django.utils import timezone

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.core.exceptions import ValidationError
from django.test import TestCase

from dashboard.models import (
    ClinicalNote,
    Encounter,
    Patient,
    PatientAccess,
)




User = get_user_model()


class AuthenticationAndAuthorizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.doctor_group = Group.objects.get(name="Doctor")
        cls.admin_group = Group.objects.get(name="Administrator")

        cls.doctor = User.objects.create_user(
            username="doctor_demo",
            password="Test-Only-Doctor-Password-482!",
        )
        cls.doctor.groups.add(cls.doctor_group)

        cls.administrator = User.objects.create_user(
            username="admin_demo",
            password="Test-Only-Admin-Password-739!",
        )
        cls.administrator.groups.add(cls.admin_group)

    def test_dashboard_redirects_anonymous_user_to_login(self):
        from django.urls import reverse

        response = self.client.get(reverse("dashboard:home"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('dashboard:home')}",
        )

    def test_login_page_renders(self):
        from django.urls import reverse

        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "registration/login.html",
        )

    def test_doctor_can_access_general_workspace_pages(self):
        from django.urls import reverse

        self.client.force_login(self.doctor)

        routes = [
            "dashboard:home",
            "dashboard:patients",
            "dashboard:knowledge_base",
        ]

        for route_name in routes:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)

    def test_doctor_cannot_access_ai_settings(self):
        from django.urls import reverse

        self.client.force_login(self.doctor)
        response = self.client.get(reverse("dashboard:settings"))

        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(
            response,
            "dashboard/403.html",
        )

    def test_administrator_can_access_ai_settings(self):
        from django.urls import reverse

        self.client.force_login(self.administrator)
        response = self.client.get(reverse("dashboard:settings"))

        self.assertEqual(response.status_code, 200)

    def test_logout_ends_the_session(self):
        from django.urls import reverse

        self.client.force_login(self.doctor)
        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("login"))

        response_after_logout = self.client.get(
            reverse("dashboard:home"),
        )

        self.assertRedirects(
            response_after_logout,
            f"{reverse('login')}?next={reverse('dashboard:home')}",
        )


class PatientAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.doctor_group = Group.objects.get(name="Doctor")
        cls.admin_group = Group.objects.get(name="Administrator")

        cls.doctor_a = User.objects.create_user(
            username="doctor_a",
            password="Synthetic-Test-Doctor-A-942!",
        )
        cls.doctor_a.groups.add(cls.doctor_group)

        cls.doctor_b = User.objects.create_user(
            username="doctor_b",
            password="Synthetic-Test-Doctor-B-841!",
        )
        cls.doctor_b.groups.add(cls.doctor_group)

        cls.administrator = User.objects.create_user(
            username="admin_only",
            password="Synthetic-Test-Admin-384!",
        )
        cls.administrator.groups.add(cls.admin_group)

        cls.superuser = User.objects.create_superuser(
            username="root_test",
            email="root-test@example.invalid",
            password="Synthetic-Test-Root-735!",
        )

        cls.patient_a = Patient.objects.create(
            identifier="DEMO-001",
            display_name="Synthetic Patient Alpha",
            created_by=cls.doctor_a,
        )
        cls.patient_b = Patient.objects.create(
            identifier="DEMO-002",
            display_name="Synthetic Patient Beta",
            created_by=cls.doctor_b,
        )

        PatientAccess.objects.create(
            patient=cls.patient_a,
            doctor=cls.doctor_a,
            granted_by=cls.administrator,
        )
        PatientAccess.objects.create(
            patient=cls.patient_b,
            doctor=cls.doctor_b,
            granted_by=cls.administrator,
        )

    def test_doctor_sees_only_explicitly_assigned_patients(self):
        identifiers = set(
            Patient.objects.accessible_to(self.doctor_a)
            .values_list("identifier", flat=True)
        )

        self.assertEqual(identifiers, {"DEMO-001"})
        self.assertNotIn("DEMO-002", identifiers)

    def test_anonymous_user_sees_no_patients(self):
        patients = Patient.objects.accessible_to(AnonymousUser())

        self.assertEqual(patients.count(), 0)

    def test_administrator_without_doctor_role_sees_no_patients(self):
        patients = Patient.objects.accessible_to(self.administrator)

        self.assertEqual(patients.count(), 0)

    def test_superuser_can_access_all_local_demo_patients(self):
        identifiers = set(
            Patient.objects.accessible_to(self.superuser)
            .values_list("identifier", flat=True)
        )

        self.assertEqual(identifiers, {"DEMO-001", "DEMO-002"})

    def test_patient_cannot_have_duplicate_access_grants(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PatientAccess.objects.create(
                    patient=self.patient_a,
                    doctor=self.doctor_a,
                    granted_by=self.administrator,
                )


class ClinicalNoteHistoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.doctor_group = Group.objects.get(name="Doctor")

        cls.doctor = User.objects.create_user(
            username="note_author",
            password="Synthetic-Note-Author-573!",
        )
        cls.doctor.groups.add(cls.doctor_group)

        cls.patient = Patient.objects.create(
            identifier="DEMO-NOTE-001",
            display_name="Synthetic Note Patient",
            created_by=cls.doctor,
        )

        cls.encounter = Encounter.objects.create(
            patient=cls.patient,
            title="Synthetic consultation",
            encounter_date=datetime(
                2026, 10, 16, 8, 0, tzinfo=datetime_timezone.utc
            ),
            status=Encounter.Status.OPEN,
            created_by=cls.doctor,
        )

    def test_encounter_belongs_to_the_correct_patient(self):
        self.assertEqual(self.encounter.patient, self.patient)

    def test_note_versions_can_preserve_prior_text(self):
        first_note = ClinicalNote.objects.create(
            encounter=self.encounter,
            version_number=1,
            original_text="Synthetic original note version one.",
            source=ClinicalNote.Source.MANUAL,
            created_by=self.doctor,
        )

        second_note = ClinicalNote.objects.create(
            encounter=self.encounter,
            version_number=2,
            original_text="Synthetic original note version two.",
            source=ClinicalNote.Source.MANUAL,
            created_by=self.doctor,
        )

        self.assertEqual(first_note.original_text,
                         "Synthetic original note version one.")
        self.assertEqual(second_note.original_text,
                         "Synthetic original note version two.")
        self.assertEqual(self.encounter.notes.count(), 2)

    def test_existing_note_cannot_be_edited(self):
        note = ClinicalNote.objects.create(
            encounter=self.encounter,
            version_number=1,
            original_text="Original synthetic note.",
            source=ClinicalNote.Source.MANUAL,
            created_by=self.doctor,
        )

        note.original_text = "Edited text that must not be saved."

        with self.assertRaises(ValidationError):
            note.save()

        note.refresh_from_db()
        self.assertEqual(note.original_text, "Original synthetic note.")

    def test_note_instance_cannot_be_deleted(self):
        note = ClinicalNote.objects.create(
            encounter=self.encounter,
            version_number=1,
            original_text="Synthetic note retained for audit.",
            source=ClinicalNote.Source.MANUAL,
            created_by=self.doctor,
        )

        with self.assertRaises(ValidationError):
            note.delete()

        self.assertTrue(
            ClinicalNote.objects.filter(pk=note.pk).exists()
        )

class PatientInterfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.doctor_group = Group.objects.get(name="Doctor")
        cls.admin_group = Group.objects.get(name="Administrator")

        cls.doctor_a = User.objects.create_user(
            username="patient_view_doctor_a",
            password="Synthetic-Test-Doctor-A-942!",
        )
        cls.doctor_a.groups.add(cls.doctor_group)

        cls.doctor_b = User.objects.create_user(
            username="patient_view_doctor_b",
            password="Synthetic-Test-Doctor-B-841!",
        )
        cls.doctor_b.groups.add(cls.doctor_group)

        cls.admin_user = User.objects.create_user(
            username="patient_view_admin",
            password="Synthetic-Test-Admin-384!",
        )
        cls.admin_user.groups.add(cls.admin_group)

        cls.patient_a = Patient.objects.create(
            identifier="DEMO-101",
            display_name="Synthetic Patient Alpha",
            created_by=cls.doctor_a,
        )
        cls.patient_b = Patient.objects.create(
            identifier="DEMO-202",
            display_name="Synthetic Patient Beta",
            created_by=cls.doctor_b,
        )

        PatientAccess.objects.create(
            patient=cls.patient_a,
            doctor=cls.doctor_a,
            granted_by=cls.admin_user,
        )
        PatientAccess.objects.create(
            patient=cls.patient_b,
            doctor=cls.doctor_b,
            granted_by=cls.admin_user,
        )

        cls.current_encounter = Encounter.objects.create(
            patient=cls.patient_a,
            title="Synthetic current consultation",
            encounter_date=timezone.now(),
            status=Encounter.Status.OPEN,
            created_by=cls.doctor_a,
        )

        cls.previous_encounter = Encounter.objects.create(
            patient=cls.patient_a,
            title="Synthetic previous consultation",
            encounter_date=timezone.now() - timedelta(days=30),
            status=Encounter.Status.COMPLETED,
            created_by=cls.doctor_a,
        )

        ClinicalNote.objects.create(
            encounter=cls.current_encounter,
            version_number=1,
            original_text=(
                "Synthetic demonstration note for the current encounter."
            ),
            source=ClinicalNote.Source.MANUAL,
            created_by=cls.doctor_a,
        )

        ClinicalNote.objects.create(
            encounter=cls.previous_encounter,
            version_number=1,
            original_text=(
                "Synthetic demonstration note for the previous encounter."
            ),
            source=ClinicalNote.Source.MANUAL,
            created_by=cls.doctor_a,
        )

    def test_patient_list_contains_only_assigned_patients(self):
        from django.urls import reverse

        self.client.force_login(self.doctor_a)

        response = self.client.get(reverse("dashboard:patients"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DEMO-101")
        self.assertNotContains(response, "DEMO-202")

    def test_patient_search_filters_authorized_records(self):
        from django.urls import reverse

        self.client.force_login(self.doctor_a)

        response = self.client.get(
            reverse("dashboard:patients"),
            {"q": "Alpha"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DEMO-101")
        self.assertNotContains(response, "DEMO-202")

    def test_unauthorized_patient_detail_returns_404(self):
        from django.urls import reverse

        self.client.force_login(self.doctor_a)

        response = self.client.get(
            reverse(
                "dashboard:patient_detail",
                kwargs={"patient_id": self.patient_b.pk},
            )
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn(
            b"Synthetic Patient Beta",
            response.content,
        )

    def test_authorized_patient_detail_shows_encounter_history(self):
        from django.urls import reverse

        self.client.force_login(self.doctor_a)

        response = self.client.get(
            reverse(
                "dashboard:patient_detail",
                kwargs={"patient_id": self.patient_a.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Synthetic current consultation")
        self.assertContains(response, "Synthetic previous consultation")
        self.assertContains(response, "Synthetic demonstration note")
        self.assertContains(response, "Current encounters")
        self.assertContains(response, "Previous encounters")

    def test_dashboard_counters_use_authorized_database_records(self):
        from django.urls import reverse

        self.client.force_login(self.doctor_a)

        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)

        summary_cards = response.context["summary_cards"]

        self.assertEqual(summary_cards[0]["value"], "1")
        self.assertEqual(summary_cards[1]["value"], "1")
        self.assertEqual(summary_cards[2]["value"], "—")
        self.assertEqual(summary_cards[3]["value"], "—")
        self.assertEqual(response.context["review_queue"], [])

    def test_administrator_group_without_assignment_sees_no_patients(self):
        from django.urls import reverse

        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("dashboard:patients"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "DEMO-101")
        self.assertNotContains(response, "DEMO-202")

class ClinicalNoteEntryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.doctor_group = Group.objects.get(name="Doctor")
        cls.admin_group = Group.objects.get(name="Administrator")

        cls.doctor = User.objects.create_user(
            username="note_entry_doctor",
            password="Synthetic-Note-Test-Doctor-482!",
        )
        cls.doctor.groups.add(cls.doctor_group)

        cls.other_doctor = User.objects.create_user(
            username="note_entry_other_doctor",
            password="Synthetic-Note-Test-Other-583!",
        )
        cls.other_doctor.groups.add(cls.doctor_group)

        cls.admin = User.objects.create_user(
            username="note_entry_admin",
            password="Synthetic-Note-Test-Admin-739!",
        )
        cls.admin.groups.add(cls.admin_group)

        cls.patient = Patient.objects.create(
            identifier="DEMO-NOTE-ENTRY",
            display_name="Synthetic Note Entry Patient",
            created_by=cls.doctor,
        )

        PatientAccess.objects.create(
            patient=cls.patient,
            doctor=cls.doctor,
            granted_by=cls.admin,
        )

        cls.encounter = Encounter.objects.create(
            patient=cls.patient,
            title="Synthetic note entry encounter",
            encounter_date=timezone.now(),
            status=Encounter.Status.OPEN,
            created_by=cls.doctor,
        )

    def test_authorized_doctor_can_open_note_form(self):
        from django.urls import reverse

        self.client.force_login(self.doctor)

        response = self.client.get(
            reverse(
                "dashboard:clinical_note_create",
                kwargs={"encounter_id": self.encounter.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add clinical note")
        self.assertContains(response, "New version: 1")

    def test_saving_note_creates_version_one(self):
        from django.urls import reverse

        self.client.force_login(self.doctor)

        response = self.client.post(
            reverse(
                "dashboard:clinical_note_create",
                kwargs={"encounter_id": self.encounter.pk},
            ),
            {
                "original_text": (
                    "Synthetic original note for version one."
                ),
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "dashboard:patient_detail",
                kwargs={"patient_id": self.patient.pk},
            ),
        )

        note = ClinicalNote.objects.get(encounter=self.encounter)
        self.assertEqual(note.version_number, 1)
        self.assertEqual(
            note.original_text,
            "Synthetic original note for version one.",
        )
        self.assertEqual(note.created_by, self.doctor)

    def test_saving_second_note_preserves_first_version(self):
        from django.urls import reverse

        first_note = ClinicalNote.objects.create(
            encounter=self.encounter,
            version_number=1,
            original_text="Synthetic original version one.",
            source=ClinicalNote.Source.MANUAL,
            created_by=self.doctor,
        )

        self.client.force_login(self.doctor)

        response = self.client.post(
            reverse(
                "dashboard:clinical_note_create",
                kwargs={"encounter_id": self.encounter.pk},
            ),
            {
                "original_text": (
                    "Synthetic original version two."
                ),
            },
        )

        self.assertEqual(response.status_code, 302)

        first_note.refresh_from_db()

        self.assertEqual(
            first_note.original_text,
            "Synthetic original version one.",
        )
        self.assertEqual(
            ClinicalNote.objects.filter(
                encounter=self.encounter,
            ).count(),
            2,
        )
        self.assertTrue(
            ClinicalNote.objects.filter(
                encounter=self.encounter,
                version_number=2,
                original_text="Synthetic original version two.",
            ).exists()
        )

    def test_blank_note_is_rejected(self):
        from django.urls import reverse

        self.client.force_login(self.doctor)

        response = self.client.post(
            reverse(
                "dashboard:clinical_note_create",
                kwargs={"encounter_id": self.encounter.pk},
            ),
            {"original_text": "   "},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Enter some note text before saving.",
        )
        self.assertEqual(
            ClinicalNote.objects.filter(
                encounter=self.encounter,
            ).count(),
            0,
        )

    def test_doctor_cannot_open_an_unassigned_encounter(self):
        from django.urls import reverse

        self.client.force_login(self.other_doctor)

        response = self.client.get(
            reverse(
                "dashboard:clinical_note_create",
                kwargs={"encounter_id": self.encounter.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_administrator_without_patient_access_cannot_add_note(self):
        from django.urls import reverse

        self.client.force_login(self.admin)

        response = self.client.get(
            reverse(
                "dashboard:clinical_note_create",
                kwargs={"encounter_id": self.encounter.pk},
            )
        )

        self.assertEqual(response.status_code, 403)