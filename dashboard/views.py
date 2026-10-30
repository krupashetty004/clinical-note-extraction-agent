import hashlib
import importlib.util
import json
import os
from pathlib import Path

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Prefetch, Q
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone
from django.conf import settings
from django.core.paginator import Paginator

from dashboard.forms import (
    AIConfigurationForm,
    ClinicalNoteForm,
    EncounterForm,
    KnowledgeDocumentForm,
    LocalAnnotationForm,
    PatientForm,
    ProcessingRunReviewForm,
)

from dashboard.access import role_required
from dashboard.models import (
    AIConfiguration,
    ClinicalNote,
    ClinicalProcessingRun,
    Encounter,
    KnowledgeDocument,
    Patient,
    PatientAccess,
)
from dashboard.knowledge_ingestion import KnowledgeIngestionError, extract_uploaded_source

from django.views.decorators.http import require_POST

from dashboard.extraction.processing_service import process_clinical_note
from dashboard.extraction.synthetic_demo import (
    SyntheticDemoExtractionProvider,
    SyntheticDemoVerificationProvider,
)

ANNOTATION_SPECIALTIES = [
    "Cardiology",
    "Neurology",
    "Pulmonology",
    "Endocrinology",
    "Gastroenterology",
    "Orthopedics",
    "Dermatology",
    "Family Medicine",
    "Oncology",
    "Internal Medicine",
]

ANNOTATION_SOURCE_DATASET = "kaggle:tboyle10/medicaltranscriptions"
ANNOTATION_SOURCE_URL = "https://www.kaggle.com/datasets/tboyle10/medicaltranscriptions/data"
ANNOTATION_WORKING_QUEUE_FILENAME = ".annotation_working_queue.jsonl"


def _annotation_template_path() -> Path:
    """Prefer the uploaded CSV's locally prepared queue; fall back to the tracked template."""
    repo_root = Path(settings.BASE_DIR).resolve()
    local_candidate = (
        repo_root
        / ".dataset_working"
        / "annotations"
        / "annotation_template_100.jsonl"
    )
    tracked_candidate = (
        repo_root
        / "mirai_dataset_preparation_pack"
        / "data"
        / "external"
        / "mtsamples"
        / "annotations"
        / "annotation_template_100.jsonl"
    )
    candidate = local_candidate if local_candidate.is_file() else tracked_candidate
    try:
        candidate.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("annotation queue path escapes repository root") from exc
    return candidate


def _annotation_working_path() -> Path:
    """Resolve the ignored working queue beside the selected source template."""
    template_path = _annotation_template_path()
    if template_path.parent.parent.name == ".dataset_working":
        candidate = template_path.parent / ".annotation_working_queue.jsonl"
    else:
        candidate = Path(settings.BASE_DIR).resolve() / ANNOTATION_WORKING_QUEUE_FILENAME
    repo_root = Path(settings.BASE_DIR).resolve()
    try:
        candidate.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("annotation working path escapes repository root") from exc
    return candidate


