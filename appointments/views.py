"""
Receptionist Appointment Management Views (Step 10B).
Includes Appointment Booking, Filterable Directory with Pagination, and Cancellation.
"""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from audit.models import AuditLog
from audit.services import log_audit_event
from departments.models import Department, DoctorProfile
from patients.models import Patient
from .forms import AppointmentBookingForm
from .models import Appointment


@role_required("RECEPTIONIST", "ADMIN")
def appointment_book_view(request):
    """
    Handles scheduling of new outpatient appointments with concurrency protection.
    """
    initial_data = {}
    patient_id_param = request.GET.get("patient_id")
    if patient_id_param:
        patient_obj = Patient.objects.filter(pk=patient_id_param, is_active=True).first()
        if patient_obj:
            initial_data["patient"] = patient_obj

    if request.method == "POST":
        form = AppointmentBookingForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                appointment = form.save()

                # Audit event
                try:
                    pat_name = appointment.patient.get_full_name()
                    doc_name = appointment.doctor.user.get_full_name().strip() or appointment.doctor.user.username
                    log_audit_event(
                        actor=request.user,
                        action=AuditLog.Action.CREATE,
                        obj=appointment,
                        object_label=f"Booked Appointment {appointment.pk} for {pat_name} with Dr. {doc_name}",
                        metadata={
                            "appointment_id": appointment.pk,
                            "patient_mrn": appointment.patient.patient_id,
                            "date": str(appointment.appointment_date),
                            "slot": f"{appointment.start_time.strftime('%H:%M')} - {appointment.end_time.strftime('%H:%M')}",
                        },
                    )
                except Exception:
                    pass

            doc_display = appointment.doctor.user.get_full_name().strip() or appointment.doctor.user.username
            messages.success(
                request,
                f"Appointment booked successfully for {appointment.patient.get_full_name()} "
                f"({appointment.patient.patient_id}) with Dr. {doc_display} on "
                f"{appointment.appointment_date} ({appointment.start_time.strftime('%H:%M')} - {appointment.end_time.strftime('%H:%M')}).",
            )
            return redirect("appointments:list")
    else:
        form = AppointmentBookingForm(initial=initial_data)

    # Pass doctors with department IDs for dependent client-side filtering
    active_doctors = (
        DoctorProfile.objects.select_related("user", "department")
        .filter(is_active=True, department__is_active=True)
        .order_by("user__first_name", "user__last_name")
    )

    return render(
        request,
        "appointments/appointment_form.html",
        {
            "form": form,
            "active_doctors": active_doctors,
        },
    )


@role_required("RECEPTIONIST", "ADMIN")
def appointment_list_view(request):
    """
    Searchable, filterable appointment directory view with pagination.
    """
    queryset = Appointment.objects.select_related(
        "patient", "doctor", "doctor__user", "doctor__department"
    ).order_by("-appointment_date", "-start_time")

    # 1. Search Query (Patient MRN, First Name, Last Name)
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

        queryset = queryset.filter(
            Q(patient__patient_id__icontains=q) | name_q
        )

    # 2. Date Filter
    date_filter = request.GET.get("date", "").strip()
    if date_filter:
        try:
            queryset = queryset.filter(appointment_date=date_filter)
        except Exception:
            pass

    # 3. Status Filter
    status_filter = request.GET.get("status", "")
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    # 4. Department Filter
    department_filter = request.GET.get("department", "")
    if department_filter:
        queryset = queryset.filter(doctor__department_id=department_filter)

    # 5. Doctor Filter
    doctor_filter = request.GET.get("doctor", "")
    if doctor_filter:
        queryset = queryset.filter(doctor_id=doctor_filter)

    # 6. Pagination (10 appointments per page)
    paginator = Paginator(queryset, 10)
    page = request.GET.get("page", 1)
    try:
        appointments_page = paginator.page(page)
    except PageNotAnInteger:
        appointments_page = paginator.page(1)
    except EmptyPage:
        appointments_page = paginator.page(paginator.num_pages)

    departments = Department.objects.filter(is_active=True).order_by("name")
    doctors = (
        DoctorProfile.objects.select_related("user")
        .filter(is_active=True)
        .order_by("user__first_name")
    )

    context = {
        "appointments": appointments_page,
        "q": q,
        "date_filter": date_filter,
        "status_filter": status_filter,
        "department_filter": department_filter,
        "doctor_filter": doctor_filter,
        "departments": departments,
        "doctors": doctors,
        "status_choices": Appointment.Status.choices,
        "total_count": paginator.count,
    }
    return render(request, "appointments/appointment_list.html", context)


