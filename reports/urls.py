from django.urls import path
from . import views

app_name = "reports"

urlpatterns = [
    path("", views.reports_index_view, name="index"),
    path("api/data/", views.dashboard_data_view, name="dashboard_data"),
    path("export/patients/", views.export_patients_csv_view, name="export_patients"),
    path("export/appointments/", views.export_appointments_csv_view, name="export_appointments"),
    path("export/departments/", views.export_departments_csv_view, name="export_departments"),
    path("export/doctor-workload/", views.export_doctor_workload_csv_view, name="export_doctor_workload"),
    path("printable/", views.report_printable_view, name="printable"),
]
