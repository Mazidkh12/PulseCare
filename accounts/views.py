"""
Authentication and Role-Based Dashboard Views (Step 10A).
"""
import json
from datetime import date
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from appointments.models import Appointment
from audit.models import AuditLog
from audit.services import log_audit_event
from consultations.models import Consultation
from departments.models import Department, DoctorProfile
from patients.models import Patient
from prescriptions.models import Prescription
from reports.services import (
    get_daily_activity,
    get_department_statistics,
    get_doctor_statistics,
    parse_and_validate_date_range,
)
from .decorators import role_required
from .forms import SignUpForm, UserCreationAdminForm, UserUpdateAdminForm

User = get_user_model()


def login_view(request):
    """
    Handles user authentication for clinic staff (Doctors, Receptionists, Administrators).
    Supports login via username or email.
    """
    if request.user.is_authenticated:
        return redirect("accounts:dashboard_redirect")

    error_message = None
    next_url = request.GET.get("next") or request.POST.get("next") or ""

    if request.method == "POST":
        identifier = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        username = identifier
        # If user entered an email, lookup their username
        if "@" in identifier:
            matched_user = User.objects.filter(email__iexact=identifier).first()
            if matched_user:
                username = matched_user.username

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if not user.is_active:
                error_message = "Your account has been deactivated. Please contact the administrator."
            else:
                login(request, user)
                # Audit log for login event
                try:
                    log_audit_event(
                        actor=user,
                        action=AuditLog.Action.LOGIN,
                        object_label=f"User {user.username} logged in",
                        metadata={"username": user.username, "role": user.role},
                    )
                except Exception:
                    pass

                role_display = user.get_role_display() if hasattr(user, "get_role_display") else user.role
                full_name = user.get_full_name().strip() or user.username
                messages.success(request, f"Welcome back, {full_name} ({role_display}).")

                # Validate next URL to prevent open-redirect vulnerabilities
                if next_url and url_has_allowed_host_and_scheme(
                    url=next_url,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    return redirect(next_url)

                return redirect("accounts:dashboard_redirect")
        else:
            error_message = "Invalid username or password. Please try again."

    return render(
        request,
        "accounts/login.html",
        {
            "error_message": error_message,
            "next_url": next_url,
            "username": request.POST.get("username", ""),
        },
    )


def logout_view(request):
    """
    Logs out the authenticated user and redirects to the login view with an audit event.
    """
    if request.user.is_authenticated:
        try:
            log_audit_event(
                actor=request.user,
                action=AuditLog.Action.LOGOUT,
                object_label=f"User {request.user.username} logged out",
                metadata={"username": request.user.username},
            )
        except Exception:
            pass
        logout(request)
        messages.info(request, "You have been logged out successfully.")

    return redirect("accounts:login")


def signup_view(request):
    """
    Handles self-service registration for new clinic staff (Receptionists, Doctors, Administrators).
    Automatically creates the appropriate user and linked profile, logs the user in,
    and redirects them to their role-specific dashboard.
    """
    if request.user.is_authenticated:
        return redirect("accounts:dashboard_redirect")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()

            # Record audit log event for new user registration
            try:
                log_audit_event(
                    actor=user,
                    action=AuditLog.Action.CREATE,
                    object_label=f"User {user.username} registered account ({user.get_role_display()})",
                    metadata={"username": user.username, "role": user.role},
                )
            except Exception:
                pass

            # Automatically log the newly registered user in
            login(request, user)

            role_display = user.get_role_display()
            full_name = user.get_full_name().strip() or user.username
            messages.success(
                request,
                f"Account successfully created! Welcome to PulseCare Clinic, {full_name} ({role_display}).",
            )
            return redirect("accounts:dashboard_redirect")
    else:
        form = SignUpForm()

    return render(
        request,
        "accounts/signup.html",
        {
            "form": form,
        },
    )


@login_required
def dashboard_redirect_view(request):
    """
    Central dispatcher routing authenticated users to their role-specific dashboard.
    """
    role = getattr(request.user, "role", None)

    if request.user.is_superuser or role == User.Role.ADMIN:
        return redirect("accounts:admin_dashboard")
    elif role == User.Role.RECEPTIONIST:
        return redirect("accounts:receptionist_dashboard")
    elif role == User.Role.DOCTOR:
        return redirect("accounts:doctor_dashboard")

    raise PermissionDenied("User does not have an assigned role for dashboard access.")


@role_required("ADMIN")
def admin_dashboard_view(request):
    """
    Administrator dashboard view consolidating clinic operations, clinical volume,
    department statistics, doctor workload, and daily activity trends.
    """
    today = timezone.localdate()
    tz = timezone.get_current_timezone()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()), tz)
    today_end = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.max.time()), tz)

    # Date filter parameters
    preset = request.GET.get("preset", "last_7_days")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    try:
        d_start, d_end, start_dt, end_dt = parse_and_validate_date_range(
            start_date=start_date, end_date=end_date, preset=preset
        )
    except ValidationError as err:
        messages.error(request, str(err.message if hasattr(err, "message") else err))
        d_start, d_end, start_dt, end_dt = parse_and_validate_date_range(preset="last_7_days")
        preset = "last_7_days"

    # 1. Summary Cards
    total_patients = Patient.objects.count()
    new_patients_today = Patient.objects.filter(created_at__range=(today_start, today_end)).count()
    active_doctors_count = DoctorProfile.objects.filter(is_active=True).count()
    total_departments_count = Department.objects.filter(is_active=True).count()
    today_appointments = Appointment.objects.filter(appointment_date=today).count()
    completed_consultations = Consultation.objects.filter(status=Consultation.Status.FINALIZED).count()
    pending_appointments = Appointment.objects.filter(
        status__in=[
            Appointment.Status.SCHEDULED,
            Appointment.Status.CONFIRMED,
            Appointment.Status.IN_PROGRESS,
        ]
    ).count()
    prescriptions_issued = Prescription.objects.filter(status=Prescription.Status.ISSUED).count()

    # 2. Department Statistics
    raw_dept_stats = get_department_statistics(d_start, d_end)
    dept_stats = []
    for dept_data in raw_dept_stats:
        dept_obj = Department.objects.filter(pk=dept_data["department_id"]).first()
        active_docs = dept_obj.doctor_profiles.filter(is_active=True).count() if dept_obj else 0
        dept_data["active_doctors"] = active_docs
        dept_stats.append(dept_data)

    # 3. Doctor Workload
    doctors_qs = DoctorProfile.objects.select_related("user", "department").filter(is_active=True).order_by("user__first_name")
    doctor_workload = []
    for doc in doctors_qs:
        total_apts = Appointment.objects.filter(doctor=doc).count()
        completed_consults = Consultation.objects.filter(
            doctor=doc, status=Consultation.Status.FINALIZED
        ).count()
        upcoming_apts = Appointment.objects.filter(
            doctor=doc,
            appointment_date__gte=today,
            status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED],
        ).count()
        doctor_workload.append({
            "doctor": doc,
            "doctor_name": f"Dr. {doc.user.get_full_name().strip() or doc.user.username}",
            "department": doc.department.name if doc.department else "Unassigned",
            "total_appointments": total_apts,
            "completed_consultations": completed_consults,
            "upcoming_appointments": upcoming_apts,
        })

    # 4. Daily Activity Trends
    daily_activity = get_daily_activity(d_start, d_end)
    chart_labels = [day["date"] for day in daily_activity]
    chart_footfall = [day["patient_footfall"] for day in daily_activity]
    chart_appointments = [day["total_appointments"] for day in daily_activity]
    chart_consultations = [day["completed_consultations"] for day in daily_activity]
    chart_prescriptions = [day["prescriptions_issued"] for day in daily_activity]

    chart_data_json = json.dumps({
        "labels": chart_labels,
        "footfall": chart_footfall,
        "appointments": chart_appointments,
        "consultations": chart_consultations,
        "prescriptions": chart_prescriptions,
    })

    context = {
        "preset": preset,
        "start_date": str(d_start),
        "end_date": str(d_end),
        "total_patients": total_patients,
        "new_patients_today": new_patients_today,
        "active_doctors": active_doctors_count,
        "total_departments": total_departments_count,
        "today_appointments": today_appointments,
        "completed_consultations": completed_consultations,
        "pending_appointments": pending_appointments,
        "prescriptions_issued": prescriptions_issued,
        "department_statistics": dept_stats,
        "doctor_workload": doctor_workload,
        "chart_data_json": chart_data_json,
    }
    return render(request, "dashboards/admin_dashboard.html", context)


