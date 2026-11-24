"""
Comprehensive End-to-End Workflow & Security Hardening Tests (Step 11).

Covers:
1. Full Receptionist Workflow: Patient Registration -> Patient Search -> Appointment Booking.
2. Full Doctor Workflow: Queue Inspection -> Clinical Case-Taking -> Vitals & BMI -> Diagnoses -> Consultation Finalization -> Prescription Issuance -> Patient Timeline.
3. Full Administrator Workflow: Dashboard Oversight -> Department Management -> Doctor & Staff Provisioning -> Reports & Audit Trail.
4. Cross-Role Authorization and Data Isolation.
5. CSRF and Security Error Handling.
"""
from datetime import date, time, timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from audit.models import AuditLog
from consultations.models import Consultation, Diagnosis, VitalSign
from departments.models import Department, DoctorProfile
from patients.models import Patient
from prescriptions.models import Prescription, PrescriptionItem

User = get_user_model()


class EndToEndClinicWorkflowsTest(TestCase):
    """
    Simulates real clinic operations across Receptionist, Doctor, and Administrator roles.
    """

    def setUp(self):
        # 1. Administrator User
        self.admin_user = User.objects.create_user(
            username="admin_e2e",
            email="admin.e2e@clinic.test",
            password="SecureAdminPass123!",
            first_name="Admin",
            last_name="Director",
            role=User.Role.ADMIN,
        )

        # 2. Specialty Departments
        self.cardiology = Department.objects.create(
            name="Cardiology E2E",
            description="Cardiac specialty clinic",
            is_active=True,
        )
        self.pediatrics = Department.objects.create(
            name="Pediatrics E2E",
            description="Child health clinic",
            is_active=True,
        )

        # 3. Doctor A (Cardiologist)
        self.doc_a_user = User.objects.create_user(
            username="dr_meredith_grey",
            email="meredith@clinic.test",
            password="SecurePass123!",
            first_name="Meredith",
            last_name="Grey",
            role=User.Role.DOCTOR,
        )
        self.doctor_a = DoctorProfile.objects.create(
            user=self.doc_a_user,
            department=self.cardiology,
            specialization="Interventional Cardiology",
            qualification="MBBS, MD",
            is_active=True,
        )

        # 4. Doctor B (Pediatrician)
        self.doc_b_user = User.objects.create_user(
            username="dr_alex_karev",
            email="alex@clinic.test",
            password="SecurePass123!",
            first_name="Alex",
            last_name="Karev",
            role=User.Role.DOCTOR,
        )
        self.doctor_b = DoctorProfile.objects.create(
            user=self.doc_b_user,
            department=self.pediatrics,
            specialization="Pediatric Medicine",
            qualification="MBBS, DCH",
            is_active=True,
        )

        # 5. Receptionist User
        self.receptionist_user = User.objects.create_user(
            username="rec_april_kepner",
            email="april@clinic.test",
            password="SecurePass123!",
            first_name="April",
            last_name="Kepner",
            role=User.Role.RECEPTIONIST,
        )

    # ==========================================================================
    # 1. RECEPTIONIST COMPLETE WORKFLOW
    # ==========================================================================

    def test_complete_receptionist_workflow(self):
        """
        Tests receptionist login, patient registration, MRN verification,
        patient search, profile inspection, and appointment booking.
        """
        client = Client()

        # Step 1: Login as Receptionist
        login_res = client.post(
            reverse("accounts:login"),
            {"username": "rec_april_kepner", "password": "SecurePass123!"},
        )
        self.assertEqual(login_res.status_code, 302)

        # Step 2: Register a new patient
        reg_res = client.post(
            reverse("patients:register"),
            {
                "first_name": "Jackson",
                "last_name": "Avery",
                "date_of_birth": "1985-04-12",
                "gender": "MALE",
                "blood_group": "O+",
                "contact_number": "9876543210",
                "email": "jackson.avery@example.com",
                "address": "123 Medical Center Blvd",
                "city": "Metropolis",
                "state": "State",
                "pincode": "123456",
                "emergency_contact_name": "Catherine Avery",
                "emergency_contact_number": "9876543211",
            },
        )
        self.assertEqual(reg_res.status_code, 302)

        # Step 3: Verify unique MRN generation (P-YYYY-NNNN format)
        patient = Patient.objects.get(first_name="Jackson", last_name="Avery")
        self.assertTrue(patient.patient_id.startswith("P-"))
        self.assertIn(str(timezone.now().year), patient.patient_id)

        # Step 4: Search for registered patient
        search_res = client.get(reverse("patients:list") + "?q=Jackson")
        self.assertEqual(search_res.status_code, 200)
        self.assertContains(search_res, "Jackson Avery")
        self.assertContains(search_res, patient.patient_id)

        # Step 5: Open patient details page
        detail_res = client.get(reverse("patients:detail", args=[patient.pk]))
        self.assertEqual(detail_res.status_code, 200)
        self.assertContains(detail_res, "Catherine Avery")

        # Step 6: Book an appointment for the patient
        tomorrow = timezone.localdate() + timedelta(days=1)
        book_res = client.post(
            reverse("appointments:book"),
            {
                "patient": patient.pk,
                "department": self.cardiology.pk,
                "doctor": self.doctor_a.pk,
                "appointment_date": str(tomorrow),
                "start_time": "14:00",
                "end_time": "14:30",
                "reason": "Cardiac checkup",
            },
        )
        self.assertEqual(book_res.status_code, 302)

        # Step 7: Verify appointment appears in appointment list
        apt_list_res = client.get(reverse("appointments:list") + f"?q={patient.patient_id}")
        self.assertEqual(apt_list_res.status_code, 200)
        self.assertContains(apt_list_res, "Cardiac checkup")
        self.assertContains(apt_list_res, "Scheduled")

        # Step 8: Verify appointment status and model validation
        appointment = Appointment.objects.get(patient=patient)
        self.assertEqual(appointment.status, Appointment.Status.SCHEDULED)
        self.assertEqual(appointment.doctor, self.doctor_a)

    # ==========================================================================
    # 2. DOCTOR COMPLETE WORKFLOW
    # ==========================================================================

    def test_complete_doctor_workflow(self):
        """
        Tests doctor login, queue viewing, consultation start, case taking,
        vitals & live BMI, primary/secondary diagnoses, finalization,
        multi-item prescription builder, prescription issuance, and timeline history.
        """
        # Setup: Pre-register patient and scheduled appointment for Doctor A
        patient = Patient.objects.create(
            first_name="Callie",
            last_name="Torres",
            date_of_birth=date(1982, 5, 20),
            gender=Patient.Gender.FEMALE,
            contact_number="9876512345",
            is_active=True,
        )
        tomorrow = timezone.localdate() + timedelta(days=1)
        appointment = Appointment.objects.create(
            patient=patient,
            doctor=self.doctor_a,
            appointment_date=tomorrow,
            start_time=time(10, 0),
            end_time=time(10, 30),
            status=Appointment.Status.CONFIRMED,
            reason="Chest discomfort and palpitations",
        )

        client = Client()

        # Step 1: Log in as assigned Doctor A
        login_res = client.post(
            reverse("accounts:login"),
            {"username": "dr_meredith_grey", "password": "SecurePass123!"},
        )
        self.assertEqual(login_res.status_code, 302)

        # Step 2: Open doctor dashboard
        dash_res = client.get(reverse("accounts:doctor_dashboard"))
        self.assertEqual(dash_res.status_code, 200)
        self.assertContains(dash_res, "Dr. Meredith Grey")

        # Step 3: View outpatient queue
        queue_res = client.get(reverse("appointments:doctor_queue") + "?filter=upcoming")
        self.assertEqual(queue_res.status_code, 200)
        self.assertContains(queue_res, "Callie Torres")

        # Step 4: Open patient medical history timeline
        hist_res = client.get(reverse("patients:doctor_history", args=[patient.pk]))
        self.assertEqual(hist_res.status_code, 200)
        self.assertContains(hist_res, "Callie Torres")

        # Step 5: Start consultation (transitions appointment to IN_PROGRESS and creates DRAFT)
        start_res = client.get(reverse("appointments:start_consultation", args=[appointment.pk]))
        self.assertEqual(start_res.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.IN_PROGRESS)

        consultation = Consultation.objects.get(appointment=appointment)
        self.assertEqual(consultation.status, Consultation.Status.DRAFT)

        # Step 6: Enter case-taking information
        case_res = client.post(
            reverse("consultations:edit", args=[consultation.pk]),
            {
                "action": "save_case",
                "chief_complaint": "Recurrent palpitations for 2 weeks",
                "history_of_present_illness": "Episodes occur after mild exertion, no syncope",
                "past_medical_history": "Mild hypertension",
                "physical_examination": "S1 S2 normal, no murmurs, chest clear",
                "treatment_plan": "Lifestyle modification, ECG, Metoprolol",
            },
        )
        self.assertEqual(case_res.status_code, 302)
        consultation.refresh_from_db()
        self.assertEqual(consultation.chief_complaint, "Recurrent palpitations for 2 weeks")

        # Step 7: Record vital signs (Height 170 cm, Weight 68 kg -> BMI = 68 / 1.7^2 = 23.53)
        vitals_res = client.post(
            reverse("consultations:edit", args=[consultation.pk]),
            {
                "action": "save_vitals",
                "chief_complaint": consultation.chief_complaint,
                "systolic_bp": "120",
                "diastolic_bp": "80",
                "pulse_rate": "76",
                "respiratory_rate": "16",
                "temperature": "37.0",
                "spo2": "99.0",
                "height": "170.0",
                "weight": "68.0",
            },
        )
        self.assertEqual(vitals_res.status_code, 302)
        vitals = VitalSign.objects.get(consultation=consultation)
        self.assertIsNotNone(vitals.bmi)
        self.assertAlmostEqual(float(vitals.bmi), 23.53, places=1)

        # Step 8: Add Primary and Secondary diagnoses
        diag1_res = client.post(
            reverse("consultations:edit", args=[consultation.pk]),
            {
                "action": "add_diagnosis",
                "diagnosis_name": "Supraventricular Tachycardia",
                "diagnosis_code": "I47.1",
                "diagnosis_type": "PRIMARY",
                "description": "Episodic paroxysmal palpitations",
            },
        )
        self.assertEqual(diag1_res.status_code, 302)

        diag2_res = client.post(
            reverse("consultations:edit", args=[consultation.pk]),
            {
                "action": "add_diagnosis",
                "diagnosis_name": "Essential Hypertension",
                "diagnosis_code": "I10",
                "diagnosis_type": "SECONDARY",
                "description": "Controlled blood pressure",
            },
        )
        self.assertEqual(diag2_res.status_code, 302)
        self.assertEqual(consultation.diagnoses.count(), 2)

        # Step 9: Save and Finalize the consultation
        finalize_res = client.post(reverse("consultations:finalize", args=[consultation.pk]))
        self.assertEqual(finalize_res.status_code, 302)
        consultation.refresh_from_db()
        self.assertEqual(consultation.status, Consultation.Status.FINALIZED)

        # Step 10 & 11: Create a Prescription with multiple items and Issue it
        rx_post_data = {
            "action": "issue",
            "general_instructions": "Take medications after meals with water.",
            "items-TOTAL_FORMS": "2",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            # Item 0
            "items-0-medicine_name": "Metoprolol Succinate",
            "items-0-dosage_form": "TABLET",
            "items-0-strength": "25 mg",
            "items-0-dosage": "1 tablet",
            "items-0-frequency": "OD",
            "items-0-duration": 14,
            "items-0-intake_timing": "AFTER_FOOD",
            "items-0-special_instructions": "Morning after breakfast",
            # Item 1
            "items-1-medicine_name": "Amlodipine Besylate",
            "items-1-dosage_form": "TABLET",
            "items-1-strength": "5 mg",
            "items-1-dosage": "1 tablet",
            "items-1-frequency": "OD",
            "items-1-duration": 14,
            "items-1-intake_timing": "AFTER_FOOD",
            "items-1-special_instructions": "Night before sleep",
        }
        rx_res = client.post(
            reverse("prescriptions:create", args=[consultation.pk]),
            rx_post_data,
        )
        self.assertEqual(rx_res.status_code, 302)

        prescription = Prescription.objects.get(consultation=consultation)
        self.assertEqual(prescription.status, Prescription.Status.ISSUED)
        self.assertEqual(prescription.items.count(), 2)

        # Step 12: Appointment automatically marked COMPLETED on prescription issuance
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.COMPLETED)

        # Step 13: Verify all clinical records appear in patient timeline history
        history_res = client.get(reverse("patients:doctor_history", args=[patient.pk]))
        self.assertEqual(history_res.status_code, 200)
        self.assertContains(history_res, "Supraventricular Tachycardia")
        self.assertContains(history_res, "Essential Hypertension")
        self.assertContains(history_res, "Metoprolol Succinate")
        self.assertContains(history_res, "Amlodipine Besylate")
        self.assertContains(history_res, prescription.prescription_number)

    # ==========================================================================
    # 3. ADMINISTRATOR COMPLETE WORKFLOW
    # ==========================================================================

    def test_complete_administrator_workflow(self):
        """
        Tests administrator login, executive dashboard verification, department management,
        doctor account provisioning, receptionist creation, reports exploration, and audit trail.
        """
        client = Client()

        # Step 1: Login as Administrator
        login_res = client.post(
            reverse("accounts:login"),
            {"username": "admin_e2e", "password": "SecureAdminPass123!"},
        )
        self.assertEqual(login_res.status_code, 302)

        # Step 2: Open executive dashboard and verify statistics
        dash_res = client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(dash_res.status_code, 200)
        self.assertContains(dash_res, "Clinic Executive Administration")
        self.assertIn("total_patients", dash_res.context)
        self.assertIn("active_doctors", dash_res.context)

        # Step 3: Create and manage a department
        dept_res = client.post(
            reverse("departments:department_create"),
            {
                "name": "Dermatology E2E",
                "description": "Skin and cosmetic clinic",
                "is_active": True,
            },
        )
        self.assertEqual(dept_res.status_code, 302)
        new_dept = Department.objects.get(name="Dermatology E2E")
        self.assertTrue(new_dept.is_active)

        # Step 4: Create a doctor account and assign to the new department
        doc_create_res = client.post(
            reverse("departments:doctor_create"),
            {
                "username": "dr_mark_sloan",
                "email": "sloan@clinic.test",
                "first_name": "Mark",
                "last_name": "Sloan",
                "password": "SecureDoctorPass123!",
                "password_confirm": "SecureDoctorPass123!",
                "department": new_dept.pk,
                "specialization": "Dermatology & Plastic Surgery",
                "qualification": "MD, FACS",
                "contact_number": "9876599999",
                "is_active": True,
            },
        )
        self.assertEqual(doc_create_res.status_code, 302)
        sloan_user = User.objects.get(username="dr_mark_sloan")
        self.assertEqual(sloan_user.role, User.Role.DOCTOR)
        self.assertTrue(sloan_user.check_password("SecureDoctorPass123!"))
        self.assertEqual(sloan_user.doctor_profile.department, new_dept)

        # Step 5: Create a receptionist account
        rec_create_res = client.post(
            reverse("accounts:user_create"),
            {
                "username": "rec_lexie_grey",
                "email": "lexie@clinic.test",
                "first_name": "Lexie",
                "last_name": "Grey",
                "role": User.Role.RECEPTIONIST,
                "password": "SecureReceptionPass123!",
                "password_confirm": "SecureReceptionPass123!",
                "is_active": True,
            },
        )
        self.assertEqual(rec_create_res.status_code, 302)
        lexie_user = User.objects.get(username="rec_lexie_grey")
        self.assertEqual(lexie_user.role, User.Role.RECEPTIONIST)

        # Step 6: View patients, appointments, and report hubs
        self.assertEqual(client.get(reverse("patients:list")).status_code, 200)
        self.assertEqual(client.get(reverse("appointments:list")).status_code, 200)
        self.assertEqual(client.get(reverse("reports:index")).status_code, 200)

        # Step 7: Export operational CSV report
        csv_res = client.get(reverse("reports:export_departments") + "?preset=last_7_days")
        self.assertEqual(csv_res.status_code, 200)
        self.assertEqual(csv_res["Content-Type"], "text/csv; charset=utf-8-sig")
        content = csv_res.content.decode("utf-8-sig")
        self.assertIn("Dermatology E2E", content)

        # Step 8: View audit logs and verify administrative actions were recorded
        audit_res = client.get(reverse("audit:list"))
        self.assertEqual(audit_res.status_code, 200)
        self.assertContains(audit_res, "Dermatology E2E")
        self.assertContains(audit_res, "Mark Sloan")

    # ==========================================================================
    # 4. CROSS-ROLE AUTHORIZATION AND DATA ISOLATION
    # ==========================================================================

    def test_cross_role_authorization_and_isolation(self):
        """
        Enforces strict authorization:
        - Anonymous users cannot access private pages.
        - Receptionists cannot access doctor consultation or admin pages.
        - Doctors cannot access admin pages.
        - Doctor A cannot access or modify Doctor B's consultation.
        """
        # Create consultation belonging strictly to Doctor B
        patient = Patient.objects.create(
            first_name="Richard",
            last_name="Webber",
            date_of_birth=date(1954, 7, 1),
            gender=Patient.Gender.MALE,
            contact_number="9876588888",
            is_active=True,
        )
        consult_b = Consultation.objects.create(
            patient=patient,
            doctor=self.doctor_b,
            chief_complaint="Pediatric consultation",
            status=Consultation.Status.DRAFT,
        )

        anon_client = Client()
        rec_client = Client()
        rec_client.login(username="rec_april_kepner", password="SecurePass123!")
        doc_a_client = Client()
        doc_a_client.login(username="dr_meredith_grey", password="SecurePass123!")

        # 1. Anonymous user redirected to login
        r_anon = anon_client.get(reverse("patients:list"))
        self.assertEqual(r_anon.status_code, 302)
        self.assertIn(reverse("accounts:login"), r_anon.url)

        # 2. Receptionist cannot access doctor consultation editor (403)
        r_rec_consult = rec_client.get(reverse("consultations:edit", args=[consult_b.pk]))
        self.assertEqual(r_rec_consult.status_code, 403)

        # 3. Receptionist cannot access administrator dashboard or user list (403)
        r_rec_admin = rec_client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(r_rec_admin.status_code, 403)
        r_rec_users = rec_client.get(reverse("accounts:user_list"))
        self.assertEqual(r_rec_users.status_code, 403)

        # 4. Doctor cannot access administrator management pages (403)
        r_doc_admin = doc_a_client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(r_doc_admin.status_code, 403)
        r_doc_dept = doc_a_client.get(reverse("departments:department_create"))
        self.assertEqual(r_doc_dept.status_code, 403)

        # 5. Doctor A cannot access or tamper with Doctor B's consultation (403)
        r_doc_a_tamper = doc_a_client.get(reverse("consultations:edit", args=[consult_b.pk]))
        self.assertEqual(r_doc_a_tamper.status_code, 403)

        # 6. Inactive user cannot log in or access protected features
        self.receptionist_user.is_active = False
        self.receptionist_user.save()

        inactive_client = Client()
        r_inactive_login = inactive_client.post(
            reverse("accounts:login"),
            {"username": "rec_april_kepner", "password": "SecurePass123!"},
        )
        self.assertEqual(r_inactive_login.status_code, 200)
        self.assertContains(r_inactive_login, "Invalid username or password")


