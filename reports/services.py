"""
Reports and Analytics Service (Step 9).

Provides reusable, database-optimized aggregation functions for clinic dashboards
and reports, with strict date filtering and role-based access control.
"""
from datetime import date, datetime, time, timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.utils import timezone

from appointments.models import Appointment
from consultations.models import Consultation
from departments.models import Department, DoctorProfile
from patients.models import Patient
from prescriptions.models import Prescription


def parse_and_validate_date_range(
    start_date=None, end_date=None, preset=None
):
    """
    Parses and validates a date range, supporting presets ('today', 'last_7_days', 'last_30_days')
    or explicit custom dates.

    Returns:
        tuple: (start_date_obj, end_date_obj, start_datetime_tz, end_datetime_tz)
    Raises:
        ValidationError: If start_date > end_date or dates are invalid.
    """
    today = timezone.localdate()

    if preset == "today":
        d_start = today
        d_end = today
    elif preset == "last_7_days":
        d_start = today - timedelta(days=6)
        d_end = today
    elif preset == "last_30_days":
        d_start = today - timedelta(days=29)
        d_end = today
    elif start_date is not None or end_date is not None:
        # Custom dates
        def _parse(val, default):
            if val is None or val == "":
                return default
            if isinstance(val, date) and not isinstance(val, datetime):
                return val
            if isinstance(val, datetime):
                return val.date()
            if isinstance(val, str):
                try:
                    return datetime.strptime(val.strip(), "%Y-%m-%d").date()
                except ValueError:
                    raise ValidationError(
                        f"Invalid date format '{val}'. Expected YYYY-MM-DD."
                    )
            return default

        d_start = _parse(start_date, today - timedelta(days=6))
        d_end = _parse(end_date, today)
    else:
        # Default preset when nothing is specified
        d_start = today - timedelta(days=6)
        d_end = today

    if d_start > d_end:
        raise ValidationError(
            f"Start date ({d_start}) cannot be later than end date ({d_end})."
        )

    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(d_start, time.min), tz)
    end_dt = timezone.make_aware(datetime.combine(d_end, time.max), tz)

    return d_start, d_end, start_dt, end_dt


def get_patient_statistics(start_date=None, end_date=None, preset=None):
    """
    Retrieves patient master metrics and distinct patient footfall.
    Patient footfall is defined as the count of distinct patients who had at least
    one consultation within the date range (walk-ins included; bookings alone do not count).
    """
    d_start, d_end, start_dt, end_dt = parse_and_validate_date_range(
        start_date, end_date, preset
    )

    total_patients = Patient.objects.count()
    active_patients = Patient.objects.filter(is_active=True).count()
    new_patients = Patient.objects.filter(
        created_at__range=(start_dt, end_dt)
    ).count()

    # Footfall: distinct patients with at least one consultation in this range
    patient_footfall = (
        Consultation.objects.filter(consultation_date__range=(start_dt, end_dt))
        .values("patient_id")
        .distinct()
        .count()
    )

    return {
        "total_patients": total_patients,
        "active_patients": active_patients,
        "new_patients": new_patients,
        "patient_footfall": patient_footfall,
        "date_range": {"start_date": str(d_start), "end_date": str(d_end)},
    }


def get_appointment_statistics(
    start_date=None, end_date=None, preset=None, doctor=None
):
    """
    Retrieves appointment volume and status breakdown within the selected date range.
    """
    d_start, d_end, _, _ = parse_and_validate_date_range(
        start_date, end_date, preset
    )

    qs = Appointment.objects.filter(appointment_date__range=(d_start, d_end))
    if doctor is not None:
        qs = qs.filter(doctor=doctor)

    status_counts = qs.aggregate(
        total=Count("id"),
        scheduled=Count("id", filter=Q(status=Appointment.Status.SCHEDULED)),
        confirmed=Count("id", filter=Q(status=Appointment.Status.CONFIRMED)),
        in_progress=Count("id", filter=Q(status=Appointment.Status.IN_PROGRESS)),
        completed=Count("id", filter=Q(status=Appointment.Status.COMPLETED)),
        cancelled=Count("id", filter=Q(status=Appointment.Status.CANCELLED)),
        no_show=Count("id", filter=Q(status=Appointment.Status.NO_SHOW)),
    )

    return {
        "total_appointments": status_counts["total"] or 0,
        "scheduled_appointments": status_counts["scheduled"] or 0,
        "confirmed_appointments": status_counts["confirmed"] or 0,
        "in_progress_appointments": status_counts["in_progress"] or 0,
        "completed_appointments": status_counts["completed"] or 0,
        "cancelled_appointments": status_counts["cancelled"] or 0,
        "no_show_appointments": status_counts["no_show"] or 0,
        "date_range": {"start_date": str(d_start), "end_date": str(d_end)},
    }


