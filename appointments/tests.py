from datetime import date, time, timedelta
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from audit.models import AuditLog
from departments.models import Department, DoctorProfile
from patients.models import Patient
from .admin import AppointmentAdmin, AppointmentAdminForm
from .models import Appointment

User = get_user_model()


class AppointmentSchedulingTests(TestCase):
    """
    Comprehensive test suite for the Appointment Scheduling Module (Step 5).
    """

    def setUp(self):
        # 1. Clinic Department
        self.department = Department.objects.create(
            name="General Medicine",
            description="Primary outpatient care",
            is_active=True,
        )

        # 2. Active Doctor 1
        self.doc_user1 = User.objects.create_user(
            username="dr_gregory_house",
            email="house@clinic.test",
            password="SecureDoctorPass123!",
            first_name="Gregory",
            last_name="House",
            role=User.Role.DOCTOR,
        )
        self.doctor1 = DoctorProfile.objects.create(
            user=self.doc_user1,
            department=self.department,
            specialization="Diagnostic Medicine",
            qualification="MD",
            is_active=True,
        )

        # 3. Active Doctor 2
        self.doc_user2 = User.objects.create_user(
            username="dr_james_wilson",
            email="wilson@clinic.test",
            password="SecureDoctorPass123!",
            first_name="James",
            last_name="Wilson",
            role=User.Role.DOCTOR,
        )
        self.doctor2 = DoctorProfile.objects.create(
            user=self.doc_user2,
            department=self.department,
            specialization="Oncology",
            qualification="MD",
            is_active=True,
        )

        # 4. Inactive Doctor
        self.doc_user_inactive = User.objects.create_user(
            username="dr_eric_foreman",
            email="foreman@clinic.test",
            password="SecureDoctorPass123!",
            first_name="Eric",
            last_name="Foreman",
            role=User.Role.DOCTOR,
        )
        self.doctor_inactive = DoctorProfile.objects.create(
            user=self.doc_user_inactive,
            department=self.department,
            specialization="Neurology",
            qualification="MD",
            is_active=False,
        )

        # 5. Active Patients
        self.patient1 = Patient.objects.create(
            first_name="Arthur",
            last_name="Dent",
            date_of_birth=date(1982, 3, 11),
            gender=Patient.Gender.MALE,
            contact_number="9876543210",
            is_active=True,
        )
        self.patient2 = Patient.objects.create(
            first_name="Ford",
            last_name="Prefect",
            date_of_birth=date(1980, 7, 24),
            gender=Patient.Gender.MALE,
            contact_number="9876543211",
            is_active=True,
        )

        # 6. Inactive Patient
        self.patient_inactive = Patient.objects.create(
            first_name="Tricia",
            last_name="McMillan",
            date_of_birth=date(1985, 4, 15),
            gender=Patient.Gender.FEMALE,
            contact_number="9876543212",
            is_active=False,
        )

        # Standard Future Target Date (tomorrow)
        self.tomorrow = timezone.now().date() + timedelta(days=1)

    # 1. Successful Appointment Creation
    def test_successful_appointment_creation(self):
        """Verify that an appointment can be created successfully with valid parameters."""
        apt = Appointment.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            appointment_date=self.tomorrow,
            start_time=time(10, 0),
            end_time=time(10, 30),
            reason="Routine health checkup",
        )
        self.assertIsNotNone(apt.pk)
        self.assertEqual(apt.patient, self.patient1)
        self.assertEqual(apt.doctor, self.doctor1)
        self.assertEqual(apt.department, self.department)
        self.assertIn("Arthur Dent", str(apt))
        self.assertIn("Gregory House", str(apt))

    # 2. Default Status is SCHEDULED
    def test_default_status_is_scheduled(self):
        """Verify that new appointments default to SCHEDULED status."""
        apt = Appointment.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            appointment_date=self.tomorrow,
            start_time=time(11, 0),
            end_time=time(11, 30),
        )
        self.assertEqual(apt.status, Appointment.Status.SCHEDULED)

    # 3. Invalid Past Appointment Date is Rejected
    def test_invalid_past_appointment_date_rejected(self):
        """Verify that appointments booked for past dates raise ValidationError."""
        yesterday = timezone.now().date() - timedelta(days=1)
        with self.assertRaises(ValidationError) as ctx:
            Appointment.objects.create(
                patient=self.patient1,
                doctor=self.doctor1,
                appointment_date=yesterday,
                start_time=time(10, 0),
                end_time=time(10, 30),
            )
        self.assertIn("appointment_date", ctx.exception.message_dict)

    # 4. Today's Appointment with a Past Start Time is Rejected
    def test_today_appointment_with_past_start_time_rejected(self):
        """Verify that scheduling an appointment earlier today raises ValidationError."""
        today = timezone.localtime().date() if timezone.is_aware(timezone.now()) else timezone.now().date()
        past_time = time(0, 1)  # 00:01 AM has already passed today
        with self.assertRaises(ValidationError) as ctx:
            Appointment.objects.create(
                patient=self.patient1,
                doctor=self.doctor1,
                appointment_date=today,
                start_time=past_time,
                end_time=time(0, 30),
            )
        self.assertIn("start_time", ctx.exception.message_dict)

    # 5. End Time Must Be Later than Start Time
    def test_end_time_must_be_later_than_start_time(self):
        """Verify that zero duration or end_time <= start_time is rejected."""
        # Equal times (zero duration)
        with self.assertRaises(ValidationError) as ctx1:
            Appointment.objects.create(
                patient=self.patient1,
                doctor=self.doctor1,
                appointment_date=self.tomorrow,
                start_time=time(10, 0),
                end_time=time(10, 0),
            )
        self.assertIn("end_time", ctx1.exception.message_dict)

        # Inverted times
        with self.assertRaises(ValidationError) as ctx2:
            Appointment.objects.create(
                patient=self.patient1,
                doctor=self.doctor1,
                appointment_date=self.tomorrow,
                start_time=time(11, 0),
                end_time=time(10, 0),
            )
        self.assertIn("end_time", ctx2.exception.message_dict)

    # 6. Inactive Patients Cannot Receive New Appointments
    def test_inactive_patients_cannot_receive_new_appointments(self):
        """Verify that inactive patient records cannot receive new appointments."""
        with self.assertRaises(ValidationError) as ctx:
            Appointment.objects.create(
                patient=self.patient_inactive,
                doctor=self.doctor1,
                appointment_date=self.tomorrow,
                start_time=time(14, 0),
                end_time=time(14, 30),
            )
        self.assertIn("patient", ctx.exception.message_dict)

    # 7. Inactive Doctors Cannot Receive New Appointments
    def test_inactive_doctors_cannot_receive_new_appointments(self):
        """Verify that inactive doctors cannot receive new appointments."""
        with self.assertRaises(ValidationError) as ctx:
            Appointment.objects.create(
                patient=self.patient1,
                doctor=self.doctor_inactive,
                appointment_date=self.tomorrow,
                start_time=time(14, 0),
                end_time=time(14, 30),
            )
        self.assertIn("doctor", ctx.exception.message_dict)

    # 8. Same Doctor Cannot Receive Appointments at Identical Times
    def test_same_doctor_identical_time_rejected(self):
        """Verify that a doctor cannot be double-booked at the identical time slot."""
        Appointment.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            appointment_date=self.tomorrow,
            start_time=time(10, 0),
            end_time=time(10, 30),
        )
        with self.assertRaises(ValidationError) as ctx:
            Appointment.objects.create(
                patient=self.patient2,
                doctor=self.doctor1,
                appointment_date=self.tomorrow,
                start_time=time(10, 0),
                end_time=time(10, 30),
            )
        self.assertIn("start_time", ctx.exception.message_dict)

    # 9. Same Doctor Cannot Receive Overlapping Appointments
    def test_same_doctor_overlapping_appointments_rejected(self):
        """Verify that any overlapping time interval for the same doctor is rejected."""
        # Baseline appointment: 10:00 - 10:30
        Appointment.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            appointment_date=self.tomorrow,
            start_time=time(10, 0),
            end_time=time(10, 30),
        )

        # Overlap A: Starts inside (10:15 - 10:45)
        with self.assertRaises(ValidationError):
            Appointment.objects.create(
                patient=self.patient2,
                doctor=self.doctor1,
                appointment_date=self.tomorrow,
                start_time=time(10, 15),
                end_time=time(10, 45),
            )

        # Overlap B: Ends inside (09:45 - 10:15)
        with self.assertRaises(ValidationError):
            Appointment.objects.create(
                patient=self.patient2,
                doctor=self.doctor1,
                appointment_date=self.tomorrow,
                start_time=time(9, 45),
                end_time=time(10, 15),
            )

        # Overlap C: Encloses existing (09:30 - 11:00)
        with self.assertRaises(ValidationError):
            Appointment.objects.create(
                patient=self.patient2,
                doctor=self.doctor1,
                appointment_date=self.tomorrow,
                start_time=time(9, 30),
                end_time=time(11, 0),
            )

        # Overlap D: Inside existing (10:05 - 10:25)
        with self.assertRaises(ValidationError):
            Appointment.objects.create(
                patient=self.patient2,
                doctor=self.doctor1,
                appointment_date=self.tomorrow,
                start_time=time(10, 5),
                end_time=time(10, 25),
            )

    # 10. Back-to-Back Appointments are Allowed
    def test_back_to_back_appointments_allowed(self):
        """Verify that back-to-back appointments (start equals previous end) are allowed."""
        apt1 = Appointment.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            appointment_date=self.tomorrow,
            start_time=time(10, 0),
            end_time=time(10, 30),
        )
        # Exactly adjacent after: 10:30 - 11:00
        apt2 = Appointment.objects.create(
            patient=self.patient2,
            doctor=self.doctor1,
            appointment_date=self.tomorrow,
            start_time=time(10, 30),
            end_time=time(11, 0),
        )
        # Exactly adjacent before: 09:30 - 10:00
        apt3 = Appointment.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            appointment_date=self.tomorrow,
            start_time=time(9, 30),
            end_time=time(10, 0),
        )

        self.assertIsNotNone(apt1.pk)
        self.assertIsNotNone(apt2.pk)
        self.assertIsNotNone(apt3.pk)

    # 11. Different Doctors Can Have Appointments at the Same Time
    def test_different_doctors_same_time_allowed(self):
        """Verify that two distinct doctors can have concurrent appointments at the identical time slot."""
        apt1 = Appointment.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            appointment_date=self.tomorrow,
            start_time=time(10, 0),
            end_time=time(10, 30),
        )
        apt2 = Appointment.objects.create(
            patient=self.patient2,
            doctor=self.doctor2,  # Different doctor
            appointment_date=self.tomorrow,
            start_time=time(10, 0),
            end_time=time(10, 30),
        )
        self.assertIsNotNone(apt1.pk)
        self.assertIsNotNone(apt2.pk)
        self.assertEqual(apt1.start_time, apt2.start_time)

    # 12. Cancelled Appointments Do Not Block New Bookings
    def test_cancelled_appointments_do_not_block_new_bookings(self):
        """Verify that cancelling an appointment frees up the time slot for a new booking."""
        apt1 = Appointment.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            appointment_date=self.tomorrow,
            start_time=time(10, 0),
            end_time=time(10, 30),
        )
        apt1.cancel()
        self.assertEqual(apt1.status, Appointment.Status.CANCELLED)

        # Now booking the exact same time slot should succeed
        apt2 = Appointment.objects.create(
            patient=self.patient2,
            doctor=self.doctor1,
            appointment_date=self.tomorrow,
            start_time=time(10, 0),
            end_time=time(10, 30),
        )
        self.assertIsNotNone(apt2.pk)
        self.assertEqual(apt2.status, Appointment.Status.SCHEDULED)

    # 13. Appointment Status Can Be Updated
    def test_appointment_status_can_be_updated(self):
        """Verify status progression helper methods on the appointment model."""
        apt = Appointment.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            appointment_date=self.tomorrow,
            start_time=time(15, 0),
            end_time=time(15, 30),
        )
        self.assertEqual(apt.status, Appointment.Status.SCHEDULED)

        apt.confirm()
        self.assertEqual(apt.status, Appointment.Status.CONFIRMED)

        apt.start()
        self.assertEqual(apt.status, Appointment.Status.IN_PROGRESS)

        apt.complete()
        self.assertEqual(apt.status, Appointment.Status.COMPLETED)

        # Test NO_SHOW on another appointment
        apt_no_show = Appointment.objects.create(
            patient=self.patient2,
            doctor=self.doctor1,
            appointment_date=self.tomorrow,
            start_time=time(16, 0),
            end_time=time(16, 30),
        )
        apt_no_show.mark_no_show()
        self.assertEqual(apt_no_show.status, Appointment.Status.NO_SHOW)

    # 14. Appointment Admin Configuration
    def test_appointment_admin_configuration(self):
        """Verify that Appointment is registered in Django Admin with expected search, filters, and forms."""
        self.assertIn(Appointment, admin.site._registry)
        apt_admin = admin.site._registry[Appointment]
        self.assertIsInstance(apt_admin, AppointmentAdmin)

        # List display
        self.assertIn("get_patient_mrn", apt_admin.list_display)
        self.assertIn("get_patient_name", apt_admin.list_display)
        self.assertIn("get_doctor_name", apt_admin.list_display)
        self.assertIn("appointment_date", apt_admin.list_display)
        self.assertIn("status", apt_admin.list_display)

        # Filters and search
        self.assertIn("status", apt_admin.list_filter)
        self.assertIn("appointment_date", apt_admin.list_filter)
        self.assertIn("patient__patient_id", apt_admin.search_fields)
        self.assertIn("patient__first_name", apt_admin.search_fields)
        self.assertIn("doctor__user__first_name", apt_admin.search_fields)
        self.assertEqual(apt_admin.date_hierarchy, "appointment_date")

        # Admin form choices restrict to active patient and active doctor
        form = AppointmentAdminForm()
        patient_active_states = set(form.fields["patient"].queryset.values_list("is_active", flat=True))
        self.assertEqual(patient_active_states, {True})
        doctor_active_states = set(form.fields["doctor"].queryset.values_list("is_active", flat=True))
        self.assertEqual(doctor_active_states, {True})


