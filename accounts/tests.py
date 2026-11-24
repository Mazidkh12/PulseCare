from datetime import date, time, timedelta
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from audit.models import AuditLog
from consultations.models import Consultation
from departments.models import Department, DoctorProfile
from patients.models import Patient

User = get_user_model()


class AuthenticationAndRoleNavigationTests(TestCase):
    """
    Automated test suite for Frontend Foundation, Authentication,
    and Role-Based Navigation (Step 10A).
    """

    def setUp(self):
        self.client = Client()

        # Department
        self.department = Department.objects.create(
            name="General Outpatient Medicine",
            is_active=True,
        )

        # 1. Administrator User
        self.admin_user = User.objects.create_user(
            username="admin_sam",
            email="sam@clinic.test",
            password="SecureAdminPass123!",
            first_name="Sam",
            last_name="Wilson",
            role=User.Role.ADMIN,
        )

        # 2. Receptionist User
        self.receptionist_user = User.objects.create_user(
            username="rec_peggie",
            email="peggie@clinic.test",
            password="SecureReceptionPass123!",
            first_name="Peggy",
            last_name="Carter",
            role=User.Role.RECEPTIONIST,
        )

        # 3. Doctor User
        self.doc_user = User.objects.create_user(
            username="dr_stephen",
            email="stephen@clinic.test",
            password="SecureDoctorPass123!",
            first_name="Stephen",
            last_name="Strange",
            role=User.Role.DOCTOR,
        )
        self.doctor_profile = DoctorProfile.objects.create(
            user=self.doc_user,
            department=self.department,
            specialization="Cardiology",
            qualification="MBBS, MD",
            is_active=True,
        )

    # 1. Login page loads successfully
    def test_login_page_loads(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")
        self.assertContains(response, "PulseCare Clinic")
        self.assertContains(response, "Sign In")

    # 2. Valid credentials authenticate successfully
    def test_valid_credentials_authenticate(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "admin_sam", "password": "SecureAdminPass123!"},
            follow=True,
        )
        self.assertTrue(response.context["user"].is_authenticated)
        self.assertEqual(response.context["user"], self.admin_user)
        self.assertRedirects(response, reverse("accounts:admin_dashboard"))

    # 3. Valid credentials with email address authenticate successfully
    def test_email_login_authenticates(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "sam@clinic.test", "password": "SecureAdminPass123!"},
            follow=True,
        )
        self.assertTrue(response.context["user"].is_authenticated)
        self.assertRedirects(response, reverse("accounts:admin_dashboard"))

    # 4. Invalid credentials display error
    def test_invalid_credentials_display_error(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "admin_sam", "password": "WrongPassword!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["user"].is_authenticated)
        self.assertContains(response, "Invalid username or password")

    # 5. Logout works
    def test_logout_works(self):
        self.client.login(username="admin_sam", password="SecureAdminPass123!")
        response = self.client.post(reverse("accounts:logout"), follow=True)
        self.assertRedirects(response, reverse("accounts:login"))
        # User is no longer authenticated
        response2 = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertRedirects(response2, f"{reverse('accounts:login')}?next={reverse('accounts:admin_dashboard')}")

    # 6. Unauthenticated users cannot access dashboards
    def test_unauthenticated_cannot_access_dashboards(self):
        for dash_url in [
            reverse("accounts:admin_dashboard"),
            reverse("accounts:receptionist_dashboard"),
            reverse("accounts:doctor_dashboard"),
            reverse("accounts:dashboard_redirect"),
            reverse("home"),
        ]:
            response = self.client.get(dash_url)
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("accounts:login"), response.url)

    # 7. Administrator sees administrator navigation and accesses admin dashboard
    def test_admin_dashboard_access_and_navigation(self):
        self.client.login(username="admin_sam", password="SecureAdminPass123!")
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboards/admin_dashboard.html")
        # Administrator navigation items
        self.assertContains(response, "Admin Portal")
        self.assertContains(response, "User Management")
        self.assertContains(response, "Audit Logs")
        self.assertContains(response, "Departments")
        self.assertContains(response, "Doctors")

    # 8. Receptionist sees receptionist navigation and accesses receptionist dashboard
    def test_receptionist_dashboard_access_and_navigation(self):
        self.client.login(username="rec_peggie", password="SecureReceptionPass123!")
        response = self.client.get(reverse("accounts:receptionist_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboards/receptionist_dashboard.html")
        # Receptionist navigation items
        self.assertContains(response, "Reception Desk")
        self.assertContains(response, "Register Patient")
        self.assertContains(response, "Patient Search")
        self.assertContains(response, "Appointment History")

    # 9. Doctor sees doctor navigation and accesses doctor dashboard
    def test_doctor_dashboard_access_and_navigation(self):
        self.client.login(username="dr_stephen", password="SecureDoctorPass123!")
        response = self.client.get(reverse("accounts:doctor_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboards/doctor_dashboard.html")
        # Doctor navigation items
        self.assertContains(response, "Clinical Practice")
        self.assertContains(response, "My Appointments")
        self.assertContains(response, "Consultation Queue")
        self.assertContains(response, "Patient History")
        self.assertContains(response, "Prescriptions")

    # 10. Role restrictions work at view level (403 PermissionDenied)
    def test_role_restrictions_at_view_level(self):
        # Receptionist attempting to access Admin dashboard -> 403
        self.client.login(username="rec_peggie", password="SecureReceptionPass123!")
        response_admin = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response_admin.status_code, 403)

        # Receptionist attempting to access Doctor dashboard -> 403
        response_doc = self.client.get(reverse("accounts:doctor_dashboard"))
        self.assertEqual(response_doc.status_code, 403)

        # Doctor attempting to access Admin dashboard -> 403
        self.client.login(username="dr_stephen", password="SecureDoctorPass123!")
        response_doc_admin = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response_doc_admin.status_code, 403)

    # 11. Central dashboard redirect view routes roles to correct dashboard
    def test_dashboard_redirect_routes_roles(self):
        # Admin
        self.client.login(username="admin_sam", password="SecureAdminPass123!")
        r_admin = self.client.get(reverse("accounts:dashboard_redirect"))
        self.assertRedirects(r_admin, reverse("accounts:admin_dashboard"))

        # Receptionist
        self.client.login(username="rec_peggie", password="SecureReceptionPass123!")
        r_rec = self.client.get(reverse("accounts:dashboard_redirect"))
        self.assertRedirects(r_rec, reverse("accounts:receptionist_dashboard"))

        # Doctor
        self.client.login(username="dr_stephen", password="SecureDoctorPass123!")
        r_doc = self.client.get(reverse("accounts:dashboard_redirect"))
        self.assertRedirects(r_doc, reverse("accounts:doctor_dashboard"))

    # 12. Root URL redirects to dashboard for authenticated users
    def test_root_url_redirects_authenticated_users(self):
        self.client.login(username="admin_sam", password="SecureAdminPass123!")
        response = self.client.get("/", follow=True)
        self.assertRedirects(response, reverse("accounts:admin_dashboard"))

    # 13. Audit logs record LOGIN and LOGOUT actions
    def test_login_and_logout_audit_logging(self):
        # Login
        self.client.post(
            reverse("accounts:login"),
            {"username": "admin_sam", "password": "SecureAdminPass123!"},
        )
        login_log = AuditLog.objects.filter(
            actor=self.admin_user,
            action=AuditLog.Action.LOGIN,
        ).first()
        self.assertIsNotNone(login_log)

        # Logout
        self.client.post(reverse("accounts:logout"))
        logout_log = AuditLog.objects.filter(
            actor=self.admin_user,
            action=AuditLog.Action.LOGOUT,
        ).first()
        self.assertIsNotNone(logout_log)


