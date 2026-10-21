from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class PatientQuerySet(models.QuerySet):
    """Patient queries scoped to the requesting user's permissions."""

    def accessible_to(self, user):
        if not getattr(user, "is_authenticated", False):
            return self.none()

        # Superusers have full access for local administration.
        if user.is_superuser:
            return self.all()

        # Application administrators do not automatically receive
        # clinical-record access. A Doctor role and explicit assignment
        # are required.
        if not user.groups.filter(name="Doctor").exists():
            return self.none()

        return self.filter(
            access_grants__doctor_id=user.pk,
        ).distinct()


class Patient(models.Model):
    """A patient record with a minimal set of identifying fields."""

    identifier = models.CharField(
        max_length=40,
        unique=True,
    )
    display_name = models.CharField(max_length=120)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="patients_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PatientQuerySet.as_manager()

    class Meta:
        ordering = ["identifier"]

    def __str__(self) -> str:
        return f"{self.identifier} — {self.display_name}"


class PatientAccess(models.Model):
    """An explicit grant allowing a doctor to access a patient."""

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="access_grants",
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="patient_access_assignments",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="patient_access_grants_made",
    )
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "doctor"],
                name="unique_patient_doctor_access",
            ),
        ]
        indexes = [
            models.Index(
                fields=["doctor", "patient"],
                name="pataccess_doc_pat_idx",
            ),
        ]
        ordering = ["patient_id", "doctor_id"]

    def __str__(self) -> str:
        return f"{self.doctor} → {self.patient}"


class Encounter(models.Model):
    """A visit or consultation belonging to a patient."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="encounters",
    )
    title = models.CharField(max_length=160)
    encounter_date = models.DateTimeField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="encounters_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-encounter_date", "-pk"]
        indexes = [
            models.Index(
                fields=["patient", "status"],
                name="enc_patient_status_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.patient.identifier} — {self.title}"


class ClinicalNote(models.Model):

    """An append-only version of the original clinical note text."""

    class Source(models.TextChoices):
        MANUAL = "manual", "Manually entered"
        TEXT_IMPORT = "text_import", "Text import"

    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.PROTECT,
        related_name="notes",
    )
    version_number = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    original_text = models.TextField()
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.MANUAL,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="clinical_notes_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["encounter_id", "-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["encounter", "version_number"],
                name="unique_encounter_note_version",
            ),
            models.CheckConstraint(
                condition=Q(version_number__gte=1),
                name="clinical_note_version_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["encounter", "-version_number"],
                name="note_enc_ver_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        # Original notes are append-only through normal model saves.
        # Create a new version instead of editing an existing one.
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError(
                "Clinical notes cannot be edited. Create a new version."
            )

        if not self.original_text.strip():
            raise ValidationError(
                {"original_text": "Clinical note text cannot be empty."}
            )

        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Clinical notes are retained as versioned history."
        )

    def __str__(self) -> str:
        return (
            f"{self.encounter.patient.identifier} — "
            f"{self.encounter.title} — v{self.version_number}"
        )

class ICDCode(models.Model):
    """Official ICD-10-CM diagnosis code and description."""

    code = models.CharField(
        max_length=7,
        primary_key=True,
    )
    description = models.TextField()

    class Meta:
        ordering = ["code"]
        verbose_name = "ICD-10-CM code"
        verbose_name_plural = "ICD-10-CM codes"

    def __str__(self) -> str:
        return f"{self.code} - {self.description}"