from datetime import date, time, timedelta
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from audit.admin import AuditLogAdmin
from audit.models import AuditLog
from audit.services import log_audit_event, sanitize_metadata
from consultations.models import Consultation, Diagnosis
from departments.models import Department, DoctorProfile
from patients.models import Patient
from prescriptions.models import Prescription, PrescriptionItem

User = get_user_model()


class AuditLoggingTests(TestCase):
    """
    Automated test suite for Audit Logging (Step 9 - Part A).
    """

    def setUp(self):
        self.factory = RequestFactory()

        # Department
        self.department = Department.objects.create(
            name="General Medicine",
            is_active=True,
        )

        # Users
        self.admin_user = User.objects.create_user(
            username="admin_tony",
            email="tony@clinic.test",
            password="SecurePass123!",
            role=User.Role.ADMIN,
        )
        self.doc_user = User.objects.create_user(
            username="dr_bruce_banner",
            email="banner@clinic.test",
            password="SecurePass123!",
            role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doc_user,
            department=self.department,
            specialization="Internal Medicine",
            qualification="MBBS, MD",
            is_active=True,
        )
        self.receptionist_user = User.objects.create_user(
            username="rec_natasha",
            email="natasha@clinic.test",
            password="SecurePass123!",
            role=User.Role.RECEPTIONIST,
        )

        # Patient
        self.patient = Patient.objects.create(
            first_name="Steve",
            last_name="Rogers",
            date_of_birth=date(1985, 7, 4),
            gender=Patient.Gender.MALE,
            contact_number="9876543210",
            is_active=True,
        )

    # 1. Successful audit log creation
    def test_successful_audit_log_creation(self):
        log = log_audit_event(
            actor=self.admin_user,
            action=AuditLog.Action.CREATE,
            obj=self.patient,
            object_label="Patient Steve Rogers created",
            metadata={"source": "registration_desk"},
        )
        self.assertIsNotNone(log.pk)
        self.assertEqual(log.action, AuditLog.Action.CREATE)
        self.assertEqual(log.object_label, "Patient Steve Rogers created")

    # 2. Correct actor association
    def test_correct_actor_association(self):
        log = log_audit_event(
            actor=self.doc_user,
            action=AuditLog.Action.UPDATE,
            obj=self.patient,
        )
        self.assertEqual(log.actor, self.doc_user)
        self.assertIn("dr_bruce_banner", str(log))

    # 3. Correct action recording
    def test_correct_action_recording(self):
        log = log_audit_event(
            actor=self.admin_user,
            action=AuditLog.Action.LOGIN,
            object_label="User logged in",
        )
        self.assertEqual(log.action, AuditLog.Action.LOGIN)

    # 4. Correct affected object reference
    def test_correct_affected_object_reference(self):
        log = log_audit_event(
            actor=self.doc_user,
            action=AuditLog.Action.CREATE,
            obj=self.patient,
        )
        self.assertEqual(log.object_id, str(self.patient.pk))
        self.assertEqual(log.content_type.model, "patient")

    # 5. Timestamp generation
    def test_timestamp_generation(self):
        before = timezone.now()
        log = log_audit_event(
            actor=self.admin_user,
            action=AuditLog.Action.CREATE,
            object_label="Timestamp test",
        )
        after = timezone.now()
        self.assertGreaterEqual(log.timestamp, before)
        self.assertLessEqual(log.timestamp, after)

    # 6. Consultation finalization audit event
    def test_consultation_finalization_audit_event(self):
        c = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            chief_complaint="Chest tightness",
            status=Consultation.Status.DRAFT,
        )
        c.finalize(finalized_by=self.doc_user)
        self.assertEqual(c.status, Consultation.Status.FINALIZED)

        log = AuditLog.objects.filter(
            action=AuditLog.Action.FINALIZE_CONSULTATION,
            object_id=str(c.pk),
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.doc_user)
        self.assertEqual(log.metadata.get("status"), Consultation.Status.FINALIZED)

    # 7. Prescription issuance audit event
    def test_prescription_issuance_audit_event(self):
        c = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            chief_complaint="Productive cough",
        )
        c.finalize()

        rx = Prescription.objects.create(consultation=c)
        PrescriptionItem.objects.create(
            prescription=rx,
            medicine_name="Amoxicillin",
            dosage="1 capsule",
            frequency="TID",
            duration=5,
        )
        rx.issue(issued_by=self.doc_user)

        log = AuditLog.objects.filter(
            action=AuditLog.Action.ISSUE_PRESCRIPTION,
            object_id=str(rx.pk),
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.doc_user)
        self.assertEqual(log.metadata.get("prescription_number"), rx.prescription_number)

    # 8. Diagnosis creation and update audit events
    def test_diagnosis_creation_and_update_audit_events(self):
        c = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            chief_complaint="Elevated blood sugar",
            status=Consultation.Status.FINALIZED,
        )

        dx = Diagnosis.objects.create(
            consultation=c,
            diagnosis_name="Type 2 Diabetes",
            diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
            recorded_by=self.doc_user,
        )

        create_log = AuditLog.objects.filter(
            action=AuditLog.Action.CREATE_DIAGNOSIS,
            object_id=str(dx.pk),
        ).first()
        self.assertIsNotNone(create_log)
        self.assertEqual(create_log.actor, self.doc_user)

        # Update
        dx.diagnosis_code = "E11.9"
        dx.save()

        update_log = AuditLog.objects.filter(
            action=AuditLog.Action.UPDATE_DIAGNOSIS,
            object_id=str(dx.pk),
        ).first()
        self.assertIsNotNone(update_log)
        self.assertEqual(update_log.metadata.get("diagnosis_code"), "E11.9")

    # 9. Appointment cancellation audit event
    def test_appointment_cancellation_audit_event(self):
        apt = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=timezone.now().date() + timedelta(days=2),
            start_time=time(10, 0),
            end_time=time(10, 30),
            status=Appointment.Status.SCHEDULED,
        )
        apt.cancel(cancelled_by=self.receptionist_user)
        self.assertEqual(apt.status, Appointment.Status.CANCELLED)

        log = AuditLog.objects.filter(
            action=AuditLog.Action.CANCEL_APPOINTMENT,
            object_id=str(apt.pk),
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.receptionist_user)

    # 10. Audit records cannot be casually edited or deleted through Django Admin
    def test_admin_disallows_add_change_delete(self):
        admin_instance = AuditLogAdmin(AuditLog, admin.site)
        req = self.factory.get("/")
        req.user = self.admin_user

        self.assertFalse(admin_instance.has_add_permission(req))
        self.assertFalse(admin_instance.has_change_permission(req))
        self.assertFalse(admin_instance.has_delete_permission(req))

    # 11. Sensitive clinical text is not stored in audit metadata
    def test_sensitive_clinical_text_scrubbed_from_metadata(self):
        raw_meta = {
            "password": "SecretPassword123!",
            "token": "bearer-token-abc",
            "clinical_notes": "Patient has severe depressive symptoms...",
            "chief_complaint": "Chest pain",
            "treatment_plan": "Statins and beta blockers",
            "prescription_id": 42,
            "status": "FINALIZED",
        }
        clean = sanitize_metadata(raw_meta)

        self.assertNotIn("password", clean)
        self.assertNotIn("token", clean)
        self.assertNotIn("clinical_notes", clean)
        self.assertNotIn("chief_complaint", clean)
        self.assertNotIn("treatment_plan", clean)
        self.assertEqual(clean.get("prescription_id"), 42)
        self.assertEqual(clean.get("status"), "FINALIZED")

    # 12. Unauthorized users cannot access restricted audit records
    def test_unauthorized_users_cannot_access_audit_records(self):
        admin_instance = AuditLogAdmin(AuditLog, admin.site)

        # Receptionist request
        req_rec = self.factory.get("/")
        req_rec.user = self.receptionist_user
        self.assertFalse(admin_instance.has_view_permission(req_rec))

        # Doctor request
        req_doc = self.factory.get("/")
        req_doc.user = self.doc_user
        self.assertFalse(admin_instance.has_view_permission(req_doc))

        # Admin request
        req_adm = self.factory.get("/")
        req_adm.user = self.admin_user
        self.assertTrue(admin_instance.has_view_permission(req_adm))