class ReceptionistAppointmentWorkflowTests(TestCase):
    """
    Automated test suite for Receptionist Portal - Appointment Booking & Management (Step 10B).
    Covers access control, booking, department-doctor validation, double booking protection,
    listing/filters, and cancellations.
    """

    def setUp(self):
        self.client = Client()

        # Departments
        self.cardiology = Department.objects.create(name="Cardiology", is_active=True)
        self.neurology = Department.objects.create(name="Neurology", is_active=True)

        # Users
        self.receptionist = User.objects.create_user(
            username="rec_chloe",
            email="chloe@clinic.test",
            password="SecurePass123!",
            role=User.Role.RECEPTIONIST,
        )
        self.admin_user = User.objects.create_user(
            username="admin_nick",
            email="nick@clinic.test",
            password="SecurePass123!",
            role=User.Role.ADMIN,
        )
        self.doc_user = User.objects.create_user(
            username="doc_stephen",
            email="doc_stephen@clinic.test",
            password="SecurePass123!",
            first_name="Stephen",
            last_name="Strange",
            role=User.Role.DOCTOR,
        )

        # Doctors
        self.doctor = DoctorProfile.objects.create(
            user=self.doc_user,
            department=self.cardiology,
            specialization="Interventional Cardiology",
            qualification="MBBS, MD",
            is_active=True,
        )

        # Patient
        self.patient = Patient.objects.create(
            first_name="Peter",
            last_name="Parker",
            date_of_birth=date(2001, 8, 10),
            gender=Patient.Gender.MALE,
            contact_number="9876500003",
            is_active=True,
        )

        self.tomorrow = timezone.localdate() + timedelta(days=1)
        self.valid_booking_data = {
            "patient": self.patient.pk,
            "department": self.cardiology.pk,
            "doctor": self.doctor.pk,
            "appointment_date": str(self.tomorrow),
            "start_time": "10:00",
            "end_time": "10:30",
            "reason": "Routine heart health checkup",
            "notes": "First visit to clinic",
        }

    # 17. Unauthenticated request to appointment booking redirects to login
    def test_unauthenticated_booking_redirects_to_login(self):
        response = self.client.get(reverse("appointments:book"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    # 18. Doctor role gets 403 Forbidden on appointment booking
    def test_doctor_forbidden_on_appointment_booking(self):
        self.client.login(username="doc_stephen", password="SecurePass123!")
        response = self.client.get(reverse("appointments:book"))
        self.assertEqual(response.status_code, 403)

    # 19. Receptionist role accesses appointment booking successfully (HTTP 200)
    def test_receptionist_accesses_appointment_booking(self):
        self.client.login(username="rec_chloe", password="SecurePass123!")
        response = self.client.get(reverse("appointments:book"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "appointments/appointment_form.html")

    # 20. Receptionist books appointment with valid data; status is SCHEDULED; redirected
    def test_receptionist_books_appointment_successfully(self):
        self.client.login(username="rec_chloe", password="SecurePass123!")
        response = self.client.post(reverse("appointments:book"), self.valid_booking_data, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("appointments:list"))

        appointment = Appointment.objects.filter(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=self.tomorrow,
        ).first()
        self.assertIsNotNone(appointment)
        self.assertEqual(appointment.status, Appointment.Status.SCHEDULED)
        self.assertEqual(appointment.reason, "Routine heart health checkup")

    # 21. Audit log entry created on appointment booking
    def test_audit_log_created_on_appointment_booking(self):
        self.client.login(username="rec_chloe", password="SecurePass123!")
        self.client.post(reverse("appointments:book"), self.valid_booking_data)

        appointment = Appointment.objects.filter(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=self.tomorrow,
        ).first()
        self.assertIsNotNone(appointment)

        audit = AuditLog.objects.filter(
            actor=self.receptionist,
            action=AuditLog.Action.CREATE,
            object_id=str(appointment.pk),
        ).first()
        self.assertIsNotNone(audit)
        self.assertIn("Booked Appointment", audit.object_label)

    # 22. Booking with inactive patient is rejected with form error
    def test_booking_inactive_patient_rejected(self):
        inactive_patient = Patient.objects.create(
            first_name="Inactive",
            last_name="Patient",
            date_of_birth=date(1990, 1, 1),
            gender=Patient.Gender.OTHER,
            contact_number="9876500004",
            is_active=False,
        )
        self.client.login(username="rec_chloe", password="SecurePass123!")
        data = self.valid_booking_data.copy()
        data["patient"] = inactive_patient.pk

        response = self.client.post(reverse("appointments:book"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("patient", response.context["form"].errors)

    # 23. Booking with inactive doctor is rejected with form error
    def test_booking_inactive_doctor_rejected(self):
        inactive_doc_user = User.objects.create_user(
            username="doc_inactive",
            email="inactive@clinic.test",
            password="SecurePass123!",
            role=User.Role.DOCTOR,
        )
        inactive_doctor = DoctorProfile.objects.create(
            user=inactive_doc_user,
            department=self.cardiology,
            specialization="General Cardiology",
            qualification="MBBS",
            is_active=False,
        )
        self.client.login(username="rec_chloe", password="SecurePass123!")
        data = self.valid_booking_data.copy()
        data["doctor"] = inactive_doctor.pk

        response = self.client.post(reverse("appointments:book"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("doctor", response.context["form"].errors)

    # 24. Booking doctor that does not belong to selected department is rejected with form error
    def test_booking_doctor_wrong_department_rejected(self):
        self.client.login(username="rec_chloe", password="SecurePass123!")
        data = self.valid_booking_data.copy()
        data["department"] = self.neurology.pk  # Doctor belongs to Cardiology!

        response = self.client.post(reverse("appointments:book"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("doctor", response.context["form"].errors)

    # 25. Overlapping / double booking for same doctor is rejected
    def test_double_booking_same_doctor_rejected(self):
        # Create first appointment 10:00 - 10:30
        Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=self.tomorrow,
            start_time=time(10, 0),
            end_time=time(10, 30),
            status=Appointment.Status.SCHEDULED,
        )

        patient2 = Patient.objects.create(
            first_name="Miles",
            last_name="Morales",
            date_of_birth=date(2005, 5, 5),
            gender=Patient.Gender.MALE,
            contact_number="9876500005",
            is_active=True,
        )

        self.client.login(username="rec_chloe", password="SecurePass123!")
        # Try booking overlapping slot 10:15 - 10:45
        overlapping_data = {
            "patient": patient2.pk,
            "department": self.cardiology.pk,
            "doctor": self.doctor.pk,
            "appointment_date": str(self.tomorrow),
            "start_time": "10:15",
            "end_time": "10:45",
            "reason": "Second appointment overlapping",
        }
        response = self.client.post(reverse("appointments:book"), overlapping_data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Appointment.objects.filter(patient=patient2, appointment_date=self.tomorrow).exists()
        )

    # 26. Receptionist can cancel an appointment; status becomes CANCELLED; audit log created
    def test_receptionist_cancels_appointment(self):
        appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=self.tomorrow,
            start_time=time(14, 0),
            end_time=time(14, 30),
            status=Appointment.Status.SCHEDULED,
        )
        self.client.login(username="rec_chloe", password="SecurePass123!")
        response = self.client.post(reverse("appointments:cancel", args=[appointment.pk]), follow=True)
        self.assertEqual(response.status_code, 200)

        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CANCELLED)

        # Audit log verification
        audit = AuditLog.objects.filter(
            actor=self.receptionist,
            action=AuditLog.Action.CANCEL_APPOINTMENT,
            object_id=str(appointment.pk),
        ).first()
        self.assertIsNotNone(audit)

    # 27. Receptionist cannot cancel an already completed or cancelled appointment
    def test_cannot_cancel_already_completed_appointment(self):
        appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=self.tomorrow,
            start_time=time(15, 0),
            end_time=time(15, 30),
            status=Appointment.Status.COMPLETED,
        )
        self.client.login(username="rec_chloe", password="SecurePass123!")
        response = self.client.post(reverse("appointments:cancel", args=[appointment.pk]), follow=True)
        self.assertEqual(response.status_code, 200)

        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.COMPLETED)


class DoctorAppointmentQueueWorkflowTests(TestCase):
    """
    Automated test suite for Doctor Outpatient Appointment Queue & Status Transitions (Step 10C).
    """

    def setUp(self):
        self.client = Client()

        self.dept = Department.objects.create(name="Endocrinology", is_active=True)

        # Doctor A
        self.doc_user_a = User.objects.create_user(
            username="dr_alan_grant",
            email="alan@clinic.test",
            password="SecurePass123!",
            first_name="Alan",
            last_name="Grant",
            role=User.Role.DOCTOR,
        )
        self.doctor_a = DoctorProfile.objects.create(
            user=self.doc_user_a,
            department=self.dept,
            specialization="Endocrinology",
            qualification="MBBS, MD",
            is_active=True,
        )

        # Doctor B
        self.doc_user_b = User.objects.create_user(
            username="dr_ellie_sattler",
            email="ellie@clinic.test",
            password="SecurePass123!",
            first_name="Ellie",
            last_name="Sattler",
            role=User.Role.DOCTOR,
        )
        self.doctor_b = DoctorProfile.objects.create(
            user=self.doc_user_b,
            department=self.dept,
            specialization="Pediatric Endocrinology",
            qualification="MBBS, MD",
            is_active=True,
        )

        self.patient = Patient.objects.create(
            first_name="Ian",
            last_name="Malcolm",
            date_of_birth=date(1970, 3, 15),
            gender=Patient.Gender.MALE,
            contact_number="9876500333",
            is_active=True,
        )

        self.today = timezone.localdate()
        self.yesterday = self.today - timedelta(days=1)
        self.tomorrow = self.today + timedelta(days=1)

        # Doctor A's appointments
        self.apt_a_today = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor_a,
            appointment_date=self.today,
            start_time=time(22, 0),
            end_time=time(22, 30),
            status=Appointment.Status.SCHEDULED,
            reason="Diabetes review",
        )
        self.apt_a_upcoming = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor_a,
            appointment_date=self.tomorrow,
            start_time=time(11, 0),
            end_time=time(11, 30),
            status=Appointment.Status.CONFIRMED,
            reason="Follow-up",
        )
        self.apt_a_previous = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor_a,
            appointment_date=self.today,
            start_time=time(22, 30),
            end_time=time(23, 0),
            status=Appointment.Status.COMPLETED,
            reason="Initial intake",
        )
        Appointment.objects.filter(pk=self.apt_a_previous.pk).update(appointment_date=self.yesterday)
        self.apt_a_previous.refresh_from_db()

        # Doctor B's appointment
        self.apt_b = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor_b,
            appointment_date=self.today,
            start_time=time(23, 0),
            end_time=time(23, 30),
            status=Appointment.Status.SCHEDULED,
            reason="Doctor B confidential patient",
        )

    # 4. Doctor A cannot access Doctor B's appointments
    def test_doctor_cannot_access_or_update_another_doctors_appointment(self):
        self.client.login(username="dr_alan_grant", password="SecurePass123!")

        # Doctor A attempting to start consultation on Doctor B's appointment -> 403 Forbidden
        response_start = self.client.get(reverse("appointments:start_consultation", args=[self.apt_b.pk]))
        self.assertEqual(response_start.status_code, 403)

        # Doctor A attempting to update Doctor B's appointment status -> 403 Forbidden
        response_update = self.client.post(
            reverse("appointments:update_status", args=[self.apt_b.pk]),
            {"status": "CONFIRMED"},
        )
        self.assertEqual(response_update.status_code, 403)

    # 7. Doctor sees only their appointments in queue
    def test_doctor_sees_only_own_appointments_in_queue(self):
        self.client.login(username="dr_alan_grant", password="SecurePass123!")
        response = self.client.get(reverse("appointments:doctor_queue") + "?filter=all")
        self.assertEqual(response.status_code, 200)

        # Doctor A's appointments must be visible
        self.assertContains(response, "Diabetes review")
        # Doctor B's appointment MUST NOT be visible
        self.assertNotContains(response, "Doctor B confidential patient")

    # 8. Appointment filters work (today, upcoming, previous, status)
    def test_appointment_queue_filters(self):
        self.client.login(username="dr_alan_grant", password="SecurePass123!")

        # Filter today
        r_today = self.client.get(reverse("appointments:doctor_queue") + "?filter=today")
        self.assertContains(r_today, "Diabetes review")
        self.assertNotContains(r_today, "Initial intake")

        # Filter previous
        r_prev = self.client.get(reverse("appointments:doctor_queue") + "?filter=previous")
        self.assertContains(r_prev, "Initial intake")
        self.assertNotContains(r_prev, "Diabetes review")

        # Filter status
        r_status = self.client.get(reverse("appointments:doctor_queue") + "?filter=all&status=COMPLETED")
        self.assertContains(r_status, "Initial intake")
        self.assertNotContains(r_status, "Diabetes review")

    # 9. Appointment search works by MRN and patient name
    def test_appointment_queue_search(self):
        self.client.login(username="dr_alan_grant", password="SecurePass123!")

        # Search by patient name
        r_name = self.client.get(reverse("appointments:doctor_queue") + "?filter=all&q=Malcolm")
        self.assertContains(r_name, "Ian Malcolm")

        # Search non-matching
        r_none = self.client.get(reverse("appointments:doctor_queue") + "?filter=all&q=NonExistentPatient999")
        self.assertContains(r_none, "No Appointments Found")

    # 10. Appointment status updates follow permitted transitions
    def test_appointment_status_transitions(self):
        self.client.login(username="dr_alan_grant", password="SecurePass123!")

        # Confirm scheduled appointment
        self.client.post(
            reverse("appointments:update_status", args=[self.apt_a_today.pk]),
            {"status": "CONFIRMED"},
        )
        self.apt_a_today.refresh_from_db()
        self.assertEqual(self.apt_a_today.status, Appointment.Status.CONFIRMED)

        # Mark no-show
        self.client.post(
            reverse("appointments:update_status", args=[self.apt_a_today.pk]),
            {"status": "NO_SHOW"},
        )
        self.apt_a_today.refresh_from_db()
        self.assertEqual(self.apt_a_today.status, Appointment.Status.NO_SHOW)

        # Completed appointment cannot be casually reopened
        self.client.post(
            reverse("appointments:update_status", args=[self.apt_a_previous.pk]),
            {"status": "SCHEDULED"},
        )
        self.apt_a_previous.refresh_from_db()
        self.assertEqual(self.apt_a_previous.status, Appointment.Status.COMPLETED)


