from django import forms
from django.contrib import admin
from django.db.models import Q
from consultations.models import Consultation
from .models import Prescription, PrescriptionIDSequence, PrescriptionItem


class PrescriptionItemInline(admin.TabularInline):
    """
    Inline editor for prescription items directly within the prescription workspace.
    """

    model = PrescriptionItem
    extra = 1
    fields = (
        "medicine_name",
        "dosage_form",
        "strength",
        "dosage",
        "frequency",
        "duration",
        "intake_timing",
        "special_instructions",
    )


class PrescriptionAdminForm(forms.ModelForm):
    """
    Custom admin form for prescriptions restricting consultation selection.
    """

    class Meta:
        model = Prescription
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "consultation" in self.fields:
            if not self.instance.pk:
                # When adding a new prescription, only show consultations that don't already have one
                self.fields["consultation"].queryset = Consultation.objects.filter(
                    prescription__isnull=True
                )
            else:
                self.fields["consultation"].queryset = Consultation.objects.filter(
                    Q(prescription__isnull=True) | Q(pk=self.instance.consultation_id)
                )


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    """
    Admin configuration for medical prescriptions.
    """

    form = PrescriptionAdminForm
    inlines = [PrescriptionItemInline]
    date_hierarchy = "prescription_date"

    list_display = (
        "prescription_number",
        "get_patient_name",
        "get_patient_mrn",
        "get_doctor_name",
        "get_consultation_date",
        "status",
        "get_items_count",
        "created_at",
    )
    list_filter = (
        "status",
        "prescription_date",
        "consultation__doctor__department",
        "created_at",
    )
    search_fields = (
        "prescription_number",
        "consultation__patient__patient_id",
        "consultation__patient__first_name",
        "consultation__patient__last_name",
        "consultation__doctor__user__first_name",
        "consultation__doctor__user__last_name",
    )
    list_editable = ("status",)
    ordering = ("-prescription_date", "-created_at")
    readonly_fields = ("prescription_number", "issued_at", "created_at", "updated_at")

    fieldsets = (
        (
            "Prescription Identification",
            {
                "fields": (
                    ("prescription_number", "status"),
                    "consultation",
                    ("prescription_date", "issued_at"),
                ),
                "description": "Prescription identifier is auto-generated upon creation.",
            },
        ),
        (
            "General Patient Instructions",
            {
                "fields": ("general_instructions",),
            },
        ),
        (
            "Addenda & Amendments",
            {
                "classes": ("collapse",),
                "fields": ("amendment_notes",),
                "description": "Document clinical justification when amending an issued prescription.",
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

    @admin.display(description="Patient Name", ordering="consultation__patient__first_name")
    def get_patient_name(self, obj):
        return obj.patient.get_full_name() if obj.patient else "-"

    @admin.display(description="MRN", ordering="consultation__patient__patient_id")
    def get_patient_mrn(self, obj):
        return obj.patient.patient_id if obj.patient else "-"

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

    @admin.display(description="Medicines Prescribed")
    def get_items_count(self, obj):
        return obj.items.count()


@admin.register(PrescriptionItem)
class PrescriptionItemAdmin(admin.ModelAdmin):
    """
    Admin configuration for individual prescribed medication items.
    """

    list_display = (
        "medicine_name",
        "dosage_form",
        "strength",
        "dosage",
        "frequency",
        "duration",
        "intake_timing",
        "get_prescription_number",
        "get_patient_name",
    )
    search_fields = (
        "medicine_name",
        "prescription__prescription_number",
        "prescription__consultation__patient__patient_id",
        "prescription__consultation__patient__first_name",
        "prescription__consultation__patient__last_name",
    )
    list_filter = ("dosage_form", "intake_timing", "created_at")
    ordering = ("-created_at",)

    @admin.display(description="Prescription", ordering="prescription__prescription_number")
    def get_prescription_number(self, obj):
        return obj.prescription.prescription_number

    @admin.display(description="Patient", ordering="prescription__consultation__patient__first_name")
    def get_patient_name(self, obj):
        return obj.prescription.patient.get_full_name() if obj.prescription and obj.prescription.patient else "-"


@admin.register(PrescriptionIDSequence)
class PrescriptionIDSequenceAdmin(admin.ModelAdmin):
    """
    Read-only view for tracking Prescription ID sequence counters.
    """

    list_display = ("year", "last_sequence")
    readonly_fields = ("year", "last_sequence")
