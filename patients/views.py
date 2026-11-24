"""
Receptionist Patient Management Views (Step 10B).
Includes Patient Registration, Searchable Directory with Pagination, and Patient Details.
"""
from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from audit.models import AuditLog
from audit.services import log_audit_event
from .forms import PatientRegistrationForm
from .models import Patient


@role_required("RECEPTIONIST", "ADMIN")
def patient_register_view(request):
    """
    Handles new patient registration and automated MRN assignment.
    """
    if request.method == "POST":
        form = PatientRegistrationForm(request.POST)
        if form.is_valid():
            patient = form.save()

            # Record audit event
            try:
                log_audit_event(
                    actor=request.user,
                    action=AuditLog.Action.CREATE,
                    obj=patient,
                    object_label=f"Registered Patient {patient.patient_id} ({patient.get_full_name()})",
                    metadata={
                        "patient_id": patient.patient_id,
                        "name": patient.get_full_name(),
                        "contact_number": patient.contact_number,
                    },
                )
            except Exception:
                pass

            messages.success(
                request,
                f"Patient '{patient.get_full_name()}' registered successfully! "
                f"Assigned MRN: {patient.patient_id}",
            )
            return redirect("patients:detail", pk=patient.pk)
    else:
        form = PatientRegistrationForm()

    return render(request, "patients/patient_form.html", {"form": form})


@role_required("RECEPTIONIST", "ADMIN")
def patient_list_view(request):
    """
    Searchable, filterable patient directory view with pagination.
    """
    queryset = Patient.objects.all().order_by("-created_at")

    # 1. Search Query
    q = request.GET.get("q", "").strip()
    if q:
        # Multi-field search supporting MRN, name, phone, and combined full names
        name_parts = q.split()
        if len(name_parts) >= 2:
            name_q = (
                Q(first_name__icontains=name_parts[0], last_name__icontains=name_parts[1])
                | Q(first_name__icontains=name_parts[1], last_name__icontains=name_parts[0])
            )
        else:
            name_q = Q(first_name__icontains=q) | Q(last_name__icontains=q)

        queryset = queryset.filter(
            Q(patient_id__icontains=q)
            | Q(contact_number__icontains=q)
            | name_q
        )

    # 2. Status Filter
    status_filter = request.GET.get("status", "all")
    if status_filter == "active":
        queryset = queryset.filter(is_active=True)
    elif status_filter == "inactive":
        queryset = queryset.filter(is_active=False)

    # 3. Gender Filter
    gender_filter = request.GET.get("gender", "")
    if gender_filter:
        queryset = queryset.filter(gender=gender_filter)

    # 4. Pagination (10 records per page)
    paginator = Paginator(queryset, 10)
    page = request.GET.get("page", 1)
    try:
        patients_page = paginator.page(page)
    except PageNotAnInteger:
        patients_page = paginator.page(1)
    except EmptyPage:
        patients_page = paginator.page(paginator.num_pages)

    context = {
        "patients": patients_page,
        "q": q,
        "status_filter": status_filter,
        "gender_filter": gender_filter,
        "total_count": paginator.count,
    }
    return render(request, "patients/patient_list.html", context)


@role_required("RECEPTIONIST", "ADMIN")
def patient_detail_view(request, pk):
    """
    Receptionist patient profile view. Displays personal, contact, emergency details,
    and appointment history. Does NOT expose clinical notes, diagnoses, or prescriptions.
    """
    patient = get_object_or_404(Patient, pk=pk)

    # Non-sensitive appointment history
    appointments = (
        patient.appointments.select_related("doctor", "doctor__user", "doctor__department")
        .order_by("-appointment_date", "-start_time")
    )

    context = {
        "patient": patient,
        "appointments": appointments,
    }
    return render(request, "patients/patient_detail.html", context)


# ==============================================================================
# DOCTOR PATIENT MEDICAL HISTORY & SEARCH (Step 10C)
# ==============================================================================

@role_required("DOCTOR", "ADMIN")
def doctor_patient_search_view(request):
    """
    Search view for attending physicians to lookup patients and view full clinical timelines.
    """
    queryset = Patient.objects.filter(is_active=True).order_by("first_name", "last_name")

    q = request.GET.get("q", "").strip()
    if q:
        name_parts = q.split()
        if len(name_parts) >= 2:
            name_q = (
                Q(first_name__icontains=name_parts[0], last_name__icontains=name_parts[1])
                | Q(first_name__icontains=name_parts[1], last_name__icontains=name_parts[0])
            )
        else:
            name_q = Q(first_name__icontains=q) | Q(last_name__icontains=q)

        queryset = queryset.filter(
            Q(patient_id__icontains=q)
            | Q(contact_number__icontains=q)
            | name_q
        )

    paginator = Paginator(queryset, 10)
    page = request.GET.get("page", 1)
    try:
        patients_page = paginator.page(page)
    except PageNotAnInteger:
        patients_page = paginator.page(1)
    except EmptyPage:
        patients_page = paginator.page(paginator.num_pages)

    context = {
        "patients": patients_page,
        "q": q,
        "total_count": paginator.count,
    }
    return render(request, "patients/doctor_patient_search.html", context)


@role_required("DOCTOR", "ADMIN")
def doctor_patient_history_view(request, pk):
    """
    Doctor-facing comprehensive clinical timeline view.
    Retrieves chronological medical histories, recorded allergies, consultations,
    diagnoses, vital signs, and issued prescriptions via the patient timeline service.
    """
    patient = get_object_or_404(Patient, pk=pk)
    from consultations.services import get_patient_timeline

    timeline_data = get_patient_timeline(patient)

    context = {
        "patient": patient,
        "timeline": timeline_data,
        "medical_histories": timeline_data["medical_histories"],
        "allergies": timeline_data["allergies"],
        "consultations": timeline_data["consultations"],
    }
    return render(request, "patients/doctor_patient_history.html", context)
