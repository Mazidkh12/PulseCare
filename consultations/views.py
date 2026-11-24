"""
Clinical Consultation and Case-Taking Views (Step 10C).
Provides doctor-facing clinical documentation, vital signs tracking, diagnosis management,
and consultation finalization with medical-legal protections.
"""
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from appointments.models import Appointment
from audit.models import AuditLog
from audit.services import log_audit_event
from departments.models import DoctorProfile
from patients.models import Patient
from .forms import ConsultationForm, DiagnosisForm, VitalSignForm, WalkInConsultationForm
from .models import Consultation, Diagnosis, VitalSign


def get_doctor_profile_or_403(user):
    """
    Resolves active DoctorProfile for the logged-in doctor.
    Raises PermissionDenied if the user lacks an active doctor profile.
    """
    if getattr(user, "role", None) == "DOCTOR":
        profile = DoctorProfile.objects.filter(user=user, is_active=True).first()
        if not profile:
            raise PermissionDenied("Active Doctor Profile not found for this user account.")
        return profile
    elif getattr(user, "role", None) == "ADMIN" or user.is_superuser:
        profile = DoctorProfile.objects.filter(user=user, is_active=True).first()
        return profile
    raise PermissionDenied("Access restricted to medical doctors and administrators.")


@role_required("DOCTOR", "ADMIN")
def consultation_create_view(request):
    """
    Initiates a new unscheduled walk-in consultation without an appointment.
    """
    doctor_profile = get_doctor_profile_or_403(request.user)

    if request.method == "POST":
        form = WalkInConsultationForm(request.POST, doctor=doctor_profile)
        if form.is_valid():
            with transaction.atomic():
                consultation = form.save(commit=False)
                consultation.doctor = doctor_profile
                consultation.status = Consultation.Status.DRAFT
                consultation.save()

                try:
                    log_audit_event(
                        actor=request.user,
                        action=AuditLog.Action.CREATE,
                        obj=consultation,
                        object_label=f"Walk-in Consultation {consultation.pk} for {consultation.patient.get_full_name()}",
                        metadata={"consultation_id": consultation.pk, "type": "walk_in"},
                    )
                except Exception:
                    pass

            messages.success(
                request,
                f"Walk-in consultation opened for {consultation.patient.get_full_name()} ({consultation.patient.patient_id}).",
            )
            return redirect("consultations:edit", pk=consultation.pk)
    else:
        initial_data = {}
        patient_id_param = request.GET.get("patient_id")
        if patient_id_param:
            pat = Patient.objects.filter(pk=patient_id_param, is_active=True).first()
            if pat:
                initial_data["patient"] = pat
        form = WalkInConsultationForm(initial=initial_data)

    return render(
        request,
        "consultations/consultation_create.html",
        {"form": form, "doctor": doctor_profile},
    )


@role_required("DOCTOR", "ADMIN")
def consultation_edit_view(request, pk):
    """
    Doctor-facing clinical case-taking, vitals recording, and diagnosis management interface.
    """
    doctor_profile = get_doctor_profile_or_403(request.user)
    consultation = get_object_or_404(
        Consultation.objects.select_related(
            "patient", "doctor", "doctor__user", "doctor__department", "appointment"
        ).prefetch_related("diagnoses", "vitals"),
        pk=pk,
    )

    # Ownership enforcement: A doctor can only access consultations assigned to them
    if getattr(request.user, "role", None) == "DOCTOR":
        if doctor_profile and consultation.doctor_id != doctor_profile.id:
            raise PermissionDenied("You are not authorized to access consultations assigned to another physician.")

    vitals_instance = getattr(consultation, "vitals", None)
    consultation_form = ConsultationForm(instance=consultation)
    vitals_form = VitalSignForm(instance=vitals_instance)
    diagnosis_form = DiagnosisForm(consultation=consultation)

    if request.method == "POST":
        action = request.POST.get("action", "save_draft")

        # 1. Action: Add Diagnosis
        if action == "add_diagnosis":
            diag_form = DiagnosisForm(request.POST, consultation=consultation)
            if diag_form.is_valid():
                diagnosis = diag_form.save(commit=False)
                diagnosis.consultation = consultation
                diagnosis.recorded_by = request.user
                try:
                    diagnosis.save()
                    messages.success(request, f"{diagnosis.get_diagnosis_type_display()} Diagnosis '{diagnosis.diagnosis_name}' added.")
                except ValidationError as e:
                    messages.error(request, f"Diagnosis validation error: {e}")
                return redirect("consultations:edit", pk=consultation.pk)
            else:
                diagnosis_form = diag_form
                messages.error(request, "Failed to add diagnosis. Please verify required fields.")

        # 2. Action: Delete Diagnosis
        elif action == "delete_diagnosis":
            diag_id = request.POST.get("diagnosis_id")
            diag_obj = get_object_or_404(Diagnosis, pk=diag_id, consultation=consultation)
            diag_name = diag_obj.diagnosis_name
            diag_obj.delete()
            messages.info(request, f"Diagnosis '{diag_name}' removed.")
            return redirect("consultations:edit", pk=consultation.pk)

        # 3. Action: Save Case-Taking Details, Vitals, and optionally Finalize
        else:
            consultation_form = ConsultationForm(request.POST, instance=consultation)
            vitals_form = VitalSignForm(request.POST, instance=vitals_instance)

            # Check vitals fields: only validate vitals_form if any vitals field was filled
            vitals_data_present = any(
                request.POST.get(field)
                for field in [
                    "systolic_bp",
                    "diastolic_bp",
                    "pulse_rate",
                    "respiratory_rate",
                    "temperature",
                    "spo2",
                    "height",
                    "weight",
                ]
            )

            consultation_valid = consultation_form.is_valid()
            vitals_valid = vitals_form.is_valid() if vitals_data_present else True

            if consultation_valid and vitals_valid:
                try:
                    with transaction.atomic():
                        consultation = consultation_form.save()

                        # Save vitals if entered
                        if vitals_data_present:
                            vitals = vitals_form.save(commit=False)
                            vitals.consultation = consultation
                            vitals.save()

                        # Finalize consultation if requested
                        if action == "finalize":
                            consultation.finalize(finalized_by=request.user)
                            messages.success(
                                request,
                                f"Consultation {consultation.pk} finalized successfully. You can now build the prescription.",
                            )
                            return redirect("prescriptions:create", consultation_id=consultation.pk)

                        messages.success(request, "Consultation record saved successfully.")
                        return redirect("consultations:edit", pk=consultation.pk)
                except ValidationError as e:
                    messages.error(request, f"Clinical validation error: {e}")
            else:
                messages.error(request, "Please correct the errors indicated below.")
    else:
        consultation_form = ConsultationForm(instance=consultation)
        vitals_form = VitalSignForm(instance=vitals_instance)

    diagnosis_form = DiagnosisForm(consultation=consultation)
    diagnoses = consultation.diagnoses.all().order_by("diagnosis_type", "-recorded_at")

    # Patient clinical banner details
    patient = consultation.patient
    allergies = patient.allergies.all().order_by("-severity")
    medical_histories = patient.medical_histories.all().order_by("-diagnosed_date")

    context = {
        "consultation": consultation,
        "consultation_form": consultation_form,
        "vitals_form": vitals_form,
        "vitals_instance": vitals_instance,
        "diagnosis_form": diagnosis_form,
        "diagnoses": diagnoses,
        "patient": patient,
        "allergies": allergies,
        "medical_histories": medical_histories,
        "is_finalized": consultation.status == Consultation.Status.FINALIZED,
    }
    return render(request, "consultations/consultation_form.html", context)


