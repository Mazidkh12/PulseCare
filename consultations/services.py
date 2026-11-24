"""
Patient Medical History and Timeline Service (Step 8).

Provides reusable, efficient query logic to retrieve the complete clinical
timeline for a given patient, ordered newest-first.
"""
from patients.models import Patient
from .models import Consultation


def get_patient_timeline(patient: Patient) -> dict:
    """
    Returns a structured dictionary representing the full clinical timeline
    for the given patient.

    Includes:
    - Patient registration details
    - Medical history entries
    - Recorded allergies
    - All consultations (appointment-based and walk-in)
    - Diagnoses per consultation
    - Prescriptions and prescription items per consultation
    - Vital signs per consultation
    - Linked appointment date/status where available

    All records are ordered newest-first.
    Performance: select_related and prefetch_related are used to minimise
    database round-trips for patients with many historical records.
    """
    consultations = (
        Consultation.objects.filter(patient=patient)
        .select_related(
            "doctor",
            "doctor__user",
            "doctor__department",
            "appointment",
        )
        .prefetch_related(
            "diagnoses",
            "diagnoses__recorded_by",
            "vitals",
            "prescription",
            "prescription__items",
        )
        .order_by("-consultation_date", "-created_at")
    )

    medical_histories = patient.medical_histories.order_by(
        "-diagnosed_date", "-created_at"
    )
    allergies = patient.allergies.order_by("-severity", "-created_at")

    return {
        "patient": patient,
        "medical_histories": list(medical_histories),
        "allergies": list(allergies),
        "consultations": list(consultations),
    }
