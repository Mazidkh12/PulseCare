from django import forms
from django.contrib import admin
from django.db.models import Q
from appointments.models import Appointment
from departments.models import DoctorProfile
from patients.models import Patient
from .models import Consultation, Diagnosis, VitalSign


class DiagnosisInline(admin.TabularInline):
    """
    Inline diagnosis entry directly embedded into the consultation workspace.
    """

    model = Diagnosis
    extra = 1
    fields = (
        "diagnosis_type",
        "diagnosis_name",
        "diagnosis_code",
        "description",
        "recorded_by",
        "recorded_at",
    )


class VitalSignInline(admin.StackedInline):
    """
    Inline vitals recorder directly embedded into the consultation workspace.
    """

    model = VitalSign
    can_delete = False
    extra = 0
    readonly_fields = ("bmi", "recorded_at")
    fieldsets = (
        (
            "Physiological Vital Signs",
            {
                "fields": (
                    ("systolic_bp", "diastolic_bp"),
                    ("pulse_rate", "respiratory_rate"),
                    ("temperature", "spo2"),
                    ("height", "weight", "bmi"),
                    "recorded_at",
                )
            },
        ),
    )


class ConsultationAdminForm(forms.ModelForm):
    """
    Custom admin form for consultations providing active patient/doctor filtering
    and appointment validation.
    """

    class Meta:
        model = Consultation
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Restrict patient dropdown to active patients
        if "patient" in self.fields:
            if not self.instance.pk:
                self.fields["patient"].queryset = Patient.objects.filter(is_active=True)
            else:
                self.fields["patient"].queryset = Patient.objects.filter(
                    Q(is_active=True) | Q(pk=self.instance.patient_id)
                )

        # Restrict doctor dropdown to active doctors
        if "doctor" in self.fields:
            if not self.instance.pk:
                self.fields["doctor"].queryset = DoctorProfile.objects.filter(is_active=True)
            else:
                self.fields["doctor"].queryset = DoctorProfile.objects.filter(
                    Q(is_active=True) | Q(pk=self.instance.doctor_id)
                )

        # Restrict appointment dropdown to uncompleted/active appointments
        if "appointment" in self.fields:
            if not self.instance.pk:
                self.fields["appointment"].queryset = Appointment.objects.filter(
                    consultation__isnull=True
                ).exclude(status__in=[Appointment.Status.CANCELLED, Appointment.Status.NO_SHOW])
            else:
                self.fields["appointment"].queryset = Appointment.objects.filter(
                    Q(consultation__isnull=True) | Q(pk=self.instance.appointment_id)
                )


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    """
    Admin interface for outpatient consultations and case-taking documentation.
    """

    form = ConsultationAdminForm
    inlines = [VitalSignInline, DiagnosisInline]
    date_hierarchy = "consultation_date"

    list_display = (
        "get_patient_mrn",
        "get_patient_name",
        "get_doctor_name",
        "get_department",
        "consultation_date",
        "status",
        "has_vitals",
        "created_at",
    )
    list_filter = (
        "status",
        "consultation_date",
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
        "chief_complaint",
        "provisional_diagnosis",
    )
    list_editable = ("status",)
    ordering = ("-consultation_date", "-created_at")
    readonly_fields = ("created_at", "updated_at", "finalized_at")

    fieldsets = (
        (
            "Consultation Context",
            {
                "fields": (
                    ("patient", "doctor"),
                    "appointment",
                    ("consultation_date", "status"),
                    "finalized_at",
                ),
                "description": "Select the patient and attending doctor. Link an appointment if scheduled or leave blank for walk-ins.",
            },
        ),
        (
            "Chief Complaint & Presenting Illness",
            {
                "fields": (
                    "chief_complaint",
                    "history_of_present_illness",
                ),
            },
        ),
        (
            "Medical & Surgical Background",
            {
                "classes": ("collapse",),
                "fields": (
                    "past_medical_history",
                    "past_surgical_history",
                    "family_history",
                    "personal_history",
                ),
            },
        ),
        (
            "Medications & Allergies",
            {
                "fields": (
                    "current_medications",
                    "allergy_notes",
                ),
            },
        ),
        (
            "Clinical Examination & Impression",
            {
                "fields": (
                    "physical_examination",
                    "clinical_assessment",
                    "provisional_diagnosis",
                ),
            },
        ),
        (
            "Management Plan & Follow-Up",
            {
                "fields": (
                    "treatment_plan",
                    "follow_up_notes",
                    "follow_up_date",
                ),
            },
        ),
        (
            "Addenda & Amendments",
            {
                "classes": ("collapse",),
                "fields": ("amendment_notes",),
                "description": "Document clinical justification when amending a finalized record.",
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
    def get_department(self, obj):
        return obj.doctor.department.name if obj.doctor and obj.doctor.department else "-"

    @admin.display(description="Vitals Recorded", boolean=True)
    def has_vitals(self, obj):
        return hasattr(obj, "vitals") and obj.vitals is not None


@admin.register(VitalSign)
class VitalSignAdmin(admin.ModelAdmin):
    """
    Admin configuration for standalone review of recorded vital signs.
    """

    list_display = (
        "get_patient_mrn",
        "get_patient_name",
        "get_consultation_date",
        "get_blood_pressure",
        "pulse_rate",
        "respiratory_rate",
        "temperature",
        "spo2",
        "bmi",
        "recorded_at",
    )
    search_fields = (
        "consultation__patient__patient_id",
        "consultation__patient__first_name",
        "consultation__patient__last_name",
        "consultation__doctor__user__first_name",
        "consultation__doctor__user__last_name",
    )
    readonly_fields = ("bmi", "recorded_at")
    ordering = ("-recorded_at",)

    @admin.display(description="MRN", ordering="consultation__patient__patient_id")
    def get_patient_mrn(self, obj):
        return obj.consultation.patient.patient_id

    @admin.display(description="Patient Name", ordering="consultation__patient__first_name")
    def get_patient_name(self, obj):
        return obj.consultation.patient.get_full_name()

    @admin.display(description="Consultation Date", ordering="consultation__consultation_date")
    def get_consultation_date(self, obj):
        return obj.consultation.consultation_date.strftime("%Y-%m-%d %H:%M")

    @admin.display(description="Blood Pressure (mmHg)")
    def get_blood_pressure(self, obj):
        if obj.systolic_bp and obj.diastolic_bp:
            return f"{obj.systolic_bp}/{obj.diastolic_bp}"
        return "-"


@admin.register(Diagnosis)
class DiagnosisAdmin(admin.ModelAdmin):
    """
    Admin configuration for clinical diagnoses.
    """

    list_display = (
        "diagnosis_name",
        "get_patient_name",
        "get_doctor_name",
        "diagnosis_type",
        "get_consultation_date",
        "diagnosis_code",
        "recorded_at",
    )
    list_filter = (
        "diagnosis_type",
        "consultation__consultation_date",
        "recorded_at",
    )
    search_fields = (
        "diagnosis_name",
        "diagnosis_code",
        "consultation__patient__patient_id",
        "consultation__patient__first_name",
        "consultation__patient__last_name",
    )
    ordering = ("-recorded_at",)

    fieldsets = (
        (
            "Diagnosis Information",
            {
                "fields": (
                    "consultation",
                    ("diagnosis_name", "diagnosis_type"),
                    "diagnosis_code",
                    "description",
                )
            },
        ),
        (
            "Clinical Attribution",
            {
                "fields": (
                    "recorded_by",
                    "recorded_at",
                ),
            },
        ),
    )

    @admin.display(description="Patient Name", ordering="consultation__patient__first_name")
    def get_patient_name(self, obj):
        return obj.patient.get_full_name() if obj.patient else "-"

    @admin.display(description="Doctor", ordering="consultation__doctor__user__first_name")
    def get_doctor_name(self, obj):
        if obj.doctor:
            full_name = obj.doctor.user.get_full_name().strip()
            return f"Dr. {full_name or obj.doctor.user.username}"
        return "-"

    @admin.display(description="Consultation Date", ordering="consultation__consultation_date")
    def get_consultation_date(self, obj):
        if obj.consultation:
            return obj.consultation.consultation_date.strftime("%Y-%m-%d %H:%M")
        return "-"
