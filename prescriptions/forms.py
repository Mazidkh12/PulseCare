from django import forms
from django.forms import inlineformset_factory
from .models import Prescription, PrescriptionItem


class PrescriptionForm(forms.ModelForm):
    """
    Form for prescription header metadata, instructions, and amendment documentation.
    """

    class Meta:
        model = Prescription
        fields = ["general_instructions", "amendment_notes"]
        widgets = {
            "general_instructions": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Dietary recommendations, hydration, activity restrictions, general precautions",
                }
            ),
            "amendment_notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Document clinical justification if amending an already issued prescription",
                }
            ),
        }


class PrescriptionItemForm(forms.ModelForm):
    """
    Individual medication item form.
    """

    class Meta:
        model = PrescriptionItem
        fields = [
            "medicine_name",
            "dosage_form",
            "strength",
            "dosage",
            "frequency",
            "duration",
            "intake_timing",
            "special_instructions",
        ]
        widgets = {
            "medicine_name": forms.TextInput(
                attrs={"class": "form-control form-control-sm", "placeholder": "e.g. Paracetamol", "required": "required"}
            ),
            "dosage_form": forms.Select(
                attrs={"class": "form-select form-select-sm"}
            ),
            "strength": forms.TextInput(
                attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 500 mg"}
            ),
            "dosage": forms.TextInput(
                attrs={"class": "form-control form-control-sm", "placeholder": "e.g. 1 tablet", "required": "required"}
            ),
            "frequency": forms.TextInput(
                attrs={"class": "form-control form-control-sm", "placeholder": "e.g. TID / 1-0-1", "required": "required"}
            ),
            "duration": forms.NumberInput(
                attrs={"class": "form-control form-control-sm", "placeholder": "Days", "min": 1, "required": "required"}
            ),
            "intake_timing": forms.Select(
                attrs={"class": "form-select form-select-sm"}
            ),
            "special_instructions": forms.TextInput(
                attrs={"class": "form-control form-control-sm", "placeholder": "Optional special advice"}
            ),
        }


# Formset supporting dynamic multiple medicine items
PrescriptionItemFormSet = inlineformset_factory(
    Prescription,
    PrescriptionItem,
    form=PrescriptionItemForm,
    extra=1,
    can_delete=True,
)
