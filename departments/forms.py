from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models, transaction

from .models import Department, DoctorProfile

User = get_user_model()


class DepartmentForm(forms.ModelForm):
    """
    Administrator form for creating and updating clinic departments.
    """

    class Meta:
        model = Department
        fields = ["name", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Department Name (e.g. Cardiology)"}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Department clinical scope, specialties, and description...",
                }
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise ValidationError("Department name is required.")

        # Check unique name case-insensitively excluding current instance
        qs = Department.objects.filter(name__iexact=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"A department named '{name}' already exists.")
        return name


class DoctorCreationForm(forms.Form):
    """
    Administrator form to register a new Doctor User account and linked DoctorProfile atomically.
    """

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Username (e.g. dr_smith)"}),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "doctor@clinic.test"}),
    )
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "First Name"}),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Last Name"}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Initial password"}),
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Confirm password"}),
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.filter(is_active=True),
        empty_label="Select Department",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    specialization = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Specialization (e.g. Cardiology)"}),
    )
    qualification = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Qualifications (e.g. MBBS, MD)"}),
    )
    contact_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Direct contact number"}),
    )
    is_active = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if not username:
            raise ValidationError("Username is required.")
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(f"A user with username '{username}' already exists.")
        return username

    def clean_department(self):
        dept = self.cleaned_data.get("department")
        if not dept:
            raise ValidationError("A clinic department is required.")
        if not dept.is_active:
            raise ValidationError("Cannot assign doctor to an inactive department.")
        return dept

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "Passwords do not match.")
        return cleaned_data

    @transaction.atomic
    def save(self):
        cleaned = self.cleaned_data
        user = User(
            username=cleaned["username"],
            email=cleaned.get("email", ""),
            first_name=cleaned["first_name"],
            last_name=cleaned["last_name"],
            role=User.Role.DOCTOR,
            is_active=cleaned.get("is_active", True),
        )
        user.set_password(cleaned["password"])
        user.save()

        profile = DoctorProfile.objects.create(
            user=user,
            department=cleaned["department"],
            specialization=cleaned["specialization"],
            qualification=cleaned["qualification"],
            contact_number=cleaned.get("contact_number", ""),
            is_active=cleaned.get("is_active", True),
        )
        return user, profile


class DoctorUpdateForm(forms.ModelForm):
    """
    Administrator form for updating an existing doctor's profile and basic user details.
    """

    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )

    class Meta:
        model = DoctorProfile
        fields = [
            "department",
            "specialization",
            "qualification",
            "contact_number",
            "is_active",
        ]
        widgets = {
            "department": forms.Select(attrs={"class": "form-select"}),
            "specialization": forms.TextInput(attrs={"class": "form-control"}),
            "qualification": forms.TextInput(attrs={"class": "form-control"}),
            "contact_number": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["first_name"].initial = self.instance.user.first_name
            self.fields["last_name"].initial = self.instance.user.last_name
            self.fields["email"].initial = self.instance.user.email
            # Only allow active departments or the currently assigned department
            self.fields["department"].queryset = Department.objects.filter(
                models.Q(is_active=True) | models.Q(pk=self.instance.department_id)
            )

    def clean_department(self):
        dept = self.cleaned_data.get("department")
        if not dept:
            raise ValidationError("Department is required.")
        # If changing department, must be active
        if self.instance and self.instance.department != dept and not dept.is_active:
            raise ValidationError("Cannot reassign doctor to an inactive department.")
        return dept

    @transaction.atomic
    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user
        user.first_name = self.cleaned_data.get("first_name", user.first_name)
        user.last_name = self.cleaned_data.get("last_name", user.last_name)
        user.email = self.cleaned_data.get("email", user.email)
        # Synchronize user is_active with profile is_active
        user.is_active = profile.is_active
        user.save()
        if commit:
            profile.save()
        return profile
