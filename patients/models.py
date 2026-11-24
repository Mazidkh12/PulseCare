import re
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class PatientIDSequence(models.Model):
    """
    Database-backed sequence table for concurrent, collision-free Patient MRN generation.
    Maintains the last used sequence integer per year.
    """

    year = models.PositiveIntegerField(unique=True, help_text="Calendar year for the sequence.")
    last_sequence = models.PositiveIntegerField(
        default=0, help_text="Highest issued sequential number for this year."
    )

    class Meta:
        verbose_name = "Patient ID Sequence"
        verbose_name_plural = "Patient ID Sequences"

    def __str__(self):
        return f"{self.year}: {self.last_sequence}"

    @classmethod
    def get_next_id(cls, year=None):
        """
        Thread-safe, transaction-safe method to generate the next unique Patient ID (MRN).
        Uses MySQL row-level locking (select_for_update) to prevent race conditions.
        Format: P-YYYY-NNNN
        """
        if year is None:
            year = timezone.now().year

        with transaction.atomic():
            seq_obj, created = cls.objects.select_for_update().get_or_create(
                year=year, defaults={"last_sequence": 0}
            )
            # Sync sequence if existing patient records exist with higher sequence numbers
            if created or seq_obj.last_sequence == 0:
                prefix = f"P-{year}-"
                last_patient = (
                    Patient.objects.filter(patient_id__startswith=prefix)
                    .order_by("-patient_id")
                    .first()
                )
                if last_patient:
                    try:
                        num_part = int(last_patient.patient_id.split("-")[-1])
                        if num_part > seq_obj.last_sequence:
                            seq_obj.last_sequence = num_part
                    except (ValueError, IndexError):
                        pass

            seq_obj.last_sequence += 1
            seq_obj.save(update_fields=["last_sequence"])
            return f"P-{year}-{seq_obj.last_sequence:04d}"


class Patient(models.Model):
    """
    Patient master record with personal, contact, and registration details.
    """

    class Gender(models.TextChoices):
        MALE = "MALE", "Male"
        FEMALE = "FEMALE", "Female"
        OTHER = "OTHER", "Other"

    class BloodGroup(models.TextChoices):
        A_POSITIVE = "A+", "A+"
        A_NEGATIVE = "A-", "A-"
        B_POSITIVE = "B+", "B+"
        B_NEGATIVE = "B-", "B-"
        AB_POSITIVE = "AB+", "AB+"
        AB_NEGATIVE = "AB-", "AB-"
        O_POSITIVE = "O+", "O+"
        O_NEGATIVE = "O-", "O-"
        UNKNOWN = "UNKNOWN", "Unknown"

    # Patient Identification
    patient_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Unique Medical Record Number (MRN), auto-generated as P-YYYY-NNNN.",
    )

    # Personal Information
    first_name = models.CharField(max_length=100, help_text="Patient's first name.")
    last_name = models.CharField(max_length=100, help_text="Patient's last name / surname.")
    date_of_birth = models.DateField(help_text="Patient's date of birth.")
    gender = models.CharField(
        max_length=10,
        choices=Gender.choices,
        help_text="Patient's biological / legal gender.",
    )
    blood_group = models.CharField(
        max_length=10,
        choices=BloodGroup.choices,
        default=BloodGroup.UNKNOWN,
        help_text="Patient's blood group.",
    )

    # Contact Information
    contact_number = models.CharField(
        max_length=17,
        help_text="Primary phone number (e.g., 9876543210 or +919876543210).",
    )
    email = models.EmailField(blank=True, help_text="Optional patient email address.")
    emergency_contact_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Name of emergency contact person / relative.",
    )
    emergency_contact_number = models.CharField(
        max_length=17,
        blank=True,
        help_text="Emergency contact phone number.",
    )
    address = models.TextField(blank=True, help_text="Residential street address.")
    city = models.CharField(max_length=100, blank=True, help_text="City or town.")
    state = models.CharField(max_length=100, blank=True, help_text="State / Province.")
    pincode = models.CharField(max_length=10, blank=True, help_text="Postal PIN code.")

    # Record Management
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this patient record is active.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Patient"
        verbose_name_plural = "Patients"
        ordering = ["-created_at"]

    def __str__(self):
        full_name = self.get_full_name()
        return f"{self.patient_id} - {full_name} ({self.get_gender_display()})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def clean(self):
        super().clean()

        # 1. Date of Birth Validation
        if self.date_of_birth and self.date_of_birth > timezone.now().date():
            raise ValidationError({
                "date_of_birth": "Date of birth cannot be in the future."
            })

        # 2. Contact Number Validation (supports standard Indian phone numbers)
        if self.contact_number:
            clean_phone = re.sub(r"[\s\-]", "", self.contact_number)
            if not re.match(r"^(?:\+91|0)?[6-9]\d{9}$", clean_phone):
                raise ValidationError({
                    "contact_number": (
                        "Please enter a valid 10-digit Indian phone number "
                        "(e.g., 9876543210 or +919876543210)."
                    )
                })

        # 3. Emergency Contact Number Validation (if provided)
        if self.emergency_contact_number:
            clean_em_phone = re.sub(r"[\s\-]", "", self.emergency_contact_number)
            if not re.match(r"^(?:\+91|0)?[6-9]\d{9}$", clean_em_phone):
                raise ValidationError({
                    "emergency_contact_number": (
                        "Please enter a valid 10-digit emergency contact number."
                    )
                })

    def save(self, *args, **kwargs):
        # Auto-generate MRN if not set
        if not self.patient_id:
            self.patient_id = PatientIDSequence.get_next_id()
        self.full_clean()
        super().save(*args, **kwargs)


