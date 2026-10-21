from django import forms

from dashboard.models import ClinicalNote


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