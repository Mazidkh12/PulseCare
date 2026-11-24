from django import forms
from django.contrib import admin
from django.db.models import Q
from departments.models import DoctorProfile
from patients.models import Patient
from .models import Appointment


class AppointmentAdminForm(forms.ModelForm):
    """
    Custom Admin Form for appointments ensuring inactive patients and inactive doctors
    cannot be selected for new bookings.
    """

    class Meta:
        model = Appointment
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Restrict patient choices to active patients (or currently assigned patient if editing)
        if "patient" in self.fields:
            if not self.instance.pk:
                self.fields["patient"].queryset = Patient.objects.filter(is_active=True)
            else:
                self.fields["patient"].queryset = Patient.objects.filter(
                    Q(is_active=True) | Q(pk=self.instance.patient_id)
                )

        # Restrict doctor choices to active doctors (or currently assigned doctor if editing)
        if "doctor" in self.fields:
            if not self.instance.pk:
                self.fields["doctor"].queryset = DoctorProfile.objects.filter(is_active=True)
            else:
                self.fields["doctor"].queryset = DoctorProfile.objects.filter(
                    Q(is_active=True) | Q(pk=self.instance.doctor_id)
                )


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    """
    Django Admin configuration for managing appointments.
    """

    form = AppointmentAdminForm
    date_hierarchy = "appointment_date"

    list_display = (
        "get_patient_mrn",
        "get_patient_name",
        "get_doctor_name",
        "get_department_name",
        "appointment_date",
        "start_time",
        "end_time",
        "status",
        "created_at",
    )
    list_filter = (
        "status",
        "appointment_date",
        "doctor__department",
        "created_at",
    )
    search_fields = (
        "patient__patient_id",
        "patient__first_name",
        "patient__last_name",
        "doctor__user__first_name",
        "doctor__user__last_name",
        "doctor__user__username",
        "reason",
    )
    list_editable = ("status",)
    ordering = ("-appointment_date", "-start_time")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "Patient & Doctor Assignment",
            {
                "fields": (("patient", "doctor"),),
                "description": "Select the patient and doctor for this consultation.",
            },
        ),
        (
            "Schedule & Status",
            {
                "fields": (
                    "appointment_date",
                    ("start_time", "end_time"),
                    "status",
                ),
            },
        ),
        (
            "Clinical Notes",
            {
                "fields": ("reason", "notes"),
            },
        ),
        (
            "Audit Timestamps",
            {
                "classes": ("collapse",),
                "fields": (("created_at", "updated_at"),),
            },
        ),
    )

    @admin.display(description="MRN", ordering="patient__patient_id")
    def get_patient_mrn(self, obj):
        return obj.patient.patient_id

    @admin.display(description="Patient Name", ordering="patient__first_name")
    def get_patient_name(self, obj):
        return obj.patient.get_full_name()

    @admin.display(description="Doctor", ordering="doctor__user__first_name")
    def get_doctor_name(self, obj):
        full_name = obj.doctor.user.get_full_name().strip()
        doc_name = full_name if full_name else obj.doctor.user.username
        return f"Dr. {doc_name}"

    @admin.display(description="Department", ordering="doctor__department__name")
    def get_department_name(self, obj):
        dept = obj.department
        return dept.name if dept else "-"