@role_required("DOCTOR", "ADMIN")
def consultation_finalize_view(request, pk):
    """
    Dedicated endpoint to finalize a consultation record.
    """
    doctor_profile = get_doctor_profile_or_403(request.user)
    consultation = get_object_or_404(Consultation, pk=pk)

    if getattr(request.user, "role", None) == "DOCTOR":
        if doctor_profile and consultation.doctor_id != doctor_profile.id:
            raise PermissionDenied("You are not authorized to finalize another physician's consultation.")

    if request.method == "POST":
        consultation.finalize(finalized_by=request.user)
        messages.success(request, f"Consultation {consultation.pk} finalized successfully.")
        return redirect("prescriptions:create", consultation_id=consultation.pk)

    return redirect("consultations:edit", pk=consultation.pk)


@role_required("DOCTOR", "ADMIN")
def consultation_list_view(request):
    """
    Directory of clinical consultations conducted by the treating doctor.
    """
    doctor_profile = get_doctor_profile_or_403(request.user)

    queryset = Consultation.objects.select_related(
        "patient", "doctor", "doctor__user", "appointment"
    ).prefetch_related("diagnoses", "prescription")

    if doctor_profile:
        queryset = queryset.filter(doctor=doctor_profile)

    # Status filter
    status_filter = request.GET.get("status", "")
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    # Search query
    q = request.GET.get("q", "").strip()
    if q:
        name_parts = q.split()
        if len(name_parts) >= 2:
            name_q = (
                Q(patient__first_name__icontains=name_parts[0], patient__last_name__icontains=name_parts[1])
                | Q(patient__first_name__icontains=name_parts[1], patient__last_name__icontains=name_parts[0])
            )
        else:
            name_q = Q(patient__first_name__icontains=q) | Q(patient__last_name__icontains=q)

        queryset = queryset.filter(Q(patient__patient_id__icontains=q) | name_q)

    # Pagination
    paginator = Paginator(queryset.order_by("-consultation_date", "-created_at"), 10)
    page = request.GET.get("page", 1)
    try:
        consultations_page = paginator.page(page)
    except PageNotAnInteger:
        consultations_page = paginator.page(1)
    except EmptyPage:
        consultations_page = paginator.page(paginator.num_pages)

    context = {
        "consultations": consultations_page,
        "status_filter": status_filter,
        "q": q,
        "status_choices": Consultation.Status.choices,
        "total_count": paginator.count,
    }
    return render(request, "consultations/consultation_list.html", context)


@role_required("DOCTOR", "ADMIN")
def consultation_detail_view(request, pk):
    """
    Clinical review summary for a consultation (vitals, case-taking, diagnoses, and prescription).
    """
    doctor_profile = get_doctor_profile_or_403(request.user)
    consultation = get_object_or_404(
        Consultation.objects.select_related(
            "patient", "doctor", "doctor__user", "doctor__department", "appointment"
        ).prefetch_related("diagnoses", "vitals", "prescription", "prescription__items"),
        pk=pk,
    )

    if getattr(request.user, "role", None) == "DOCTOR":
        if doctor_profile and consultation.doctor_id != doctor_profile.id:
            raise PermissionDenied("You are not authorized to view another physician's consultation details.")

    context = {
        "consultation": consultation,
        "patient": consultation.patient,
        "vitals": getattr(consultation, "vitals", None),
        "diagnoses": consultation.diagnoses.all().order_by("diagnosis_type", "-recorded_at"),
        "prescription": getattr(consultation, "prescription", None),
    }
    return render(request, "consultations/consultation_detail.html", context)
