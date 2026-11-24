from datetime import date, timedelta
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from audit.models import AuditLog
from consultations.models import Consultation
from departments.models import Department, DoctorProfile
from .admin import (
    AllergyAdmin,
    AllergyInline,
    MedicalHistoryAdmin,
    MedicalHistoryInline,
    PatientAdmin,
)
from .models import Allergy, MedicalHistory, Patient, PatientIDSequence

User = get_user_model()


class PatientRegistrationAndMedicalRecordsTests(TestCase):
    """
    Automated test suite for Patient Registration and Medical Records (Step 4).
    """

    def setUp(self):
        self.valid_dob = date(1990, 5, 15)
        self.patient_data = {
            "first_name": "Bruce",
            "last_name": "Wayne",
            "date_of_birth": self.valid_dob,
            "gender": Patient.Gender.MALE,
            "blood_group": Patient.BloodGroup.O_POSITIVE,
            "contact_number": "9876543210",
            "email": "bruce.wayne@enterprise.test",
            "emergency_contact_name": "Alfred Pennyworth",
            "emergency_contact_number": "9123456780",
            "address": "1007 Mountain Drive",
            "city": "Gotham",
            "state": "Maharashtra",
            "pincode": "400001",
        }

    # 1. Successful Patient Creation
    def test_successful_patient_creation(self):
        """Verify that a patient record is created successfully with valid attributes."""
        patient = Patient.objects.create(**self.patient_data)
        self.assertIsNotNone(patient.pk)
        self.assertTrue(patient.patient_id.startswith(f"P-{timezone.now().year}-"))
        self.assertTrue(patient.is_active)
        self.assertEqual(patient.get_full_name(), "Bruce Wayne")
        self.assertIn("Bruce Wayne", str(patient))
        self.assertIn(patient.patient_id, str(patient))
        self.assertEqual(patient.blood_group, "O+")

    # 2. Automatic MRN Generation
    def test_automatic_mrn_generation(self):
        """Verify that MRNs are automatically generated in sequence as P-YYYY-NNNN."""
        year = timezone.now().year
        p1 = Patient.objects.create(
            first_name="Clark",
            last_name="Kent",
            date_of_birth=date(1985, 2, 28),
            gender=Patient.Gender.MALE,
            contact_number="9876543211",
        )
        p2 = Patient.objects.create(
            first_name="Diana",
            last_name="Prince",
            date_of_birth=date(1988, 3, 22),
            gender=Patient.Gender.FEMALE,
            contact_number="9876543212",
        )

        self.assertTrue(p1.patient_id.startswith(f"P-{year}-"))
        self.assertTrue(p2.patient_id.startswith(f"P-{year}-"))
        self.assertNotEqual(p1.patient_id, p2.patient_id)

        # Extract numeric suffixes to confirm sequence progression
        seq1 = int(p1.patient_id.split("-")[-1])
        seq2 = int(p2.patient_id.split("-")[-1])
        self.assertEqual(seq2, seq1 + 1)

    # 3. Unique MRN Enforcement
    def test_unique_mrn_enforcement(self):
        """Verify that unique MRNs are enforced at the database level."""
        p1 = Patient.objects.create(**self.patient_data)
        duplicate_patient = Patient(
            patient_id=p1.patient_id,
            first_name="Duplicate",
            last_name="User",
            date_of_birth=date(1995, 1, 1),
            gender=Patient.Gender.OTHER,
            contact_number="9876543213",
        )
        with self.assertRaises((IntegrityError, ValidationError)):
            duplicate_patient.save()

    # 4. Invalid Future Date of Birth Rejection
    def test_invalid_future_date_of_birth_rejection(self):
        """Verify that a future date of birth is rejected with ValidationError."""
        future_dob = timezone.now().date() + timedelta(days=1)
        invalid_data = self.patient_data.copy()
        invalid_data["date_of_birth"] = future_dob
        with self.assertRaises(ValidationError) as ctx:
            Patient.objects.create(**invalid_data)
        self.assertIn("date_of_birth", ctx.exception.message_dict)

    # 5. Patient with Multiple Medical History Entries
    def test_patient_with_multiple_medical_histories(self):
        """Verify a patient can have multiple medical history records."""
        patient = Patient.objects.create(**self.patient_data)

        h1 = MedicalHistory.objects.create(
            patient=patient,
            condition="Essential Hypertension",
            description="Diagnosed during routine physical examination.",
            diagnosed_date=date(2020, 6, 10),
        )
        h2 = MedicalHistory.objects.create(
            patient=patient,
            condition="Type 2 Diabetes Mellitus",
            description="Under metformin treatment.",
            diagnosed_date=date(2022, 1, 15),
        )

        self.assertEqual(patient.medical_histories.count(), 2)
        self.assertIn(h1, patient.medical_histories.all())
        self.assertIn(h2, patient.medical_histories.all())
        self.assertIn("Essential Hypertension", str(h1))
        self.assertIn(patient.patient_id, str(h1))

    # 6. Patient with Multiple Allergy Entries
    def test_patient_with_multiple_allergies(self):
        """Verify a patient can have multiple allergy records with severity choices."""
        patient = Patient.objects.create(**self.patient_data)

        a1 = Allergy.objects.create(
            patient=patient,
            allergen="Penicillin",
            reaction="Anaphylaxis and respiratory distress",
            severity=Allergy.Severity.SEVERE,
            notes="Strict contraindication for all beta-lactam antibiotics.",
        )
        a2 = Allergy.objects.create(
            patient=patient,
            allergen="Latex",
            reaction="Contact dermatitis and hives",
            severity=Allergy.Severity.MODERATE,
        )

        self.assertEqual(patient.allergies.count(), 2)
        self.assertIn(a1, patient.allergies.all())
        self.assertIn(a2, patient.allergies.all())
        self.assertIn("Penicillin", str(a1))
        self.assertIn("Severe", str(a1))

    # 7. Correct Patient Relationships
    def test_correct_patient_relationships(self):
        """Verify forward and reverse relationships between Patient, MedicalHistory, and Allergy."""
        patient = Patient.objects.create(**self.patient_data)
        history = MedicalHistory.objects.create(
            patient=patient,
            condition="Asthma",
            diagnosed_date=date(2018, 4, 1),
        )
        allergy = Allergy.objects.create(
            patient=patient,
            allergen="Dust Mites",
            severity=Allergy.Severity.MILD,
        )

        # Forward relation
        self.assertEqual(history.patient, patient)
        self.assertEqual(allergy.patient, patient)

        # Reverse relation via related_name
        self.assertEqual(list(patient.medical_histories.all()), [history])
        self.assertEqual(list(patient.allergies.all()), [allergy])

    # 8. Patient Admin Registration and Search Configuration
    def test_patient_admin_registration_and_search_config(self):
        """Verify that Patient, MedicalHistory, and Allergy are registered in Django Admin with proper settings."""
        self.assertIn(Patient, admin.site._registry)
        self.assertIn(MedicalHistory, admin.site._registry)
        self.assertIn(Allergy, admin.site._registry)

        pat_admin = admin.site._registry[Patient]
        med_admin = admin.site._registry[MedicalHistory]
        all_admin = admin.site._registry[Allergy]

        self.assertIsInstance(pat_admin, PatientAdmin)
        self.assertIsInstance(med_admin, MedicalHistoryAdmin)
        self.assertIsInstance(all_admin, AllergyAdmin)

        # Verify readonly MRN
        self.assertIn("patient_id", pat_admin.readonly_fields)

        # Verify Search Fields
        self.assertIn("patient_id", pat_admin.search_fields)
        self.assertIn("first_name", pat_admin.search_fields)
        self.assertIn("last_name", pat_admin.search_fields)
        self.assertIn("contact_number", pat_admin.search_fields)

        # Verify Filters
        self.assertIn("gender", pat_admin.list_filter)
        self.assertIn("blood_group", pat_admin.list_filter)
        self.assertIn("is_active", pat_admin.list_filter)

        # Verify inlines in PatientAdmin
        inline_classes = [inline.__class__ for inline in pat_admin.inlines]
        self.assertTrue(any(issubclass(cls, MedicalHistoryInline) for cls in pat_admin.inlines))
        self.assertTrue(any(issubclass(cls, AllergyInline) for cls in pat_admin.inlines))

    # 9. Protection Against Accidental Patient Deletion
    def test_protection_against_accidental_patient_deletion(self):
        """Verify that deleting a patient with medical histories or allergies is blocked by models.PROTECT."""
        patient = Patient.objects.create(**self.patient_data)

        # Case A: Protected by MedicalHistory
        MedicalHistory.objects.create(
            patient=patient,
            condition="Chronic Sinusitis",
        )
        with self.assertRaises(ProtectedError):
            patient.delete()

        # Remove medical history, add Allergy
        patient.medical_histories.all().delete()
        Allergy.objects.create(
            patient=patient,
            allergen="Sulfa drugs",
            severity=Allergy.Severity.SEVERE,
        )

        # Case B: Protected by Allergy
        with self.assertRaises(ProtectedError):
            patient.delete()

        # Case C: Patient without medical records can be deleted (or soft-deleted)
        patient.allergies.all().delete()
        patient_id = patient.pk
        patient.delete()
        self.assertFalse(Patient.objects.filter(pk=patient_id).exists())


