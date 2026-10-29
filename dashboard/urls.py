from django.urls import path

from dashboard import views


app_name = "dashboard"


urlpatterns = [
    path("", views.home, name="home"),
    path("patients/", views.patients, name="patients"),
    path("patients/new/", views.patient_create, name="patient_create"),
    path(
        "patients/<int:patient_id>/",
        views.patient_detail,
        name="patient_detail",
    ),
    path(
        "patients/<int:patient_id>/delete/",
        views.patient_delete,
        name="patient_delete",
    ),
    path(
        "patients/<int:patient_id>/encounters/new/",
        views.encounter_create,
        name="encounter_create",
    ),
    path(
        "knowledge-base/",
        views.knowledge_base,
        name="knowledge_base",
    ),
    path(
        "knowledge-base/new/",
        views.knowledge_document_new,
        name="knowledge_document_new",
    ),
    path(
        "knowledge-base/<int:doc_id>/",
        views.knowledge_document_detail,
        name="knowledge_document_detail",
    ),
    path(
        "knowledge-base/<int:doc_id>/edit/",
        views.knowledge_document_edit,
        name="knowledge_document_edit",
    ),
    path(
    "processing-runs/<int:run_id>/",
    views.processing_run_detail,
    name="processing_run_detail",
    ),
    path(
        "processing-runs/<int:run_id>/review/",
        views.review_processing_run,
        name="review_processing_run",
    ),
    path(
        "notes/<int:note_id>/process/",
        views.run_ai_processing,
        name="run_ai_processing",
    ),
    path(
        "notes/<int:note_id>/run-synthetic-demo/",
        views.run_synthetic_processing_demo,
        name="run_synthetic_processing_demo",
    ),
    path(
        "processing-runs/<int:run_id>/export/",
        views.export_processing_run,
        name="export_processing_run",
    ),
    path(
        "annotation/",
        views.annotation_queue,
        name="annotation_queue",
    ),
    path(
        "annotation/export/",
        views.annotation_export,
        name="annotation_export",
    ),
    path(
        "annotation/<str:record_id>/",
        views.annotation_detail,
        name="annotation_detail",
    ),
    path(
        "encounters/<int:encounter_id>/notes/new/",
        views.clinical_note_create,
        name="clinical_note_create",
    ),
    path("settings/", views.settings_page, name="settings"),
]