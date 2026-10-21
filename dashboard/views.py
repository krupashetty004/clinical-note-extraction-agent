from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Prefetch, Q
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from dashboard.forms import ClinicalNoteForm

from dashboard.access import role_required
from dashboard.models import ClinicalNote, Encounter, Patient


@role_required("Doctor", "Administrator")
def home(request: HttpRequest) -> HttpResponse:
    """Render the dashboard using persisted, authorized records."""

    patients = Patient.objects.accessible_to(request.user)

    patient_count = patients.count()

    active_encounter_count = Encounter.objects.filter(
        patient__in=patients,
        status=Encounter.Status.OPEN,
    ).count()

    recent_patients = (
        patients.prefetch_related(
            Prefetch(
                "encounters",
                queryset=Encounter.objects.order_by("-encounter_date"),
                to_attr="ordered_encounters",
            )
        )
        .order_by("-updated_at")[:5]
    )

    summary_cards = [
        {
            "label": "Patient records",
            "value": str(patient_count),
            "support": "Authorized records",
            "tone": "teal",
            "symbol": "PT",
        },
        {
            "label": "Active encounters",
            "value": str(active_encounter_count),
            "support": "Open encounters",
            "tone": "blue",
            "symbol": "EN",
        },
        {
            "label": "Awaiting review",
            "value": "—",
            "support": "Review workflow not implemented",
            "tone": "amber",
            "symbol": "RV",
        },
        {
            "label": "Completed reviews",
            "value": "—",
            "support": "Review history not implemented",
            "tone": "violet",
            "symbol": "OK",
        },
    ]

    context = {
        "page_title": "Clinical workspace",
        "active_nav": "overview",
        "summary_cards": summary_cards,
        "review_queue": [],
        "recent_patients": recent_patients,
    }

    return render(request, "dashboard/home.html", context)


def _placeholder_page(
    request: HttpRequest,
    *,
    title: str,
    description: str,
    stage_note: str,
    active_nav: str,
) -> HttpResponse:
    """Render a placeholder for a feature not yet implemented."""

    return render(
        request,
        "dashboard/placeholder.html",
        {
            "page_title": title,
            "page_description": description,
            "stage_note": stage_note,
            "active_nav": active_nav,
        },
    )


@role_required("Doctor", "Administrator")
def patients(request: HttpRequest) -> HttpResponse:
    """Search and paginate patients accessible to the current user."""

    query = request.GET.get("q", "").strip()[:100]

    queryset = Patient.objects.accessible_to(
        request.user
    ).annotate(
        encounter_count=Count("encounters")
    )

    if query:
        queryset = queryset.filter(
            Q(identifier__icontains=query)
            | Q(display_name__icontains=query)
        )

    paginator = Paginator(
        queryset.order_by("identifier"),
        20,
    )
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "dashboard/patients.html",
        {
            "page_title": "Patients",
            "active_nav": "patients",
            "query": query,
            "page_obj": page_obj,
            "patients": page_obj.object_list,
        },
    )


@role_required("Doctor", "Administrator")
def patient_detail(
    request: HttpRequest,
    patient_id: int,
) -> HttpResponse:
    """Display a patient's encounters only after checking authorization."""

    # Filter access before retrieving the requested patient.
    # Unauthorized users receive 404 instead of confirmation that
    # another patient's record exists.
    patient = get_object_or_404(
        Patient.objects.accessible_to(request.user),
        pk=patient_id,
    )

    encounters = list(
        patient.encounters.prefetch_related("notes").order_by(
            "-encounter_date"
        )
    )

    current_encounters = [
        encounter
        for encounter in encounters
        if encounter.status == Encounter.Status.OPEN
    ]

    previous_encounters = [
        encounter
        for encounter in encounters
        if encounter.status != Encounter.Status.OPEN
    ]

    return render(
        request,
        "dashboard/patient_detail.html",
        {
            "page_title": patient.identifier,
            "active_nav": "patients",
            "patient": patient,
            "current_encounters": current_encounters,
            "previous_encounters": previous_encounters,
        },
    )


@role_required("Doctor", "Administrator")
def knowledge_base(request: HttpRequest) -> HttpResponse:
    return _placeholder_page(
        request,
        title="Knowledge base",
        description="Manage reference documents used by the application.",
        stage_note=(
            "Upload, extraction, preview, approval, and retrieval "
            "will be implemented in a later stage."
        ),
        active_nav="knowledge",
    )


@role_required("Administrator")
def settings_page(request: HttpRequest) -> HttpResponse:
    return _placeholder_page(
        request,
        title="AI configuration",
        description="Manage approved AI provider and model settings.",
        stage_note=(
            "Secure provider configuration and model testing "
            "will be implemented in a later stage."
        ),
        active_nav="settings",
    )


def permission_denied(
    request: HttpRequest,
    exception=None,
) -> HttpResponse:
    """Render the custom forbidden page."""

    return render(
        request,
        "dashboard/403.html",
        status=403,
    )

@role_required("Doctor")
def clinical_note_create(
    request: HttpRequest,
    encounter_id: int,
) -> HttpResponse:
    """Create a new immutable version of an encounter's clinical note."""

    authorized_patients = Patient.objects.accessible_to(request.user)

    encounter = get_object_or_404(
        Encounter.objects.filter(
            patient__in=authorized_patients,
        ).select_related("patient"),
        pk=encounter_id,
    )

    if request.method == "POST":
        form = ClinicalNoteForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():
                    latest_version = (
                        ClinicalNote.objects.filter(
                            encounter=encounter,
                        ).aggregate(
                            max_version=Max("version_number"),
                        )["max_version"]
                        or 0
                    )

                    note = form.save(commit=False)
                    note.encounter = encounter
                    note.version_number = latest_version + 1
                    note.source = ClinicalNote.Source.MANUAL
                    note.created_by = request.user
                    note.save()

            except IntegrityError:
                form.add_error(
                    None,
                    (
                        "A note version could not be saved. "
                        "Refresh the page and try again."
                    ),
                )
            else:
                return redirect(
                    "dashboard:patient_detail",
                    patient_id=encounter.patient_id,
                )
    else:
        form = ClinicalNoteForm()

    latest_version = (
        ClinicalNote.objects.filter(
            encounter=encounter,
        ).aggregate(
            max_version=Max("version_number"),
        )["max_version"]
        or 0
    )

    return render(
        request,
        "dashboard/note_form.html",
        {
            "page_title": "Add clinical note",
            "active_nav": "patients",
            "encounter": encounter,
            "patient": encounter.patient,
            "form": form,
            "next_version": latest_version + 1,
        },
    )