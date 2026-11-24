from datetime import date, time, timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from consultations.models import Consultation
from departments.models import Department, DoctorProfile
from patients.models import Patient
from prescriptions.models import Prescription, PrescriptionItem
from reports.services import (
    get_appointment_statistics,
    get_daily_activity,
    get_dashboard_report,
    get_department_statistics,
    get_doctor_statistics,
    get_patient_statistics,
    parse_and_validate_date_range,
)

User = get_user_model()


class ReportingAndAnalyticsTests(TestCase):
    """
    Automated test suite for Reports and Analytics Dashboard Backend (Step 9 - Part B).
    """

    def setUp(self):
        # 1. Departments
        self.dept_cardio = Department.objects.create(
            name="Cardiology",
            is_active=True,
        )
        self.dept_ortho = Department.objects.create(
            name="Orthopedics",
            is_active=True,
        )

        # 2. Doctor Users
        self.doc_user1 = User.objects.create_user(
            username="dr_clark_kent",
            email="kent@clinic.test",
            password="SecurePass123!",
            first_name="Clark",
            last_name="Kent",
            role=User.Role.DOCTOR,
        )
        self.doctor1 = DoctorProfile.objects.create(
            user=self.doc_user1,
            department=self.dept_cardio,
            specialization="Cardiology",
            qualification="MBBS, MD",
            is_active=True,
        )

        self.doc_user2 = User.objects.create_user(
            username="dr_bruce_wayne",
            email="wayne@clinic.test",
            password="SecurePass123!",
            first_name="Bruce",
            last_name="Wayne",
            role=User.Role.DOCTOR,
        )
        self.doctor2 = DoctorProfile.objects.create(
            user=self.doc_user2,
            department=self.dept_ortho,
            specialization="Orthopedics",
            qualification="MBBS, MS",
            is_active=True,
        )

        # 3. Staff Users
        self.admin_user = User.objects.create_user(
            username="admin_alfred",
            email="alfred@clinic.test",
            password="SecurePass123!",
            role=User.Role.ADMIN,
        )
        self.receptionist_user = User.objects.create_user(
            username="rec_lois",
            email="lois@clinic.test",
            password="SecurePass123!",
            role=User.Role.RECEPTIONIST,
        )

        # 4. Patients
        self.patient1 = Patient.objects.create(
            first_name="Barry",
            last_name="Allen",
            date_of_birth=date(1992, 1, 1),
            gender=Patient.Gender.MALE,
            contact_number="9876543210",
            is_active=True,
        )
        self.patient2 = Patient.objects.create(
            first_name="Diana",
            last_name="Prince",
            date_of_birth=date(1988, 3, 22),
            gender=Patient.Gender.FEMALE,
            contact_number="9876543211",
            is_active=True,
        )
        self.patient3 = Patient.objects.create(
            first_name="Victor",
            last_name="Stone",
            date_of_birth=date(1994, 6, 15),
            gender=Patient.Gender.MALE,
            contact_number="9876543212",
            is_active=False,  # Inactive patient
        )

        today = timezone.localdate()

        # 5. Consultations
        # Patient 1 with Doctor 1 (Today)
        self.consult1 = Consultation.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            chief_complaint="Palpitations",
            status=Consultation.Status.FINALIZED,
            consultation_date=timezone.now(),
        )

        # Patient 2 with Doctor 2 (Today)
        self.consult2 = Consultation.objects.create(
            patient=self.patient2,
            doctor=self.doctor2,
            chief_complaint="Knee ache",
            status=Consultation.Status.FINALIZED,
            consultation_date=timezone.now(),
        )

        # Walk-in consultation for Patient 1 (Yesterday, no appointment)
        yesterday_dt = timezone.now() - timedelta(days=1)
        self.walk_in_consult = Consultation.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            chief_complaint="Follow-up walk-in",
            status=Consultation.Status.DRAFT,
            consultation_date=yesterday_dt,
        )

        # 6. Appointments
        self.apt_completed = Appointment.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            appointment_date=today,
            start_time=time(22, 0),
            end_time=time(22, 30),
            status=Appointment.Status.COMPLETED,
        )
        self.apt_scheduled = Appointment.objects.create(
            patient=self.patient2,
            doctor=self.doctor2,
            appointment_date=today,
            start_time=time(22, 30),
            end_time=time(23, 0),
            status=Appointment.Status.SCHEDULED,
        )
        self.apt_cancelled = Appointment.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            appointment_date=today,
            start_time=time(23, 0),
            end_time=time(23, 30),
            status=Appointment.Status.CANCELLED,
        )

    # 1. Total registered patient count
    def test_total_registered_patient_count(self):
        stats = get_patient_statistics(preset="today")
        self.assertEqual(stats["total_patients"], 3)

    # 2. Active patient count
    def test_active_patient_count(self):
        stats = get_patient_statistics(preset="today")
        self.assertEqual(stats["active_patients"], 2)

    # 3. New patient registrations within date range
    def test_new_patient_registrations_within_date_range(self):
        stats = get_patient_statistics(preset="today")
        # Three patients created today in setUp
        self.assertEqual(stats["new_patients"], 3)

    # 4. Distinct patient footfall
    def test_distinct_patient_footfall(self):
        # Patient 1 and Patient 2 both had consultations today -> distinct count = 2
        stats_today = get_patient_statistics(preset="today")
        self.assertEqual(stats_today["patient_footfall"], 2)

        # In last 7 days, distinct patients with consultations are Patient 1 and Patient 2
        stats_7d = get_patient_statistics(preset="last_7_days")
        self.assertEqual(stats_7d["patient_footfall"], 2)

    # 5. Total appointment count
    def test_total_appointment_count(self):
        stats = get_appointment_statistics(preset="today")
        self.assertEqual(stats["total_appointments"], 3)

    # 6. Appointment counts grouped by status
    def test_appointment_counts_grouped_by_status(self):
        stats = get_appointment_statistics(preset="today")
        self.assertEqual(stats["completed_appointments"], 1)
        self.assertEqual(stats["scheduled_appointments"], 1)
        self.assertEqual(stats["cancelled_appointments"], 1)
        self.assertEqual(stats["confirmed_appointments"], 0)
        self.assertEqual(stats["no_show_appointments"], 0)

    # 7. Department-wise appointment statistics
    def test_department_wise_appointment_statistics(self):
        dept_stats = get_department_statistics(preset="today")
        cardio = next(d for d in dept_stats if d["department_name"] == "Cardiology")
        ortho = next(d for d in dept_stats if d["department_name"] == "Orthopedics")

        # Cardio had 1 completed + 1 cancelled = 2
        self.assertEqual(cardio["total_appointments"], 2)
        self.assertEqual(cardio["completed_appointments"], 1)
        self.assertEqual(cardio["cancelled_appointments"], 1)

        # Ortho had 1 scheduled = 1
        self.assertEqual(ortho["total_appointments"], 1)
        self.assertEqual(ortho["pending_appointments"], 1)

    # 8. Doctor-wise consultation statistics
    def test_doctor_wise_consultation_statistics(self):
        doc_stats = get_doctor_statistics(preset="today")
        kent = next(d for d in doc_stats if "Clark Kent" in d["doctor_name"])
        wayne = next(d for d in doc_stats if "Bruce Wayne" in d["doctor_name"])

        # Dr. Kent: 1 today + 1 yesterday = 2 total, 1 completed (finalized), 1 in range today
        self.assertEqual(kent["total_consultations"], 2)
        self.assertEqual(kent["completed_consultations"], 1)
        self.assertEqual(kent["consultations_in_range"], 1)

        # Dr. Wayne: 1 today = 1 total, 1 completed
        self.assertEqual(wayne["total_consultations"], 1)
        self.assertEqual(wayne["completed_consultations"], 1)

    # 9. Daily activity summaries
    def test_daily_activity_summaries(self):
        activity = get_daily_activity(preset="today")
        self.assertEqual(len(activity), 1)
        today_data = activity[0]
        self.assertEqual(today_data["total_appointments"], 3)
        self.assertEqual(today_data["completed_consultations"], 2)
        self.assertEqual(today_data["patient_footfall"], 2)

    # 10. Date-range filtering
    def test_date_range_filtering(self):
        d_start, d_end, s_dt, e_dt = parse_and_validate_date_range(preset="last_30_days")
        self.assertLessEqual(d_start, d_end)
        self.assertEqual((d_end - d_start).days, 29)

    # 11. Invalid date-range handling
    def test_invalid_date_range_handling(self):
        future = timezone.localdate() + timedelta(days=10)
        past = timezone.localdate() - timedelta(days=10)
        with self.assertRaises(ValidationError):
            parse_and_validate_date_range(start_date=str(future), end_date=str(past))

    # 12. Empty database handling
    def test_empty_database_handling(self):
        # Far past date with no activity
        past_start = "2000-01-01"
        past_end = "2000-01-07"
        pat_stats = get_patient_statistics(past_start, past_end, preset=None)
        self.assertEqual(pat_stats["new_patients"], 0)
        self.assertEqual(pat_stats["patient_footfall"], 0)

        apt_stats = get_appointment_statistics(past_start, past_end, preset=None)
        self.assertEqual(apt_stats["total_appointments"], 0)

    # 13. Correct role-based data filtering
    def test_role_based_data_filtering(self):
        # Admin gets all keys
        admin_rep = get_dashboard_report(self.admin_user, date_preset="today")
        self.assertEqual(admin_rep["role"], "ADMIN")
        self.assertIn("patient_statistics", admin_rep)
        self.assertIn("appointment_statistics", admin_rep)
        self.assertIn("department_statistics", admin_rep)
        self.assertIn("doctor_statistics", admin_rep)
        self.assertIn("daily_activity", admin_rep)

        # Receptionist gets admin/operational stats, not doctor stats
        rec_rep = get_dashboard_report(self.receptionist_user, date_preset="today")
        self.assertEqual(rec_rep["role"], "RECEPTIONIST")
        self.assertIn("patient_statistics", rec_rep)
        self.assertIn("appointment_statistics", rec_rep)
        self.assertIn("department_statistics", rec_rep)
        self.assertNotIn("doctor_statistics", rec_rep)

        # Doctor gets their own consultation data
        doc_rep = get_dashboard_report(self.doc_user1, date_preset="today")
        self.assertEqual(doc_rep["role"], "DOCTOR")
        self.assertIn("doctor_statistics", doc_rep)
        self.assertIn("Clark Kent", doc_rep["doctor_statistics"]["doctor_name"])

    # 14. Cancelled appointments not counted as completed visits
    def test_cancelled_appointments_not_counted_as_completed(self):
        apt_stats = get_appointment_statistics(preset="today")
        self.assertEqual(apt_stats["completed_appointments"], 1)
        self.assertEqual(apt_stats["cancelled_appointments"], 1)

    # 15. Walk-in consultations included in patient footfall
    def test_walk_in_consultations_included_in_patient_footfall(self):
        # Yesterday only had the walk_in_consultation for Patient 1
        yesterday = str(timezone.localdate() - timedelta(days=1))
        stats = get_patient_statistics(start_date=yesterday, end_date=yesterday, preset=None)
        # Walk-in consultation ensures footfall = 1 even with 0 appointments!
        self.assertEqual(stats["patient_footfall"], 1)

        apt_stats = get_appointment_statistics(start_date=yesterday, end_date=yesterday, preset=None)
        self.assertEqual(apt_stats["total_appointments"], 0)