class AuditLogExplorerTests(TestCase):
    """
    Test suite for Step 10D: Audit Log Explorer interface, security, and read-only integrity.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin_thor",
            email="thor@clinic.test",
            password="SecurePass123!",
            role=User.Role.ADMIN,
        )
        self.receptionist = User.objects.create_user(
            username="rec_loki",
            email="loki@clinic.test",
            password="SecurePass123!",
            role=User.Role.RECEPTIONIST,
        )
        self.doctor = User.objects.create_user(
            username="doc_odin",
            email="odin@clinic.test",
            password="SecurePass123!",
            role=User.Role.DOCTOR,
        )

        # Create a sample audit log
        self.log_entry = log_audit_event(
            actor=self.admin,
            action=AuditLog.Action.CREATE,
            object_label="Created Test Department",
            metadata={"dept": "Pediatrics"},
        )

    # 28. Administrator can view audit records
    def test_admin_can_view_audit_list(self):
        self.client.login(username="admin_thor", password="SecurePass123!")
        response = self.client.get(reverse("audit:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Created Test Department")
        self.assertContains(response, "admin_thor")

    # 29. Unauthorized roles cannot access audit records
    def test_unauthorized_users_denied_audit_list(self):
        # Receptionist -> 403
        self.client.login(username="rec_loki", password="SecurePass123!")
        r_rec = self.client.get(reverse("audit:list"))
        self.assertEqual(r_rec.status_code, 403)

        # Doctor -> 403
        self.client.login(username="doc_odin", password="SecurePass123!")
        r_doc = self.client.get(reverse("audit:list"))
        self.assertEqual(r_doc.status_code, 403)

    # 30. Search and filters work
    def test_audit_list_search_and_filters(self):
        self.client.login(username="admin_thor", password="SecurePass123!")

        # Search by keyword
        r_search = self.client.get(reverse("audit:list") + "?q=Pediatrics")
        self.assertEqual(r_search.status_code, 200)

        # Filter by action
        r_action = self.client.get(reverse("audit:list") + f"?action={AuditLog.Action.CREATE}")
        self.assertEqual(r_action.status_code, 200)
        self.assertContains(r_action, "Created Test Department")

    # 31. Audit detail view does not expose sensitive information
    def test_audit_detail_does_not_expose_credentials(self):
        self.client.login(username="admin_thor", password="SecurePass123!")
        response = self.client.get(reverse("audit:detail", args=[self.log_entry.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Created Test Department")
        self.assertNotContains(response, "SecurePass123!")

    # 32. Audit records cannot be edited or deleted through the interface
    def test_audit_records_no_edit_or_delete_routes(self):
        # There are no update/delete URLs exposed in audit.urls
        from django.urls import resolve
        with self.assertRaises(Exception):
            reverse("audit:edit", args=[self.log_entry.pk])
        with self.assertRaises(Exception):
            reverse("audit:delete", args=[self.log_entry.pk])