class MedicalHistory(models.Model):
    """
    Patient past medical history, chronic conditions, and previous diagnoses.
    """

    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="medical_histories",
        help_text="Associated patient record. Protected from accidental deletion.",
    )
    condition = models.CharField(
        max_length=200,
        help_text="Medical condition, diagnosis, or surgical history (e.g., Hypertension, Type 2 Diabetes).",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional additional notes, treatments, or medical context.",
    )
    diagnosed_date = models.DateField(
        null=True,
        blank=True,
        help_text="Optional date when the condition was diagnosed.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Medical History"
        verbose_name_plural = "Medical Histories"
        ordering = ["-diagnosed_date", "-created_at"]

    def __str__(self):
        return f"{self.patient.patient_id} - {self.condition}"

    def clean(self):
        super().clean()
        if self.diagnosed_date and self.diagnosed_date > timezone.now().date():
            raise ValidationError({
                "diagnosed_date": "Diagnosed date cannot be in the future."
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Allergy(models.Model):
    """
    Patient allergy records and severity classifications.
    """

    class Severity(models.TextChoices):
        MILD = "MILD", "Mild"
        MODERATE = "MODERATE", "Moderate"
        SEVERE = "SEVERE", "Severe"
        UNKNOWN = "UNKNOWN", "Unknown"

    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="allergies",
        help_text="Associated patient record. Protected from accidental deletion.",
    )
    allergen = models.CharField(
        max_length=150,
        help_text="Allergen name (e.g., Penicillin, Peanuts, Latex, Aspirin).",
    )
    reaction = models.CharField(
        max_length=200,
        blank=True,
        help_text="Observed allergic reaction (e.g., Skin rash, Anaphylaxis, Swelling).",
    )
    severity = models.CharField(
        max_length=10,
        choices=Severity.choices,
        default=Severity.UNKNOWN,
        help_text="Severity level of the allergy.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional precautions, medication advisories, or clinical notes.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Allergy"
        verbose_name_plural = "Allergies"
        ordering = ["-severity", "-created_at"]

    def __str__(self):
        return f"{self.patient.patient_id} - {self.allergen} ({self.get_severity_display()})"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
