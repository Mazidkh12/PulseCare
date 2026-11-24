"""
Reports and Dashboard Views (Step 9 & Step 10D).

Provides controller interfaces, CSV export handlers with CSV formula injection protection,
and printable report templates.
"""
import csv
from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.views import role_required
from appointments.models import Appointment
from consultations.models import Consultation
from departments.models import Department, DoctorProfile
from patients.models import Patient
from .services import (
    get_dashboard_report,
    get_department_statistics,
    get_doctor_statistics,
    parse_and_validate_date_range,
)


def sanitize_csv_cell(value):
    """
    Sanitizes values against spreadsheet formula injection (CSV Injection / CWE-1236).
    Prepends a single quote if the value begins with '=', '+', '-', '@', '\t', or '\r'.
    """
    if value is None:
        return ""
    val_str = str(value)
    if val_str and val_str[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{val_str}"
    return val_str


@login_required
def dashboard_data_view(request):
    """
    Returns dashboard analytics data for the authenticated user based on role
    and requested date parameters.
    """
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    date_preset = request.GET.get("preset", "last_7_days")

    try:
        data = get_dashboard_report(
            user=request.user,
            start_date=start_date,
            end_date=end_date,
            date_preset=date_preset,
        )
        return JsonResponse({"status": "success", "data": data})
    except PermissionDenied as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=403)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@role_required("ADMIN")
def reports_index_view(request):
    """
    Administrative reporting hub presenting operational reports,
    date filter selectors, CSV downloads, and printable views.
    """
    today = timezone.localdate()
    preset = request.GET.get("preset", "last_7_days")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    try:
        d_start, d_end, _, _ = parse_and_validate_date_range(start_date, end_date, preset)
    except ValidationError:
        d_start, d_end, _, _ = parse_and_validate_date_range(preset="last_7_days")
        preset = "last_7_days"

    return render(
        request,
        "reports/reports_index.html",
        {
            "preset": preset,
            "start_date": str(d_start),
            "end_date": str(d_end),
            "today": today,
        },
    )


@role_required("ADMIN")
def export_patients_csv_view(request):
    """
    Exports a safe, operational CSV of patient registrations.
    Omits sensitive clinical narratives, diagnoses, and medical histories.
    """
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    today_str = timezone.localdate().strftime("%Y%m%d")
    response["Content-Disposition"] = f'attachment; filename="patient_registrations_{today_str}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        sanitize_csv_cell("MRN"),
        sanitize_csv_cell("Patient Name"),
        sanitize_csv_cell("Registration Date"),
        sanitize_csv_cell("Gender"),
        sanitize_csv_cell("Active Status"),
    ])

    patients = Patient.objects.all().order_by("-created_at")
    for p in patients:
        writer.writerow([
            sanitize_csv_cell(p.patient_id),
            sanitize_csv_cell(p.get_full_name()),
            sanitize_csv_cell(p.created_at.strftime("%Y-%m-%d")),
            sanitize_csv_cell(p.get_gender_display()),
            sanitize_csv_cell("Active" if p.is_active else "Inactive"),
        ])

    return response


@role_required("ADMIN")
def export_appointments_csv_view(request):
    """
    Exports operational appointment records within the requested date range.
    Protects against CSV injection and omits clinical notes.
    """
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    preset = request.GET.get("preset", "last_7_days")

    try:
        d_start, d_end, _, _ = parse_and_validate_date_range(start_date, end_date, preset)
    except ValidationError as err:
        return HttpResponse(f"Invalid date range: {err}", status=400)

    filename = f"appointments_report_{d_start}_to_{d_end}.csv"
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        sanitize_csv_cell("Appointment Date"),
        sanitize_csv_cell("Patient MRN"),
        sanitize_csv_cell("Patient Name"),
        sanitize_csv_cell("Doctor"),
        sanitize_csv_cell("Department"),
        sanitize_csv_cell("Appointment Time"),
        sanitize_csv_cell("Appointment Status"),
    ])

    apts = (
        Appointment.objects.filter(appointment_date__range=(d_start, d_end))
        .select_related("patient", "doctor__user", "doctor__department")
        .order_by("appointment_date", "start_time")
    )

    for apt in apts:
        doc_name = (
            f"Dr. {apt.doctor.user.get_full_name() or apt.doctor.user.username}"
            if apt.doctor
            else "Unassigned"
        )
        dept_name = apt.doctor.department.name if (apt.doctor and apt.doctor.department) else "N/A"
        writer.writerow([
            sanitize_csv_cell(str(apt.appointment_date)),
            sanitize_csv_cell(apt.patient.patient_id),
            sanitize_csv_cell(apt.patient.get_full_name()),
            sanitize_csv_cell(doc_name),
            sanitize_csv_cell(dept_name),
            sanitize_csv_cell(apt.start_time.strftime("%H:%M") if apt.start_time else ""),
            sanitize_csv_cell(apt.get_status_display()),
        ])

    return response


