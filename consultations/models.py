from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from appointments.models import Appointment
from departments.models import DoctorProfile
from patients.models import Patient


class Consultation(models.Model):
    """
    Clinical case-taking and outpatient consultation record.
    Supports both scheduled appointment visits and unscheduled walk-in consultations.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        FINALIZED = "FINALIZED", "Finalized"

    # Core Relationships
    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="consultations",
        help_text="Patient undergoing consultation. Protected from accidental deletion.",
    )
    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.PROTECT,
        related_name="consultations",
        help_text="Attending physician conducting the consultation.",
    )
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="consultation",
        help_text="Optional linked appointment. Left blank for walk-in consultations.",
    )

    # Basic Consultation Details
    consultation_date = models.DateTimeField(
        default=timezone.now,
        help_text="Date and time when the consultation was conducted.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        help_text="Documentation status (DRAFT or FINALIZED).",
    )
    finalized_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text="Timestamp when the clinical record was finalized.",
    )

    # Chief Complaint & History of Presenting Illness
    chief_complaint = models.TextField(
        help_text="Primary symptoms or reason for visit as reported by patient."
    )
    history_of_present_illness = models.TextField(
        blank=True,
        help_text="Chronological account of symptoms: onset, duration, character, severity, and progression.",
    )

    # Medical & Surgical History
    past_medical_history = models.TextField(
        blank=True,
        help_text="Previous illnesses, hospitalizations, or chronic conditions.",
    )
    past_surgical_history = models.TextField(
        blank=True,
        help_text="Previous operations, surgical interventions, and approximate dates.",
    )
    family_history = models.TextField(
        blank=True,
        help_text="Familial diseases, hereditary conditions, or genetic predispositions.",
    )
    personal_history = models.TextField(
        blank=True,
        help_text="Dietary habits, smoking, alcohol, substance use, sleep patterns, and bowel/bladder habits.",
    )

    # Medications & Allergies
    current_medications = models.TextField(
        blank=True,
        help_text="Active medications, dosages, frequency, and compliance.",
    )
    allergy_notes = models.TextField(
        blank=True,
        help_text="Additional allergy observations or drug intolerances noted during this visit.",
    )

    # Physical Examination & Assessment
    physical_examination = models.TextField(
        blank=True,
        help_text="Systemic and general physical examination findings.",
    )
    clinical_assessment = models.TextField(
        blank=True,
        help_text="Doctor's clinical analysis, case synthesis, and problem list.",
    )
    provisional_diagnosis = models.TextField(
        blank=True,
        help_text="Free-text provisional diagnosis or working impression documented by the physician.",
    )

    # Treatment Plan & Follow-up
    treatment_plan = models.TextField(
        blank=True,
        help_text="Recommended management plan, investigations, therapies, and lifestyle guidance.",
    )
    follow_up_notes = models.TextField(
        blank=True,
        help_text="Recommended follow-up interval, monitoring instructions, and red-flag symptoms.",
    )
    follow_up_date = models.DateField(
        null=True,
        blank=True,
        help_text="Scheduled date for the patient's next follow-up visit.",
    )

    # Explicit Amendments to Finalized Records
    amendment_notes = models.TextField(
        blank=True,
        help_text="Documented clinical justification for any correction or addendum made after finalization.",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Consultation"
        verbose_name_plural = "Consultations"
        ordering = ["-consultation_date", "-created_at"]

    def __str__(self):
        pat_name = self.patient.get_full_name() if self.patient_id else "Unknown Patient"
        doc_name = (
            self.doctor.user.get_full_name().strip() or self.doctor.user.username
            if self.doctor_id
            else "Unknown Doctor"
        )
        date_str = (
            self.consultation_date.strftime("%Y-%m-%d %H:%M")
            if self.consultation_date
            else ""
        )
        return f"Consultation: {pat_name} with Dr. {doc_name} on {date_str} [{self.get_status_display()}]"

    def finalize(self, finalized_by=None):
        """Finalizes the clinical consultation record, stamps finalized_at, and logs audit event."""
        self.status = self.Status.FINALIZED
        self.finalized_at = timezone.now()
        self.save()

        try:
            from audit.services import log_audit_event
            actor = finalized_by or (self.doctor.user if self.doctor_id else None)
            pat_name = self.patient.get_full_name() if self.patient_id else "Unknown Patient"
            log_audit_event(
                actor=actor,
                action="FINALIZE_CONSULTATION",
                obj=self,
                object_label=f"Consultation {self.pk} - {pat_name}",
                metadata={"consultation_id": self.pk, "status": self.Status.FINALIZED},
            )
        except Exception:
            pass

    def clean(self):
        super().clean()
        errors = {}

        # 1. Mandatory Patient & Doctor Validation
        if not self.patient_id:
            errors["patient"] = "Patient is required."
        elif self._state.adding or self._has_patient_changed():
            if not self.patient.is_active:
                errors["patient"] = (
                    f"Cannot create consultation for inactive patient '{self.patient.get_full_name()}'."
                )

        if not self.doctor_id:
            errors["doctor"] = "Doctor is required."
        elif self._state.adding or self._has_doctor_changed():
            if not self.doctor.is_active:
                errors["doctor"] = (
                    f"Cannot create consultation with inactive doctor '{self.doctor}'."
                )
            if getattr(self.doctor.user, "role", None) != "DOCTOR":
                errors["doctor"] = "Assigned doctor must have the DOCTOR role."

        # 2. Appointment-based Consultation Validation
        if self.appointment_id:
            apt = self.appointment
            # Validate matching patient
            if self.patient_id and apt.patient_id != self.patient_id:
                errors["appointment"] = (
                    f"Selected appointment belongs to patient '{apt.patient.get_full_name()}', "
                    f"which does not match consultation patient '{self.patient.get_full_name()}'."
                )
            # Validate matching doctor
            if self.doctor_id and apt.doctor_id != self.doctor_id:
                errors["appointment"] = (
                    f"Selected appointment is with Dr. '{apt.doctor}', "
                    f"which does not match consultation doctor Dr. '{self.doctor}'."
                )
            # Validate appointment status
            if apt.status == Appointment.Status.CANCELLED:
                errors["appointment"] = "Cannot create a consultation for a cancelled appointment."
            elif apt.status == Appointment.Status.NO_SHOW:
                errors["appointment"] = "Cannot create a consultation for an appointment marked as no-show."

            # Verify no other consultation references this appointment
            dup_qs = Consultation.objects.filter(appointment_id=self.appointment_id)
            if self.pk:
                dup_qs = dup_qs.exclude(pk=self.pk)
            if dup_qs.exists():
                errors["appointment"] = (
                    "This appointment already has an associated consultation."
                )

        # 3. Finalization Protection against Silent Overwriting
        if self.pk:
            orig = (
                Consultation.objects.filter(pk=self.pk)
                .values("status", "amendment_notes")
                .first()
            )
            if orig and orig["status"] == self.Status.FINALIZED:
                if self.status != self.Status.FINALIZED:
                    errors["status"] = (
                        "A finalized clinical consultation cannot be reverted to draft status."
                    )
                elif orig["amendment_notes"] == self.amendment_notes:
                    # Compare clinical fields against existing DB values
                    orig_obj = Consultation.objects.get(pk=self.pk)
                    clinical_fields = [
                        "patient_id",
                        "doctor_id",
                        "appointment_id",
                        "chief_complaint",
                        "history_of_present_illness",
                        "past_medical_history",
                        "past_surgical_history",
                        "family_history",
                        "personal_history",
                        "current_medications",
                        "allergy_notes",
                        "physical_examination",
                        "clinical_assessment",
                        "provisional_diagnosis",
                        "treatment_plan",
                        "follow_up_notes",
                        "follow_up_date",
                    ]
                    changed = [
                        f
                        for f in clinical_fields
                        if getattr(orig_obj, f) != getattr(self, f)
                    ]
                    if changed:
                        errors["amendment_notes"] = (
                            f"Finalized consultations cannot be silently modified ({', '.join(changed)} modified). "
                            "Please provide explicit documentation in 'amendment_notes' to record this clinical addendum."
                        )

        if errors:
            raise ValidationError(errors)

    def _has_patient_changed(self):
        if not self.pk:
            return False
        orig = Consultation.objects.filter(pk=self.pk).values("patient_id").first()
        return bool(orig and orig["patient_id"] != self.patient_id)

    def _has_doctor_changed(self):
        if not self.pk:
            return False
        orig = Consultation.objects.filter(pk=self.pk).values("doctor_id").first()
        return bool(orig and orig["doctor_id"] != self.doctor_id)

    def save(self, *args, **kwargs):
        # Set finalized_at timestamp upon transition to FINALIZED
        if self.status == self.Status.FINALIZED and not self.finalized_at:
            self.finalized_at = timezone.now()

        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of finalized consultations to maintain medical-legal audit integrity."""
        if self.status == self.Status.FINALIZED:
            raise ValidationError(
                "Finalized clinical consultations cannot be deleted to preserve the medical audit trail."
            )
        super().delete(*args, **kwargs)


