from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard_redirect_view, name="dashboard_redirect"),
    path("dashboard/admin/", views.admin_dashboard_view, name="admin_dashboard"),
    path("dashboard/receptionist/", views.receptionist_dashboard_view, name="receptionist_dashboard"),
    path("dashboard/doctor/", views.doctor_dashboard_view, name="doctor_dashboard"),

    # User Management URLs (Step 10D)
    path("users/", views.user_list_view, name="user_list"),
    path("users/create/", views.user_create_view, name="user_create"),
    path("users/<int:pk>/", views.user_detail_view, name="user_detail"),
    path("users/<int:pk>/edit/", views.user_edit_view, name="user_edit"),
    path("users/<int:pk>/toggle/", views.user_toggle_active_view, name="user_toggle_active"),
]