class SecurityHardeningAndErrorHandlingTests(TestCase):
    """
    Validates CSRF enforcement, custom error pages, immutability of medical records,
    and audit privacy protections.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin_sec",
            email="sec@clinic.test",
            password="SecurePass123!",
            role=User.Role.ADMIN,
        )
        self.doc_user = User.objects.create_user(
            username="doc_sec",
            email="doc.sec@clinic.test",
            password="SecurePass123!",
            role=User.Role.DOCTOR,
        )
        self.dept = Department.objects.create(name="Emergency Care", is_active=True)
        self.doctor = DoctorProfile.objects.create(
            user=self.doc_user,
            department=self.dept,
            specialization="Trauma Care",
            qualification="MBBS, MS",
            is_active=True,
        )
        self.patient = Patient.objects.create(
            first_name="Bruce",
            last_name="Wayne",
            date_of_birth=date(1980, 2, 19),
            gender=Patient.Gender.MALE,
            contact_number="9876599990",
            is_active=True,
        )
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            chief_complaint="Chest trauma",
            status=Consultation.Status.FINALIZED,
        )

    # 1. Custom 404 page is rendered for missing objects
    def test_custom_404_template_renders(self):
        client = Client()
        client.login(username="admin_sec", password="SecurePass123!")
        response = client.get(reverse("patients:detail", args=[999999]))
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")
        self.assertContains(response, "Resource Not Found", status_code=404)

    # 2. CSRF enforcement blocks unverified state-changing requests
    def test_csrf_protection_enforced_on_post(self):
        csrf_client = Client(enforce_csrf_checks=True)
        # Attempting POST without CSRF token
        response = csrf_client.post(
            reverse("accounts:login"),
            {"username": "admin_sec", "password": "SecurePass123!"},
        )
        # Without CSRF token, Django returns HTTP 403 Forbidden
        self.assertEqual(response.status_code, 403)

    # 3. Finalized consultation cannot be silently altered
    def test_finalized_consultation_rejects_silent_modification(self):
        self.consultation.chief_complaint = "Silently changed complaint"
        with self.assertRaises(ValidationError):
            self.consultation.full_clean()

    # 4. Issued prescription cannot be silently altered
    def test_issued_prescription_rejects_silent_modification(self):
        rx = Prescription.objects.create(
            consultation=self.consultation,
            status=Prescription.Status.ISSUED,
            general_instructions="Take rest",
        )
        rx.general_instructions = "Altered instructions without amendment note"
        with self.assertRaises(ValidationError):
            rx.full_clean()

    # 5. Audit Log does not log sensitive clinical text in metadata
    def test_audit_log_metadata_strips_clinical_narratives(self):
        from audit.services import log_audit_event
        log = log_audit_event(
            actor=self.admin,
            action="UPDATE",
            object_label="Patient Clinical Update",
            metadata={
                "patient_id": self.patient.pk,
                "password": "SecretPassword123!",
                "clinical_notes": "Highly sensitive psychological psychiatric evaluation notes",
                "chief_complaint": "Severe acute suicidal ideation",
            },
        )
        self.assertNotIn("password", log.metadata)
        self.assertNotIn("clinical_notes", log.metadata)
        self.assertNotIn("chief_complaint", log.metadata)
        self.assertEqual(log.metadata.get("patient_id"), self.patient.pk)