def get_department_statistics(start_date=None, end_date=None, preset=None):
    """
    Generates department-wise appointment statistics for all active clinic departments.
    """
    d_start, d_end, _, _ = parse_and_validate_date_range(
        start_date, end_date, preset
    )

    departments = Department.objects.all().order_by("name")
    results = []

    for dept in departments:
        dept_apts = Appointment.objects.filter(
            doctor__department=dept,
            appointment_date__range=(d_start, d_end),
        ).aggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(status=Appointment.Status.COMPLETED)),
            cancelled=Count("id", filter=Q(status=Appointment.Status.CANCELLED)),
            pending=Count(
                "id",
                filter=Q(
                    status__in=[
                        Appointment.Status.SCHEDULED,
                        Appointment.Status.CONFIRMED,
                        Appointment.Status.IN_PROGRESS,
                    ]
                ),
            ),
        )

        results.append({
            "department_id": dept.pk,
            "department_name": dept.name,
            "total_appointments": dept_apts["total"] or 0,
            "completed_appointments": dept_apts["completed"] or 0,
            "cancelled_appointments": dept_apts["cancelled"] or 0,
            "pending_appointments": dept_apts["pending"] or 0,
        })

    return results


def get_doctor_statistics(
    doctor=None, start_date=None, end_date=None, preset=None
):
    """
    Generates doctor-wise consultation volume and completion statistics.
    Uses actual Consultation records rather than appointment counts.
    """
    d_start, d_end, start_dt, end_dt = parse_and_validate_date_range(
        start_date, end_date, preset
    )

    if doctor is not None:
        doctors = [doctor]
    else:
        doctors = (
            DoctorProfile.objects.select_related("user", "department")
            .filter(is_active=True)
            .order_by("user__first_name", "user__last_name")
        )

    results = []
    for doc in doctors:
        doc_consultations = Consultation.objects.filter(doctor=doc)
        total_all_time = doc_consultations.count()
        completed_all_time = doc_consultations.filter(
            status=Consultation.Status.FINALIZED
        ).count()
        in_range = doc_consultations.filter(
            consultation_date__range=(start_dt, end_dt)
        ).count()

        doc_name = doc.user.get_full_name().strip() or doc.user.username
        dept_name = doc.department.name if doc.department else "Unassigned"

        results.append({
            "doctor_id": doc.pk,
            "doctor_name": f"Dr. {doc_name}",
            "department": dept_name,
            "total_consultations": total_all_time,
            "completed_consultations": completed_all_time,
            "consultations_in_range": in_range,
        })

    return results


def get_daily_activity(
    start_date=None, end_date=None, preset=None, doctor=None
):
    """
    Provides daily summaries for each day in the selected date range:
    - Patient footfall (distinct patients with consultation)
    - Total appointments
    - Completed consultations (status=FINALIZED)
    - Prescriptions issued (status=ISSUED)
    """
    d_start, d_end, _, _ = parse_and_validate_date_range(
        start_date, end_date, preset
    )
    tz = timezone.get_current_timezone()

    daily_data = []
    current_day = d_start

    while current_day <= d_end:
        day_start = timezone.make_aware(datetime.combine(current_day, time.min), tz)
        day_end = timezone.make_aware(datetime.combine(current_day, time.max), tz)

        # Footfall for this day
        footfall_qs = Consultation.objects.filter(
            consultation_date__range=(day_start, day_end)
        )
        if doctor is not None:
            footfall_qs = footfall_qs.filter(doctor=doctor)
        day_footfall = footfall_qs.values("patient_id").distinct().count()

        # Appointments for this day
        apt_qs = Appointment.objects.filter(appointment_date=current_day)
        if doctor is not None:
            apt_qs = apt_qs.filter(doctor=doctor)
        day_apts = apt_qs.count()

        # Completed consultations for this day
        consult_qs = Consultation.objects.filter(
            consultation_date__range=(day_start, day_end),
            status=Consultation.Status.FINALIZED,
        )
        if doctor is not None:
            consult_qs = consult_qs.filter(doctor=doctor)
        day_completed_consults = consult_qs.count()

        # Prescriptions issued for this day
        rx_qs = Prescription.objects.filter(
            issued_at__range=(day_start, day_end),
            status=Prescription.Status.ISSUED,
        )
        if doctor is not None:
            rx_qs = rx_qs.filter(consultation__doctor=doctor)
        day_prescriptions = rx_qs.count()

        daily_data.append({
            "date": str(current_day),
            "patient_footfall": day_footfall,
            "total_appointments": day_apts,
            "completed_consultations": day_completed_consults,
            "prescriptions_issued": day_prescriptions,
        })

        current_day += timedelta(days=1)

    return daily_data