class VitalSign(models.Model):
    """
    Objective physiological vital signs recorded during a clinical consultation.
    """

    consultation = models.OneToOneField(
        Consultation,
        on_delete=models.CASCADE,
        related_name="vitals",
        help_text="Associated clinical consultation.",
    )

    # Blood Pressure (mmHg)
    systolic_bp = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Systolic blood pressure in mmHg (normal physiological bounds: 40–300).",
    )
    diastolic_bp = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Diastolic blood pressure in mmHg (normal physiological bounds: 30–200).",
    )

    # Pulse & Respiration
    pulse_rate = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Heart / pulse rate in beats per minute (bpm, 20–300).",
    )
    respiratory_rate = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Respiratory rate in breaths per minute (4–80).",
    )

    # Temperature & Oxygenation
    temperature = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Body temperature in degrees Celsius (25.0–45.0).",
    )
    spo2 = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Peripheral blood oxygen saturation percentage (0.0–100.0%).",
    )

    # Anthropometry
    height = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Patient height in centimetres (cm, positive value up to 300).",
    )
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Patient body weight in kilograms (kg, positive value up to 500).",
    )
    bmi = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        editable=False,
        help_text="Calculated Body Mass Index (kg/m²), auto-computed from height and weight.",
    )

    recorded_at = models.DateTimeField(
        default=timezone.now,
        help_text="Timestamp when vital signs were measured.",
    )

    class Meta:
        verbose_name = "Vital Sign"
        verbose_name_plural = "Vital Signs"
        ordering = ["-recorded_at"]

    def __str__(self):
        pat_name = (
            self.consultation.patient.get_full_name()
            if self.consultation_id and self.consultation.patient_id
            else "Unknown Patient"
        )
        bp_str = (
            f"{self.systolic_bp}/{self.diastolic_bp} mmHg"
            if self.systolic_bp and self.diastolic_bp
            else "BP unrecorded"
        )
        pulse_str = f"{self.pulse_rate} bpm" if self.pulse_rate else "Pulse unrecorded"
        return f"Vitals for {pat_name} ({bp_str}, {pulse_str})"

    def calculate_bmi(self):
        """
        Calculates Body Mass Index (BMI = weight_kg / (height_m)^2).
        Returns Decimal rounded to 2 decimal places, or None if data is missing or invalid.
        """
        if self.height and self.weight:
            try:
                h_cm = Decimal(str(self.height))
                w_kg = Decimal(str(self.weight))
                if h_cm > 0 and w_kg > 0:
                    h_m = h_cm / Decimal("100")
                    calculated = w_kg / (h_m * h_m)
                    return Decimal(str(round(calculated, 2)))
            except (InvalidOperation, ZeroDivisionError):
                return None
        return None

    def clean(self):
        super().clean()
        errors = {}

        # 1. Blood Pressure Validation
        if self.systolic_bp is not None:
            if self.systolic_bp < 40 or self.systolic_bp > 300:
                errors["systolic_bp"] = "Systolic blood pressure must be between 40 and 300 mmHg."

        if self.diastolic_bp is not None:
            if self.diastolic_bp < 30 or self.diastolic_bp > 200:
                errors["diastolic_bp"] = "Diastolic blood pressure must be between 30 and 200 mmHg."

        if self.systolic_bp is not None and self.diastolic_bp is not None:
            if self.systolic_bp < self.diastolic_bp:
                errors["systolic_bp"] = (
                    "Systolic blood pressure cannot be lower than diastolic blood pressure."
                )

        # 2. Pulse & Respiration Validation
        if self.pulse_rate is not None:
            if self.pulse_rate < 20 or self.pulse_rate > 300:
                errors["pulse_rate"] = "Pulse rate must be between 20 and 300 bpm."

        if self.respiratory_rate is not None:
            if self.respiratory_rate < 4 or self.respiratory_rate > 80:
                errors["respiratory_rate"] = "Respiratory rate must be between 4 and 80 breaths/min."

        # 3. Temperature & Oxygenation Validation
        if self.temperature is not None:
            if self.temperature < Decimal("25.0") or self.temperature > Decimal("45.0"):
                errors["temperature"] = "Temperature must be between 25.0°C and 45.0°C."

        if self.spo2 is not None:
            if self.spo2 < Decimal("0.0") or self.spo2 > Decimal("100.0"):
                errors["spo2"] = "SpO2 oxygen saturation must be between 0.0% and 100.0%."

        # 4. Anthropometric Validation (Height and Weight)
        if self.height is not None:
            if self.height <= Decimal("0.0") or self.height > Decimal("300.0"):
                errors["height"] = "Height must be a positive value up to 300 cm."

        if self.weight is not None:
            if self.weight <= Decimal("0.0") or self.weight > Decimal("500.0"):
                errors["weight"] = "Weight must be a positive value up to 500 kg."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Automatically recompute BMI on save
        self.bmi = self.calculate_bmi()
        self.full_clean()
        super().save(*args, **kwargs)


