from django.contrib import admin

from dashboard.models import (
    ClinicalNote,
    Encounter,
    Patient,
    PatientAccess,
)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = (
        "identifier",
        "display_name",
        "created_by",
        "created_at",
    )
    search_fields = ("identifier", "display_name")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("identifier",)

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PatientAccess)
class PatientAccessAdmin(admin.ModelAdmin):
    list_display = (
        "patient",
        "doctor",
        "granted_by",
        "granted_at",
    )
    search_fields = (
        "patient__identifier",
        "patient__display_name",
        "doctor__username",
    )
    autocomplete_fields = ("patient", "doctor", "granted_by")
    readonly_fields = ("granted_at",)
    ordering = ("patient_id", "doctor_id")


@admin.register(Encounter)
class EncounterAdmin(admin.ModelAdmin):
    list_display = (
        "patient",
        "title",
        "encounter_date",
        "status",
        "created_by",
    )
    list_filter = ("status",)
    search_fields = (
        "patient__identifier",
        "patient__display_name",
        "title",
    )
    autocomplete_fields = ("patient", "created_by")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-encounter_date",)

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ClinicalNote)
class ClinicalNoteAdmin(admin.ModelAdmin):
    list_display = (
        "encounter",
        "version_number",
        "source",
        "created_by",
        "created_at",
    )
    list_filter = ("source",)
    search_fields = (
        "encounter__patient__identifier",
        "encounter__title",
    )
    readonly_fields = tuple(
        field.name for field in ClinicalNote._meta.fields
    )
    ordering = ("encounter_id", "-version_number")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False