"""
Prescriptions and Medication Management Views (Step 10C).
Provides doctor prescription builder, inline medicine items editing,
and formal issuing with audit logging and medical-legal protections.
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
from consultations.models import Consultation
from departments.models import DoctorProfile
from .forms import PrescriptionForm, PrescriptionItemFormSet
from .models import Prescription, PrescriptionItem


def get_doctor_profile_or_403(user):
    """
    Resolves the active DoctorProfile for the logged-in doctor.
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
def prescription_builder_view(request, consultation_id):
    """
    Physician prescription builder supporting multiple medication items via formset.
    """
    doctor_profile = get_doctor_profile_or_403(request.user)
    consultation = get_object_or_404(
        Consultation.objects.select_related(
            "patient", "doctor", "doctor__user", "doctor__department", "appointment"
        ),
        pk=consultation_id,
    )

    # Ownership check: Doctor must be the attending physician on the consultation
    if getattr(request.user, "role", None) == "DOCTOR":
        if doctor_profile and consultation.doctor_id != doctor_profile.id:
            raise PermissionDenied("You are not authorized to build prescriptions for another physician's consultation.")

    # Retrieve existing or initialize draft Prescription
    prescription = getattr(consultation, "prescription", None)
    if not prescription:
        with transaction.atomic():
            prescription = Prescription.objects.create(
                consultation=consultation,
                status=Prescription.Status.DRAFT,
            )

    is_issued = prescription.status == Prescription.Status.ISSUED

    if request.method == "POST":
        action = request.POST.get("action", "save_draft")
        form = PrescriptionForm(request.POST, instance=prescription)
        formset = PrescriptionItemFormSet(request.POST, instance=prescription)

        if action == "issue":
            # Strict rule: Consultation must be finalized first
            if consultation.status != Consultation.Status.FINALIZED:
                messages.error(
                    request,
                    "A prescription cannot be issued for a consultation in DRAFT status. "
                    "Please finalize the clinical consultation first before issuing medication orders.",
                )
            else:
                form_valid = form.is_valid()
                formset_valid = formset.is_valid()
                if form_valid and formset_valid:
                    try:
                        with transaction.atomic():
                            prescription = form.save()
                            formset.save()

                            # Officially issue with role authorization check and audit event
                            prescription.issue(issued_by=request.user)

                            # Complete linked appointment if present
                            if consultation.appointment_id:
                                apt = consultation.appointment
                                if apt.status in [
                                    Appointment.Status.SCHEDULED,
                                    Appointment.Status.CONFIRMED,
                                    Appointment.Status.IN_PROGRESS,
                                ]:
                                    apt.complete()
                                    apt.save()

                        messages.success(
                            request,
                            f"Prescription {prescription.prescription_number} issued officially. "
                            f"Medication orders are now locked.",
                        )
                        return redirect("prescriptions:detail", pk=prescription.pk)
                    except ValidationError as e:
                        messages.error(request, f"Prescription issuing error: {e}")
                else:
                    messages.error(request, "Please correct the errors in the prescription items below.")
        else:
            # Save Draft
            if form.is_valid() and formset.is_valid():
                try:
                    with transaction.atomic():
                        form.save()
                        formset.save()
                    messages.success(request, f"Prescription draft {prescription.prescription_number} saved.")
                    return redirect("prescriptions:create", consultation_id=consultation.pk)
                except ValidationError as e:
                    messages.error(request, f"Validation error: {e}")
            else:
                messages.error(request, "Please correct the errors in the prescription items below.")
    else:
        form = PrescriptionForm(instance=prescription)
        formset = PrescriptionItemFormSet(instance=prescription)

    context = {
        "prescription": prescription,
        "consultation": consultation,
        "patient": consultation.patient,
        "doctor": consultation.doctor,
        "form": form,
        "formset": formset,
        "is_issued": is_issued,
        "items": prescription.items.all(),
    }
    return render(request, "prescriptions/prescription_form.html", context)


@role_required("DOCTOR", "ADMIN")
def prescription_list_view(request):
    """
    Directory of issued and draft prescriptions for the logged-in doctor.
    """
    doctor_profile = get_doctor_profile_or_403(request.user)

    queryset = Prescription.objects.select_related(
        "consultation",
        "consultation__patient",
        "consultation__doctor",
        "consultation__doctor__user",
    ).prefetch_related("items")

    if doctor_profile:
        queryset = queryset.filter(consultation__doctor=doctor_profile)

    # Status Filter
    status_filter = request.GET.get("status", "")
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    # Search Query
    q = request.GET.get("q", "").strip()
    if q:
        name_parts = q.split()
        if len(name_parts) >= 2:
            name_q = (
                Q(consultation__patient__first_name__icontains=name_parts[0], consultation__patient__last_name__icontains=name_parts[1])
                | Q(consultation__patient__first_name__icontains=name_parts[1], consultation__patient__last_name__icontains=name_parts[0])
            )
        else:
            name_q = Q(consultation__patient__first_name__icontains=q) | Q(consultation__patient__last_name__icontains=q)

        queryset = queryset.filter(
            Q(prescription_number__icontains=q)
            | Q(consultation__patient__patient_id__icontains=q)
            | name_q
        )

    # Pagination
    paginator = Paginator(queryset.order_by("-prescription_date", "-created_at"), 10)
    page = request.GET.get("page", 1)
    try:
        prescriptions_page = paginator.page(page)
    except PageNotAnInteger:
        prescriptions_page = paginator.page(1)
    except EmptyPage:
        prescriptions_page = paginator.page(paginator.num_pages)

    context = {
        "prescriptions": prescriptions_page,
        "status_filter": status_filter,
        "q": q,
        "status_choices": Prescription.Status.choices,
        "total_count": paginator.count,
    }
    return render(request, "prescriptions/prescription_list.html", context)


@role_required("DOCTOR", "ADMIN")
def prescription_detail_view(request, pk):
    """
    Official clinical printable prescription view.
    """
    doctor_profile = get_doctor_profile_or_403(request.user)
    prescription = get_object_or_404(
        Prescription.objects.select_related(
            "consultation",
            "consultation__patient",
            "consultation__doctor",
            "consultation__doctor__user",
            "consultation__doctor__department",
        ).prefetch_related("items"),
        pk=pk,
    )

    if getattr(request.user, "role", None) == "DOCTOR":
        if doctor_profile and prescription.doctor.pk != doctor_profile.pk:
            raise PermissionDenied("You are not authorized to view another physician's prescription.")

    context = {
        "prescription": prescription,
        "consultation": prescription.consultation,
        "patient": prescription.patient,
        "doctor": prescription.doctor,
        "items": prescription.items.all(),
    }
    return render(request, "prescriptions/prescription_detail.html", context)
