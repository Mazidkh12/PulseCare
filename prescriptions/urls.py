from django.urls import path
from . import views

app_name = "prescriptions"

urlpatterns = [
    path("", views.prescription_list_view, name="list"),
    path("create/<int:consultation_id>/", views.prescription_builder_view, name="create"),
    path("<int:pk>/", views.prescription_detail_view, name="detail"),
]
