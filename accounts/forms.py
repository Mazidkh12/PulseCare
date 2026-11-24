from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()


class UserCreationAdminForm(forms.ModelForm):
    """
    Administrator form for creating staff accounts (Receptionist / Admin).
    Doctors are managed via the dedicated Doctor Management workflow.
    """

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Temporary account password"}),
        help_text="Password must meet standard security requirements.",
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Confirm password"}),
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "role", "is_active"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control", "placeholder": "Unique login username"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "staff@clinic.test"}),
            "first_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "First Name"}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Last Name"}),
            "role": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit role choices: Receptionist or Admin (Doctors must use doctor management to ensure DoctorProfile creation)
        self.fields["role"].choices = [
            (User.Role.RECEPTIONIST, "Receptionist"),
            (User.Role.ADMIN, "Administrator"),
        ]

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if not username:
            raise ValidationError("Username is required.")
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(f"A user with username '{username}' already exists.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class UserUpdateAdminForm(forms.ModelForm):
    """
    Administrator form for updating user details, role assignment, and active status.
    """

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "role", "is_active"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "role": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, admin_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.admin_user = admin_user
        if self.instance and self.instance.role == User.Role.DOCTOR:
            # Prevent changing a doctor's role away from DOCTOR if they have a doctor profile
            if hasattr(self.instance, "doctor_profile"):
                self.fields["role"].disabled = True
                self.fields["role"].help_text = "Role cannot be changed for users with an active Doctor Profile."

    def clean_is_active(self):
        is_active = self.cleaned_data.get("is_active")
        # Prevent administrator from disabling their own account
        if self.admin_user and self.instance.pk == self.admin_user.pk and not is_active:
            raise ValidationError("You cannot deactivate your own active administrator account.")
        return is_active

    def clean_role(self):
        role = self.cleaned_data.get("role")
        # Prevent administrator from removing their own admin role
        if self.admin_user and self.instance.pk == self.admin_user.pk and role != User.Role.ADMIN:
            raise ValidationError("You cannot revoke your own administrator role.")
        return role


class SignUpForm(forms.Form):
    """
    Public registration form for new clinical and administrative staff.
    Allows registering as Receptionist, Doctor, or Administrator.
    When Doctor is selected, automatically captures medical specialty
    and creates a linked DoctorProfile.
    """

    ROLE_CHOICES = [
        (User.Role.RECEPTIONIST, "Receptionist (Front-Desk / Intake)"),
        (User.Role.DOCTOR, "Doctor (Clinical Practitioner)"),
        (User.Role.ADMIN, "Administrator (Clinic Management)"),
    ]

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Choose a unique username", "autocomplete": "username"}
        ),
        help_text="Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.",
    )
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "staff@pulsecare.clinic", "autocomplete": "email"}
        ),
        help_text="Enter a valid email address.",
    )
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "First Name", "autocomplete": "given-name"}
        ),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Last Name", "autocomplete": "family-name"}
        ),
    )
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        initial=User.Role.RECEPTIONIST,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_role"}),
        help_text="Select your operational role in the clinic.",
    )

    # Doctor-specific credentials (required when role is DOCTOR)
    department = forms.ModelChoiceField(
        queryset=None,  # Dynamically populated in __init__
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Assigned clinical department.",
    )
    specialization = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. General Medicine, Cardiology"}
        ),
        help_text="Primary clinical specialty.",
    )
    qualification = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. MBBS, MD (Medicine)"}
        ),
        help_text="Medical degree and qualifications.",
    )
    contact_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "e.g. +91 98765 43210"}
        ),
        help_text="Direct clinical contact number.",
    )

    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Create password", "autocomplete": "new-password"}
        ),
        help_text="Must meet standard security requirements.",
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Confirm password", "autocomplete": "new-password"}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from departments.models import Department

        self.fields["department"].queryset = Department.objects.filter(is_active=True).order_by("name")

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if not username:
            raise ValidationError("Username is required.")
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(f"A user with username '{username}' already exists. Please choose another.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if not email:
            raise ValidationError("Email address is required.")
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(f"A user with email '{email}' already exists. Please sign in or use another email.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        role = cleaned_data.get("role")

        if password and password_confirm:
            if password != password_confirm:
                self.add_error("password_confirm", "Passwords do not match.")
            else:
                from django.contrib.auth.password_validation import validate_password

                try:
                    validate_password(password)
                except ValidationError as e:
                    self.add_error("password", e)

        # Enforce Doctor Profile validation if DOCTOR role selected
        if role == User.Role.DOCTOR:
            if not cleaned_data.get("department"):
                self.add_error("department", "Clinical Department is required for Doctor accounts.")
            if not cleaned_data.get("specialization"):
                self.add_error("specialization", "Specialization is required for Doctor accounts.")
            if not cleaned_data.get("qualification"):
                self.add_error("qualification", "Medical Qualification is required for Doctor accounts.")

        return cleaned_data

    def save(self):
        from django.db import transaction
        from departments.models import DoctorProfile

        data = self.cleaned_data
        role = data["role"]

        with transaction.atomic():
            user = User.objects.create_user(
                username=data["username"],
                email=data["email"],
                first_name=data["first_name"],
                last_name=data["last_name"],
                password=data["password"],
                role=role,
                is_staff=(role == User.Role.ADMIN),
                is_active=True,
            )

            if role == User.Role.DOCTOR:
                DoctorProfile.objects.create(
                    user=user,
                    department=data["department"],
                    specialization=data["specialization"],
                    qualification=data["qualification"],
                    contact_number=data.get("contact_number", ""),
                    is_active=True,
                )

        return user
