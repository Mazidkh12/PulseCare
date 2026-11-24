from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from appointments.models import Appointment
from consultations.models import Consultation


class PrescriptionIDSequence(models.Model):
    """
    Database-backed sequence table for atomic, collision-free Prescription number generation.
    Tracks the highest sequential integer issued per calendar year.
    """

    year = models.PositiveIntegerField(unique=True, help_text="Calendar year for the sequence.")
    last_sequence = models.PositiveIntegerField(
        default=0, help_text="Highest sequential integer issued for this year."
    )

    class Meta:
        verbose_name = "Prescription ID Sequence"
        verbose_name_plural = "Prescription ID Sequences"

    def __str__(self):
        return f"{self.year}: {self.last_sequence}"

    @classmethod
    def get_next_number(cls, year=None):
        """
        Thread-safe, transaction-safe method to generate the next unique Prescription Number.
        Format: RX-YYYY-NNNN (e.g., RX-2026-0001)
        """
        if year is None:
            year = timezone.now().year

        with transaction.atomic():
            seq_obj, created = cls.objects.select_for_update().get_or_create(
                year=year, defaults={"last_sequence": 0}
            )
            # Sync sequence if existing records exist with higher sequence numbers
            if created or seq_obj.last_sequence == 0:
                prefix = f"RX-{year}-"
                last_rx = (
                    Prescription.objects.filter(prescription_number__startswith=prefix)
                    .order_by("-prescription_number")
                    .first()
                )
                if last_rx:
                    try:
                        num_part = int(last_rx.prescription_number.split("-")[-1])
                        if num_part > seq_obj.last_sequence:
                            seq_obj.last_sequence = num_part
                    except (ValueError, IndexError):
                        pass

            seq_obj.last_sequence += 1
            seq_obj.save(update_fields=["last_sequence"])
            return f"RX-{year}-{seq_obj.last_sequence:04d}"


class Prescription(models.Model):
    """
    Prescription model linked to a clinical Consultation.
    Maintains prescription metadata, issuing lifecycle, and medical-legal protections.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ISSUED = "ISSUED", "Issued"

    # Relationships
    consultation = models.OneToOneField(
        Consultation,
        on_delete=models.PROTECT,
        related_name="prescription",
        help_text="Clinical consultation associated with this prescription (protected from deletion).",
    )

    # Prescription Identification
    prescription_number = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Unique prescription number (RX-YYYY-NNNN), auto-generated.",
    )
    prescription_date = models.DateTimeField(
        default=timezone.now,
        help_text="Date and time when the prescription was created / issued.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        help_text="Operational status of the prescription.",
    )
    issued_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text="Timestamp when the prescription was officially issued.",
    )

    # Clinical Instructions & Amendments
    general_instructions = models.TextField(
        blank=True,
        help_text="General instructions, dietary advice, or precautions for the patient.",
    )
    amendment_notes = models.TextField(
        blank=True,
        help_text="Documented clinical justification for any correction or addendum to an issued prescription.",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Prescription"
        verbose_name_plural = "Prescriptions"
        ordering = ["-prescription_date", "-created_at"]

    def __str__(self):
        pat_name = self.patient.get_full_name() if self.patient else "Unknown Patient"
        doc_name = (
            self.doctor.user.get_full_name().strip() or self.doctor.user.username
            if self.doctor
            else "Unknown Doctor"
        )
        return f"Prescription {self.prescription_number} - {pat_name} (Dr. {doc_name}) [{self.get_status_display()}]"

    @property
    def patient(self):
        """Derives patient directly from the linked consultation."""
        return self.consultation.patient if self.consultation_id else None

    @property
    def doctor(self):
        """Derives doctor directly from the linked consultation."""
        return self.consultation.doctor if self.consultation_id else None

    def issue(self, issued_by=None):
        """
        Officially issues the prescription with doctor role authorization check.
        If issued_by (User) is provided, verifies that user.role == DOCTOR.
        """
        if issued_by is not None:
            if getattr(issued_by, "role", None) != "DOCTOR":
                role_label = (
                    issued_by.get_role_display()
                    if hasattr(issued_by, "get_role_display")
                    else issued_by.role
                )
                raise ValidationError({
                    "status": (
                        f"User '{issued_by.username}' with role '{role_label}' is not authorized to issue prescriptions. "
                        "Only users with the DOCTOR role can issue prescriptions."
                    )
                })

        # Ensure the consultation doctor also has DOCTOR role
        if self.consultation_id and getattr(self.consultation.doctor.user, "role", None) != "DOCTOR":
            raise ValidationError({
                "status": "Attending physician on consultation must have the DOCTOR role."
            })

        self.status = self.Status.ISSUED
        self.issued_at = timezone.now()
        self.save()

        try:
            from audit.services import log_audit_event
            actor = issued_by or (self.doctor.user if self.doctor else None)
            log_audit_event(
                actor=actor,
                action="ISSUE_PRESCRIPTION",
                obj=self,
                object_label=f"Prescription {self.prescription_number}",
                metadata={
                    "prescription_id": self.pk,
                    "prescription_number": self.prescription_number,
                    "status": self.Status.ISSUED,
                },
            )
        except Exception:
            pass

    def clean(self):
        super().clean()
        errors = {}

        # 1. Consultation Validation
        if not self.consultation_id:
            errors["consultation"] = "Consultation is required."
        else:
            consultation = self.consultation

            # Check if linked to a cancelled appointment
            if (
                consultation.appointment_id
                and consultation.appointment.status == Appointment.Status.CANCELLED
            ):
                errors["consultation"] = (
                    "Cannot issue a prescription for a consultation linked to a cancelled appointment."
                )

            # When marking ISSUED, consultation must be FINALIZED
            if self.status == self.Status.ISSUED:
                if consultation.status != Consultation.Status.FINALIZED:
                    errors["status"] = (
                        "A prescription cannot be issued for a consultation in DRAFT status. "
                        "The consultation must be FINALIZED first."
                    )

                # Attending doctor check
                if getattr(consultation.doctor.user, "role", None) != "DOCTOR":
                    errors["status"] = "Attending doctor must hold the DOCTOR role."

        # 2. Issued Prescription Protection against Silent Overwriting
        if self.pk:
            orig = (
                Prescription.objects.filter(pk=self.pk)
                .values("status", "amendment_notes", "general_instructions")
                .first()
            )
            if orig and orig["status"] == self.Status.ISSUED:
                if self.status != self.Status.ISSUED:
                    errors["status"] = (
                        "An issued prescription cannot be reverted to draft status."
                    )
                elif orig["amendment_notes"] == self.amendment_notes:
                    # Check if general_instructions changed silently
                    if orig["general_instructions"] != self.general_instructions:
                        errors["amendment_notes"] = (
                            "Issued prescriptions cannot be silently modified. "
                            "Please document explicit justification in 'amendment_notes' to record this correction."
                        )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Auto-generate prescription number if not set
        if not self.prescription_number:
            self.prescription_number = PrescriptionIDSequence.get_next_number()

        # Stamp issued_at when status transitions to ISSUED
        if self.status == self.Status.ISSUED and not self.issued_at:
            self.issued_at = timezone.now()

        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent casual deletion of issued prescriptions to maintain medical audit records."""
        if self.status == self.Status.ISSUED:
            raise ValidationError(
                "Issued prescriptions cannot be deleted to preserve the medical audit trail."
            )
        super().delete(*args, **kwargs)


