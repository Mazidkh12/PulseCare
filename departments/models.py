from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Department(models.Model):
    """
    Clinic department / specialty module (e.g., Cardiology, Pediatrics).
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique name of the clinic department.",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of the department's specialties or scope.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this department is currently active for doctor assignments.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Department"
        verbose_name_plural = "Departments"
        ordering = ["name"]

    def __str__(self):
        return self.name


class DoctorProfile(models.Model):
    """
    Doctor profile linked to the custom User model.
    Must only belong to a user whose role is DOCTOR.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="doctor_profile",
        limit_choices_to={"role": "DOCTOR"},
        help_text="User account with the DOCTOR role.",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="doctor_profiles",
        help_text="Department to which the doctor is assigned. Protected from deletion if doctors exist.",
    )
    specialization = models.CharField(
        max_length=150,
        help_text="Doctor's primary clinical specialization (e.g., General Medicine, Interventional Cardiology).",
    )
    qualification = models.CharField(
        max_length=150,
        help_text="Educational and medical qualifications (e.g., MBBS, MD, MS).",
    )
    contact_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="Optional direct contact number for clinical communication.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this doctor profile is active.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Doctor Profile"
        verbose_name_plural = "Doctor Profiles"
        ordering = ["user__first_name", "user__last_name", "user__username"]

    def __str__(self):
        full_name = self.user.get_full_name().strip() if self.user_id else ""
        doc_name = full_name if full_name else (self.user.username if self.user_id else "Unknown")
        dept_name = self.department.name if self.department_id else "No Department"
        return f"Dr. {doc_name} - {self.specialization} ({dept_name})"

    def clean(self):
        super().clean()

        # 1. Validate User Role: Must strictly be DOCTOR
        if self.user_id:
            user = self.user
            # Check against the User model's Role choice
            if getattr(user, "role", None) != "DOCTOR":
                role_label = user.get_role_display() if hasattr(user, "get_role_display") else user.role
                raise ValidationError({
                    "user": f"A Doctor Profile can only be assigned to a user with the DOCTOR role. User '{user.username}' has role '{role_label}'."
                })

            # Check for duplicate profile
            existing_qs = DoctorProfile.objects.filter(user_id=self.user_id)
            if self.pk:
                existing_qs = existing_qs.exclude(pk=self.pk)
            if existing_qs.exists():
                raise ValidationError({
                    "user": f"A Doctor Profile already exists for user '{user.username}'."
                })

        # 2. Validate Department: Inactive departments cannot be assigned to new doctors or changed to
        if self.department_id:
            dept = self.department
            if not dept.is_active:
                if self._state.adding or self._has_department_changed():
                    raise ValidationError({
                        "department": f"Cannot assign inactive department '{dept.name}'. Only active departments can be assigned to doctors."
                    })

    def _has_department_changed(self):
        if not self.pk:
            return False
        orig = DoctorProfile.objects.filter(pk=self.pk).values("department_id").first()
        return bool(orig and orig["department_id"] != self.department_id)

    def save(self, *args, **kwargs):
        # Enforce model validation rules on direct ORM calls as well as admin/forms
        self.full_clean()
        super().save(*args, **kwargs)