@role_required("RECEPTIONIST", "ADMIN")
def appointment_cancel_view(request, pk):
    """
    Cancels a scheduled appointment using the validated cancellation workflow and audit log.
    """
    appointment = get_object_or_404(Appointment, pk=pk)

    if request.method == "POST":
        if appointment.status in [Appointment.Status.COMPLETED, Appointment.Status.CANCELLED]:
            messages.warning(
                request,
                f"Appointment {appointment.pk} is already marked as {appointment.get_status_display()} and cannot be cancelled.",
            )
        else:
            appointment.cancel(cancelled_by=request.user)
            messages.success(
                request,
                f"Appointment {appointment.pk} for {appointment.patient.get_full_name()} cancelled successfully.",
            )

    return redirect("appointments:list")


# ==============================================================================
# DOCTOR PORTAL APPOINTMENT QUEUE & STATUS WORKFLOWS (Step 10C)
# ==============================================================================

def get_doctor_profile_or_403(user):
    """
    Resolves the active DoctorProfile for the authenticated DOCTOR or ADMIN user.
    Strictly denies access if the DOCTOR account lacks an active profile.
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
def doctor_queue_view(request):
    """
    Outpatient appointment queue view scoped exclusively to the logged-in doctor.
    Supports tabbed views (today, upcoming, previous), search by patient, and status filters.
    """
    doctor_profile = get_doctor_profile_or_403(request.user)
    today = timezone.localdate()

    queryset = Appointment.objects.select_related(
        "patient", "doctor", "doctor__user", "doctor__department", "consultation"
    )

    if doctor_profile:
        queryset = queryset.filter(doctor=doctor_profile)

    # 1. Tab / Date Presets
    active_tab = request.GET.get("filter", "today")
    if active_tab == "today":
        queryset = queryset.filter(appointment_date=today).order_by("start_time")
    elif active_tab == "upcoming":
        queryset = queryset.filter(appointment_date__gte=today).order_by("appointment_date", "start_time")
    elif active_tab == "previous":
        queryset = queryset.filter(appointment_date__lt=today).order_by("-appointment_date", "-start_time")
    else:
        queryset = queryset.order_by("-appointment_date", "start_time")

    # 2. Custom Date Range Filters
    start_date = request.GET.get("start_date", "").strip()
    end_date = request.GET.get("end_date", "").strip()
    if start_date:
        queryset = queryset.filter(appointment_date__gte=start_date)
    if end_date:
        queryset = queryset.filter(appointment_date__lte=end_date)

    # 3. Status Filter
    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    # 4. Search Filter (MRN or Name)
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

    # 5. Pagination
    paginator = Paginator(queryset, 10)
    page = request.GET.get("page", 1)
    try:
        appointments_page = paginator.page(page)
    except PageNotAnInteger:
        appointments_page = paginator.page(1)
    except EmptyPage:
        appointments_page = paginator.page(paginator.num_pages)

    # Today summary counts for tab pills
    today_base = Appointment.objects.filter(doctor=doctor_profile, appointment_date=today) if doctor_profile else Appointment.objects.filter(appointment_date=today)
    today_total = today_base.count()
    today_pending = today_base.filter(status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED]).count()
    today_in_progress = today_base.filter(status=Appointment.Status.IN_PROGRESS).count()

    context = {
        "doctor": doctor_profile,
        "appointments": appointments_page,
        "active_tab": active_tab,
        "status_filter": status_filter,
        "start_date": start_date,
        "end_date": end_date,
        "q": q,
        "today": today,
        "today_total": today_total,
        "today_pending": today_pending,
        "today_in_progress": today_in_progress,
        "status_choices": Appointment.Status.choices,
        "total_count": paginator.count,
    }
    return render(request, "appointments/doctor_queue.html", context)


@role_required("DOCTOR", "ADMIN")
def appointment_start_consultation_view(request, pk):
    """
    Initiates clinical consultation for an eligible appointment.
    Transitions appointment status to IN_PROGRESS, creates or fetches the consultation record,
    and redirects the physician to the case-taking interface.
    """
    doctor_profile = get_doctor_profile_or_403(request.user)
    appointment = get_object_or_404(
        Appointment.objects.select_related("patient", "doctor", "consultation"), pk=pk
    )

    # Strict Ownership Authorization
    if getattr(request.user, "role", None) == "DOCTOR":
        if doctor_profile and appointment.doctor_id != doctor_profile.id:
            raise PermissionDenied("You are not authorized to conduct consultations for another physician's appointment.")

    # Status Transition to IN_PROGRESS if SCHEDULED or CONFIRMED
    if appointment.status in [Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED]:
        appointment.start()
        appointment.save()

        try:
            log_audit_event(
                actor=request.user,
                action=AuditLog.Action.UPDATE,
                obj=appointment,
                object_label=f"Started Consultation on Appointment {appointment.pk}",
                metadata={"appointment_id": appointment.pk, "status": Appointment.Status.IN_PROGRESS},
            )
        except Exception:
            pass

    # Retrieve existing or create new Consultation
    consultation = getattr(appointment, "consultation", None)
    if not consultation:
        from consultations.models import Consultation
        with transaction.atomic():
            consultation = Consultation.objects.create(
                patient=appointment.patient,
                doctor=appointment.doctor,
                appointment=appointment,
                chief_complaint=appointment.reason or "Outpatient clinical consultation",
                status=Consultation.Status.DRAFT,
            )
            try:
                log_audit_event(
                    actor=request.user,
                    action=AuditLog.Action.CREATE,
                    obj=consultation,
                    object_label=f"Created Consultation {consultation.pk} for {appointment.patient.get_full_name()}",
                    metadata={"appointment_id": appointment.pk, "consultation_id": consultation.pk},
                )
            except Exception:
                pass

    return redirect("consultations:edit", pk=consultation.pk)


@role_required("DOCTOR", "ADMIN")
def appointment_update_status_view(request, pk):
    """
    Handles granular appointment status transitions triggered by the treating doctor.
    """
    doctor_profile = get_doctor_profile_or_403(request.user)
    appointment = get_object_or_404(Appointment, pk=pk)

    # Strict Ownership Authorization
    if getattr(request.user, "role", None) == "DOCTOR":
        if doctor_profile and appointment.doctor_id != doctor_profile.id:
            raise PermissionDenied("You are not authorized to update another physician's appointment.")

    if request.method == "POST":
        new_status = request.POST.get("status")
        old_status = appointment.status

        # Disallow reopening completed appointments
        if old_status == Appointment.Status.COMPLETED and new_status != Appointment.Status.COMPLETED:
            messages.warning(request, f"Appointment {appointment.pk} is completed and cannot be reopened.")
            return redirect("appointments:doctor_queue")

        # Disallow modifying cancelled appointments
        if old_status == Appointment.Status.CANCELLED:
            messages.warning(request, f"Appointment {appointment.pk} is cancelled and cannot be modified.")
            return redirect("appointments:doctor_queue")

        if new_status == Appointment.Status.CONFIRMED and old_status == Appointment.Status.SCHEDULED:
            appointment.confirm()
            appointment.save()
            messages.success(request, f"Appointment {appointment.pk} for {appointment.patient.get_full_name()} confirmed.")
        elif new_status == Appointment.Status.NO_SHOW and old_status in [Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED]:
            appointment.mark_no_show()
            appointment.save()
            messages.info(request, f"Appointment {appointment.pk} marked as No-Show.")
        elif new_status == Appointment.Status.CANCELLED:
            appointment.cancel(cancelled_by=request.user)
            messages.info(request, f"Appointment {appointment.pk} cancelled.")
        else:
            messages.warning(request, f"Invalid status transition from {old_status} to {new_status}.")
            return redirect("appointments:doctor_queue")

        try:
            log_audit_event(
                actor=request.user,
                action=AuditLog.Action.UPDATE,
                obj=appointment,
                object_label=f"Updated Appointment {appointment.pk} status from {old_status} to {appointment.status}",
                metadata={"appointment_id": appointment.pk, "old_status": old_status, "new_status": appointment.status},
            )
        except Exception:
            pass

    return redirect("appointments:doctor_queue")
