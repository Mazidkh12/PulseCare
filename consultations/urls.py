from django.urls import path
from . import views

app_name = "consultations"

urlpatterns = [
    path("", views.consultation_list_view, name="list"),
    path("create/", views.consultation_create_view, name="create"),
    path("<int:pk>/", views.consultation_detail_view, name="detail"),
    path("<int:pk>/edit/", views.consultation_edit_view, name="edit"),
    path("<int:pk>/finalize/", views.consultation_finalize_view, name="finalize"),
]
