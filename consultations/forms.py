from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from patients.models import Patient
from .models import Consultation, Diagnosis, VitalSign


class ConsultationForm(forms.ModelForm):
    """
    Clinical case-taking and consultation documentation form.
    Provides structured clinical documentation with Bootstrap 5 inputs.
    """

    class Meta:
        model = Consultation
        fields = [
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
            "amendment_notes",
        ]
        widgets = {
            "chief_complaint": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Primary symptoms or reason for visit reported by patient"}
            ),
            "history_of_present_illness": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Chronological progression of symptoms, onset, character, severity, triggers"}
            ),
            "past_medical_history": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Previous major illnesses, chronic conditions, hospitalizations"}
            ),
            "past_surgical_history": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Surgical procedures, operations, approximate dates"}
            ),
            "family_history": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Familial health conditions, hereditary diseases"}
            ),
            "personal_history": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Diet, lifestyle, smoking, alcohol, sleep patterns"}
            ),
            "current_medications": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Current medications, dosage, compliance"}
            ),
            "allergy_notes": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Drug intolerances, adverse reactions noted during this visit"}
            ),
            "physical_examination": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "General and systemic physical examination findings"}
            ),
            "clinical_assessment": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Physician clinical synthesis, case analysis, problem list"}
            ),
            "provisional_diagnosis": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Working clinical impression / differential diagnosis"}
            ),
            "treatment_plan": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Investigations ordered, therapy, advice, lifestyle recommendations"}
            ),
            "follow_up_notes": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Follow-up instructions, warning signs, emergency triggers"}
            ),
            "follow_up_date": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "amendment_notes": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Document clinical justification if modifying a finalized record"}
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        # If modifying a finalized consultation without changing amendment notes,
        # model clean() handles the medical-legal validation
        return cleaned_data


class VitalSignForm(forms.ModelForm):
    """
    Vital signs recording form. BMI is non-editable and auto-calculated from height and weight.
    """

    class Meta:
        model = VitalSign
        fields = [
            "systolic_bp",
            "diastolic_bp",
            "pulse_rate",
            "respiratory_rate",
            "temperature",
            "spo2",
            "height",
            "weight",
        ]
        widgets = {
            "systolic_bp": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "e.g. 120", "min": 40, "max": 300}
            ),
            "diastolic_bp": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "e.g. 80", "min": 30, "max": 200}
            ),
            "pulse_rate": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "e.g. 72", "min": 20, "max": 300}
            ),
            "respiratory_rate": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "e.g. 16", "min": 4, "max": 80}
            ),
            "temperature": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "e.g. 37.0", "step": "0.1", "min": 25, "max": 45}
            ),
            "spo2": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "e.g. 98.0", "step": "0.1", "min": 0, "max": 100}
            ),
            "height": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "e.g. 175.0", "step": "0.1", "id": "id_height"}
            ),
            "weight": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "e.g. 70.00", "step": "0.01", "id": "id_weight"}
            ),
        }


class DiagnosisForm(forms.ModelForm):
    """
    Form for documenting structured primary or secondary clinical diagnoses.
    """

    class Meta:
        model = Diagnosis
        fields = ["diagnosis_name", "diagnosis_code", "diagnosis_type", "description"]
        widgets = {
            "diagnosis_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. Essential Hypertension"}
            ),
            "diagnosis_code": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. ICD-10: I10"}
            ),
            "diagnosis_type": forms.Select(
                attrs={"class": "form-select"}
            ),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Optional clinical notes or differential reasoning"}
            ),
        }

    def __init__(self, *args, consultation=None, **kwargs):
        super().__init__(*args, **kwargs)
        if consultation:
            self.instance.consultation = consultation


class WalkInConsultationForm(forms.ModelForm):
    """
    Intake form for unscheduled walk-in patient consultations.
    """

    patient = forms.ModelChoiceField(
        queryset=Patient.objects.filter(is_active=True).order_by("first_name", "last_name"),
        empty_label="-- Select Active Registered Patient --",
        widget=forms.Select(attrs={"class": "form-select", "id": "id_walkin_patient"}),
        help_text="Select an active registered patient for walk-in triage.",
    )

    class Meta:
        model = Consultation
        fields = ["patient", "chief_complaint"]
        widgets = {
            "chief_complaint": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Presenting symptoms or reason for walk-in consultation"}
            ),
        }

    def __init__(self, *args, doctor=None, **kwargs):
        super().__init__(*args, **kwargs)
        if doctor:
            self.instance.doctor = doctor
