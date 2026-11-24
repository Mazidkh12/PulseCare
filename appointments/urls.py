from django.urls import path
from . import views

app_name = "appointments"

urlpatterns = [
    path("book/", views.appointment_book_view, name="book"),
    path("", views.appointment_list_view, name="list"),
    path("<int:pk>/cancel/", views.appointment_cancel_view, name="cancel"),
    # Doctor Queue & Status Workflows
    path("doctor/queue/", views.doctor_queue_view, name="doctor_queue"),
    path("<int:pk>/start-consultation/", views.appointment_start_consultation_view, name="start_consultation"),
    path("<int:pk>/update-status/", views.appointment_update_status_view, name="update_status"),
]
