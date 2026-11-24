from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.models import Q
from .models import Department, DoctorProfile

User = get_user_model()


class DoctorProfileAdminForm(forms.ModelForm):
    """
    Custom Admin Form for DoctorProfile with smart filtering for user and department choices.
    """

    class Meta:
        model = DoctorProfile
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 1. User field: only show users with the DOCTOR role
        user_field = self.fields.get("user")
        if user_field:
            qs = User.objects.filter(role="DOCTOR")
            if not self.instance.pk:
                # When adding a new profile, exclude doctors who already have one
                qs = qs.filter(doctor_profile__isnull=True)
            else:
                # When editing, include current user or unassigned doctors
                qs = qs.filter(Q(doctor_profile__isnull=True) | Q(pk=self.instance.user_id))
            user_field.queryset = qs.order_by("first_name", "last_name", "username")

        # 2. Department field: only show active departments (or current one if editing)
        dept_field = self.fields.get("department")
        if dept_field:
            if self.instance.pk and self.instance.department_id:
                dept_field.queryset = Department.objects.filter(
                    Q(is_active=True) | Q(pk=self.instance.department_id)
                ).order_by("name")
            else:
                dept_field.queryset = Department.objects.filter(is_active=True).order_by("name")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """
    Admin configuration for clinic departments.
    """

    list_display = ("name", "is_active", "doctor_count", "created_at", "updated_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "description")
    list_editable = ("is_active",)
    ordering = ("name",)

    @admin.display(description="Assigned Doctors")
    def doctor_count(self, obj):
        return obj.doctor_profiles.count()


@admin.register(DoctorProfile)
class DoctorProfileAdmin(admin.ModelAdmin):
    """
    Admin configuration for doctor profiles.
    """

    form = DoctorProfileAdminForm
    list_display = (
        "get_doctor_name",
        "department",
        "specialization",
        "qualification",
        "contact_number",
        "is_active",
        "created_at",
    )
    list_filter = ("department", "is_active", "created_at")
    search_fields = (
        "user__first_name",
        "user__last_name",
        "user__username",
        "specialization",
        "qualification",
        "contact_number",
    )
    list_editable = ("is_active",)
    ordering = ("user__first_name", "user__last_name", "user__username")

    @admin.display(description="Doctor Name", ordering="user__first_name")
    def get_doctor_name(self, obj):
        full_name = obj.user.get_full_name().strip()
        return f"Dr. {full_name}" if full_name else f"Dr. {obj.user.username}"