class ReceptionistPatientWorkflowTests(TestCase):
    """
    Automated test suite for Receptionist Portal - Patient Workflows (Step 10B).
    Covers permission enforcement, registration, validation, search, and privacy redaction.
    """

    def setUp(self):
        self.client = Client()

        # Users
        self.receptionist = User.objects.create_user(
            username="rec_mary",
            email="mary@clinic.test",
            password="SecurePass123!",
            role=User.Role.RECEPTIONIST,
        )
        self.admin_user = User.objects.create_user(
            username="admin_arthur",
            email="arthur@clinic.test",
            password="SecurePass123!",
            role=User.Role.ADMIN,
        )
        self.doctor_user = User.objects.create_user(
            username="doc_doolittle",
            email="doolittle@clinic.test",
            password="SecurePass123!",
            role=User.Role.DOCTOR,
        )

        self.valid_post_data = {
            "first_name": "Tony",
            "last_name": "Stark",
            "date_of_birth": "1970-05-29",
            "gender": Patient.Gender.MALE,
            "blood_group": Patient.BloodGroup.A_POSITIVE,
            "contact_number": "9876500001",
            "email": "tony.stark@avengers.test",
            "emergency_contact_name": "Pepper Potts",
            "emergency_contact_number": "9876500002",
            "address": "10880 Malibu Point",
            "city": "Malibu",
            "state": "California",
            "pincode": "90265",
            "is_active": True,
        }

    # 1. Unauthenticated request to patient registration redirects to login
    def test_unauthenticated_registration_redirects_to_login(self):
        response = self.client.get(reverse("patients:register"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    # 2. Doctor role gets 403 Forbidden on patient registration
    def test_doctor_forbidden_on_patient_registration(self):
        self.client.login(username="doc_doolittle", password="SecurePass123!")
        response = self.client.get(reverse("patients:register"))
        self.assertEqual(response.status_code, 403)

    # 3. Receptionist role accesses patient registration successfully (HTTP 200)
    def test_receptionist_can_access_patient_registration(self):
        self.client.login(username="rec_mary", password="SecurePass123!")
        response = self.client.get(reverse("patients:register"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "patients/patient_form.html")

    # 4. Administrator role accesses patient registration successfully (HTTP 200)
    def test_admin_can_access_patient_registration(self):
        self.client.login(username="admin_arthur", password="SecurePass123!")
        response = self.client.get(reverse("patients:register"))
        self.assertEqual(response.status_code, 200)

    # 5. Receptionist registers patient with valid data; MRN generated automatically; redirected
    def test_receptionist_registers_patient_successfully(self):
        self.client.login(username="rec_mary", password="SecurePass123!")
        response = self.client.post(reverse("patients:register"), self.valid_post_data, follow=False)
        self.assertEqual(response.status_code, 302)

        patient = Patient.objects.filter(contact_number="9876500001").first()
        self.assertIsNotNone(patient)
        self.assertEqual(patient.first_name, "Tony")
        self.assertEqual(patient.last_name, "Stark")
        self.assertTrue(patient.patient_id.startswith(f"P-{timezone.now().year}-"))
        self.assertRedirects(response, reverse("patients:detail", args=[patient.pk]))

    # 6. Audit log entry created on patient registration
    def test_audit_log_created_on_patient_registration(self):
        self.client.login(username="rec_mary", password="SecurePass123!")
        self.client.post(reverse("patients:register"), self.valid_post_data)

        patient = Patient.objects.filter(contact_number="9876500001").first()
        audit = AuditLog.objects.filter(
            actor=self.receptionist,
            action=AuditLog.Action.CREATE,
            object_id=str(patient.pk),
        ).first()
        self.assertIsNotNone(audit)
        self.assertIn("Tony Stark", audit.object_label)

    # 7. Future date of birth rejected with validation error on form
    def test_future_date_of_birth_rejected_in_form(self):
        self.client.login(username="rec_mary", password="SecurePass123!")
        data = self.valid_post_data.copy()
        data["date_of_birth"] = "2099-01-01"
        response = self.client.post(reverse("patients:register"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Patient.objects.filter(contact_number="9876500001").exists())
        self.assertIn("date_of_birth", response.context["form"].errors)

    # 8. Invalid contact number rejected
    def test_invalid_contact_number_rejected_in_form(self):
        self.client.login(username="rec_mary", password="SecurePass123!")
        data = self.valid_post_data.copy()
        data["contact_number"] = "12345"  # Invalid phone format
        response = self.client.post(reverse("patients:register"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("contact_number", response.context["form"].errors)

    # 9. Empty required fields rejected
    def test_empty_required_fields_rejected(self):
        self.client.login(username="rec_mary", password="SecurePass123!")
        data = self.valid_post_data.copy()
        data["first_name"] = ""
        data["last_name"] = ""
        data["date_of_birth"] = ""
        response = self.client.post(reverse("patients:register"), data)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertIn("first_name", form.errors)
        self.assertIn("last_name", form.errors)
        self.assertIn("date_of_birth", form.errors)

    # 10. Unauthenticated patient list redirects to login
    def test_unauthenticated_patient_list_redirects_to_login(self):
        response = self.client.get(reverse("patients:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    # 11. Doctor role gets 403 Forbidden on receptionist patient directory
    def test_doctor_forbidden_on_patient_list(self):
        self.client.login(username="doc_doolittle", password="SecurePass123!")
        response = self.client.get(reverse("patients:list"))
        self.assertEqual(response.status_code, 403)

    # 12. Receptionist accesses patient list; returns 200
    def test_receptionist_accesses_patient_list(self):
        self.client.login(username="rec_mary", password="SecurePass123!")
        response = self.client.get(reverse("patients:list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "patients/patient_list.html")

    # 13. Patient search by MRN returns matching patient
    def test_patient_search_by_mrn(self):
        p = Patient.objects.create(
            first_name="Wanda",
            last_name="Maximoff",
            date_of_birth=date(1989, 2, 10),
            gender=Patient.Gender.FEMALE,
            contact_number="9876543299",
        )
        self.client.login(username="rec_mary", password="SecurePass123!")
        response = self.client.get(reverse("patients:list") + f"?q={p.patient_id}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, p.patient_id)
        self.assertContains(response, "Wanda")

    # 14. Patient search by first/last name returns matching patient
    def test_patient_search_by_name(self):
        p = Patient.objects.create(
            first_name="Natasha",
            last_name="Romanoff",
            date_of_birth=date(1984, 11, 22),
            gender=Patient.Gender.FEMALE,
            contact_number="9876543288",
        )
        self.client.login(username="rec_mary", password="SecurePass123!")

        # Search by first name
        r1 = self.client.get(reverse("patients:list") + "?q=Natasha")
        self.assertContains(r1, "Romanoff")

        # Search by full name
        r2 = self.client.get(reverse("patients:list") + "?q=Natasha Romanoff")
        self.assertContains(r2, "Romanoff")

    # 15. Patient search with no match displays empty message
    def test_patient_search_no_match(self):
        self.client.login(username="rec_mary", password="SecurePass123!")
        response = self.client.get(reverse("patients:list") + "?q=NonExistentQueryXYZ")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No Patients Found")

    # 16. Receptionist patient detail view displays demographic & emergency info, but REDACTS clinical notes
    def test_patient_detail_redacts_clinical_notes_and_prescriptions(self):
        dept = Department.objects.create(name="Psychiatry", is_active=True)
        doc = DoctorProfile.objects.create(
            user=self.doctor_user,
            department=dept,
            specialization="General",
            qualification="MD",
            is_active=True,
        )
        patient = Patient.objects.create(
            first_name="Steve",
            last_name="Rogers",
            date_of_birth=date(1918, 7, 4),
            gender=Patient.Gender.MALE,
            contact_number="9876543277",
            emergency_contact_name="Bucky Barnes",
            emergency_contact_number="9876543278",
        )
        Consultation.objects.create(
            patient=patient,
            doctor=doc,
            chief_complaint="Fatigue after freezing",
            history_of_present_illness="CONFIDENTIAL CLINICAL NOTE: Super soldier serum observation",
            status=Consultation.Status.FINALIZED,
        )

        self.client.login(username="rec_mary", password="SecurePass123!")
        response = self.client.get(reverse("patients:detail", args=[patient.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "patients/patient_detail.html")

        # Demographics & emergency contact MUST be visible
        self.assertContains(response, "Steve Rogers")
        self.assertContains(response, patient.patient_id)
        self.assertContains(response, "Bucky Barnes")
        self.assertContains(response, "9876543278")

        # Clinical notes and prescriptions MUST NOT be in response content
        self.assertNotContains(response, "CONFIDENTIAL CLINICAL NOTE: Super soldier serum observation")
        self.assertNotContains(response, "Super soldier serum observation")
        self.assertNotIn("consultations", response.context)
        self.assertNotIn("prescriptions", response.context)

