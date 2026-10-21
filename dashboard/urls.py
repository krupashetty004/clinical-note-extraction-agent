from django.urls import path

from dashboard import views


app_name = "dashboard"


urlpatterns = [
    path("", views.home, name="home"),
    path("patients/", views.patients, name="patients"),
    path(
        "patients/<int:patient_id>/",
        views.patient_detail,
        name="patient_detail",
    ),
    path(
        "knowledge-base/",
        views.knowledge_base,
        name="knowledge_base",
    ),
    path(
        "encounters/<int:encounter_id>/notes/new/",
        views.clinical_note_create,
        name="clinical_note_create",
    ),
    path("settings/", views.settings_page, name="settings"),
]