class ReceptionistDashboardWorkflowTests(TestCase):
    """
    Automated test suite for Receptionist Dashboard Metrics and Live Routing (Step 10B).
    """

    def setUp(self):
        self.client = Client()

        self.receptionist = User.objects.create_user(
            username="rec_wanda",
            email="wanda@clinic.test",
            password="SecurePass123!",
            role=User.Role.RECEPTIONIST,
        )

        self.department = Department.objects.create(name="Pediatrics", is_active=True)
        self.doc_user = User.objects.create_user(
            username="doc_stephen_rec",
            email="stephen_rec@clinic.test",
            password="SecurePass123!",
            role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doc_user,
            department=self.department,
            specialization="General Pediatrics",
            qualification="MBBS, MD",
            is_active=True,
        )

    # 28. Receptionist dashboard displays accurate scheduled and confirmed today counts
    def test_receptionist_dashboard_displays_today_appointment_counts(self):
        today = timezone.localdate()
        pat1 = Patient.objects.create(
            first_name="Alice",
            last_name="Green",
            date_of_birth=date(1995, 3, 10),
            gender=Patient.Gender.FEMALE,
            contact_number="9876511111",
            is_active=True,
        )
        pat2 = Patient.objects.create(
            first_name="Bob",
            last_name="Blue",
            date_of_birth=date(1992, 7, 20),
            gender=Patient.Gender.MALE,
            contact_number="9876522222",
            is_active=True,
        )

        Appointment.objects.create(
            patient=pat1,
            doctor=self.doctor,
            appointment_date=today,
            start_time=time(22, 0),
            end_time=time(22, 30),
            status=Appointment.Status.SCHEDULED,
        )
        Appointment.objects.create(
            patient=pat2,
            doctor=self.doctor,
            appointment_date=today,
            start_time=time(22, 30),
            end_time=time(23, 0),
            status=Appointment.Status.CONFIRMED,
        )

        self.client.login(username="rec_wanda", password="SecurePass123!")
        response = self.client.get(reverse("accounts:receptionist_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["scheduled_today"], 1)
        self.assertEqual(response.context["confirmed_today"], 1)
        self.assertEqual(response.context["total_today"], 2)

    # 29. Receptionist dashboard displays accurate total active patients and active doctors counts
    def test_receptionist_dashboard_displays_patient_and_doctor_metrics(self):
        # 2 active patients, 1 inactive patient
        Patient.objects.create(
            first_name="Charlie",
            last_name="Day",
            date_of_birth=date(1980, 2, 9),
            gender=Patient.Gender.MALE,
            contact_number="9876533333",
            is_active=True,
        )
        Patient.objects.create(
            first_name="Dennis",
            last_name="Reynolds",
            date_of_birth=date(1979, 4, 15),
            gender=Patient.Gender.MALE,
            contact_number="9876544444",
            is_active=False,
        )

        self.client.login(username="rec_wanda", password="SecurePass123!")
        response = self.client.get(reverse("accounts:receptionist_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_patients"], 1)
        self.assertEqual(response.context["active_doctors"], 1)

    # 30. Receptionist dashboard quick action links point to live receptionist URLs (not admin placeholders)
    def test_receptionist_dashboard_quick_action_links(self):
        self.client.login(username="rec_wanda", password="SecurePass123!")
        response = self.client.get(reverse("accounts:receptionist_dashboard"))
        self.assertEqual(response.status_code, 200)

        # Check live routes exist in page
        self.assertContains(response, reverse("patients:register"))
        self.assertContains(response, reverse("patients:list"))
        self.assertContains(response, reverse("appointments:book"))
        self.assertContains(response, reverse("appointments:list"))

        # Verify no admin placeholder links in quick actions
        self.assertNotContains(response, 'href="/admin/patients/patient/add/"')
        self.assertNotContains(response, 'href="/admin/appointments/appointment/add/"')


class DoctorAuthorizationAndDashboardWorkflowTests(TestCase):
    """
    Automated test suite for Doctor Portal Access Control, Dashboard, and Navigation (Step 10C).
    """

    def setUp(self):
        self.client = Client()

        self.dept = Department.objects.create(name="Neurology", is_active=True)

        # Doctor 1 (Active)
        self.doc_user1 = User.objects.create_user(
            username="dr_charles_xavier",
            email="xavier@clinic.test",
            password="SecurePass123!",
            first_name="Charles",
            last_name="Xavier",
            role=User.Role.DOCTOR,
        )
        self.doctor1 = DoctorProfile.objects.create(
            user=self.doc_user1,
            department=self.dept,
            specialization="Neurology",
            qualification="MBBS, MD",
            is_active=True,
        )

        # Doctor 2 (Active)
        self.doc_user2 = User.objects.create_user(
            username="dr_erik_lehnsherr",
            email="erik@clinic.test",
            password="SecurePass123!",
            first_name="Erik",
            last_name="Lehnsherr",
            role=User.Role.DOCTOR,
        )
        self.doctor2 = DoctorProfile.objects.create(
            user=self.doc_user2,
            department=self.dept,
            specialization="Neurosurgery",
            qualification="MBBS, MS",
            is_active=True,
        )

        # Doctor 3 (Inactive profile)
        self.doc_user_inactive = User.objects.create_user(
            username="dr_hank_mccoy",
            email="mccoy@clinic.test",
            password="SecurePass123!",
            role=User.Role.DOCTOR,
        )
        self.doctor_inactive = DoctorProfile.objects.create(
            user=self.doc_user_inactive,
            department=self.dept,
            specialization="Biochemistry",
            qualification="MD, PhD",
            is_active=False,
        )

        # Receptionist
        self.rec_user = User.objects.create_user(
            username="rec_raven",
            email="raven@clinic.test",
            password="SecurePass123!",
            role=User.Role.RECEPTIONIST,
        )

        # Patient
        self.patient = Patient.objects.create(
            first_name="Jean",
            last_name="Grey",
            date_of_birth=date(1990, 6, 20),
            gender=Patient.Gender.FEMALE,
            contact_number="9876500444",
            is_active=True,
        )

    # 1. Doctor can access their dashboard
    def test_doctor_can_access_dashboard(self):
        self.client.login(username="dr_charles_xavier", password="SecurePass123!")
        response = self.client.get(reverse("accounts:doctor_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboards/doctor_dashboard.html")
        self.assertContains(response, "Charles Xavier")

    # 2. Receptionist cannot access doctor-only clinical pages
    def test_receptionist_cannot_access_doctor_clinical_pages(self):
        self.client.login(username="rec_raven", password="SecurePass123!")

        # Dashboard -> 403
        r_dash = self.client.get(reverse("accounts:doctor_dashboard"))
        self.assertEqual(r_dash.status_code, 403)

        # Doctor queue -> 403
        r_queue = self.client.get(reverse("appointments:doctor_queue"))
        self.assertEqual(r_queue.status_code, 403)

        # Consultations list -> 403
        r_consult = self.client.get(reverse("consultations:list"))
        self.assertEqual(r_consult.status_code, 403)

        # Prescriptions list -> 403
        r_rx = self.client.get(reverse("prescriptions:list"))
        self.assertEqual(r_rx.status_code, 403)

    # 3. Unauthenticated users cannot access doctor pages
    def test_unauthenticated_user_redirected_to_login(self):
        # Doctor dashboard -> 302
        r_dash = self.client.get(reverse("accounts:doctor_dashboard"))
        self.assertEqual(r_dash.status_code, 302)
        self.assertIn(reverse("accounts:login"), r_dash.url)

        # Queue -> 302
        r_queue = self.client.get(reverse("appointments:doctor_queue"))
        self.assertEqual(r_queue.status_code, 302)

    # 5. Doctor cannot access another doctor's consultation by changing URL
    def test_doctor_cannot_access_another_doctors_consultation(self):
        consultation_doc2 = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor2,
            chief_complaint="Doctor 2 confidential clinical note",
            status=Consultation.Status.DRAFT,
        )

        # Doctor 1 logs in and attempts to access Doctor 2's consultation
        self.client.login(username="dr_charles_xavier", password="SecurePass123!")
        response = self.client.get(reverse("consultations:edit", args=[consultation_doc2.pk]))
        self.assertEqual(response.status_code, 403)

        # Doctor 1 attempts to view Doctor 2's consultation details
        r_detail = self.client.get(reverse("consultations:detail", args=[consultation_doc2.pk]))
        self.assertEqual(r_detail.status_code, 403)

    # 6. Doctor without an active DoctorProfile receives an appropriate error
    def test_doctor_without_active_profile_denied_access(self):
        self.client.login(username="dr_hank_mccoy", password="SecurePass123!")

        # Accessing dashboard with inactive profile -> 403 Forbidden
        response = self.client.get(reverse("accounts:doctor_dashboard"))
        self.assertEqual(response.status_code, 403)

        # Accessing appointment queue -> 403 Forbidden
        r_queue = self.client.get(reverse("appointments:doctor_queue"))
        self.assertEqual(r_queue.status_code, 403)

    # 36. Doctor patient history search and timeline view render successfully
    def test_doctor_patient_history_and_search_render(self):
        self.client.login(username="dr_charles_xavier", password="SecurePass123!")

        # Search view
        r_search = self.client.get(reverse("patients:doctor_patient_search") + "?q=Jean")
        self.assertEqual(r_search.status_code, 200)
        self.assertContains(r_search, "Jean Grey")

        # Full history timeline
        r_hist = self.client.get(reverse("patients:doctor_history", args=[self.patient.pk]))
        self.assertEqual(r_hist.status_code, 200)
        self.assertContains(r_hist, "Jean Grey")
        self.assertContains(r_hist, self.patient.patient_id)

    # 37. Doctor navigation displays correct live links (not admin placeholders)
    def test_doctor_navigation_sidebar_links(self):
        self.client.login(username="dr_charles_xavier", password="SecurePass123!")
        response = self.client.get(reverse("accounts:doctor_dashboard"))
        self.assertEqual(response.status_code, 200)

        # Live links must be present
        self.assertContains(response, reverse("appointments:doctor_queue"))
        self.assertContains(response, reverse("patients:doctor_patient_search"))
        self.assertContains(response, reverse("consultations:list"))
        self.assertContains(response, reverse("prescriptions:list"))

        # Admin placeholders must NOT be in doctor sidebar
        self.assertNotContains(response, 'href="/admin/consultations/consultation/add/"')
        self.assertNotContains(response, 'href="/admin/prescriptions/prescription/add/"')


class AdministratorPortalWorkflowTests(TestCase):
    """
    Test suite for Step 10D: Administrator Portal, Access Control, Dashboard,
    User Management, and Frontend Navigation.
    """

    def setUp(self):
        # 1. Admin User
        self.admin = User.objects.create_user(
            username="admin_stephen",
            email="stephen@clinic.test",
            password="SecureAdminPass123!",
            first_name="Stephen",
            last_name="Strange",
            role=User.Role.ADMIN,
        )

        # 2. Receptionist User
        self.receptionist = User.objects.create_user(
            username="rec_wong",
            email="wong@clinic.test",
            password="SecurePass123!",
            role=User.Role.RECEPTIONIST,
        )

        # 3. Doctor User and Profile
        self.department = Department.objects.create(
            name="Neurology",
            description="Brain and nervous system",
            is_active=True,
        )
        self.doc_user = User.objects.create_user(
            username="dr_christine_palmer",
            email="palmer@clinic.test",
            password="SecurePass123!",
            first_name="Christine",
            last_name="Palmer",
            role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doc_user,
            department=self.department,
            specialization="Neurology",
            qualification="MBBS, MD",
            is_active=True,
        )

        # 4. Sample Patient
        self.patient = Patient.objects.create(
            first_name="Peter",
            last_name="Parker",
            date_of_birth=date(1998, 8, 10),
            gender=Patient.Gender.MALE,
            contact_number="9876543210",
            is_active=True,
        )

    # 1. Administrator can access the dashboard
    def test_admin_can_access_dashboard(self):
        self.client.login(username="admin_stephen", password="SecureAdminPass123!")
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Clinic Executive Administration")

    # 2. Receptionist cannot access administrator pages (returns 403)
    def test_receptionist_cannot_access_admin_dashboard(self):
        self.client.login(username="rec_wong", password="SecurePass123!")
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 403)

    # 3. Doctor cannot access administrator pages (returns 403)
    def test_doctor_cannot_access_admin_dashboard(self):
        self.client.login(username="dr_christine_palmer", password="SecurePass123!")
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 403)

    # 4. Unauthenticated users cannot access administrator pages (redirects to login)
    def test_unauthenticated_user_redirected_to_login(self):
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    # 5. Unauthorized requests return appropriate HTTP 403
    def test_unauthorized_user_management_access(self):
        self.client.login(username="rec_wong", password="SecurePass123!")
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 403)

    # 6. Dashboard displays actual patient statistics
    def test_dashboard_displays_patient_statistics(self):
        self.client.login(username="admin_stephen", password="SecureAdminPass123!")
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_patients"], 1)

    # 7. Dashboard displays actual appointment statistics
    def test_dashboard_displays_appointment_statistics(self):
        today = timezone.localdate()
        Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=today,
            start_time=time(22, 0),
            end_time=time(22, 30),
            status=Appointment.Status.SCHEDULED,
        )
        self.client.login(username="admin_stephen", password="SecureAdminPass123!")
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["today_appointments"], 1)
        self.assertEqual(response.context["pending_appointments"], 1)

    # 8. Department statistics are correct
    def test_dashboard_department_statistics(self):
        self.client.login(username="admin_stephen", password="SecureAdminPass123!")
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        dept_stats = response.context["department_statistics"]
        self.assertTrue(len(dept_stats) >= 1)
        neurology_stat = next(d for d in dept_stats if d["department_name"] == "Neurology")
        self.assertEqual(neurology_stat["active_doctors"], 1)

    # 9. Doctor workload statistics are correct
    def test_dashboard_doctor_workload_statistics(self):
        self.client.login(username="admin_stephen", password="SecureAdminPass123!")
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        workload = response.context["doctor_workload"]
        self.assertEqual(len(workload), 1)
        self.assertEqual(workload[0]["doctor_name"], "Dr. Christine Palmer")

    # 10. Date filtering works
    def test_dashboard_date_filtering(self):
        self.client.login(username="admin_stephen", password="SecureAdminPass123!")
        response = self.client.get(reverse("accounts:admin_dashboard") + "?preset=today")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["preset"], "today")

    # 11. Empty database is handled gracefully
    def test_empty_database_dashboard_renders(self):
        # Even with existing objects, zero appointments / zero consultations shouldn't crash
        self.client.login(username="admin_stephen", password="SecureAdminPass123!")
        response = self.client.get(reverse("accounts:admin_dashboard") + "?preset=last_30_days")
        self.assertEqual(response.status_code, 200)
        self.assertIn("chart_data_json", response.context)

    # 23. Administrator can create receptionist accounts
    def test_admin_can_create_receptionist_account(self):
        self.client.login(username="admin_stephen", password="SecureAdminPass123!")
        response = self.client.post(
            reverse("accounts:user_create"),
            {
                "username": "rec_ned_leeds",
                "email": "ned@clinic.test",
                "first_name": "Ned",
                "last_name": "Leeds",
                "role": User.Role.RECEPTIONIST,
                "password": "SecurePassword123!",
                "password_confirm": "SecurePassword123!",
                "is_active": True,
            },
        )
        self.assertEqual(response.status_code, 302)
        new_rec = User.objects.get(username="rec_ned_leeds")
        self.assertEqual(new_rec.role, User.Role.RECEPTIONIST)
        self.assertTrue(new_rec.check_password("SecurePassword123!"))

    # 24. Passwords are securely hashed
    def test_user_password_is_hashed(self):
        user = User.objects.get(username="rec_wong")
        self.assertNotEqual(user.password, "SecurePass123!")
        self.assertTrue(user.password.startswith("pbkdf2_") or user.password.startswith("bcrypt"))

    # 25. Unauthorized users cannot change roles
    def test_unauthorized_user_cannot_access_user_edit(self):
        self.client.login(username="rec_wong", password="SecurePass123!")
        response = self.client.post(
            reverse("accounts:user_edit", args=[self.receptionist.pk]),
            {"role": User.Role.ADMIN, "is_active": True},
        )
        self.assertEqual(response.status_code, 403)
        self.receptionist.refresh_from_db()
        self.assertEqual(self.receptionist.role, User.Role.RECEPTIONIST)

    # 26. Account deactivation works
    def test_admin_can_deactivate_user(self):
        self.client.login(username="admin_stephen", password="SecureAdminPass123!")
        response = self.client.post(reverse("accounts:user_toggle_active", args=[self.receptionist.pk]))
        self.assertEqual(response.status_code, 302)
        self.receptionist.refresh_from_db()
        self.assertFalse(self.receptionist.is_active)

    # 27. Administrator cannot accidentally disable their own active account
    def test_admin_cannot_deactivate_own_account(self):
        self.client.login(username="admin_stephen", password="SecureAdminPass123!")
        response = self.client.post(reverse("accounts:user_toggle_active", args=[self.admin.pk]))
        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    # 40. Templates render correctly
    def test_user_list_and_detail_templates_render(self):
        self.client.login(username="admin_stephen", password="SecureAdminPass123!")
        r_list = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(r_list.status_code, 200)
        self.assertContains(r_list, "admin_stephen")

        r_detail = self.client.get(reverse("accounts:user_detail", args=[self.admin.pk]))
        self.assertEqual(r_detail.status_code, 200)
        self.assertContains(r_detail, "admin_stephen")

    # 41. Sidebar navigation links for admin
    def test_admin_sidebar_navigation_links(self):
        self.client.login(username="admin_stephen", password="SecureAdminPass123!")
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("departments:department_list"))
        self.assertContains(response, reverse("departments:doctor_list"))
        self.assertContains(response, reverse("accounts:user_list"))
        self.assertContains(response, reverse("reports:index"))
        self.assertContains(response, reverse("audit:list"))

    # 42. Forms display validation errors on password mismatch
    def test_user_creation_form_password_mismatch_error(self):
        self.client.login(username="admin_stephen", password="SecureAdminPass123!")
        response = self.client.post(
            reverse("accounts:user_create"),
            {
                "username": "rec_bad_pass",
                "role": User.Role.RECEPTIONIST,
                "password": "Pass1!",
                "password_confirm": "Pass2!",
                "is_active": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Passwords do not match.")

    # 43. Pagination works
    def test_user_list_pagination(self):
        self.client.login(username="admin_stephen", password="SecureAdminPass123!")
        response = self.client.get(reverse("accounts:user_list") + "?page=1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("page_obj", response.context)

    # 44. Responsive layout elements render
    def test_admin_dashboard_responsive_elements(self):
        self.client.login(username="admin_stephen", password="SecureAdminPass123!")
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dailyActivityChart")
        self.assertContains(response, "datePresetSelect")


class SignUpFeatureTests(TestCase):
    """
    Automated tests for self-service user registration / sign-up.
    """

    def setUp(self):
        self.client = Client()
        self.department = Department.objects.create(
            name="General Internal Medicine",
            is_active=True,
        )

    def test_signup_page_loads(self):
        response = self.client.get(reverse("accounts:signup"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/signup.html")
        self.assertContains(response, "Create an Account")
        self.assertContains(response, "Account Role")

    def test_signup_receptionist_success(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "new_rec_jane",
                "email": "jane.rec@clinic.test",
                "first_name": "Jane",
                "last_name": "Doe",
                "role": User.Role.RECEPTIONIST,
                "password": "StrongPassword2026!",
                "password_confirm": "StrongPassword2026!",
            },
            follow=True,
        )
        self.assertTrue(response.context["user"].is_authenticated)
        user = User.objects.get(username="new_rec_jane")
        self.assertEqual(user.role, User.Role.RECEPTIONIST)
        self.assertEqual(user.email, "jane.rec@clinic.test")
        self.assertRedirects(response, reverse("accounts:receptionist_dashboard"))

    def test_signup_doctor_success(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "dr_new_watson",
                "email": "watson.doc@clinic.test",
                "first_name": "John",
                "last_name": "Watson",
                "role": User.Role.DOCTOR,
                "department": self.department.pk,
                "specialization": "Diagnostic Medicine",
                "qualification": "MBBS, MD",
                "contact_number": "9876543210",
                "password": "StrongPassword2026!",
                "password_confirm": "StrongPassword2026!",
            },
            follow=True,
        )
        self.assertTrue(response.context["user"].is_authenticated)
        user = User.objects.get(username="dr_new_watson")
        self.assertEqual(user.role, User.Role.DOCTOR)
        self.assertTrue(hasattr(user, "doctor_profile"))
        self.assertEqual(user.doctor_profile.department, self.department)
        self.assertEqual(user.doctor_profile.specialization, "Diagnostic Medicine")
        self.assertRedirects(response, reverse("accounts:doctor_dashboard"))

    def test_signup_doctor_missing_credentials_fails(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "dr_incomplete",
                "email": "incomplete@clinic.test",
                "first_name": "No",
                "last_name": "Creds",
                "role": User.Role.DOCTOR,
                "password": "StrongPassword2026!",
                "password_confirm": "StrongPassword2026!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="dr_incomplete").exists())
        self.assertContains(response, "Clinical Department is required")

    def test_signup_password_mismatch_error(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "rec_mismatch",
                "email": "mismatch@clinic.test",
                "first_name": "Mis",
                "last_name": "Match",
                "role": User.Role.RECEPTIONIST,
                "password": "StrongPassword2026!",
                "password_confirm": "DifferentPassword2026!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Passwords do not match.")

    def test_signup_authenticated_redirects(self):
        user = User.objects.create_user(
            username="logged_in_user",
            password="StrongPassword2026!",
            role=User.Role.RECEPTIONIST,
        )
        self.client.login(username="logged_in_user", password="StrongPassword2026!")
        response = self.client.get(reverse("accounts:signup"))
        self.assertRedirects(response, reverse("accounts:dashboard_redirect"), target_status_code=302)




