"""
URL configuration for config project.
"""
from django.contrib import admin
from django.urls import include, path
from accounts.views import dashboard_redirect_view

urlpatterns = [
    path("", dashboard_redirect_view, name="home"),
    path("accounts/", include("accounts.urls")),
    path("patients/", include("patients.urls")),
    path("appointments/", include("appointments.urls")),
    path("consultations/", include("consultations.urls")),
    path("prescriptions/", include("prescriptions.urls")),
    path("departments/", include("departments.urls")),
    path("reports/", include("reports.urls")),
    path("audit/", include("audit.urls")),
    path("admin/", admin.site.urls),
]
