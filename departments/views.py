from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.views import role_required
from appointments.models import Appointment
from audit.models import AuditLog
from audit.services import log_audit_event
from .forms import DepartmentForm, DoctorCreationForm, DoctorUpdateForm
from .models import Department, DoctorProfile


# ==============================================================================
# DEPARTMENT MANAGEMENT VIEWS
# ==============================================================================

@role_required("ADMIN")
def department_list_view(request):
    """
    Displays a searchable, filterable list of clinic departments.
    """
    query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "all")

    qs = Department.objects.annotate(
        active_doctor_count=Count(
            "doctor_profiles", filter=Q(doctor_profiles__is_active=True)
        ),
        total_doctor_count=Count("doctor_profiles"),
    ).order_by("name")

    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(description__icontains=query))

    if status_filter == "active":
        qs = qs.filter(is_active=True)
    elif status_filter == "inactive":
        qs = qs.filter(is_active=False)

    paginator = Paginator(qs, 10)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "departments/department_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "status_filter": status_filter,
            "total_departments": Department.objects.count(),
            "active_departments": Department.objects.filter(is_active=True).count(),
        },
    )


@role_required("ADMIN")
def department_create_view(request):
    """
    Allows administrators to register a new clinic department.
    """
    if request.method == "POST":
        form = DepartmentForm(request.POST)
        if form.is_valid():
            department = form.save()
            log_audit_event(
                actor=request.user,
                action=AuditLog.Action.CREATE,
                obj=department,
                object_label=f"Created Department '{department.name}'",
                metadata={"department_id": department.pk, "name": department.name},
            )
            messages.success(request, f"Department '{department.name}' has been created successfully.")
            return redirect("departments:department_detail", pk=department.pk)
    else:
        form = DepartmentForm()

    return render(
        request,
        "departments/department_form.html",
        {"form": form, "title": "Create Department", "action_label": "Create Department"},
    )


@role_required("ADMIN")
def department_edit_view(request, pk):
    """
    Allows administrators to update an existing clinic department.
    """
    department = get_object_or_404(Department, pk=pk)
    if request.method == "POST":
        form = DepartmentForm(request.POST, instance=department)
        if form.is_valid():
            dept = form.save()
            log_audit_event(
                actor=request.user,
                action=AuditLog.Action.UPDATE,
                obj=dept,
                object_label=f"Updated Department '{dept.name}'",
                metadata={"department_id": dept.pk, "name": dept.name, "is_active": dept.is_active},
            )
            messages.success(request, f"Department '{dept.name}' updated successfully.")
            return redirect("departments:department_detail", pk=dept.pk)
    else:
        form = DepartmentForm(instance=department)

    return render(
        request,
        "departments/department_form.html",
        {
            "form": form,
            "department": department,
            "title": f"Edit Department: {department.name}",
            "action_label": "Update Department",
        },
    )


@role_required("ADMIN")
def department_detail_view(request, pk):
    """
    Displays full details for a department, including assigned doctors and appointment stats.
    """
    department = get_object_or_404(Department, pk=pk)
    doctors = department.doctor_profiles.select_related("user").order_by("-is_active", "user__first_name")
    total_appointments = Appointment.objects.filter(doctor__department=department).count()

    return render(
        request,
        "departments/department_detail.html",
        {
            "department": department,
            "doctors": doctors,
            "total_appointments": total_appointments,
        },
    )


@role_required("ADMIN")
@require_POST
def department_toggle_active_view(request, pk):
    """
    Toggles active/inactive status of a department without breaking historical records.
    """
    department = get_object_or_404(Department, pk=pk)
    department.is_active = not department.is_active
    department.save(update_fields=["is_active", "updated_at"])

    status_str = "activated" if department.is_active else "deactivated"
    log_audit_event(
        actor=request.user,
        action=AuditLog.Action.UPDATE,
        obj=department,
        object_label=f"Department '{department.name}' {status_str}",
        metadata={"department_id": department.pk, "is_active": department.is_active},
    )
    messages.success(request, f"Department '{department.name}' has been {status_str}.")
    return redirect("departments:department_detail", pk=department.pk)


# ==============================================================================
# DOCTOR MANAGEMENT VIEWS
# ==============================================================================

