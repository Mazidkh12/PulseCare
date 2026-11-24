from django.contrib import admin
from .models import Allergy, MedicalHistory, Patient, PatientIDSequence


class MedicalHistoryInline(admin.TabularInline):
    model = MedicalHistory
    extra = 1
    fields = ("condition", "description", "diagnosed_date")


class AllergyInline(admin.TabularInline):
    model = Allergy
    extra = 1
    fields = ("allergen", "reaction", "severity", "notes")


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    """
    Admin configuration for Patient records with inlined medical histories and allergies.
    """

    inlines = [MedicalHistoryInline, AllergyInline]
    readonly_fields = ("patient_id", "created_at", "updated_at")

    list_display = (
        "patient_id",
        "get_patient_name",
        "gender",
        "blood_group",
        "contact_number",
        "is_active",
        "created_at",
    )
    list_filter = ("gender", "blood_group", "is_active", "created_at")
    search_fields = (
        "patient_id",
        "first_name",
        "last_name",
        "contact_number",
        "email",
    )
    list_editable = ("is_active",)
    ordering = ("-created_at",)

    fieldsets = (
        (
            "Medical Record Number",
            {
                "fields": ("patient_id", "is_active"),
                "description": "MRN is automatically assigned upon registration.",
            },
        ),
        (
            "Personal Information",
            {
                "fields": (
                    ("first_name", "last_name"),
                    ("date_of_birth", "gender"),
                    "blood_group",
                )
            },
        ),
        (
            "Contact Information",
            {
                "fields": (
                    ("contact_number", "email"),
                    "address",
                    ("city", "state", "pincode"),
                )
            },
        ),
        (
            "Emergency Contact",
            {
                "classes": ("collapse",),
                "fields": (
                    ("emergency_contact_name", "emergency_contact_number"),
                ),
            },
        ),
        (
            "System Timestamps",
            {
                "classes": ("collapse",),
                "fields": (("created_at", "updated_at"),),
            },
        ),
    )

    @admin.display(description="Patient Name", ordering="first_name")
    def get_patient_name(self, obj):
        return obj.get_full_name()


@admin.register(MedicalHistory)
class MedicalHistoryAdmin(admin.ModelAdmin):
    """
    Admin configuration for Patient Medical History records.
    """

    list_display = ("patient", "condition", "diagnosed_date", "created_at")
    search_fields = (
        "patient__patient_id",
        "patient__first_name",
        "patient__last_name",
        "condition",
    )
    list_filter = ("diagnosed_date", "created_at")
    ordering = ("-diagnosed_date", "-created_at")


@admin.register(Allergy)
class AllergyAdmin(admin.ModelAdmin):
    """
    Admin configuration for Patient Allergy records.
    """

    list_display = (
        "patient",
        "allergen",
        "severity",
        "reaction",
        "created_at",
    )
    search_fields = (
        "patient__patient_id",
        "patient__first_name",
        "patient__last_name",
        "allergen",
    )
    list_filter = ("severity", "created_at")
    ordering = ("-severity", "-created_at")


@admin.register(PatientIDSequence)
class PatientIDSequenceAdmin(admin.ModelAdmin):
    """
    Read-only view for tracking Patient ID sequence counters per year.
    """

    list_display = ("year", "last_sequence")
    readonly_fields = ("year", "last_sequence")