@role_required("RECEPTIONIST", "ADMIN")
def receptionist_dashboard_view(request):
    """
    Receptionist front-desk dashboard view.
    """
    today = timezone.localdate()
    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()), tz)
    end_dt = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.max.time()), tz)

    scheduled_today = Appointment.objects.filter(appointment_date=today, status=Appointment.Status.SCHEDULED).count()
    confirmed_today = Appointment.objects.filter(appointment_date=today, status=Appointment.Status.CONFIRMED).count()
    total_today = Appointment.objects.filter(appointment_date=today).count()
    total_patients = Patient.objects.filter(is_active=True).count()
    active_doctors = DoctorProfile.objects.filter(is_active=True, department__is_active=True).count()
    patient_footfall = Consultation.objects.filter(consultation_date__range=(start_dt, end_dt)).values("patient_id").distinct().count()

    context = {
        "scheduled_today": scheduled_today,
        "confirmed_today": confirmed_today,
        "total_today": total_today,
        "total_patients": total_patients,
        "active_doctors": active_doctors,
        "patient_footfall": patient_footfall,
    }
    return render(request, "dashboards/receptionist_dashboard.html", context)


@role_required("DOCTOR")
def doctor_dashboard_view(request):
    """
    Attending physician dashboard view with comprehensive clinical statistics
    and quick-action links scoped strictly to the authenticated doctor.
    """
    doctor_profile = DoctorProfile.objects.filter(user=request.user, is_active=True).first()
    if not doctor_profile:
        raise PermissionDenied("Active Doctor Profile not found for this user account.")

    today = timezone.localdate()

    # Scoped appointments for today
    today_appointments = Appointment.objects.filter(
        doctor=doctor_profile, appointment_date=today
    )
    today_count = today_appointments.count()
    scheduled_count = today_appointments.filter(status=Appointment.Status.SCHEDULED).count()
    confirmed_count = today_appointments.filter(status=Appointment.Status.CONFIRMED).count()
    in_progress_count = today_appointments.filter(status=Appointment.Status.IN_PROGRESS).count()
    completed_today = today_appointments.filter(status=Appointment.Status.COMPLETED).count()

    # Upcoming appointments (today and future with active scheduled/confirmed status)
    upcoming_count = Appointment.objects.filter(
        doctor=doctor_profile,
        appointment_date__gte=today,
        status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED],
    ).count()

    # Scoped consultations & prescriptions
    waiting_queue = Consultation.objects.filter(
        doctor=doctor_profile,
        status=Consultation.Status.DRAFT,
    ).count()
    completed_consultations = Consultation.objects.filter(
        doctor=doctor_profile,
        status=Consultation.Status.FINALIZED,
    ).count()
    prescriptions_issued = Prescription.objects.filter(
        consultation__doctor=doctor_profile,
        status=Prescription.Status.ISSUED,
    ).count()

    # Today's queue preview (up to 6 appointments)
    today_queue_preview = (
        today_appointments.select_related("patient")
        .order_by("start_time")[:6]
    )

    context = {
        "doctor": doctor_profile,
        "today_count": today_count,
        "scheduled_count": scheduled_count,
        "confirmed_count": confirmed_count,
        "in_progress_count": in_progress_count,
        "completed_today": completed_today,
        "upcoming_count": upcoming_count,
        "waiting_queue": waiting_queue,
        "completed_consultations": completed_consultations,
        "prescriptions_issued": prescriptions_issued,
        "today_queue_preview": today_queue_preview,
    }
    return render(request, "dashboards/doctor_dashboard.html", context)