class ReportsAndCSVExportTests(TestCase):
    """
    Test suite for Step 10D: Operational CSV report exports, date filters,
    spreadsheet formula injection protection, and access permissions.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin_steve",
            email="steve@clinic.test",
            password="SecurePass123!",
            role=User.Role.ADMIN,
        )
        self.receptionist = User.objects.create_user(
            username="rec_bucky",
            email="bucky@clinic.test",
            password="SecurePass123!",
            role=User.Role.RECEPTIONIST,
        )
        self.doc_user = User.objects.create_user(
            username="dr_sam_wilson",
            email="sam@clinic.test",
            password="SecurePass123!",
            role=User.Role.DOCTOR,
        )
        self.dept = Department.objects.create(name="Aviation Medicine", is_active=True)
        self.doctor = DoctorProfile.objects.create(
            user=self.doc_user,
            department=self.dept,
            specialization="Aviation Medicine",
            qualification="MBBS, MD",
            is_active=True,
        )
        # Create a patient with a tricky name that would trigger formula injection if not sanitized
        self.patient = Patient.objects.create(
            first_name="=cmd|' /C calc'!A0",
            last_name="FormulaTarget",
            date_of_birth=date(1990, 1, 1),
            gender=Patient.Gender.MALE,
            contact_number="9876543210",
            is_active=True,
        )
        today = timezone.localdate()
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=today,
            start_time=time(22, 0),
            end_time=time(22, 30),
            status=Appointment.Status.SCHEDULED,
        )

    # 33. Patient CSV report downloads correctly
    def test_patient_csv_export(self):
        self.client.login(username="admin_steve", password="SecurePass123!")
        response = self.client.get(reverse("reports:export_patients"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8-sig")
        self.assertIn("attachment; filename=", response["Content-Disposition"])
        content = response.content.decode("utf-8-sig")
        self.assertIn("MRN", content)
        self.assertIn("Patient Name", content)
        self.assertIn("FormulaTarget", content)

    # 34. Appointment CSV report downloads correctly
    def test_appointment_csv_export(self):
        self.client.login(username="admin_steve", password="SecurePass123!")
        response = self.client.get(reverse("reports:export_appointments") + "?preset=today")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8-sig")
        self.assertIn("Appointment Date", content)
        self.assertIn("Aviation Medicine", content)

    # 35. Department report downloads correctly
    def test_department_csv_export(self):
        self.client.login(username="admin_steve", password="SecurePass123!")
        response = self.client.get(reverse("reports:export_departments") + "?preset=today")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8-sig")
        self.assertIn("Aviation Medicine", content)
        self.assertIn("Total Appointments", content)

    # 36. Doctor workload report downloads correctly
    def test_doctor_workload_csv_export(self):
        self.client.login(username="admin_steve", password="SecurePass123!")
        response = self.client.get(reverse("reports:export_doctor_workload") + "?preset=today")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8-sig")
        self.assertIn("dr_sam_wilson", content)
        self.assertIn("Aviation Medicine", content)

    # 37. Date filters apply correctly
    def test_date_filters_on_reports(self):
        self.client.login(username="admin_steve", password="SecurePass123!")
        today_str = str(timezone.localdate())
        response = self.client.get(
            reverse("reports:export_appointments") + f"?start_date={today_str}&end_date={today_str}"
        )
        self.assertEqual(response.status_code, 200)

    # 38. CSV formula injection protection works
    def test_csv_formula_injection_sanitization(self):
        self.client.login(username="admin_steve", password="SecurePass123!")
        response = self.client.get(reverse("reports:export_patients"))
        content = response.content.decode("utf-8-sig")
        # Formula injection starting with '=' must be prefixed with a single quote: "'="
        self.assertIn("'=cmd|", content)

    # 39. Unauthorized users cannot download reports
    def test_unauthorized_users_cannot_export_csv(self):
        self.client.login(username="rec_bucky", password="SecurePass123!")
        response = self.client.get(reverse("reports:export_patients"))
        self.assertEqual(response.status_code, 403)

        r_apts = self.client.get(reverse("reports:export_appointments"))
        self.assertEqual(r_apts.status_code, 403)

