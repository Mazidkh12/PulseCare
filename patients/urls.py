from django.urls import path
from . import views

app_name = "patients"

urlpatterns = [
    path("register/", views.patient_register_view, name="register"),
    path("", views.patient_list_view, name="list"),
    path("doctor/search/", views.doctor_patient_search_view, name="doctor_patient_search"),
    path("<int:pk>/", views.patient_detail_view, name="detail"),
    path("<int:pk>/history/", views.doctor_patient_history_view, name="doctor_history"),
]
