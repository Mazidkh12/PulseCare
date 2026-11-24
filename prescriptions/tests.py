from datetime import date, time, timedelta
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from audit.models import AuditLog
from appointments.models import Appointment
from consultations.models import Consultation
from departments.models import Department, DoctorProfile
from patients.models import Patient
from .admin import PrescriptionAdmin, PrescriptionItemAdmin, PrescriptionItemInline
from .models import Prescription, PrescriptionIDSequence, PrescriptionItem

User = get_user_model()


class PrescriptionAndMedicationTests(TestCase):
    """
    Automated test suite for Prescriptions and Medication Management (Step 7).
    """

    def setUp(self):
        # 1. Department
        self.department = Department.objects.create(
            name="Cardiology & Internal Medicine",
            description="Outpatient medicine and cardiovascular health",
            is_active=True,
        )

        # 2. Doctor User (Role: DOCTOR)
        self.doc_user = User.objects.create_user(
            username="dr_stephen_strange",
            email="strange@clinic.test",
            password="SecureDoctorPass123!",
            first_name="Stephen",
            last_name="Strange",
            role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doc_user,
            department=self.department,
            specialization="Cardiology",
            qualification="MBBS, MD",
            is_active=True,
        )

        # 3. Receptionist User (Role: RECEPTIONIST)
        self.receptionist_user = User.objects.create_user(
            username="receptionist_wong",
            email="wong@clinic.test",
            password="SecureReceptionPass123!",
            first_name="Wong",
            last_name="Librarian",
            role=User.Role.RECEPTIONIST,
        )

        # 4. Admin User (Role: ADMIN)
        self.admin_user = User.objects.create_user(
            username="admin_nick_fury",
            email="fury@clinic.test",
            password="SecureAdminPass123!",
            first_name="Nick",
            last_name="Fury",
            role=User.Role.ADMIN,
        )

        # 5. Patient
        self.patient = Patient.objects.create(
            first_name="Peter",
            last_name="Parker",
            date_of_birth=date(1998, 8, 10),
            gender=Patient.Gender.MALE,
            contact_number="9876543210",
            is_active=True,
        )

        # 6. Consultation (Default: DRAFT)
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            chief_complaint="Chest congestion and productive cough for 4 days",
            status=Consultation.Status.DRAFT,
        )

    # 1. Successful Prescription Creation
    def test_successful_prescription_creation(self):
        """Verify that a prescription is created with draft status and derived patient/doctor."""
        rx = Prescription.objects.create(
            consultation=self.consultation,
            general_instructions="Take medications after meals with plenty of water.",
        )
        self.assertIsNotNone(rx.pk)
        self.assertEqual(rx.status, Prescription.Status.DRAFT)
        self.assertEqual(rx.patient, self.patient)
        self.assertEqual(rx.doctor, self.doctor)
        self.assertTrue(rx.prescription_number.startswith(f"RX-{timezone.now().year}-"))
        self.assertIn("Peter Parker", str(rx))
        self.assertIn("Stephen Strange", str(rx))

    # 2. Automatic Prescription Number Generation
    def test_automatic_prescription_number_generation(self):
        """Verify prescription numbers increment sequentially as RX-YYYY-NNNN."""
        year = timezone.now().year
        rx1 = Prescription.objects.create(consultation=self.consultation)

        # Create second consultation for another prescription
        c2 = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            chief_complaint="Follow-up consultation",
        )
        rx2 = Prescription.objects.create(consultation=c2)

        self.assertTrue(rx1.prescription_number.startswith(f"RX-{year}-"))
        self.assertTrue(rx2.prescription_number.startswith(f"RX-{year}-"))
        self.assertNotEqual(rx1.prescription_number, rx2.prescription_number)

        seq1 = int(rx1.prescription_number.split("-")[-1])
        seq2 = int(rx2.prescription_number.split("-")[-1])
        self.assertEqual(seq2, seq1 + 1)

    # 3. Unique Prescription Number Enforcement
    def test_unique_prescription_number_enforcement(self):
        """Verify that duplicate prescription numbers are blocked at the database level."""
        rx1 = Prescription.objects.create(consultation=self.consultation)
        c2 = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            chief_complaint="Second consultation",
        )
        duplicate_rx = Prescription(
            consultation=c2,
            prescription_number=rx1.prescription_number,
        )
        with self.assertRaises((IntegrityError, ValidationError)):
            duplicate_rx.save()

    # 4. Multiple Medicine Items in One Prescription
    def test_multiple_medicine_items_in_one_prescription(self):
        """Verify that a single prescription can hold multiple distinct medicine items."""
        rx = Prescription.objects.create(consultation=self.consultation)
        item1 = PrescriptionItem.objects.create(
            prescription=rx,
            medicine_name="Amoxicillin",
            dosage_form=PrescriptionItem.DosageForm.CAPSULE,
            strength="500 mg",
            dosage="1 capsule",
            frequency="TID (Thrice daily)",
            duration=7,
            intake_timing=PrescriptionItem.IntakeTiming.AFTER_FOOD,
        )
        item2 = PrescriptionItem.objects.create(
            prescription=rx,
            medicine_name="Paracetamol",
            dosage_form=PrescriptionItem.DosageForm.TABLET,
            strength="650 mg",
            dosage="1 tablet",
            frequency="SOS (When needed)",
            duration=3,
            intake_timing=PrescriptionItem.IntakeTiming.AFTER_FOOD,
        )
        self.assertEqual(rx.items.count(), 2)
        self.assertIn(item1, rx.items.all())
        self.assertIn(item2, rx.items.all())
        self.assertIn("Amoxicillin", str(item1))
        self.assertIn("Paracetamol", str(item2))

    # 5. Required Medicine Name Validation
    def test_required_medicine_name_validation(self):
        """Verify that medicine_name cannot be blank or empty."""
        rx = Prescription.objects.create(consultation=self.consultation)
        with self.assertRaises(ValidationError) as ctx:
            PrescriptionItem.objects.create(
                prescription=rx,
                medicine_name="",  # Blank
                dosage="1 tablet",
                frequency="OD",
                duration=5,
            )
        self.assertIn("medicine_name", ctx.exception.message_dict)

    # 6. Required Dosage and Frequency Validation
    def test_required_dosage_and_frequency_validation(self):
        """Verify that dosage and frequency are mandatory fields."""
        rx = Prescription.objects.create(consultation=self.consultation)

        # Missing dosage
        with self.assertRaises(ValidationError) as ctx_dose:
            PrescriptionItem.objects.create(
                prescription=rx,
                medicine_name="Ibuprofen",
                dosage="",
                frequency="BD",
                duration=5,
            )
        self.assertIn("dosage", ctx_dose.exception.message_dict)

        # Missing frequency
        with self.assertRaises(ValidationError) as ctx_freq:
            PrescriptionItem.objects.create(
                prescription=rx,
                medicine_name="Ibuprofen",
                dosage="1 tablet",
                frequency="",
                duration=5,
            )
        self.assertIn("frequency", ctx_freq.exception.message_dict)

    # 7. Duration Must Be Greater than Zero
    def test_duration_must_be_greater_than_zero(self):
        """Verify that zero duration is rejected with ValidationError."""
        rx = Prescription.objects.create(consultation=self.consultation)
        with self.assertRaises(ValidationError) as ctx:
            PrescriptionItem.objects.create(
                prescription=rx,
                medicine_name="Cetirizine",
                dosage="1 tablet",
                frequency="HS",
                duration=0,  # Invalid
            )
        self.assertIn("duration", ctx.exception.message_dict)

    # 8. Draft Prescription Can Be Edited
    def test_draft_prescription_can_be_edited(self):
        """Verify that prescriptions in DRAFT status can have instructions modified."""
        rx = Prescription.objects.create(
            consultation=self.consultation,
            general_instructions="Initial instructions",
        )
        rx.general_instructions = "Updated instructions with steam inhalation advice."
        rx.save()

        rx.refresh_from_db()
        self.assertEqual(
            rx.general_instructions,
            "Updated instructions with steam inhalation advice.",
        )
        self.assertEqual(rx.status, Prescription.Status.DRAFT)

    # 9. Prescription Can Be Issued for Finalized Consultation
    def test_prescription_can_be_issued_for_finalized_consultation(self):
        """Verify that a prescription is issued when the consultation is finalized and doctor authorized."""
        self.consultation.finalize()
        self.assertEqual(self.consultation.status, Consultation.Status.FINALIZED)

        rx = Prescription.objects.create(consultation=self.consultation)
        PrescriptionItem.objects.create(
            prescription=rx,
            medicine_name="Azithromycin",
            strength="500 mg",
            dosage="1 tablet",
            frequency="OD",
            duration=3,
        )

        rx.issue(issued_by=self.doc_user)
        self.assertEqual(rx.status, Prescription.Status.ISSUED)
        self.assertIsNotNone(rx.issued_at)

    # 10. Prescription Cannot Be Issued for Draft Consultation
    def test_prescription_cannot_be_issued_for_draft_consultation(self):
        """Verify that issuing a prescription when the consultation is still in DRAFT raises ValidationError."""
        self.assertEqual(self.consultation.status, Consultation.Status.DRAFT)
        rx = Prescription.objects.create(consultation=self.consultation)

        with self.assertRaises(ValidationError) as ctx:
            rx.issue(issued_by=self.doc_user)
        self.assertIn("status", ctx.exception.message_dict)

    # 11. Prescription Cannot Be Issued for Cancelled Appointment Consultation
    def test_prescription_cannot_be_issued_for_cancelled_appointment(self):
        """Verify that a prescription cannot be created for a consultation linked to a cancelled appointment."""
        apt = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment_date=timezone.now().date() + timedelta(days=2),
            start_time=time(11, 0),
            end_time=time(11, 30),
            status=Appointment.Status.CANCELLED,
        )
        cancelled_consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            appointment=None,  # Created without direct link first
            chief_complaint="Post cancellation visit",
        )
        # Force appointment to cancelled one to test validation
        cancelled_consultation.appointment = apt

        with self.assertRaises(ValidationError) as ctx:
            Prescription.objects.create(consultation=cancelled_consultation)
        self.assertIn("consultation", ctx.exception.message_dict)

    # 12. Issued Prescription Cannot Be Silently Modified
    def test_issued_prescription_cannot_be_silently_modified(self):
        """Verify that modifying an issued prescription requires explicit amendment notes."""
        self.consultation.finalize()
        rx = Prescription.objects.create(
            consultation=self.consultation,
            general_instructions="Original instructions",
        )
        rx.issue(issued_by=self.doc_user)
        self.assertEqual(rx.status, Prescription.Status.ISSUED)

        # Attempt silent change without amendment notes
        rx.general_instructions = "Silent unapproved modification"
        with self.assertRaises(ValidationError) as ctx:
            rx.save()
        self.assertIn("amendment_notes", ctx.exception.message_dict)

        # Documented amendment succeeds
        rx.refresh_from_db()
        rx.general_instructions = "Modified instructions with reduced sodium diet."
        rx.amendment_notes = "Added low-sodium diet precaution following BP review."
        rx.save()

        rx.refresh_from_db()
        self.assertEqual(
            rx.general_instructions,
            "Modified instructions with reduced sodium diet.",
        )

    # 13. Issued Prescription Cannot Be Casually Deleted
    def test_issued_prescription_cannot_be_casually_deleted(self):
        """Verify that issued prescriptions are protected against deletion."""
        self.consultation.finalize()
        rx = Prescription.objects.create(consultation=self.consultation)
        rx.issue(issued_by=self.doc_user)

        with self.assertRaises(ValidationError):
            rx.delete()

    # 14. Prescription Items Remain Linked to Correct Prescription
    def test_prescription_items_remain_linked(self):
        """Verify relational integrity between items and their prescription."""
        rx = Prescription.objects.create(consultation=self.consultation)
        item = PrescriptionItem.objects.create(
            prescription=rx,
            medicine_name="Metformin",
            strength="500 mg",
            dosage="1 tablet",
            frequency="BD",
            duration=30,
        )
        self.assertEqual(item.prescription, rx)
        self.assertEqual(list(rx.items.all()), [item])

    # 15. Only Authorized Doctors Can Issue Prescriptions
    def test_only_authorized_doctors_can_issue_prescriptions(self):
        """Verify that non-doctor users (Receptionist, Admin) cannot issue prescriptions."""
        self.consultation.finalize()
        rx = Prescription.objects.create(consultation=self.consultation)

        # Receptionist attempt
        with self.assertRaises(ValidationError) as ctx_rec:
            rx.issue(issued_by=self.receptionist_user)
        self.assertIn("status", ctx_rec.exception.message_dict)

        # Admin attempt
        with self.assertRaises(ValidationError) as ctx_adm:
            rx.issue(issued_by=self.admin_user)
        self.assertIn("status", ctx_adm.exception.message_dict)

        # Doctor attempt
        rx.issue(issued_by=self.doc_user)
        self.assertEqual(rx.status, Prescription.Status.ISSUED)

    # 16. Prescription Admin Configuration
    def test_prescription_admin_configuration(self):
        """Verify admin registration, list display, inlines, and search fields."""
        self.assertIn(Prescription, admin.site._registry)
        self.assertIn(PrescriptionItem, admin.site._registry)
        self.assertIn(PrescriptionIDSequence, admin.site._registry)

        rx_admin = admin.site._registry[Prescription]
        item_admin = admin.site._registry[PrescriptionItem]

        self.assertIsInstance(rx_admin, PrescriptionAdmin)
        self.assertIsInstance(item_admin, PrescriptionItemAdmin)

        # List display
        self.assertIn("prescription_number", rx_admin.list_display)
        self.assertIn("get_patient_name", rx_admin.list_display)
        self.assertIn("status", rx_admin.list_display)

        # Search fields
        self.assertIn("prescription_number", rx_admin.search_fields)
        self.assertIn("consultation__patient__first_name", rx_admin.search_fields)

        # Filters
        self.assertIn("status", rx_admin.list_filter)
        self.assertIn("prescription_date", rx_admin.list_filter)

        # Inlines
        self.assertIn(PrescriptionItemInline, rx_admin.inlines)