# ==============================================================================
# USER MANAGEMENT VIEWS (Step 10D - Administrator Portal)
# ==============================================================================

@role_required("ADMIN")
def user_list_view(request):
    """
    Searchable and filterable registry of all staff accounts.
    """
    query = request.GET.get("q", "").strip()
    role_filter = request.GET.get("role", "all")
    status_filter = request.GET.get("status", "all")

    qs = User.objects.all().order_by("role", "username")

    if query:
        qs = qs.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )

    if role_filter in [User.Role.ADMIN, User.Role.DOCTOR, User.Role.RECEPTIONIST]:
        qs = qs.filter(role=role_filter)

    if status_filter == "active":
        qs = qs.filter(is_active=True)
    elif status_filter == "inactive":
        qs = qs.filter(is_active=False)

    paginator = Paginator(qs, 15)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "accounts/user_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "role_filter": role_filter,
            "status_filter": status_filter,
            "roles": User.Role.choices,
            "total_users": User.objects.count(),
            "active_users": User.objects.filter(is_active=True).count(),
        },
    )


@role_required("ADMIN")
def user_create_view(request):
    """
    Allows administrators to register staff user accounts (Receptionists and Admins).
    Doctor accounts are directed through the Doctor Management flow.
    """
    if request.method == "POST":
        form = UserCreationAdminForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            log_audit_event(
                actor=request.user,
                action=AuditLog.Action.CREATE,
                obj=new_user,
                object_label=f"Created user account '{new_user.username}' ({new_user.get_role_display()})",
                metadata={"user_id": new_user.pk, "username": new_user.username, "role": new_user.role},
            )
            messages.success(request, f"User account '{new_user.username}' created successfully.")
            return redirect("accounts:user_detail", pk=new_user.pk)
    else:
        form = UserCreationAdminForm()

    return render(
        request,
        "accounts/user_form.html",
        {"form": form, "title": "Create Staff Account", "action_label": "Create Account"},
    )


