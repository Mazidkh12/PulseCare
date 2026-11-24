from django.urls import path
from . import views

app_name = "departments"

urlpatterns = [
    # Department URLs
    path("", views.department_list_view, name="department_list"),
    path("create/", views.department_create_view, name="department_create"),
    path("<int:pk>/", views.department_detail_view, name="department_detail"),
    path("<int:pk>/edit/", views.department_edit_view, name="department_edit"),
    path("<int:pk>/toggle/", views.department_toggle_active_view, name="department_toggle_active"),

    # Doctor URLs
    path("doctors/", views.doctor_list_view, name="doctor_list"),
    path("doctors/create/", views.doctor_create_view, name="doctor_create"),
    path("doctors/<int:pk>/", views.doctor_detail_view, name="doctor_detail"),
    path("doctors/<int:pk>/edit/", views.doctor_edit_view, name="doctor_edit"),
    path("doctors/<int:pk>/toggle/", views.doctor_toggle_active_view, name="doctor_toggle_active"),
]
