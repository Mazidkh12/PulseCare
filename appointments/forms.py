from django import forms
from departments.models import Department, DoctorProfile
from patients.models import Patient
from .models import Appointment


class AppointmentBookingForm(forms.ModelForm):
    """
    Receptionist front-desk appointment booking form with dependent department-doctor validation.
    """

    department = forms.ModelChoiceField(
        queryset=Department.objects.filter(is_active=True).order_by("name"),
        empty_label="-- Select Department --",
        widget=forms.Select(attrs={"class": "form-select", "id": "id_department"}),
        help_text="Clinical specialty department.",
    )

    class Meta:
        model = Appointment
        fields = [
            "patient",
            "department",
            "doctor",
            "appointment_date",
            "start_time",
            "end_time",
            "reason",
            "notes",
        ]
        widgets = {
            "patient": forms.Select(attrs={"class": "form-select", "id": "id_patient"}),
            "doctor": forms.Select(attrs={"class": "form-select", "id": "id_doctor"}),
            "appointment_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "start_time": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "end_time": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "reason": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Reason for visit or primary symptoms"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Optional internal administrative notes"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Restrict patient choices strictly to active patient records
        self.fields["patient"].queryset = Patient.objects.filter(is_active=True).order_by("first_name", "last_name")

        # Restrict doctor choices strictly to active doctors in active departments
        self.fields["doctor"].queryset = (
            DoctorProfile.objects.select_related("user", "department")
            .filter(is_active=True, department__is_active=True)
            .order_by("user__first_name", "user__last_name")
        )

        # If instance already has a doctor with a department, set initial department
        if self.instance.pk and self.instance.doctor_id:
            self.fields["department"].initial = self.instance.doctor.department_id

    def clean(self):
        cleaned_data = super().clean()
        doctor = cleaned_data.get("doctor")
        department = cleaned_data.get("department")
        patient = cleaned_data.get("patient")

        # Inactive patient check
        if patient and not patient.is_active:
            self.add_error("patient", f"Cannot book appointment for inactive patient '{patient.get_full_name()}'.")

        # Inactive doctor check
        if doctor and not doctor.is_active:
            self.add_error("doctor", f"Cannot book appointment with inactive doctor '{doctor}'.")

        # Dependent department-doctor verification
        if doctor and department:
            if doctor.department_id != department.id:
                self.add_error(
                    "doctor",
                    f"Selected doctor (Dr. {doctor.user.get_full_name().strip() or doctor.user.username}) "
                    f"does not belong to department '{department.name}'.",
                )

        return cleaned_data