@role_required("ADMIN")
def user_edit_view(request, pk):
    """
    Allows administrators to update user demographics, active flag, and role.
    """
    target_user = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = UserUpdateAdminForm(request.POST, instance=target_user, admin_user=request.user)
        if form.is_valid():
            updated_user = form.save()
            log_audit_event(
                actor=request.user,
                action=AuditLog.Action.UPDATE,
                obj=updated_user,
                object_label=f"Updated user account '{updated_user.username}'",
                metadata={"user_id": updated_user.pk, "role": updated_user.role, "is_active": updated_user.is_active},
            )
            messages.success(request, f"User '{updated_user.username}' updated successfully.")
            return redirect("accounts:user_detail", pk=updated_user.pk)
    else:
        form = UserUpdateAdminForm(instance=target_user, admin_user=request.user)

    return render(
        request,
        "accounts/user_form.html",
        {
            "form": form,
            "target_user": target_user,
            "title": f"Edit Account: {target_user.username}",
            "action_label": "Update Account",
        },
    )


@role_required("ADMIN")
def user_detail_view(request, pk):
    """
    Displays user account details and recent audit trail of actions performed by this user.
    """
    target_user = get_object_or_404(User, pk=pk)
    recent_activity = AuditLog.objects.filter(actor=target_user).order_by("-timestamp")[:10]

    return render(
        request,
        "accounts/user_detail.html",
        {
            "target_user": target_user,
            "recent_activity": recent_activity,
        },
    )


@role_required("ADMIN")
@require_POST
def user_toggle_active_view(request, pk):
    """
    Toggles user active flag. Strictly prohibits administrator from deactivating their own account.
    """
    target_user = get_object_or_404(User, pk=pk)

    if target_user.pk == request.user.pk:
        messages.error(request, "You cannot deactivate your own active administrator account.")
        return redirect("accounts:user_detail", pk=target_user.pk)

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=["is_active"])

    status_str = "activated" if target_user.is_active else "deactivated"
    log_audit_event(
        actor=request.user,
        action=AuditLog.Action.UPDATE,
        obj=target_user,
        object_label=f"Account '{target_user.username}' {status_str}",
        metadata={"user_id": target_user.pk, "is_active": target_user.is_active},
    )
    messages.success(request, f"User account '{target_user.username}' has been {status_str}.")
    return redirect("accounts:user_detail", pk=target_user.pk)