def get_dashboard_report(
    user, start_date=None, end_date=None, date_preset="last_7_days"
):
    """
    Central entry point for role-based clinic reports:
    - Administrator: Full clinic oversight (patients, appointments, departments, doctors, daily activity).
    - Receptionist: Patient registration and appointment statistics, department appointment volumes.
    - Doctor: Own consultation, appointment, and daily activity statistics.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required to access reporting metrics.")

    role = getattr(user, "role", None)
    is_admin = getattr(user, "is_clinic_admin", False) or getattr(user, "is_superuser", False) or role == "ADMIN"

    d_start, d_end, _, _ = parse_and_validate_date_range(
        start_date, end_date, date_preset
    )
    date_range_info = {"start_date": str(d_start), "end_date": str(d_end)}

    if is_admin:
        return {
            "role": "ADMIN",
            "date_range": date_range_info,
            "patient_statistics": get_patient_statistics(d_start, d_end, preset=None),
            "appointment_statistics": get_appointment_statistics(
                d_start, d_end, preset=None
            ),
            "department_statistics": get_department_statistics(
                d_start, d_end, preset=None
            ),
            "doctor_statistics": get_doctor_statistics(
                start_date=d_start, end_date=d_end, preset=None
            ),
            "daily_activity": get_daily_activity(d_start, d_end, preset=None),
        }

    if role == "RECEPTIONIST":
        return {
            "role": "RECEPTIONIST",
            "date_range": date_range_info,
            "patient_statistics": get_patient_statistics(d_start, d_end, preset=None),
            "appointment_statistics": get_appointment_statistics(
                d_start, d_end, preset=None
            ),
            "department_statistics": get_department_statistics(
                d_start, d_end, preset=None
            ),
        }

    if role == "DOCTOR":
        doctor_profile = getattr(user, "doctor_profile", None)
        if not doctor_profile:
            # Fallback lookup
            doctor_profile = DoctorProfile.objects.filter(user=user).first()
        if not doctor_profile:
            raise PermissionDenied("Doctor profile not found for this user account.")

        doc_stats = get_doctor_statistics(
            doctor=doctor_profile, start_date=d_start, end_date=d_end, preset=None
        )
        apt_stats = get_appointment_statistics(
            start_date=d_start, end_date=d_end, preset=None, doctor=doctor_profile
        )
        daily_stats = get_daily_activity(
            start_date=d_start, end_date=d_end, preset=None, doctor=doctor_profile
        )

        # Footfall for this doctor's consultations
        _, _, start_dt, end_dt = parse_and_validate_date_range(d_start, d_end, None)
        doc_footfall = (
            Consultation.objects.filter(
                doctor=doctor_profile, consultation_date__range=(start_dt, end_dt)
            )
            .values("patient_id")
            .distinct()
            .count()
        )

        return {
            "role": "DOCTOR",
            "date_range": date_range_info,
            "doctor_statistics": doc_stats[0] if doc_stats else {},
            "appointment_statistics": apt_stats,
            "daily_activity": daily_stats,
            "patient_footfall": doc_footfall,
        }

    raise PermissionDenied("You do not have permission to view reporting dashboards.")