class DoctorPrescriptionWorkflowTests(TestCase):
    """
    Automated test suite for Doctor Portal - Prescription Builder & Issuance (Step 10C).
    """

    def setUp(self):
        self.client = Client()

        self.dept = Department.objects.create(name="Cardiology & Pharmacology", is_active=True)

        self.doc_user = User.objects.create_user(
            username="dr_house_rx",
            email="house_rx@clinic.test",
            password="SecurePass123!",
            first_name="Gregory",
            last_name="House",
            role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doc_user,
            department=self.dept,
            specialization="Diagnostic Medicine",
            qualification="MD",
            is_active=True,
        )

        self.patient = Patient.objects.create(
            first_name="James",
            last_name="Wilson",
            date_of_birth=date(1975, 4, 12),
            gender=Patient.Gender.MALE,
            contact_number="9876500222",
            is_active=True,
        )

        self.consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            chief_complaint="Persistent joint pain and inflammation",
            status=Consultation.Status.DRAFT,
        )

    # 25. Doctor can create a prescription draft
    def test_doctor_creates_prescription_draft(self):
        self.client.login(username="dr_house_rx", password="SecurePass123!")
        response = self.client.get(reverse("prescriptions:create", args=[self.consultation.pk]))
        self.assertEqual(response.status_code, 200)

        rx = Prescription.objects.filter(consultation=self.consultation).first()
        self.assertIsNotNone(rx)
        self.assertEqual(rx.status, Prescription.Status.DRAFT)
        self.assertTrue(rx.prescription_number.startswith("RX-"))

    # 26. Multiple medicine items can be added
    def test_multiple_medicine_items_added(self):
        rx = Prescription.objects.create(consultation=self.consultation, status=Prescription.Status.DRAFT)
        self.client.login(username="dr_house_rx", password="SecurePass123!")

        post_data = {
            "general_instructions": "Drink plenty of water and rest.",
            "action": "save_draft",
            "items-TOTAL_FORMS": "2",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-medicine_name": "Ibuprofen",
            "items-0-dosage_form": "TABLET",
            "items-0-strength": "400 mg",
            "items-0-dosage": "1 tablet",
            "items-0-frequency": "TID",
            "items-0-duration": "5",
            "items-0-intake_timing": "AFTER_FOOD",
            "items-0-special_instructions": "Take with meals",
            "items-1-medicine_name": "Omeprazole",
            "items-1-dosage_form": "CAPSULE",
            "items-1-strength": "20 mg",
            "items-1-dosage": "1 capsule",
            "items-1-frequency": "OD",
            "items-1-duration": "7",
            "items-1-intake_timing": "BEFORE_FOOD",
            "items-1-special_instructions": "Morning before breakfast",
        }
        response = self.client.post(reverse("prescriptions:create", args=[self.consultation.pk]), post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(rx.items.count(), 2)

    # 27. Prescription cannot be issued for a draft consultation
    def test_prescription_cannot_be_issued_for_draft_consultation(self):
        rx = Prescription.objects.create(consultation=self.consultation, status=Prescription.Status.DRAFT)
        self.assertEqual(self.consultation.status, Consultation.Status.DRAFT)

        self.client.login(username="dr_house_rx", password="SecurePass123!")
        post_data = {
            "general_instructions": "Take medicines as advised.",
            "action": "issue",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-medicine_name": "Paracetamol",
            "items-0-dosage_form": "TABLET",
            "items-0-strength": "500 mg",
            "items-0-dosage": "1 tablet",
            "items-0-frequency": "TID",
            "items-0-duration": "3",
            "items-0-intake_timing": "AFTER_FOOD",
        }
        response = self.client.post(reverse("prescriptions:create", args=[self.consultation.pk]), post_data, follow=True)
        rx.refresh_from_db()
        self.assertEqual(rx.status, Prescription.Status.DRAFT)
        self.assertContains(response, "cannot be issued for a consultation in DRAFT status")

    # 28. Prescription can be issued after consultation finalization
    def test_prescription_issued_after_finalization(self):
        self.consultation.finalize()
        self.assertEqual(self.consultation.status, Consultation.Status.FINALIZED)

        rx = Prescription.objects.create(consultation=self.consultation, status=Prescription.Status.DRAFT)
        self.client.login(username="dr_house_rx", password="SecurePass123!")

        post_data = {
            "general_instructions": "Complete the full antibiotic course.",
            "action": "issue",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-medicine_name": "Amoxicillin",
            "items-0-dosage_form": "CAPSULE",
            "items-0-strength": "500 mg",
            "items-0-dosage": "1 capsule",
            "items-0-frequency": "TID",
            "items-0-duration": "5",
            "items-0-intake_timing": "AFTER_FOOD",
        }
        response = self.client.post(reverse("prescriptions:create", args=[self.consultation.pk]), post_data, follow=False)
        self.assertEqual(response.status_code, 302)

        rx.refresh_from_db()
        self.assertEqual(rx.status, Prescription.Status.ISSUED)
        self.assertIsNotNone(rx.issued_at)

    # 29. Issued prescription cannot be silently modified
    def test_issued_prescription_cannot_be_silently_modified(self):
        self.consultation.finalize()
        rx = Prescription.objects.create(
            consultation=self.consultation,
            general_instructions="Initial instructions",
        )
        rx.issue(issued_by=self.doc_user)
        self.assertEqual(rx.status, Prescription.Status.ISSUED)

        # Silent modification without amendment notes is rejected by model
        rx.general_instructions = "Tampered instructions"
        with self.assertRaises(ValidationError) as ctx:
            rx.save()
        self.assertIn("amendment_notes", ctx.exception.message_dict)

    # 30. Prescription audit logging works
    def test_prescription_audit_logging(self):
        self.consultation.finalize()
        rx = Prescription.objects.create(consultation=self.consultation)
        rx.issue(issued_by=self.doc_user)

        audit = AuditLog.objects.filter(
            actor=self.doc_user,
            action=AuditLog.Action.ISSUE_PRESCRIPTION,
            object_id=str(rx.pk),
        ).first()
        self.assertIsNotNone(audit)
        self.assertIn(rx.prescription_number, audit.object_label)

    # Prescription Directory & Detail Render Test
    def test_prescription_directory_and_detail_render(self):
        self.consultation.finalize()
        rx = Prescription.objects.create(consultation=self.consultation)
        rx.issue(issued_by=self.doc_user)
        PrescriptionItem.objects.create(
            prescription=rx,
            medicine_name="Paracetamol",
            dosage_form="TABLET",
            strength="650 mg",
            dosage="1 tab",
            frequency="TID",
            duration=3,
        )
        self.client.login(username="dr_house_rx", password="SecurePass123!")

        # List
        r_list = self.client.get(reverse("prescriptions:list"))
        self.assertEqual(r_list.status_code, 200)
        self.assertContains(r_list, rx.prescription_number)

        # Detail
        r_detail = self.client.get(reverse("prescriptions:detail", args=[rx.pk]))
        self.assertEqual(r_detail.status_code, 200)
        self.assertContains(r_detail, rx.prescription_number)
        self.assertContains(r_detail, "Paracetamol")