class Diagnosis(models.Model):
    """
    Structured clinical diagnosis linked to a Consultation record.

    Supports one PRIMARY diagnosis and multiple SECONDARY diagnoses per
    consultation, enforced at both the application and database level.
    Free-text provisional diagnosis already exists on the Consultation
    model; this model captures the structured, coded diagnosis record.
    """

    class DiagnosisType(models.TextChoices):
        PRIMARY = "PRIMARY", "Primary"
        SECONDARY = "SECONDARY", "Secondary"

    # Relationships
    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.PROTECT,
        related_name="diagnoses",
        help_text="Consultation to which this diagnosis belongs. Protected from accidental deletion.",
    )
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="recorded_diagnoses",
        help_text="Clinician who recorded this diagnosis.",
    )

    # Diagnosis Information
    diagnosis_name = models.CharField(
        max_length=255,
        help_text="Clinical diagnosis name (e.g., Essential Hypertension, Type 2 Diabetes Mellitus).",
    )
    diagnosis_code = models.CharField(
        max_length=20,
        blank=True,
        help_text="Optional clinical classification code (e.g., ICD-10: I10, E11).",
    )
    diagnosis_type = models.CharField(
        max_length=10,
        choices=DiagnosisType.choices,
        default=DiagnosisType.PRIMARY,
        help_text="PRIMARY (principal diagnosis) or SECONDARY (comorbidity / complication).",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional additional clinical description, notes or differential reasoning.",
    )

    # Timestamps
    recorded_at = models.DateTimeField(
        default=timezone.now,
        help_text="Timestamp when this diagnosis was recorded.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Diagnosis"
        verbose_name_plural = "Diagnoses"
        ordering = ["diagnosis_type", "recorded_at"]
        # Enforce at the DB level: at most one PRIMARY diagnosis per consultation
        constraints = [
            models.UniqueConstraint(
                fields=["consultation"],
                condition=models.Q(diagnosis_type="PRIMARY"),
                name="unique_primary_diagnosis_per_consultation",
            )
        ]

    def __str__(self):
        pat_name = (
            self.consultation.patient.get_full_name()
            if self.consultation_id and self.consultation.patient_id
            else "Unknown Patient"
        )
        type_label = self.get_diagnosis_type_display()
        code_str = f" [{self.diagnosis_code}]" if self.diagnosis_code else ""
        return f"{type_label} Dx: {self.diagnosis_name}{code_str} — {pat_name}"

    @property
    def patient(self):
        """Derives patient from the linked consultation."""
        return self.consultation.patient if self.consultation_id else None

    @property
    def doctor(self):
        """Derives doctor from the linked consultation."""
        return self.consultation.doctor if self.consultation_id else None

    def clean(self):
        super().clean()
        errors = {}

        # 1. Diagnosis name is required
        if not self.diagnosis_name or not self.diagnosis_name.strip():
            errors["diagnosis_name"] = "Diagnosis name is required and cannot be blank."

        # 2. Consultation required
        if not self.consultation_id:
            errors["consultation"] = "A valid consultation is required."
        else:
            # 3. One-PRIMARY rule (application-level, mirrors the DB constraint)
            if self.diagnosis_type == self.DiagnosisType.PRIMARY:
                dup_qs = Diagnosis.objects.filter(
                    consultation=self.consultation,
                    diagnosis_type=self.DiagnosisType.PRIMARY,
                )
                if self.pk:
                    dup_qs = dup_qs.exclude(pk=self.pk)
                if dup_qs.exists():
                    errors["diagnosis_type"] = (
                        "This consultation already has a PRIMARY diagnosis. "
                        "Only one PRIMARY diagnosis is permitted per consultation. "
                        "Use SECONDARY for additional diagnoses."
                    )

            # 4. Recorded-by must have DOCTOR role if supplied
            if self.recorded_by_id:
                if getattr(self.recorded_by, "role", None) != "DOCTOR":
                    errors["recorded_by"] = (
                        f"User '{self.recorded_by.username}' does not hold the DOCTOR role "
                        "and is not authorized to record clinical diagnoses."
                    )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        self.full_clean()
        super().save(*args, **kwargs)

        try:
            from audit.services import log_audit_event
            action = "CREATE_DIAGNOSIS" if is_new else "UPDATE_DIAGNOSIS"
            log_audit_event(
                actor=self.recorded_by,
                action=action,
                obj=self,
                object_label=f"{self.get_diagnosis_type_display()} Dx: {self.diagnosis_name}",
                metadata={
                    "diagnosis_id": self.pk,
                    "diagnosis_type": self.diagnosis_type,
                    "diagnosis_code": self.diagnosis_code,
                    "consultation_id": self.consultation_id,
                },
            )
        except Exception:
            pass