def _annotation_validator():
    """Load the project validator for local export integrity checks."""
    validator_path = (
        Path(__file__).resolve().parents[1]
        / "mirai_dataset_preparation_pack"
        / "scripts"
        / "validate_annotations.py"
    )
    spec = importlib.util.spec_from_file_location(
        "mirai_annotation_validator",
        validator_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load annotation validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ANNOTATION_VALIDATOR = _annotation_validator()


def _empty_gold_annotations() -> dict:
    return {
        "diagnoses": [],
        "procedures": [],
        "medications": [],
        "allergies": [],
        "vital_signs": [],
        "icd10_cm_codes": [],
    }


def _provisional_annotation_terms() -> dict[str, list[str]]:
    return {
        "diagnoses": [
            "hypertension",
            "diabetes mellitus",
            "osteoarthritis",
            "migraine",
            "lung cancer",
            "chronic kidney disease",
            "allergic rhinitis",
            "pneumonia",
            "asthma",
            "depression",
        ],
        "procedures": [
            "surgery",
            "vasectomy",
            "bunionectomy",
            "intubation",
            "screening",
            "ultrasound",
            "imaging",
            "biopsy",
            "resection",
        ],
        "medications": [
            "metformin",
            "sumatriptan",
            "aspirin",
            "insulin",
            "warfarin",
            "topical corticosteroid",
            "vicodin",
            "ibuprofen",
            "prednisone",
        ],
        "allergies": [
            "penicillin",
            "latex",
            "peanuts",
            "shellfish",
            "sulfa",
            "allergy",
        ],
        "vital_signs": [
            "blood pressure",
            "temperature",
            "heart rate",
            "respiratory rate",
            "oxygen saturation",
        ],
    }


def _build_provisional_annotations(note_text: str) -> dict[str, list[dict]]:
    text = note_text or ""
    suggestions: dict[str, list[dict]] = {
        "diagnoses": [],
        "procedures": [],
        "medications": [],
        "allergies": [],
        "vital_signs": [],
    }
    seen: set[tuple[str, int, int]] = set()

    for category, terms in _provisional_annotation_terms().items():
        for term in sorted(terms, key=len, reverse=True):
            lower_term = term.lower()
            cursor = 0
            while True:
                found = text.lower().find(lower_term, cursor)
                if found == -1:
                    break
                end_offset = found + len(term)
                key = (category, found, end_offset)
                if key in seen:
                    cursor = end_offset
                    continue
                evidence = text[found:end_offset]
                item = {
                    "entity": evidence,
                    "evidence_text": evidence,
                    "start_offset": found,
                    "end_offset": end_offset,
                    "status": "active" if category in {"diagnoses", "medications"} else "current" if category == "medications" else None,
                    "verification_status": "UNVERIFIED",
                    "provisional": True,
                }
                if category in {"diagnoses", "medications"}:
                    item["status"] = "active" if category == "diagnoses" else "current"
                elif category == "vital_signs":
                    item["status"] = None
                elif category == "allergies":
                    item["status"] = None
                suggestions[category].append(item)
                seen.add(key)
                cursor = end_offset
    return suggestions


def _load_annotation_queue_from_jsonl(path: Path) -> list[dict]:
    """Read the JSONL queue while preserving the original note text and provenance."""
    queue: list[dict] = []
    if not path.exists():
        return queue
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            if not raw_line.strip():
                continue
            record = json.loads(raw_line)
            if not isinstance(record, dict):
                continue
            queue.append(record)
    return queue


def _persist_local_annotation_queue_file(queue: list[dict]) -> Path:
    """Persist local drafts to a Git-ignored working queue without mutating the source template."""
    working_path = _annotation_working_path()
    working_path.parent.mkdir(parents=True, exist_ok=True)
    with working_path.open("w", encoding="utf-8") as handle:
        for record in queue:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    return working_path


def _build_annotation_queue() -> list[dict]:
    """Load the canonical annotation template from the repository instead of synthesizing a queue."""
    template_path = _annotation_template_path()
    if not template_path.exists():
        raise FileNotFoundError(f"Annotation queue template not found: {template_path}")

    queue: list[dict] = []
    with template_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            if not raw_line.strip():
                continue
            record = json.loads(raw_line)
            if not isinstance(record, dict):
                continue
            normalized = {
                "record_id": record.get("record_id"),
                "specialty": record.get("specialty", ""),
                "note_text": record.get("note_text", ""),
                "source_dataset": record.get("source_dataset", ANNOTATION_SOURCE_DATASET),
                "source_url": record.get("source_url", ANNOTATION_SOURCE_URL),
                "source_row_number": record.get("source_row_number", 1),
                "source_keywords": record.get("source_keywords", ""),
                "annotator_id": "",
                "annotation_complete": False,
                "adjudication_status": record.get("adjudication_status", "not_required"),
                "conflict_status": record.get("conflict_status", "not_reviewed"),
                "conflict_notes": record.get("conflict_notes", ""),
                "reviewer_decision": record.get("reviewer_decision", "pending"),
                "reviewer_comment": record.get("reviewer_comment", ""),
                "gold_annotations": record.get("gold_annotations") or _empty_gold_annotations(),
                "provisional_annotations": _build_provisional_annotations(record.get("note_text", "")),
            }
            queue.append(normalized)
    return queue


def _get_local_annotation_queue(request: HttpRequest) -> list[dict]:
    working_path = _annotation_working_path()
    if working_path.exists() and working_path.stat().st_size > 0:
        queue = _load_annotation_queue_from_jsonl(working_path)
        if queue:
            # If any record was previously initialized with hardcoded empty/default values,
            # backfill missing saved selections from the canonical template without overwriting manual drafts.
            template_records = None
            modified = False
            for record in queue:
                if not record.get("annotator_id") and record.get("adjudication_status") == "not_required":
                    if template_records is None:
                        template_records = {r["record_id"]: r for r in _build_annotation_queue()}
                    tmpl = template_records.get(record.get("record_id"))
                    if tmpl:
                        record["adjudication_status"] = tmpl.get("adjudication_status", "not_required")
                        record["conflict_status"] = tmpl.get("conflict_status", "not_reviewed")
                        record["reviewer_decision"] = tmpl.get("reviewer_decision", "pending")
                        modified = True
            if modified:
                _persist_local_annotation_queue_file(queue)
            request.session["local_annotation_queue"] = queue
            return queue

    queue = _build_annotation_queue()
    _persist_local_annotation_queue_file(queue)
    request.session["local_annotation_queue"] = queue
    return queue


def _save_local_annotation_queue(request: HttpRequest, queue: list[dict]) -> None:
    request.session["local_annotation_queue"] = queue
    _persist_local_annotation_queue_file(queue)


def _record_to_form_initial(record: dict) -> dict:
    gold = record.get("gold_annotations") or _empty_gold_annotations()
    provisional = record.get("provisional_annotations") or _build_provisional_annotations(record.get("note_text", ""))
    chosen = {
        "diagnoses": gold.get("diagnoses") or provisional.get("diagnoses", []),
        "procedures": gold.get("procedures") or provisional.get("procedures", []),
        "medications": gold.get("medications") or provisional.get("medications", []),
        "allergies": gold.get("allergies") or provisional.get("allergies", []),
        "vital_signs": gold.get("vital_signs") or provisional.get("vital_signs", []),
    }
    return {
        "record_id": record["record_id"],
        "specialty": record.get("specialty", ""),
        "note_text": record.get("note_text", ""),
        "source_dataset": record.get("source_dataset", ANNOTATION_SOURCE_DATASET),
        "source_url": record.get("source_url", ANNOTATION_SOURCE_URL),
        "source_row_number": record.get("source_row_number", 1),
        "source_keywords": record.get("source_keywords", ""),
        "diagnoses": json.dumps(chosen["diagnoses"], ensure_ascii=False),
        "procedures": json.dumps(chosen["procedures"], ensure_ascii=False),
        "medications": json.dumps(chosen["medications"], ensure_ascii=False),
        "allergies": json.dumps(chosen["allergies"], ensure_ascii=False),
        "vital_signs": json.dumps(chosen["vital_signs"], ensure_ascii=False),
        "icd10_cm_codes": json.dumps(gold.get("icd10_cm_codes", []), ensure_ascii=False),
        "annotator_id": record.get("annotator_id", ""),
        "annotation_complete": bool(record.get("annotation_complete")),
        "adjudication_status": record.get("adjudication_status", "not_required"),
        "conflict_status": record.get("conflict_status", "not_reviewed"),
        "conflict_notes": record.get("conflict_notes", ""),
        "reviewer_decision": record.get("reviewer_decision", "pending"),
        "reviewer_comment": record.get("reviewer_comment", ""),
    }


def _validate_record_for_export(record: dict) -> list[str]:
    payload = dict(record)
    payload["gold_annotations"] = payload.get("gold_annotations", _empty_gold_annotations())
    if not payload.get("annotation_complete"):
        return ["This draft is not marked complete and cannot be exported as gold."]
    return ANNOTATION_VALIDATOR.validate_record(payload, 0)


@role_required("Doctor", "Administrator")
def home(request: HttpRequest) -> HttpResponse:
    """Render the dashboard using persisted, authorized records."""

    patients = Patient.objects.accessible_to(request.user)

    patient_count = patients.count()

    active_encounter_count = Encounter.objects.filter(
        patient__in=patients,
        status=Encounter.Status.OPEN,
    ).count()

    processing_runs = ClinicalProcessingRun.objects.filter(
        clinical_note__encounter__patient__in=patients,
    ).select_related(
        "clinical_note__encounter__patient",
    )
    review_queue = list(
        processing_runs.filter(
            status=ClinicalProcessingRun.Status.NEEDS_REVIEW,
        ).order_by("-created_at")[:5]
    )
    completed_review_count = processing_runs.filter(
        status=ClinicalProcessingRun.Status.COMPLETED,
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
            "value": str(
                processing_runs.filter(
                    status=ClinicalProcessingRun.Status.NEEDS_REVIEW,
                ).count()
            ),
            "support": "Processing runs needing review",
            "tone": "amber",
            "symbol": "RV",
        },
        {
            "label": "Completed reviews",
            "value": str(completed_review_count),
            "support": "Completed processing runs",
            "tone": "violet",
            "symbol": "OK",
        },
    ]

    context = {
        "page_title": "Clinical workspace",
        "active_nav": "overview",
        "summary_cards": summary_cards,
        "review_queue": review_queue,
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
def patient_create(request: HttpRequest) -> HttpResponse:
    """Allow doctors or administrators to register a new patient."""
    if request.method == "POST":
        form = PatientForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                patient = form.save(commit=False)
                patient.created_by = request.user
                patient.save()
                # Automatically grant access to the doctor who created the patient
                PatientAccess.objects.get_or_create(
                    patient=patient,
                    doctor=request.user,
                    defaults={"granted_by": request.user},
                )
            return redirect("dashboard:patient_detail", patient_id=patient.pk)
    else:
        form = PatientForm()

    return render(
        request,
        "dashboard/patient_form.html",
        {
            "page_title": "Register new patient",
            "active_nav": "patients",
            "form": form,
        },
    )


@role_required("Doctor", "Administrator")
@require_POST
def patient_delete(request: HttpRequest, patient_id: int) -> HttpResponse:
    """Delete a patient record with permission checks and cascade cleaning."""
    patient = get_object_or_404(
        Patient.objects.accessible_to(request.user),
        pk=patient_id,
    )

    # Permission: only the creator doctor or an Administrator can delete the patient
    is_creator = patient.created_by_id == request.user.pk
    is_admin = request.user.groups.filter(name="Administrator").exists() or request.user.is_superuser
    if not (is_creator or is_admin):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Only the creator doctor or an Administrator can delete this patient record.")

    with transaction.atomic():
        # Specific cleanup: if any knowledge-base document was added referencing this patient, delete it
        KnowledgeDocument.objects.filter(
            Q(title__icontains=patient.identifier)
            | Q(summary__icontains=patient.identifier)
            | Q(content__icontains=patient.identifier)
        ).delete()

        # Delete all processing runs, clinical notes, and encounters for this patient
        encounters = Encounter.objects.filter(patient=patient)
        notes = ClinicalNote.objects.filter(encounter__in=encounters)
        ClinicalProcessingRun.objects.filter(clinical_note__in=notes).delete()
        notes.delete()
        encounters.delete()

        # Delete access grants and the patient
        PatientAccess.objects.filter(patient=patient).delete()
        patient.delete()

    return redirect("dashboard:patients")


@role_required("Doctor", "Administrator")
def encounter_create(request: HttpRequest, patient_id: int) -> HttpResponse:
    """Allow doctors to create a new encounter for an authorized patient."""
    patient = get_object_or_404(
        Patient.objects.accessible_to(request.user),
        pk=patient_id,
    )

    if request.method == "POST":
        form = EncounterForm(request.POST)
        if form.is_valid():
            encounter = form.save(commit=False)
            encounter.patient = patient
            encounter.created_by = request.user
            encounter.save()
            return redirect("dashboard:patient_detail", patient_id=patient.pk)
    else:
        form = EncounterForm()

    return render(
        request,
        "dashboard/encounter_form.html",
        {
            "page_title": f"New encounter — {patient.display_name}",
            "active_nav": "patients",
            "patient": patient,
            "form": form,
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
        patient.encounters.prefetch_related(
            "notes__processing_runs"
        ).order_by("-encounter_date")
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
            "synthetic_demo_enabled": (
                settings.SYNTHETIC_DEMO_ENABLED
                and request.user.groups.filter(name="Doctor").exists()
            ),
            "can_delete": (
                patient.created_by_id == request.user.pk
                or request.user.groups.filter(name="Administrator").exists()
                or request.user.is_superuser
            ),
        },
    )


@role_required("Doctor")
def annotation_queue(request: HttpRequest) -> HttpResponse:
    """Render the local annotation queue and progress summary."""
    queue = _get_local_annotation_queue(request)
    completed = sum(1 for record in queue if record.get("annotation_complete"))
    adjudicated = sum(1 for record in queue if record.get("adjudication_status") == "adjudicated")
    progress = {
        "prepared": len(queue),
        "annotated": completed,
        "adjudicated": adjudicated,
        "remaining": len(queue) - completed,
    }
    return render(
        request,
        "dashboard/annotation_queue.html",
        {
            "page_title": "Annotation queue",
            "active_nav": "annotation",
            "queue": queue,
            "progress": progress,
        },
    )


@role_required("Doctor")
def annotation_detail(request: HttpRequest, record_id: str) -> HttpResponse:
    """Render the note view and save local annotation drafts."""
    queue = _get_local_annotation_queue(request)
    record = next((item for item in queue if item["record_id"] == record_id), None)
    if record is None:
        raise Http404

    record.setdefault("provisional_annotations", _build_provisional_annotations(record.get("note_text", "")))
    form = LocalAnnotationForm(request.POST or None, initial=_record_to_form_initial(record))
    if request.method == "POST":
        if form.is_valid():
            cleaned = form.cleaned_data
            record.update(
                {
                    "record_id": cleaned["record_id"],
                    "specialty": cleaned["specialty"],
                    "note_text": cleaned["note_text"],
                    "source_dataset": cleaned.get("source_dataset") or ANNOTATION_SOURCE_DATASET,
                    "source_url": cleaned.get("source_url") or ANNOTATION_SOURCE_URL,
                    "source_row_number": cleaned.get("source_row_number") or record.get("source_row_number", 1),
                    "source_keywords": cleaned.get("source_keywords", ""),
                    "annotator_id": cleaned.get("annotator_id", ""),
                    "annotation_complete": bool(cleaned.get("annotation_complete")),
                    "adjudication_status": cleaned.get("adjudication_status", "not_required"),
                    "conflict_status": cleaned.get("conflict_status", "not_reviewed"),
                    "conflict_notes": cleaned.get("conflict_notes", ""),
                    "reviewer_decision": cleaned.get("reviewer_decision", "pending"),
                    "reviewer_comment": cleaned.get("reviewer_comment", ""),
                    "gold_annotations": {
                        "diagnoses": cleaned.get("diagnoses", []),
                        "procedures": cleaned.get("procedures", []),
                        "medications": cleaned.get("medications", []),
                        "allergies": cleaned.get("allergies", []),
                        "vital_signs": cleaned.get("vital_signs", []),
                        "icd10_cm_codes": cleaned.get("icd10_cm_codes", []),
                    },
                    "provisional_annotations": _build_provisional_annotations(cleaned.get("note_text", "")),
                }
            )
            _save_local_annotation_queue(request, queue)
            if request.POST.get("action") == "export":
                errors = _validate_record_for_export(record)
                if errors:
                    form.add_error(None, errors[0])
                    validation_errors = errors
                    return render(
                        request,
                        "dashboard/annotation_note.html",
                        {
                            "page_title": f"Annotation {record['record_id']}",
                            "active_nav": "annotation",
                            "record": record,
                            "form": form,
                            "queue_index": next((index for index, item in enumerate(queue) if item["record_id"] == record["record_id"]), 0),
                            "validation_errors": validation_errors,
                            "queue": queue,
                        },
                    )
                response = JsonResponse({
                    "record_id": record["record_id"],
                    "status": "ready_for_export",
                    "message": "Draft validated; export safe to generate.",
                })
                response.status_code = 200
                return response
            return redirect("dashboard:annotation_detail", record_id=record["record_id"])

    validation_errors = _validate_record_for_export(record) if record.get("annotation_complete") else []
    return render(
        request,
        "dashboard/annotation_note.html",
        {
            "page_title": f"Annotation {record['record_id']}",
            "active_nav": "annotation",
            "record": record,
            "form": form,
            "queue_index": next((index for index, item in enumerate(queue) if item["record_id"] == record_id), 0),
            "validation_errors": validation_errors,
            "queue": queue,
        },
    )


@role_required("Doctor")
def annotation_export(request: HttpRequest) -> HttpResponse:
    """Validate queued annotations before returning a local JSONL export."""
    queue = _get_local_annotation_queue(request)
    invalid = []
    export_records = []
    completed = [record for record in queue if record.get("annotation_complete")]
    if not completed:
        return JsonResponse({
            "status": "blocked",
            "invalid_records": [{"record_id": record["record_id"], "errors": ["No drafts are marked complete for export."]} for record in queue[:1]],
            "message": "No completed annotations are ready for local export.",
        }, status=400)

    for record in completed:
        errors = _validate_record_for_export(record)
        if errors:
            invalid.append({"record_id": record["record_id"], "errors": errors})
        else:
            export_records.append(record)

    if invalid or not export_records:
        return JsonResponse({
            "status": "blocked",
            "invalid_records": invalid,
            "message": "One or more drafts failed validation and cannot be exported.",
        }, status=400)

    payload = "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in export_records)
    response = HttpResponse(payload + ("\n" if payload else ""), content_type="application/jsonl; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="local_annotation_export.jsonl"'
    return response


def _processing_run_context(
    run: ClinicalProcessingRun,
    *,
    form: ProcessingRunReviewForm | None = None,
) -> dict:
    """Build the shared, access-controlled processing-run context."""
    def format_result(value: object) -> str:
        return (
            json.dumps(value, indent=2, ensure_ascii=False)
            if value is not None
            else "No result recorded."
        )

    return {
        "page_title": f"Processing run #{run.pk}",
        "active_nav": "patients",
        "run": run,
        "note": run.clinical_note,
        "patient": run.clinical_note.encounter.patient,
        "extraction_json": format_result(run.extraction_result),
        "coding_json": format_result(run.coding_result),
        "verification_json": format_result(run.verification_result),
        "knowledge_retrieval_json": format_result({
            "status": run.knowledge_retrieval_status,
            "references": run.knowledge_references,
        }),
        "dispositions_json": format_result(run.item_dispositions),
        "review_reasons_json": format_result(run.review_reasons),
        "review_form": form or ProcessingRunReviewForm(
            initial=(
                {"decision": run.review_decision}
                if run.review_decision
                in {
                    ClinicalProcessingRun.ReviewDecision.APPROVED,
                    ClinicalProcessingRun.ReviewDecision.REJECTED,
                }
                else None
            )
        ),
    }

@role_required("Doctor")
def processing_run_detail(
    request: HttpRequest,
    run_id: int,
) -> HttpResponse:
    """Display a processing run only to a doctor with patient access."""

    authorized_patients = Patient.objects.accessible_to(request.user)

    run = get_object_or_404(
        ClinicalProcessingRun.objects.filter(
            clinical_note__encounter__patient__in=authorized_patients,
        ).select_related(
            "clinical_note__encounter__patient",
            "created_by",
        ),
        pk=run_id,
    )

    return render(
        request,
        "dashboard/processing_run_detail.html",
        _processing_run_context(run),
    )


@role_required("Doctor")
@require_POST
def review_processing_run(
    request: HttpRequest,
    run_id: int,
) -> HttpResponse:
    """Persist an authorized human review decision for a processing run."""
    authorized_patients = Patient.objects.accessible_to(request.user)
    with transaction.atomic():
        run = get_object_or_404(
            ClinicalProcessingRun.objects.select_for_update().filter(
                clinical_note__encounter__patient__in=authorized_patients,
                status=ClinicalProcessingRun.Status.NEEDS_REVIEW,
                review_decision=ClinicalProcessingRun.ReviewDecision.PENDING,
            ),
            pk=run_id,
        )
        form = ProcessingRunReviewForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "dashboard/processing_run_detail.html",
                _processing_run_context(run, form=form),
                status=400,
            )

        decision = form.cleaned_data["decision"]
        run.review_decision = decision
        run.reviewed_by = request.user
        run.reviewed_at = timezone.now()
        run.reviewer_comment = form.cleaned_data["comment"]
        # A recorded approval or rejection completes the review cycle.
        # The separate review_decision field preserves the actual outcome.
        run.status = ClinicalProcessingRun.Status.COMPLETED
        run.save(
            update_fields=[
                "review_decision",
                "reviewed_by",
                "reviewed_at",
                "reviewer_comment",
                "status",
            ]
        )
    return redirect("dashboard:processing_run_detail", run_id=run.pk)


@role_required("Doctor", "Administrator")
def knowledge_base(request: HttpRequest) -> HttpResponse:
    query = (request.GET.get("q") or "").strip()
    sort = request.GET.get("sort", "priority")
    sort_fields = {
        "priority": ["-priority", "title", "-pk"],
        "title": ["title", "-pk"],
        "updated": ["-updated_at", "-pk"],
    }
    if sort not in sort_fields:
        sort = "priority"
    queryset = KnowledgeDocument.objects.all()
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(content__icontains=query)
            | Q(source_citations__icontains=query)
        )
    return render(
        request,
        "dashboard/knowledge_base.html",
        {
            "page_title": "Knowledge base",
            "active_nav": "knowledge",
            "documents": queryset.order_by(*sort_fields[sort]),
            "query": query,
            "sort": sort,
        },
    )