@role_required("ADMIN")
def doctor_list_view(request):
    """
    Displays a searchable, filterable directory of clinical specialists.
    """
    query = request.GET.get("q", "").strip()
    dept_id = request.GET.get("department")
    status_filter = request.GET.get("status", "all")

    qs = DoctorProfile.objects.select_related("user", "department").order_by(
        "-is_active", "user__first_name", "user__last_name"
    )

    if query:
        qs = qs.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(specialization__icontains=query)
            | Q(qualification__icontains=query)
        )

    if dept_id and dept_id.isdigit():
        qs = qs.filter(department_id=int(dept_id))

    if status_filter == "active":
        qs = qs.filter(is_active=True)
    elif status_filter == "inactive":
        qs = qs.filter(is_active=False)

    paginator = Paginator(qs, 10)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    departments = Department.objects.all().order_by("name")

    return render(
        request,
        "departments/doctor_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "dept_id": dept_id,
            "status_filter": status_filter,
            "departments": departments,
            "total_doctors": DoctorProfile.objects.count(),
            "active_doctors": DoctorProfile.objects.filter(is_active=True).count(),
        },
    )


@role_required("ADMIN")
def doctor_create_view(request):
    """
    Allows administrators to register a new physician account and profile.
    """
    if request.method == "POST":
        form = DoctorCreationForm(request.POST)
        if form.is_valid():
            user, profile = form.save()
            log_audit_event(
                actor=request.user,
                action=AuditLog.Action.CREATE,
                obj=profile,
                object_label=f"Registered Doctor Dr. {user.get_full_name() or user.username}",
                metadata={"doctor_id": profile.pk, "username": user.username, "department": profile.department.name},
            )
            messages.success(request, f"Doctor account for Dr. {user.get_full_name() or user.username} created successfully.")
            return redirect("departments:doctor_detail", pk=profile.pk)
    else:
        form = DoctorCreationForm()

    return render(
        request,
        "departments/doctor_form.html",
        {"form": form, "title": "Add New Doctor", "action_label": "Create Doctor Account"},
    )


@role_required("ADMIN")
def doctor_edit_view(request, pk):
    """
    Allows administrators to update an existing doctor's profile and user details.
    """
    profile = get_object_or_404(DoctorProfile.objects.select_related("user", "department"), pk=pk)
    if request.method == "POST":
        form = DoctorUpdateForm(request.POST, instance=profile)
        if form.is_valid():
            prof = form.save()
            log_audit_event(
                actor=request.user,
                action=AuditLog.Action.UPDATE,
                obj=prof,
                object_label=f"Updated Doctor Dr. {prof.user.get_full_name() or prof.user.username}",
                metadata={"doctor_id": prof.pk, "department": prof.department.name, "is_active": prof.is_active},
            )
            messages.success(request, f"Dr. {prof.user.get_full_name() or prof.user.username}'s profile updated successfully.")
            return redirect("departments:doctor_detail", pk=prof.pk)
    else:
        form = DoctorUpdateForm(instance=profile)

    return render(
        request,
        "departments/doctor_form.html",
        {
            "form": form,
            "profile": profile,
            "title": f"Edit Doctor: Dr. {profile.user.get_full_name() or profile.user.username}",
            "action_label": "Update Doctor Profile",
        },
    )


@role_required("ADMIN")
def doctor_detail_view(request, pk):
    """
    Displays comprehensive doctor profile, credentials, department, and appointment statistics.
    """
    profile = get_object_or_404(DoctorProfile.objects.select_related("user", "department"), pk=pk)
    total_appointments = Appointment.objects.filter(doctor=profile).count()
    completed_appointments = Appointment.objects.filter(
        doctor=profile, status=Appointment.Status.COMPLETED
    ).count()

    recent_appointments = (
        Appointment.objects.filter(doctor=profile)
        .select_related("patient")
        .order_by("-appointment_date", "-appointment_time")[:5]
    )

    return render(
        request,
        "departments/doctor_detail.html",
        {
            "profile": profile,
            "total_appointments": total_appointments,
            "completed_appointments": completed_appointments,
            "recent_appointments": recent_appointments,
        },
    )


@role_required("ADMIN")
@require_POST
def doctor_toggle_active_view(request, pk):
    """
    Toggles doctor active status. Deactivating prevents future appointments while preserving history.
    """
    profile = get_object_or_404(DoctorProfile.objects.select_related("user"), pk=pk)
    profile.is_active = not profile.is_active
    profile.save(update_fields=["is_active", "updated_at"])

    # Synchronize User model active flag
    user = profile.user
    user.is_active = profile.is_active
    user.save(update_fields=["is_active"])

    status_str = "activated" if profile.is_active else "deactivated"
    log_audit_event(
        actor=request.user,
        action=AuditLog.Action.UPDATE,
        obj=profile,
        object_label=f"Doctor Dr. {user.get_full_name() or user.username} {status_str}",
        metadata={"doctor_id": profile.pk, "is_active": profile.is_active},
    )
    messages.success(request, f"Doctor Dr. {user.get_full_name() or user.username} has been {status_str}.")
    return redirect("departments:doctor_detail", pk=profile.pk)