class PrescriptionItem(models.Model):
    """
    Individual medication item prescribed with dosage, frequency, and instructions.
    """

    class DosageForm(models.TextChoices):
        TABLET = "TABLET", "Tablet"
        CAPSULE = "CAPSULE", "Capsule"
        SYRUP = "SYRUP", "Syrup"
        INJECTION = "INJECTION", "Injection"
        DROPS = "DROPS", "Drops"
        OINTMENT = "OINTMENT", "Ointment"
        CREAM = "CREAM", "Cream"
        OTHER = "OTHER", "Other"

    class IntakeTiming(models.TextChoices):
        BEFORE_FOOD = "BEFORE_FOOD", "Before Food"
        AFTER_FOOD = "AFTER_FOOD", "After Food"
        WITH_FOOD = "WITH_FOOD", "With Food"
        ANY_TIME = "ANY_TIME", "Any Time"

    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="items",
        help_text="Prescription this medication item belongs to.",
    )

    # Medicine Information
    medicine_name = models.CharField(
        max_length=200,
        help_text="Brand or generic name of prescribed medicine (e.g., Paracetamol, Amoxicillin).",
    )
    dosage_form = models.CharField(
        max_length=20,
        choices=DosageForm.choices,
        default=DosageForm.TABLET,
        help_text="Pharmaceutical dosage form.",
    )
    strength = models.CharField(
        max_length=100,
        blank=True,
        help_text="Medicine strength (e.g., 500 mg, 250 mg/5 ml, 10 mg).",
    )

    # Dosage Instructions
    dosage = models.CharField(
        max_length=100,
        help_text="Prescribed dose per intake (e.g., 1 tablet, 5 ml, 2 drops, 1 puff).",
    )
    frequency = models.CharField(
        max_length=50,
        help_text="Administration schedule (e.g., OD (Once daily), BD (Twice daily), TID, 1-0-1, PRN).",
    )
    duration = models.PositiveIntegerField(
        help_text="Duration of treatment in days (must be greater than 0).",
    )
    intake_timing = models.CharField(
        max_length=20,
        choices=IntakeTiming.choices,
        default=IntakeTiming.AFTER_FOOD,
        help_text="Timing relative to meals.",
    )
    special_instructions = models.TextField(
        blank=True,
        help_text="Optional special precautions or administration guidance.",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Prescription Item"
        verbose_name_plural = "Prescription Items"
        ordering = ["created_at"]

    def __str__(self):
        strength_str = f" {self.strength}" if self.strength else ""
        return (
            f"{self.medicine_name}{strength_str} ({self.get_dosage_form_display()}) - "
            f"{self.dosage} {self.frequency} x {self.duration} days"
        )

    def clean(self):
        super().clean()
        errors = {}

        # 1. Medicine Name Required
        if not self.medicine_name or not self.medicine_name.strip():
            errors["medicine_name"] = "Medicine name is required."

        # 2. Dosage Required
        if not self.dosage or not self.dosage.strip():
            errors["dosage"] = "Dosage amount is required."

        # 3. Frequency Required
        if not self.frequency or not self.frequency.strip():
            errors["frequency"] = "Dosing frequency is required."

        # 4. Duration Validation (must be > 0)
        if self.duration is not None and self.duration <= 0:
            errors["duration"] = "Duration must be greater than zero days."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
