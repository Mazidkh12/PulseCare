from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone
from departments.models import DoctorProfile
from patients.models import Patient


class Appointment(models.Model):
    """
    Appointment model managing outpatient clinical visits between patients and doctors.
    """

    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        CONFIRMED = "CONFIRMED", "Confirmed"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"
        NO_SHOW = "NO_SHOW", "No Show"

    # Relationships
    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="appointments",
        help_text="Patient for whom the appointment is booked.",
    )
    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.PROTECT,
        related_name="appointments",
        help_text="Doctor with whom the appointment is scheduled.",
    )

    # Schedule Details
    appointment_date = models.DateField(
        help_text="Date on which the appointment is scheduled."
    )
    start_time = models.TimeField(
        help_text="Start time of the appointment slot."
    )
    end_time = models.TimeField(
        help_text="End time of the appointment slot."
    )

    # Status & Clinical Notes
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
        help_text="Current operational status of the appointment.",
    )
    reason = models.TextField(
        blank=True,
        help_text="Optional reason for visit, chief complaint, or consultation motive.",
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional internal administrative or clinical notes.",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Appointment"
        verbose_name_plural = "Appointments"
        ordering = ["-appointment_date", "-start_time"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")),
                name="appointment_end_time_after_start_time",
            )
        ]

    def __str__(self):
        pat_name = self.patient.get_full_name() if self.patient_id else "Unknown Patient"
        doc_name = (
            self.doctor.user.get_full_name().strip() or self.doctor.user.username
            if self.doctor_id
            else "Unknown Doctor"
        )
        date_str = str(self.appointment_date) if self.appointment_date else ""
        time_str = (
            f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"
            if self.start_time and self.end_time
            else ""
        )
        return f"Appointment: {pat_name} with Dr. {doc_name} on {date_str} ({time_str}) [{self.get_status_display()}]"

    @property
    def department(self):
        """Derived department from the doctor's profile to avoid redundant database storage."""
        return self.doctor.department if self.doctor_id else None

    # Status Transition Helpers
    def confirm(self):
        self.status = self.Status.CONFIRMED
        self.save(update_fields=["status", "updated_at"])

    def start(self):
        self.status = self.Status.IN_PROGRESS
        self.save(update_fields=["status", "updated_at"])

    def complete(self):
        self.status = self.Status.COMPLETED
        self.save(update_fields=["status", "updated_at"])

    def cancel(self, cancelled_by=None):
        self.status = self.Status.CANCELLED
        self.save(update_fields=["status", "updated_at"])

        try:
            from audit.services import log_audit_event
            pat_name = self.patient.get_full_name() if self.patient_id else "Unknown Patient"
            log_audit_event(
                actor=cancelled_by,
                action="CANCEL_APPOINTMENT",
                obj=self,
                object_label=f"Appointment {self.pk} for {pat_name}",
                metadata={"appointment_id": self.pk, "status": self.Status.CANCELLED},
            )
        except Exception:
            pass

    def mark_no_show(self):
        self.status = self.Status.NO_SHOW
        self.save(update_fields=["status", "updated_at"])

    def clean(self):
        super().clean()
        errors = {}

        now = timezone.localtime() if timezone.is_aware(timezone.now()) else timezone.now()
        today = now.date()
        current_time = now.time()

        # 1. Timing Validation
        if self.start_time and self.end_time:
            if self.end_time <= self.start_time:
                errors["end_time"] = "Appointment end time must be later than start time."

        # Date validation: disallow scheduling for past dates
        if self.appointment_date:
            timing_changed = self._has_timing_changed()
            is_new = self._state.adding

            if is_new or timing_changed:
                if self.appointment_date < today:
                    errors["appointment_date"] = "Cannot schedule an appointment for a past date."
                elif self.appointment_date == today and self.start_time:
                    if self.start_time < current_time:
                        errors["start_time"] = (
                            "Cannot schedule an appointment for a time that has already passed today."
                        )

        # 2. Patient Validation
        if self.patient_id:
            if self._state.adding or self._has_patient_changed():
                if not self.patient.is_active:
                    errors["patient"] = (
                        f"Cannot book appointment for inactive patient '{self.patient.get_full_name()}'."
                    )

        # 3. Doctor Validation
        if self.doctor_id:
            if self._state.adding or self._has_doctor_changed():
                if not self.doctor.is_active:
                    errors["doctor"] = (
                        f"Cannot book appointment with inactive doctor '{self.doctor}'."
                    )
            # Ensure the linked user has role DOCTOR
            if getattr(self.doctor.user, "role", None) != "DOCTOR":
                errors["doctor"] = "Assigned doctor must have the DOCTOR role."

        # 4. Double-Booking Validation (Application-level check)
        if (
            self.doctor_id
            and self.appointment_date
            and self.start_time
            and self.end_time
            and self.status != self.Status.CANCELLED
        ):
            overlapping_qs = Appointment.objects.filter(
                doctor_id=self.doctor_id,
                appointment_date=self.appointment_date,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time,
            ).exclude(status=self.Status.CANCELLED)

            if self.pk:
                overlapping_qs = overlapping_qs.exclude(pk=self.pk)

            if overlapping_qs.exists():
                existing = overlapping_qs.first()
                errors["start_time"] = (
                    f"Doctor already has an appointment ({existing.start_time.strftime('%H:%M')} - "
                    f"{existing.end_time.strftime('%H:%M')}) overlapping with this time slot."
                )

        if errors:
            raise ValidationError(errors)

    def _has_patient_changed(self):
        if not self.pk:
            return False
        orig = Appointment.objects.filter(pk=self.pk).values("patient_id").first()
        return bool(orig and orig["patient_id"] != self.patient_id)

    def _has_doctor_changed(self):
        if not self.pk:
            return False
        orig = Appointment.objects.filter(pk=self.pk).values("doctor_id").first()
        return bool(orig and orig["doctor_id"] != self.doctor_id)

    def _has_timing_changed(self):
        if not self.pk:
            return False
        orig = (
            Appointment.objects.filter(pk=self.pk)
            .values("appointment_date", "start_time")
            .first()
        )
        return bool(
            orig
            and (
                orig["appointment_date"] != self.appointment_date
                or orig["start_time"] != self.start_time
            )
        )

    def save(self, *args, **kwargs):
        """
        Concurrency-safe save utilizing MySQL row-level locking (select_for_update)
        on the doctor record to serialize simultaneous booking attempts for the same doctor.
        """
        with transaction.atomic():
            if self.doctor_id:
                # Lock doctor record to prevent concurrent double-booking race conditions
                DoctorProfile.objects.select_for_update().filter(pk=self.doctor_id).first()

            # Execute model validation
            self.full_clean()

            # Concurrency double-check inside locked transaction
            if (
                self.doctor_id
                and self.appointment_date
                and self.start_time
                and self.end_time
                and self.status != self.Status.CANCELLED
            ):
                conflict = (
                    Appointment.objects.select_for_update()
                    .filter(
                        doctor_id=self.doctor_id,
                        appointment_date=self.appointment_date,
                        start_time__lt=self.end_time,
                        end_time__gt=self.start_time,
                    )
                    .exclude(status=self.Status.CANCELLED)
                )
                if self.pk:
                    conflict = conflict.exclude(pk=self.pk)
                if conflict.exists():
                    raise ValidationError({
                        "start_time": "Doctor already has an overlapping appointment in this time slot."
                    })

            super().save(*args, **kwargs)