@role_required("ADMIN")
def export_departments_csv_view(request):
    """
    Exports department operational metrics: appointments volume, completions, cancellations, and doctors.
    """
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    preset = request.GET.get("preset", "last_7_days")

    try:
        d_start, d_end, _, _ = parse_and_validate_date_range(start_date, end_date, preset)
    except ValidationError as err:
        return HttpResponse(f"Invalid date range: {err}", status=400)

    filename = f"departments_report_{d_start}_to_{d_end}.csv"
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        sanitize_csv_cell("Department"),
        sanitize_csv_cell("Total Appointments"),
        sanitize_csv_cell("Completed Appointments"),
        sanitize_csv_cell("Cancelled Appointments"),
        sanitize_csv_cell("Active Doctors"),
    ])

    dept_stats = get_department_statistics(d_start, d_end)
    for stat in dept_stats:
        dept_obj = Department.objects.filter(pk=stat["department_id"]).first()
        active_docs = dept_obj.doctor_profiles.filter(is_active=True).count() if dept_obj else 0
        writer.writerow([
            sanitize_csv_cell(stat["department_name"]),
            sanitize_csv_cell(stat["total_appointments"]),
            sanitize_csv_cell(stat["completed_appointments"]),
            sanitize_csv_cell(stat["cancelled_appointments"]),
            sanitize_csv_cell(active_docs),
        ])

    return response


@role_required("ADMIN")
def export_doctor_workload_csv_view(request):
    """
    Exports doctor clinical workload metrics across the clinic.
    """
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    preset = request.GET.get("preset", "last_7_days")

    try:
        d_start, d_end, _, _ = parse_and_validate_date_range(start_date, end_date, preset)
    except ValidationError as err:
        return HttpResponse(f"Invalid date range: {err}", status=400)

    filename = f"doctor_workload_{d_start}_to_{d_end}.csv"
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        sanitize_csv_cell("Doctor"),
        sanitize_csv_cell("Department"),
        sanitize_csv_cell("Total Appointments"),
        sanitize_csv_cell("Completed Consultations"),
        sanitize_csv_cell("Date Range"),
    ])

    doctors = DoctorProfile.objects.select_related("user", "department").filter(is_active=True).order_by("user__first_name")
    date_range_str = f"{d_start} to {d_end}"

    for doc in doctors:
        total_apts = Appointment.objects.filter(
            doctor=doc, appointment_date__range=(d_start, d_end)
        ).count()
        completed_consults = Consultation.objects.filter(
            doctor=doc,
            consultation_date__date__range=(d_start, d_end),
            status=Consultation.Status.FINALIZED,
        ).count()
        doc_name = f"Dr. {doc.user.get_full_name() or doc.user.username}"
        dept_name = doc.department.name if doc.department else "Unassigned"

        writer.writerow([
            sanitize_csv_cell(doc_name),
            sanitize_csv_cell(dept_name),
            sanitize_csv_cell(total_apts),
            sanitize_csv_cell(completed_consults),
            sanitize_csv_cell(date_range_str),
        ])

    return response


@role_required("ADMIN")
def report_printable_view(request):
    """
    Renders a clean printable HTML operational report with clinic header,
    summary tables, and CSS print styling.
    """
    report_type = request.GET.get("type", "overview")
    preset = request.GET.get("preset", "last_7_days")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    try:
        d_start, d_end, start_dt, end_dt = parse_and_validate_date_range(start_date, end_date, preset)
    except ValidationError:
        d_start, d_end, start_dt, end_dt = parse_and_validate_date_range(preset="last_7_days")
        preset = "last_7_days"

    today = timezone.localdate()

    # Load data for the printable report
    dept_stats = get_department_statistics(d_start, d_end)
    for stat in dept_stats:
        dept_obj = Department.objects.filter(pk=stat["department_id"]).first()
        stat["active_doctors"] = dept_obj.doctor_profiles.filter(is_active=True).count() if dept_obj else 0

    doctors = DoctorProfile.objects.select_related("user", "department").filter(is_active=True).order_by("user__first_name")
    doctor_workload = []
    for doc in doctors:
        apts = Appointment.objects.filter(doctor=doc, appointment_date__range=(d_start, d_end)).count()
        completed = Consultation.objects.filter(
            doctor=doc,
            consultation_date__date__range=(d_start, d_end),
            status=Consultation.Status.FINALIZED,
        ).count()
        doctor_workload.append({
            "name": f"Dr. {doc.user.get_full_name() or doc.user.username}",
            "department": doc.department.name if doc.department else "Unassigned",
            "specialization": doc.specialization,
            "appointments": apts,
            "completed": completed,
        })

    recent_appointments = (
        Appointment.objects.filter(appointment_date__range=(d_start, d_end))
        .select_related("patient", "doctor__user", "doctor__department")
        .order_by("-appointment_date", "-start_time")[:25]
    )

    context = {
        "report_type": report_type,
        "start_date": d_start,
        "end_date": d_end,
        "generated_at": timezone.now(),
        "today": today,
        "department_statistics": dept_stats,
        "doctor_workload": doctor_workload,
        "recent_appointments": recent_appointments,
        "total_patients": Patient.objects.count(),
        "total_appointments": Appointment.objects.filter(appointment_date__range=(d_start, d_end)).count(),
    }
    return render(request, "reports/report_print.html", context)
