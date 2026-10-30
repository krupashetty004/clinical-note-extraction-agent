from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
import base64
import hashlib


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


class KnowledgeDocument(models.Model):
    """A local, versioned knowledge-base document with citations."""

    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True)
    content = models.TextField()
    source_citations = models.JSONField(default=list, blank=True)
    source_file = models.FileField(upload_to="knowledge_sources/", blank=True, null=True)
    source_filename = models.CharField(max_length=255, blank=True, default="")
    source_type = models.CharField(max_length=32, blank=True, default="text")
    ingestion_status = models.CharField(max_length=32, default="manual")
    ingestion_error = models.TextField(blank=True, default="")
    priority = models.PositiveIntegerField(
        default=0,
        help_text="Higher values appear first when sorted by priority.",
    )
    version_number = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="knowledge_documents_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="knowledge_documents_deactivated",
    )

    class Meta:
        ordering = ["-updated_at", "-pk"]

    def clean(self):
        super().clean()
        if not self.title.strip():
            raise ValidationError({"title": "Document title cannot be empty."})
        if not self.content.strip():
            raise ValidationError({"content": "Document content cannot be empty."})
        if not isinstance(self.source_citations, list):
            raise ValidationError({"source_citations": "Citations must be a JSON list."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.title} (v{self.version_number})"


class AIConfiguration(models.Model):
    """Versioned allowlisted AI configuration without storing provider secrets."""

    PROVIDER_CHOICES = (
        ("synthetic", "Local synthetic test provider"),
        ("groq", "Groq"),
        ("gemini", "Google Gemini (adapter not implemented)"),
    )

    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES)
    model = models.CharField(max_length=120)
    temperature = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0,
    )
    max_tokens = models.PositiveIntegerField(default=2048)
    request_limit = models.PositiveIntegerField(default=100)
    token_limit = models.PositiveIntegerField(default=100000)
    requests_used = models.PositiveIntegerField(default=0)
    tokens_used = models.PositiveIntegerField(default=0)
    api_key_encrypted = models.TextField(blank=True, default="")
    version_number = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=False)
    last_test_status = models.CharField(max_length=24, default="not_tested")
    last_test_result = models.CharField(max_length=255, blank=True, default="")
    tested_at = models.DateTimeField(null=True, blank=True)
    tested_fingerprint = models.CharField(max_length=64, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ai_configurations_created",
    )
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_configurations_activated",
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-pk"]

    def clean(self):
        super().clean()
        allowed_models = {
            "synthetic": {"local-synthetic-v1"},
            "groq": {
                "openai/gpt-oss-20b",
                "openai/gpt-oss-120b",
                "qwen/qwen3.8-27b",
            },
            "gemini": {
                "gemini-1.5-flash",
                "gemini-2.0-flash",
            },
        }
        if self.provider not in allowed_models:
            raise ValidationError({"provider": "Select an approved provider."})
        if self.model not in allowed_models[self.provider]:
            raise ValidationError({"model": "Select an approved model for this provider."})
        if not 0 <= self.temperature <= 2:
            raise ValidationError({"temperature": "Temperature must be between 0 and 2."})
        if not 1 <= self.max_tokens <= 8192:
            raise ValidationError({"max_tokens": "Max tokens must be between 1 and 8192."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def get_api_key(self) -> str:
        """Decrypt and return the stored plaintext API key."""
        if not self.api_key_encrypted:
            return ""
        from cryptography.fernet import Fernet
        key = base64.urlsafe_b64encode(
            hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        )
        try:
            return Fernet(key).decrypt(self.api_key_encrypted.encode("ascii")).decode("utf-8")
        except Exception:
            return ""

    def set_api_key(self, value: str) -> None:
        value = value.strip()
        if not value:
            return
        from cryptography.fernet import Fernet

        key = base64.urlsafe_b64encode(
            hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        )
        self.api_key_encrypted = Fernet(key).encrypt(value.encode("utf-8")).decode("ascii")

    def has_api_key(self) -> bool:
        return bool(self.api_key_encrypted)

    @property
    def remaining_requests(self) -> int:
        return max(self.request_limit - self.requests_used, 0)

    @property
    def remaining_tokens(self) -> int:
        return max(self.token_limit - self.tokens_used, 0)

    def __str__(self) -> str:
        return f"{self.provider}/{self.model} (v{self.version_number})"


class ClinicalProcessingRun(models.Model):
    """Persist one processing attempt for an immutable clinical note."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        NEEDS_REVIEW = "needs_review", "Needs review"
        FAILED = "failed", "Failed"

    class ExecutionMode(models.TextChoices):
        UNKNOWN = "unknown", "Unknown / legacy"
        SYNTHETIC_DEMO = "synthetic_demo", "Synthetic demonstration"
        AI_AGENT = "ai_agent", "AI Extraction Agent"

    class ReviewDecision(models.TextChoices):
        PENDING = "pending", "Pending human review"
        APPROVED = "approved", "Approved by reviewer"
        REJECTED = "rejected", "Rejected by reviewer"

    execution_mode = models.CharField(
        max_length=24,
        choices=ExecutionMode.choices,
        default=ExecutionMode.UNKNOWN,
    )

    clinical_note = models.ForeignKey(
        ClinicalNote,
        on_delete=models.PROTECT,
        related_name="processing_runs",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    extraction_attempts = models.PositiveSmallIntegerField(default=0)
    verification_attempts = models.PositiveSmallIntegerField(default=0)

    # Structured outputs are stored independently for traceability.
    # These may contain clinical text and must be access-controlled.
    extraction_result = models.JSONField(null=True, blank=True)
    coding_result = models.JSONField(null=True, blank=True)
    verification_result = models.JSONField(null=True, blank=True)
    # Trace the approved reference passages supplied to the agent. This is
    # metadata only; the retrieved text remains in the prompt at execution time.
    knowledge_references = models.JSONField(default=list, blank=True)
    knowledge_retrieval_status = models.CharField(
        max_length=20,
        default="not_attempted",
        choices=(
            ("not_attempted", "Not attempted"),
            ("no_matches", "No matching references"),
            ("retrieved", "References retrieved"),
            ("unavailable", "Retrieval unavailable"),
        ),
    )
    item_dispositions = models.JSONField(default=list, blank=True)
    review_reasons = models.JSONField(default=list, blank=True)
    review_decision = models.CharField(
        max_length=16,
        choices=ReviewDecision.choices,
        default=ReviewDecision.PENDING,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="clinical_processing_reviews",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer_comment = models.TextField(blank=True, default="")

    # Safe error identifier only; do not store exception messages.
    failure_code = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="clinical_processing_runs",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(
                fields=["clinical_note", "-created_at"],
                name="proc_run_note_date_idx",
            ),
            models.Index(
                fields=["status", "-created_at"],
                name="proc_run_status_date_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Processing run {self.pk} "
            f"for clinical note {self.clinical_note_id}: "
            f"{self.status}"
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
from django.conf import settings