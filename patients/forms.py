from django import forms
from .models import Patient


class PatientRegistrationForm(forms.ModelForm):
    """
    Receptionist front-desk patient registration form.
    MRN (patient_id) is generated automatically by the Patient model save() method.
    """

    class Meta:
        model = Patient
        fields = [
            # Personal Information
            "first_name",
            "last_name",
            "date_of_birth",
            "gender",
            "blood_group",
            # Contact Information
            "contact_number",
            "email",
            "address",
            "city",
            "state",
            "pincode",
            # Emergency Contact
            "emergency_contact_name",
            "emergency_contact_number",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "First name"}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name"}),
            "date_of_birth": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "blood_group": forms.Select(attrs={"class": "form-select"}),
            "contact_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "10-digit mobile number"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "patient@example.com"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Residential street address"}),
            "city": forms.TextInput(attrs={"class": "form-control", "placeholder": "City"}),
            "state": forms.TextInput(attrs={"class": "form-control", "placeholder": "State"}),
            "pincode": forms.TextInput(attrs={"class": "form-control", "placeholder": "PIN code"}),
            "emergency_contact_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Relative / Contact person"}),
            "emergency_contact_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Emergency phone number"}),
        }

    def clean_first_name(self):
        first_name = self.cleaned_data.get("first_name", "").strip()
        if not first_name:
            raise forms.ValidationError("First name is required.")
        return first_name

    def clean_last_name(self):
        last_name = self.cleaned_data.get("last_name", "").strip()
        if not last_name:
            raise forms.ValidationError("Last name is required.")
        return last_name
