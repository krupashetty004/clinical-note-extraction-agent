import json
from pathlib import Path

from django import forms

from dashboard.models import ClinicalNote
from dashboard.models import AIConfiguration, ClinicalProcessingRun, KnowledgeDocument


class _JsonListField(forms.CharField):
    """Validate a JSON array of objects while preserving a readable textarea."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("widget", forms.Textarea(attrs={"rows": 4, "class": "form-control font-monospace"}))
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        cleaned = super().to_python(value)
        if cleaned in (None, ""):
            return []
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Enter valid JSON for this annotation list.") from exc
        if not isinstance(parsed, list):
            raise forms.ValidationError("This field must be a JSON array.")
        return parsed


class ClinicalNoteForm(forms.ModelForm):
    """Validate clinical note text without changing its contents."""

    original_text = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control note-editor",
                "rows": 14,
                "placeholder": "Enter synthetic clinical note text...",
                "spellcheck": "true",
            }
        ),
    )

    class Meta:
        model = ClinicalNote
        fields = ("original_text",)

    def clean_original_text(self) -> str:
        """Reject empty or whitespace-only text while preserving valid text."""
        text = self.cleaned_data.get("original_text", "")

        if not text.strip():
            raise forms.ValidationError(
                "Enter some note text before saving."
            )

        # Preserve the original submitted text for evidence-offset accuracy.
        return text


class ProcessingRunReviewForm(forms.Form):
    """Capture a human disposition without changing pipeline outputs."""

    decision = forms.ChoiceField(
        choices=(
            (
                ClinicalProcessingRun.ReviewDecision.APPROVED,
                "Approve result",
            ),
            (
                ClinicalProcessingRun.ReviewDecision.REJECTED,
                "Reject result",
            ),
        ),
        widget=forms.RadioSelect,
    )
    comment = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Optional reviewer rationale",
            }
        ),
    )


class LocalAnnotationForm(forms.Form):
    """Capture a local annotation draft while preserving source provenance."""

    record_id = forms.CharField(widget=forms.HiddenInput())
    specialty = forms.CharField(max_length=80)
    note_text = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 12,
                "class": "form-control font-monospace",
                "readonly": "readonly",
            }
        )
    )
    source_dataset = forms.CharField(required=False, widget=forms.HiddenInput())
    source_url = forms.CharField(required=False, widget=forms.HiddenInput())
    source_row_number = forms.IntegerField(min_value=1, required=False)
    source_keywords = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
    )
    diagnoses = _JsonListField()
    procedures = _JsonListField()
    medications = _JsonListField()
    allergies = _JsonListField()
    vital_signs = _JsonListField()
    icd10_cm_codes = _JsonListField()
    annotator_id = forms.CharField(max_length=80, required=False)
    annotation_complete = forms.BooleanField(required=False)
    adjudication_status = forms.ChoiceField(
        required=False,
        choices=(
            ("not_required", "Not required"),
            ("adjudicated", "Adjudicated"),
            ("needs_rework", "Needs rework"),
        ),
    )
    conflict_status = forms.ChoiceField(
        required=False,
        choices=(
            ("not_reviewed", "Not reviewed"),
            ("not_applicable", "Not applicable"),
            ("resolved", "Resolved"),
        ),
    )
    conflict_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
    )
    reviewer_decision = forms.ChoiceField(
        required=False,
        choices=(
            ("pending", "Pending"),
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
        ),
    )
    reviewer_comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
    )

    def clean_note_text(self):
        text = self.cleaned_data.get("note_text", "")
        if not text.strip():
            raise forms.ValidationError("The source note text cannot be empty.")
        return text


class KnowledgeDocumentForm(forms.ModelForm):
    """Create or update knowledge-base documents with local citation metadata."""

    source_title = forms.CharField(max_length=200, required=False, label="Source title")
    source_url = forms.URLField(required=False, label="Source URL")
    source_quote = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        label="Citation quote",
    )
    source_file = forms.FileField(
        required=False,
        label="Source file",
        help_text="Supported locally: .txt, .md, .pdf, .png, .jpg, .jpeg. Maximum 10 MB.",
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".txt,.md,.pdf,.png,.jpg,.jpeg"}),
    )
    priority = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        label="Priority",
        help_text="Higher values appear first in priority order.",
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 0}),
    )

    class Meta:
        model = KnowledgeDocument
        fields = ("title", "summary", "content", "priority", "is_active")
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "summary": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "content": forms.Textarea(attrs={"rows": 18, "class": "form-control font-monospace"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["content"].required = False

    def clean_content(self):
        content = self.cleaned_data.get("content", "")
        cleaned = content.strip()
        if not cleaned:
            return ""
        lowered = cleaned.lower()
        for forbidden in ("<script", "</script>", "javascript:"):
            if forbidden in lowered:
                raise forms.ValidationError("Embedded scripts are not allowed in knowledge-base content.")
        return cleaned

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("content") and cleaned.get("source_file"):
            # Model validation requires content; the upload view replaces this
            # placeholder with extracted text before saving the document.
            cleaned["content"] = "Pending local extraction review."
            self.instance.content = cleaned["content"]
        elif not cleaned.get("content"):
            self.add_error("content", "Enter content or upload a supported source file.")
        return cleaned

    def clean_source_file(self):
        uploaded = self.cleaned_data.get("source_file")
        if not uploaded:
            return uploaded
        allowed = {".txt", ".md", ".pdf", ".png", ".jpg", ".jpeg"}
        suffix = Path(uploaded.name).suffix.lower()
        if suffix not in allowed:
            raise forms.ValidationError("Unsupported file type. Use TXT, Markdown, PDF, PNG, or JPEG.")
        if uploaded.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Files must be 10 MB or smaller.")
        first_bytes = uploaded.read(8)
        uploaded.seek(0)
        if suffix == ".pdf" and not first_bytes.startswith(b"%PDF"):
            raise forms.ValidationError("The uploaded file is not a valid PDF.")
        if suffix in {".jpg", ".jpeg"} and not first_bytes.startswith(b"\xff\xd8\xff"):
            raise forms.ValidationError("The uploaded file is not a valid JPEG.")
        if suffix == ".png" and first_bytes != b"\x89PNG\r\n\x1a\n":
            raise forms.ValidationError("The uploaded file is not a valid PNG.")
        return uploaded

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise forms.ValidationError("Title is required.")
        return title

    def clean(self):
        cleaned = super().clean()
        source_title = (cleaned.get("source_title") or "").strip()
        source_url = (cleaned.get("source_url") or "").strip()
        source_quote = (cleaned.get("source_quote") or "").strip()
        citations = []
        if source_title or source_url or source_quote:
            if not source_title:
                self.add_error("source_title", "A citation title is required when a source citation is supplied.")
            if not source_url:
                self.add_error("source_url", "A citation URL is required when a source citation is supplied.")
            if not source_quote:
                self.add_error("source_quote", "A citation quote is required when a source citation is supplied.")
            if not self.errors:
                citations.append({
                    "title": source_title,
                    "url": source_url,
                    "quote": source_quote,
                })
        cleaned["source_citations"] = citations
        return cleaned

    def save(self, commit=True, *, created_by=None, version_increment=False):
        instance = super().save(commit=False)
        instance.created_by = created_by or getattr(instance, "created_by", None)
        instance.source_citations = self.cleaned_data.get("source_citations", [])
        if version_increment and instance.pk:
            instance.version_number = (instance.version_number or 0) + 1
        if commit:
            instance.save()
        return instance


class AIConfigurationForm(forms.ModelForm):
    """Restrict provider settings to the documented local allowlist."""

    provider = forms.ChoiceField(
        choices=AIConfiguration.PROVIDER_CHOICES,
        widget=forms.Select(attrs={"class": "form-select", "data-provider-select": "true"}),
    )
    model = forms.ChoiceField(
        choices=(
            ("", "Select an approved model"),
            ("local-synthetic-v1", "Local synthetic v1"),
            ("openai/gpt-oss-20b", "Groq: openai/gpt-oss-20b"),
        ),
        widget=forms.Select(attrs={"class": "form-select", "data-model-select": "true"}),
    )
    api_key = forms.CharField(
        required=False,
        label="API key",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "autocomplete": "new-password",
                "placeholder": "Leave blank to keep the saved key",
            }
        ),
        help_text="Stored encrypted with the deployment secret and never displayed back.",
    )

    class Meta:
        model = AIConfiguration
        fields = (
            "provider",
            "model",
            "temperature",
            "max_tokens",
            "request_limit",
            "token_limit",
        )
        widgets = {
            "temperature": forms.NumberInput(
                attrs={"class": "form-control", "min": "0", "max": "2", "step": "0.01"}
            ),
            "max_tokens": forms.NumberInput(
                attrs={"class": "form-control", "min": "1", "max": "8192"}
            ),
            "request_limit": forms.NumberInput(
                attrs={"class": "form-control", "min": "1", "max": "1000000"}
            ),
            "token_limit": forms.NumberInput(
                attrs={"class": "form-control", "min": "1", "max": "1000000000"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["request_limit"].required = False
        self.fields["token_limit"].required = False
        self.fields["request_limit"].initial = self.instance.request_limit or 100
        self.fields["token_limit"].initial = self.instance.token_limit or 100000

    def clean(self):
        cleaned = super().clean()
        provider = cleaned.get("provider")
        model = cleaned.get("model")
        expected = {
            "synthetic": "local-synthetic-v1",
            "groq": "openai/gpt-oss-20b",
        }
        if provider and model and expected.get(provider) != model:
            self.add_error("model", "That model is not approved for the selected provider.")
        return cleaned