@role_required("Doctor", "Administrator")
def knowledge_document_new(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form_data = request.POST.copy()
        if request.FILES.get("source_file") and not form_data.get("content"):
            form_data["content"] = "Pending local extraction review."
        form = KnowledgeDocumentForm(form_data, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.created_by = request.user
            document.version_number = 1
            uploaded = form.cleaned_data.get("source_file")
            if uploaded:
                try:
                    extracted, source_type, status = extract_uploaded_source(uploaded)
                except KnowledgeIngestionError as exc:
                    form.add_error("source_file", str(exc))
                else:
                    document.content = extracted
                    document.source_file = uploaded
                    document.source_filename = uploaded.name[:255]
                    document.source_type = source_type
                    document.ingestion_status = "needs_review"
                    document.ingestion_error = ""
                    document.is_active = False
                    document.save()
                    return redirect("dashboard:knowledge_document_edit", doc_id=document.pk)
            else:
                document.ingestion_status = "manual"
                document.save()
                return redirect("dashboard:knowledge_document_detail", doc_id=document.pk)
    else:
        form = KnowledgeDocumentForm(initial={"is_active": True})

    return render(
        request,
        "dashboard/knowledge_document_form.html",
        {
            "page_title": "New knowledge document",
            "active_nav": "knowledge",
            "form": form,
            "is_edit": False,
        },
    )


@role_required("Doctor", "Administrator")
def knowledge_document_detail(request: HttpRequest, doc_id: int) -> HttpResponse:
    document = get_object_or_404(KnowledgeDocument, pk=doc_id)
    return render(
        request,
        "dashboard/knowledge_document_detail.html",
        {
            "page_title": document.title,
            "active_nav": "knowledge",
            "document": document,
        },
    )


@role_required("Doctor", "Administrator")
def knowledge_document_edit(request: HttpRequest, doc_id: int) -> HttpResponse:
    document = get_object_or_404(KnowledgeDocument, pk=doc_id)
    citation = (document.source_citations or [{}])[0]

    if request.method == "POST":
        prior_active = document.is_active
        form_data = request.POST.copy()
        if request.FILES.get("source_file") and not form_data.get("content"):
            form_data["content"] = "Pending local extraction review."
        form = KnowledgeDocumentForm(form_data, request.FILES, instance=document)
        if form.is_valid():
            updated = form.save(commit=False)
            uploaded = form.cleaned_data.get("source_file")
            if uploaded:
                try:
                    extracted, source_type, _status = extract_uploaded_source(uploaded)
                except KnowledgeIngestionError as exc:
                    form.add_error("source_file", str(exc))
                else:
                    updated.content = extracted
                    updated.source_file = uploaded
                    updated.source_filename = uploaded.name[:255]
                    updated.source_type = source_type
                    updated.ingestion_status = "needs_review"
                    updated.ingestion_error = ""
                    updated.is_active = False
            if form.errors:
                return render(
                    request,
                    "dashboard/knowledge_document_form.html",
                    {
                        "page_title": f"Edit {document.title}",
                        "active_nav": "knowledge",
                        "form": form,
                        "is_edit": True,
                        "document": document,
                    },
                )
            # Publishing an uploaded draft is an explicit reviewer action.
            # Active documents still in needs_review are never retrieved by RAG.
            if updated.is_active and updated.ingestion_status == "needs_review":
                updated.ingestion_status = "published"
            elif not updated.is_active and updated.ingestion_status == "published":
                updated.ingestion_status = "draft"

            updated.version_number = document.version_number + 1
            updated.created_by = document.created_by or request.user
            if not updated.is_active and prior_active:
                updated.deactivated_at = timezone.now()
                updated.deactivated_by = request.user
            elif updated.is_active:
                updated.deactivated_at = None
                updated.deactivated_by = None
            updated.save()
            return redirect("dashboard:knowledge_document_detail", doc_id=document.pk)
    else:
        form = KnowledgeDocumentForm(
            instance=document,
            initial={
                "source_title": citation.get("title", ""),
                "source_url": citation.get("url", ""),
                "source_quote": citation.get("quote", ""),
            },
        )

    return render(
        request,
        "dashboard/knowledge_document_form.html",
        {
            "page_title": f"Edit {document.title}",
            "active_nav": "knowledge",
            "form": form,
            "is_edit": True,
            "document": document,
        },
    )


def _ai_configuration_fingerprint(configuration: AIConfiguration) -> str:
    """Fingerprint all values that affect the provider connection test.

    The credential itself is never persisted in the fingerprint; only its
    one-way SHA-256 digest is included.
    """
    api_key = configuration.get_api_key() or os.environ.get("GROQ_API_KEY", "").strip()
    payload = {
        "provider": configuration.provider,
        "model": configuration.model,
        "temperature": str(configuration.temperature),
        "max_tokens": configuration.max_tokens,
        "api_key_sha256": hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        if api_key else "",
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _test_ai_configuration(configuration: AIConfiguration) -> tuple[str, str]:
    """Test only with a fixed synthetic note; never submit user/patient data."""
    if configuration.provider == "synthetic":
        return (
            "passed",
            "Synthetic configuration validated locally; no external request was made.",
        )

    if configuration.provider != "groq":
        return (
            "blocked",
            "Gemini execution is not implemented in this build; no request was made.",
        )

    if not getattr(settings, "GROQ_PROVIDER_ENABLED", False):
        return (
            "blocked",
            "Live provider testing is disabled in this local build; no request was made.",
        )

    api_key = configuration.get_api_key() or os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return ("blocked", "No Groq API key is configured; no request was made.")

    synthetic_note = (
        "Synthetic provider connectivity test only. "
        "Assessment: hypertension. Medication: metformin."
    )
    try:
        from dashboard.extraction.groq_provider import (
            GroqExtractionProvider,
            GroqProviderConfigurationError,
            GroqProviderError,
        )
        from dashboard.extraction.service import validate_extraction_output

        provider = GroqExtractionProvider(
            api_key=api_key,
            model=configuration.model,
        )
        payload = provider.extract(synthetic_note)
        validate_extraction_output(payload, synthetic_note)
    except GroqProviderConfigurationError:
        return ("blocked", "Groq client configuration is incomplete; no clinical note was sent.")
    except GroqProviderError as exc:
        return ("failed", f"Groq synthetic connection test failed ({exc.code}).")
    except Exception as exc:
        return (
            "failed",
            f"Groq synthetic connection test failed ({type(exc).__name__}).",
        )

    return (
        "passed",
        f"Groq synthetic extraction test passed for {configuration.model}; no patient data was used.",
    )


@role_required("Administrator")
def settings_page(request: HttpRequest) -> HttpResponse:
    """Manage versioned provider configuration with real synthetic-only tests."""
    active_configuration = AIConfiguration.objects.filter(is_active=True).first()
    draft = AIConfiguration.objects.filter(is_active=False).first()
    form = AIConfigurationForm(request.POST or None, instance=draft)
    test_result = None

    if request.method == "POST":
        action = request.POST.get("action")
        if action in {"save_draft", "test", "activate"}:
            if form.is_valid():
                configuration = form.save(commit=False)
                if configuration.created_by_id is None:
                    configuration.created_by = request.user

                api_key = form.cleaned_data.get("api_key", "")
                if api_key:
                    configuration.set_api_key(api_key)

                if not configuration.version_number:
                    configuration.version_number = 1

                if action == "save_draft":
                    configuration.is_active = False
                    configuration.last_test_status = "not_tested"
                    configuration.last_test_result = (
                        "Draft saved. Run a new synthetic connection test before activation."
                    )
                    configuration.tested_fingerprint = ""
                    configuration.tested_at = None
                    configuration.save()
                    test_result = configuration.last_test_result

                elif action == "test":
                    status, result_text = _test_ai_configuration(configuration)
                    configuration.is_active = False
                    configuration.last_test_status = status
                    configuration.last_test_result = result_text
                    configuration.tested_at = timezone.now()
                    configuration.tested_fingerprint = (
                        _ai_configuration_fingerprint(configuration)
                        if status == "passed"
                        else ""
                    )
                    configuration.save()
                    test_result = result_text

                elif action == "activate":
                    current_fingerprint = _ai_configuration_fingerprint(configuration)
                    test_matches_current_configuration = (
                        configuration.last_test_status == "passed"
                        and configuration.tested_fingerprint
                        and configuration.tested_fingerprint == current_fingerprint
                    )
                    if not test_matches_current_configuration:
                        configuration.is_active = False
                        configuration.last_test_status = "not_tested"
                        configuration.last_test_result = (
                            "Configuration values or credentials changed after the last test. "
                            "Run Test connection again before activation."
                        )
                        configuration.tested_fingerprint = ""
                        configuration.tested_at = None
                        configuration.save()
                        form.add_error(
                            None,
                            "Test this configuration successfully before activation. "
                            + configuration.last_test_result,
                        )
                        test_result = configuration.last_test_result
                    else:
                        AIConfiguration.objects.filter(is_active=True).exclude(
                            pk=configuration.pk
                        ).update(
                            is_active=False,
                            activated_at=None,
                            activated_by=None,
                        )
                        configuration.is_active = True
                        configuration.activated_by = request.user
                        configuration.activated_at = timezone.now()
                        configuration.save()
                        active_configuration = configuration
                        test_result = (
                            f"{configuration.get_provider_display()} / "
                            f"{configuration.model} activated."
                        )

                draft = configuration
                if not form.errors:
                    form = AIConfigurationForm(instance=draft)
            else:
                test_result = "Form validation failed."

    return render(
        request,
        "dashboard/settings.html",
        {
            "page_title": "AI settings",
            "active_nav": "settings",
            "form": form,
            "active_configuration": active_configuration,
            "draft": draft,
            "test_result": test_result,
            "provider_key_configured": bool(
                os.environ.get("GROQ_API_KEY", "").strip()
                or (draft and draft.has_api_key())
            ),
            "usage_configuration": active_configuration or draft,
        },
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
        form = ClinicalNoteForm(request.POST, request.FILES)

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


@role_required("Doctor")
@require_POST
def run_synthetic_processing_demo(
    request: HttpRequest,
    note_id: int,
) -> HttpResponse:
    """Run a gated local plumbing demo; this does not perform AI analysis."""
    if not settings.SYNTHETIC_DEMO_ENABLED:
        raise Http404

    authorized_patients = Patient.objects.accessible_to(request.user)
    note = get_object_or_404(
        ClinicalNote.objects.filter(encounter__patient__in=authorized_patients),
        pk=note_id,
    )

    run = process_clinical_note(
        note,
        request.user,
        extraction_provider=SyntheticDemoExtractionProvider(),
        verification_provider=SyntheticDemoVerificationProvider(),
        execution_mode=ClinicalProcessingRun.ExecutionMode.SYNTHETIC_DEMO,
    )
    return redirect("dashboard:processing_run_detail", run_id=run.pk)


@role_required("Doctor")
@require_POST
def run_ai_processing(
    request: HttpRequest,
    note_id: int,
) -> HttpResponse:
    """Run only the explicitly selected, configured and approved provider."""
    authorized_patients = Patient.objects.accessible_to(request.user)
    note = get_object_or_404(
        ClinicalNote.objects.filter(encounter__patient__in=authorized_patients),
        pk=note_id,
    )

    active_config = AIConfiguration.objects.filter(is_active=True).first()
    if active_config and active_config.provider == "gemini":
        messages.error(
            request,
            "Gemini processing is not available because its provider adapter is not implemented. "
            "No alternative provider was selected.",
        )
        return redirect(
            "dashboard:patient_detail",
            patient_id=note.encounter.patient_id,
        )

    if active_config and active_config.provider == "groq":
        if not getattr(settings, "GROQ_PROVIDER_ENABLED", False):
            messages.error(
                request,
                "Groq is disabled in this environment. No alternative provider was selected.",
            )
            return redirect(
                "dashboard:patient_detail",
                patient_id=note.encounter.patient_id,
            )
        if not getattr(settings, "EXTERNAL_CLINICAL_DATA_APPROVED", False):
            messages.error(
                request,
                "External clinical-note processing has not been approved. "
                "The note was not sent to Groq and no alternative provider was selected.",
            )
            return redirect(
                "dashboard:patient_detail",
                patient_id=note.encounter.patient_id,
            )

        api_key = active_config.get_api_key() or os.environ.get("GROQ_API_KEY", "").strip()
        if not api_key:
            messages.error(
                request,
                "The active Groq configuration has no usable credential. "
                "No alternative provider was selected.",
            )
            return redirect(
                "dashboard:patient_detail",
                patient_id=note.encounter.patient_id,
            )

        from dashboard.extraction.groq_provider import (
            GroqExtractionProvider,
            GroqVerificationProvider,
        )

        extraction_provider = GroqExtractionProvider(
            api_key=api_key,
            model=active_config.model,
        )
        verification_provider = GroqVerificationProvider(
            api_key=api_key,
            model=active_config.model,
        )
    else:
        from dashboard.extraction.local_provider import (
            LocalClinicalExtractionProvider,
            LocalClinicalVerificationProvider,
        )

        extraction_provider = LocalClinicalExtractionProvider()
        verification_provider = LocalClinicalVerificationProvider()

    run = process_clinical_note(
        note,
        request.user,
        extraction_provider=extraction_provider,
        verification_provider=verification_provider,
        execution_mode=ClinicalProcessingRun.ExecutionMode.AI_AGENT,
    )
    return redirect("dashboard:processing_run_detail", run_id=run.pk)


@role_required("Doctor")
def export_processing_run(
    request: HttpRequest,
    run_id: int,
) -> HttpResponse:
    """Export the reviewed processing run output as structured JSON."""
    authorized_patients = Patient.objects.accessible_to(request.user)
    run = get_object_or_404(
        ClinicalProcessingRun.objects.filter(
            clinical_note__encounter__patient__in=authorized_patients,
        ).select_related(
            "clinical_note__encounter__patient",
            "clinical_note__encounter",
            "reviewed_by",
            "created_by",
        ),
        pk=run_id,
    )

    encounter = run.clinical_note.encounter
    patient = encounter.patient

    payload = {
        "export_type": "mirai_clinical_reviewed_processing_run",
        "exported_at": timezone.now().isoformat(),
        "run_id": run.pk,
        "execution_mode": run.execution_mode,
        "patient": {
            "identifier": patient.identifier,
            "display_name": patient.display_name,
        },
        "encounter": {
            "title": encounter.title,
            "encounter_date": encounter.encounter_date.isoformat(),
            "status": encounter.status,
        },
        "clinical_note": {
            "version_number": run.clinical_note.version_number,
            "source": run.clinical_note.source,
            "original_text": run.clinical_note.original_text,
        },
        "extraction_result": run.extraction_result,
        "coding_result": run.coding_result,
        "verification_result": run.verification_result,
        "knowledge_retrieval": {
            "status": run.knowledge_retrieval_status,
            "references": run.knowledge_references,
        },
        "item_dispositions": run.item_dispositions,
        "review": {
            "status": run.status,
            "review_decision": run.review_decision,
            "reviewed_by": run.reviewed_by.get_username() if run.reviewed_by else None,
            "reviewed_at": run.reviewed_at.isoformat() if run.reviewed_at else None,
            "reviewer_comment": run.reviewer_comment,
            "review_reasons": run.review_reasons,
        },
    }

    content = json.dumps(payload, indent=2, ensure_ascii=False)
    response = HttpResponse(content, content_type="application/json; charset=utf-8")
    filename = f"reviewed_run_{run.pk}_patient_{patient.identifier}.json"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
