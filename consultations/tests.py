from datetime import date, time, timedelta
from decimal import Decimal
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from appointments.models import Appointment
from departments.models import Department, DoctorProfile
from patients.models import Allergy, MedicalHistory, Patient
from prescriptions.models import Prescription, PrescriptionItem
from .admin import (
    ConsultationAdmin,
    DiagnosisAdmin,
    DiagnosisInline,
    VitalSignAdmin,
    VitalSignInline,
)
from .models import Consultation, Diagnosis, VitalSign
from .services import get_patient_timeline

User = get_user_model()


class ConsultationAndVitalSignsTests(TestCase):
    """
    Automated test suite for Consultations, Clinical Case-Taking, and Vital Signs (Step 6).
    """

    def setUp(self):
        # 1. Department
        self.department = Department.objects.create(
            name="General Internal Medicine",
            description="Comprehensive adult outpatient care",
            is_active=True,
        )

        # 2. Doctor 1 (Active)
        self.doc_user1 = User.objects.create_user(
            username="dr_meredith_grey",
            email="meredith@clinic.test",
            password="SecureDoctorPass123!",
            first_name="Meredith",
            last_name="Grey",
            role=User.Role.DOCTOR,
        )
        self.doctor1 = DoctorProfile.objects.create(
            user=self.doc_user1,
            department=self.department,
            specialization="General Surgery / Medicine",
            qualification="MBBS, MS",
            is_active=True,
        )

        # 3. Doctor 2 (Active)
        self.doc_user2 = User.objects.create_user(
            username="dr_derek_shepherd",
            email="derek@clinic.test",
            password="SecureDoctorPass123!",
            first_name="Derek",
            last_name="Shepherd",
            role=User.Role.DOCTOR,
        )
        self.doctor2 = DoctorProfile.objects.create(
            user=self.doc_user2,
            department=self.department,
            specialization="Neurosurgery",
            qualification="MD",
            is_active=True,
        )

        # 4. Doctor Inactive
        self.doc_user_inactive = User.objects.create_user(
            username="dr_richard_webber",
            email="richard@clinic.test",
            password="SecureDoctorPass123!",
            first_name="Richard",
            last_name="Webber",
            role=User.Role.DOCTOR,
        )
        self.doctor_inactive = DoctorProfile.objects.create(
            user=self.doc_user_inactive,
            department=self.department,
            specialization="General Medicine",
            qualification="MD",
            is_active=False,
        )

        # 5. Patient 1 (Active)
        self.patient1 = Patient.objects.create(
            first_name="George",
            last_name="O'Malley",
            date_of_birth=date(1985, 4, 12),
            gender=Patient.Gender.MALE,
            contact_number="9876543210",
            is_active=True,
        )

        # 6. Patient 2 (Active)
        self.patient2 = Patient.objects.create(
            first_name="Izzie",
            last_name="Stevens",
            date_of_birth=date(1987, 8, 20),
            gender=Patient.Gender.FEMALE,
            contact_number="9876543211",
            is_active=True,
        )

        # 7. Patient Inactive
        self.patient_inactive = Patient.objects.create(
            first_name="Alex",
            last_name="Karev",
            date_of_birth=date(1984, 11, 5),
            gender=Patient.Gender.MALE,
            contact_number="9876543212",
            is_active=False,
        )

        # 8. Standard Appointment
        self.tomorrow = timezone.now().date() + timedelta(days=1)
        self.appointment = Appointment.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            appointment_date=self.tomorrow,
            start_time=time(10, 0),
            end_time=time(10, 30),
            status=Appointment.Status.SCHEDULED,
        )

    # 1. Successful Appointment-Based Consultation Creation
    def test_successful_appointment_based_consultation(self):
        """Verify an appointment-based consultation is created with matching patient and doctor."""
        consultation = Consultation.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            appointment=self.appointment,
            chief_complaint="Fever and persistent dry cough for 3 days",
            history_of_present_illness="Patient reports gradual onset of low-grade fever with malaise.",
            physical_examination="Chest clear on auscultation, no added sounds.",
            clinical_assessment="Probable viral upper respiratory tract infection.",
            treatment_plan="Symptomatic therapy with paracetamol and oral hydration.",
        )
        self.assertIsNotNone(consultation.pk)
        self.assertEqual(consultation.appointment, self.appointment)
        self.assertEqual(consultation.status, Consultation.Status.DRAFT)
        self.assertIn("George O'Malley", str(consultation))
        self.assertIn("Meredith Grey", str(consultation))

    # 2. Successful Walk-in Consultation Creation
    def test_successful_walk_in_consultation(self):
        """Verify a walk-in consultation can be created without an appointment."""
        walk_in = Consultation.objects.create(
            patient=self.patient2,
            doctor=self.doctor1,
            appointment=None,  # No appointment
            chief_complaint="Acute right ankle sprain while running",
            physical_examination="Mild swelling over lateral malleolus, no bony tenderness.",
            treatment_plan="RICE protocol (Rest, Ice, Compression, Elevation).",
        )
        self.assertIsNotNone(walk_in.pk)
        self.assertIsNone(walk_in.appointment)
        self.assertEqual(walk_in.patient, self.patient2)

    # 3. Patient and Doctor are Required
    def test_patient_and_doctor_are_required(self):
        """Verify that consultation cannot be saved without patient or doctor."""
        # Missing patient
        with self.assertRaises(ValidationError) as ctx1:
            c1 = Consultation(
                patient=None,
                doctor=self.doctor1,
                chief_complaint="Severe headache",
            )
            c1.save()
        self.assertIn("patient", ctx1.exception.message_dict)

        # Missing doctor
        with self.assertRaises(ValidationError) as ctx2:
            c2 = Consultation(
                patient=self.patient1,
                doctor=None,
                chief_complaint="Severe headache",
            )
            c2.save()
        self.assertIn("doctor", ctx2.exception.message_dict)

    # 4. Appointment Patient and Doctor Must Match
    def test_appointment_patient_and_doctor_must_match(self):
        """Verify that appointment patient and doctor must strictly match consultation fields."""
        # Mismatched Patient
        with self.assertRaises(ValidationError) as ctx_pat:
            Consultation.objects.create(
                patient=self.patient2,  # Mismatch: Appointment is for patient1
                doctor=self.doctor1,
                appointment=self.appointment,
                chief_complaint="Mismatched patient test",
            )
        self.assertIn("appointment", ctx_pat.exception.message_dict)

        # Mismatched Doctor
        with self.assertRaises(ValidationError) as ctx_doc:
            Consultation.objects.create(
                patient=self.patient1,
                doctor=self.doctor2,  # Mismatch: Appointment is with doctor1
                appointment=self.appointment,
                chief_complaint="Mismatched doctor test",
            )
        self.assertIn("appointment", ctx_doc.exception.message_dict)

    # 5. Cancelled Appointments Cannot Receive Consultations
    def test_cancelled_appointments_cannot_receive_consultations(self):
        """Verify that a cancelled appointment is rejected for consultation creation."""
        self.appointment.cancel()
        with self.assertRaises(ValidationError) as ctx:
            Consultation.objects.create(
                patient=self.patient1,
                doctor=self.doctor1,
                appointment=self.appointment,
                chief_complaint="Cancelled appointment test",
            )
        self.assertIn("appointment", ctx.exception.message_dict)

    # 6. An Appointment Cannot Have Multiple Consultations
    def test_appointment_cannot_have_multiple_consultations(self):
        """Verify that an appointment cannot be linked to more than one consultation."""
        Consultation.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            appointment=self.appointment,
            chief_complaint="First consultation for this appointment",
        )
        with self.assertRaises((ValidationError, IntegrityError)):
            Consultation.objects.create(
                patient=self.patient1,
                doctor=self.doctor1,
                appointment=self.appointment,
                chief_complaint="Second consultation attempt",
            )

    # 7. Inactive Patients Cannot Receive New Consultations
    def test_inactive_patients_cannot_receive_new_consultations(self):
        """Verify that inactive patients cannot receive new consultations."""
        with self.assertRaises(ValidationError) as ctx:
            Consultation.objects.create(
                patient=self.patient_inactive,
                doctor=self.doctor1,
                chief_complaint="Inactive patient test",
            )
        self.assertIn("patient", ctx.exception.message_dict)

    # 8. Inactive Doctors Cannot Receive New Consultations
    def test_inactive_doctors_cannot_receive_new_consultations(self):
        """Verify that inactive doctors cannot receive new consultations."""
        with self.assertRaises(ValidationError) as ctx:
            Consultation.objects.create(
                patient=self.patient1,
                doctor=self.doctor_inactive,
                chief_complaint="Inactive doctor test",
            )
        self.assertIn("doctor", ctx.exception.message_dict)

    # 9. Successful VitalSign Creation
    def test_successful_vitalsign_creation(self):
        """Verify that physiological vital signs can be recorded and linked to a consultation."""
        consultation = Consultation.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            chief_complaint="Routine health assessment",
        )
        vitals = VitalSign.objects.create(
            consultation=consultation,
            systolic_bp=120,
            diastolic_bp=80,
            pulse_rate=72,
            respiratory_rate=16,
            temperature=Decimal("36.8"),
            spo2=Decimal("98.5"),
            height=Decimal("175.0"),
            weight=Decimal("70.00"),
        )
        self.assertIsNotNone(vitals.pk)
        self.assertEqual(consultation.vitals, vitals)
        self.assertIn("120/80 mmHg", str(vitals))
        self.assertIn("72 bpm", str(vitals))

    # 10. BMI Calculation Using Height and Weight
    def test_bmi_calculation_using_height_and_weight(self):
        """
        Verify automatic calculation of BMI:
        Height = 170 cm, Weight = 70 kg -> BMI = 70 / (1.70 * 1.70) = 24.22
        """
        consultation = Consultation.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            chief_complaint="Anthropometry test",
        )
        vitals = VitalSign.objects.create(
            consultation=consultation,
            height=Decimal("170.0"),
            weight=Decimal("70.00"),
        )
        self.assertEqual(vitals.bmi, Decimal("24.22"))

    # 11. BMI Recalculation After Changing Height or Weight
    def test_bmi_recalculation_after_changing_height_or_weight(self):
        """
        Verify BMI automatically recalculates when height or weight is updated:
        Update height to 180 cm, weight remains 70 kg -> BMI = 70 / (1.80 * 1.80) = 21.60
        """
        consultation = Consultation.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            chief_complaint="BMI update test",
        )
        vitals = VitalSign.objects.create(
            consultation=consultation,
            height=Decimal("170.0"),
            weight=Decimal("70.00"),
        )
        self.assertEqual(vitals.bmi, Decimal("24.22"))

        # Update height
        vitals.height = Decimal("180.0")
        vitals.save()
        self.assertEqual(vitals.bmi, Decimal("21.60"))

    # 12. Negative or Invalid Measurements are Rejected
    def test_negative_or_invalid_measurements_rejected(self):
        """Verify bounds checking on blood pressure, pulse, temperature, and measurements."""
        consultation = Consultation.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            chief_complaint="Measurement bounds test",
        )

        # Inverted blood pressure (systolic < diastolic)
        with self.assertRaises(ValidationError) as ctx_bp:
            VitalSign.objects.create(
                consultation=consultation,
                systolic_bp=80,
                diastolic_bp=120,
            )
        self.assertIn("systolic_bp", ctx_bp.exception.message_dict)

        # Invalid temperature (outside 25.0 - 45.0)
        with self.assertRaises(ValidationError) as ctx_temp:
            VitalSign.objects.create(
                consultation=consultation,
                temperature=Decimal("50.0"),
            )
        self.assertIn("temperature", ctx_temp.exception.message_dict)

        # Invalid negative height
        with self.assertRaises(ValidationError) as ctx_h:
            VitalSign.objects.create(
                consultation=consultation,
                height=Decimal("-170.0"),
            )
        self.assertIn("height", ctx_h.exception.message_dict)

    # 13. SpO2 Values Outside 0-100 are Rejected
    def test_spo2_values_outside_0_to_100_rejected(self):
        """Verify oxygen saturation SpO2 bounds (0.0 to 100.0)."""
        consultation = Consultation.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            chief_complaint="SpO2 test",
        )
        # Above 100%
        with self.assertRaises(ValidationError) as ctx_high:
            VitalSign.objects.create(
                consultation=consultation,
                spo2=Decimal("105.0"),
            )
        self.assertIn("spo2", ctx_high.exception.message_dict)

        # Below 0%
        with self.assertRaises(ValidationError) as ctx_low:
            VitalSign.objects.create(
                consultation=consultation,
                spo2=Decimal("-5.0"),
            )
        self.assertIn("spo2", ctx_low.exception.message_dict)

    # 14. Missing Measurements Handled Correctly
    def test_missing_measurements_handled_correctly(self):
        """Verify vital sign records save cleanly with partial or missing optional fields."""
        consultation = Consultation.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            chief_complaint="Partial vitals test",
        )
        vitals = VitalSign.objects.create(
            consultation=consultation,
            pulse_rate=78,
            # All other vitals omitted
        )
        self.assertIsNotNone(vitals.pk)
        self.assertIsNone(vitals.systolic_bp)
        self.assertIsNone(vitals.height)
        self.assertIsNone(vitals.bmi)

    # 15. Draft Consultation Can Be Updated
    def test_draft_consultation_can_be_updated(self):
        """Verify that draft consultations can be edited and updated freely."""
        consultation = Consultation.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            chief_complaint="Initial headache",
            status=Consultation.Status.DRAFT,
        )
        consultation.chief_complaint = "Tension headache with photophobia"
        consultation.treatment_plan = "Analgesics and darkened rest room"
        consultation.save()

        consultation.refresh_from_db()
        self.assertEqual(consultation.chief_complaint, "Tension headache with photophobia")
        self.assertEqual(consultation.status, Consultation.Status.DRAFT)

    # 16. Finalized Consultation Cannot Be Silently Overwritten
    def test_finalized_consultation_cannot_be_silently_overwritten(self):
        """Verify that finalized consultations cannot be silently modified without amendment notes."""
        consultation = Consultation.objects.create(
            patient=self.patient1,
            doctor=self.doctor1,
            chief_complaint="Chest tightness",
            status=Consultation.Status.DRAFT,
        )
        consultation.finalize()
        self.assertEqual(consultation.status, Consultation.Status.FINALIZED)
        self.assertIsNotNone(consultation.finalized_at)

        # Attempt silent edit without amendment notes -> must be blocked
        consultation.chief_complaint = "Altered complaint without documentation"
        with self.assertRaises(ValidationError) as ctx:
            consultation.save()
        self.assertIn("amendment_notes", ctx.exception.message_dict)

        # Explicit amendment with documented justification -> allowed
        consultation.refresh_from_db()
        consultation.treatment_plan = "Added sublingual nitroglycerin PRN"
        consultation.amendment_notes = "Addendum on review: prescribed nitroglycerin after stress ECG."
        consultation.save()

        consultation.refresh_from_db()
        self.assertEqual(consultation.treatment_plan, "Added sublingual nitroglycerin PRN")

        # Deletion of finalized consultation is blocked
        with self.assertRaises(ValidationError):
            consultation.delete()

    # 17. Django Admin Configuration
    def test_consultation_admin_configuration(self):
        """Verify admin registration, list displays, search fields, and inlines."""
        self.assertIn(Consultation, admin.site._registry)
        self.assertIn(VitalSign, admin.site._registry)

        c_admin = admin.site._registry[Consultation]
        v_admin = admin.site._registry[VitalSign]

        self.assertIsInstance(c_admin, ConsultationAdmin)
        self.assertIsInstance(v_admin, VitalSignAdmin)

        # List display
        self.assertIn("get_patient_mrn", c_admin.list_display)
        self.assertIn("get_patient_name", c_admin.list_display)
        self.assertIn("get_doctor_name", c_admin.list_display)
        self.assertIn("status", c_admin.list_display)

        # Filters and search
        self.assertIn("status", c_admin.list_filter)
        self.assertIn("consultation_date", c_admin.list_filter)
        self.assertIn("patient__patient_id", c_admin.search_fields)
        self.assertIn("chief_complaint", c_admin.search_fields)

        # Inlines
        self.assertIn(VitalSignInline, c_admin.inlines)
        self.assertIn(DiagnosisInline, c_admin.inlines)



class DiagnosisAndPatientTimelineTests(TestCase):
    """
    Automated test suite for Diagnosis Management and Patient Medical History (Step 8).
    """

    def setUp(self):
        # Department
        self.department = Department.objects.create(
            name="Cardiology & Internal Medicine",
            description="Outpatient cardiology and general medicine",
            is_active=True,
        )
        # Doctor User (role=DOCTOR)
        self.doc_user = User.objects.create_user(
            username="dr_gregory_house",
            email="house@clinic.test",
            password="SecurePass123!",
            first_name="Gregory",
            last_name="House",
            role=User.Role.DOCTOR,
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doc_user,
            department=self.department,
            specialization="Diagnostic Medicine",
            qualification="MD",
            is_active=True,
        )

        # Receptionist User (role=RECEPTIONIST)
        self.receptionist_user = User.objects.create_user(
            username="receptionist_pam",
            email="pam@clinic.test",
            password="SecurePass123!",
            first_name="Pam",
            last_name="Beesly",
            role=User.Role.RECEPTIONIST,
        )

        # Admin User (role=ADMIN)
        self.admin_user = User.objects.create_user(
            username="admin_cudy",
            email="cudy@clinic.test",
            password="SecurePass123!",
            first_name="Lisa",
            last_name="Cuddy",
            role=User.Role.ADMIN,
        )

        # Patient 1
        self.patient1 = Patient.objects.create(
            first_name="Arthur",
            last_name="Dent",
            date_of_birth=date(1982, 3, 11),
            gender=Patient.Gender.MALE,
            contact_number="9876543210",
            is_active=True,
        )

        # Patient 2 (for cross-patient leakage tests)
        self.patient2 = Patient.objects.create(
            first_name="Ford",
            last_name="Prefect",
            date_of_birth=date(1980, 5, 25),
            gender=Patient.Gender.MALE,
            contact_number="9876543211",
            is_active=True,
        )

        # Consultation for Patient 1
        self.consultation1 = Consultation.objects.create(
            patient=self.patient1,
            doctor=self.doctor,
            chief_complaint="Persistent headaches and elevated blood pressure",
            status=Consultation.Status.FINALIZED,
            consultation_date=timezone.now() - timedelta(days=2),
            follow_up_date=timezone.now().date() + timedelta(days=14),
            follow_up_notes="Re-check blood pressure in 2 weeks",
        )

    # 1. Successful primary diagnosis creation
    def test_successful_primary_diagnosis_creation(self):
        """Verify that a primary diagnosis can be recorded with valid attributes."""
        dx = Diagnosis.objects.create(
            consultation=self.consultation1,
            diagnosis_name="Essential (primary) hypertension",
            diagnosis_code="I10",
            diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
            description="Stage 2 hypertension, newly diagnosed.",
            recorded_by=self.doc_user,
        )
        self.assertIsNotNone(dx.pk)
        self.assertEqual(dx.diagnosis_type, Diagnosis.DiagnosisType.PRIMARY)
        self.assertEqual(dx.diagnosis_name, "Essential (primary) hypertension")
        self.assertEqual(dx.diagnosis_code, "I10")
        self.assertIn("Essential (primary) hypertension", str(dx))

    # 2. Successful secondary diagnosis creation
    def test_successful_secondary_diagnosis_creation(self):
        """Verify that a secondary diagnosis can be recorded."""
        dx = Diagnosis.objects.create(
            consultation=self.consultation1,
            diagnosis_name="Tension-type headache",
            diagnosis_code="G44.2",
            diagnosis_type=Diagnosis.DiagnosisType.SECONDARY,
            description="Episodic tension headaches.",
            recorded_by=self.doc_user,
        )
        self.assertIsNotNone(dx.pk)
        self.assertEqual(dx.diagnosis_type, Diagnosis.DiagnosisType.SECONDARY)
        self.assertIn("Secondary", str(dx))

    # 3. Multiple secondary diagnoses for one consultation
    def test_multiple_secondary_diagnoses_allowed(self):
        """Verify that multiple secondary diagnoses can be added to one consultation."""
        Diagnosis.objects.create(
            consultation=self.consultation1,
            diagnosis_name="Primary Dx",
            diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
            recorded_by=self.doc_user,
        )
        sec1 = Diagnosis.objects.create(
            consultation=self.consultation1,
            diagnosis_name="Secondary Dx 1",
            diagnosis_type=Diagnosis.DiagnosisType.SECONDARY,
            recorded_by=self.doc_user,
        )
        sec2 = Diagnosis.objects.create(
            consultation=self.consultation1,
            diagnosis_name="Secondary Dx 2",
            diagnosis_type=Diagnosis.DiagnosisType.SECONDARY,
            recorded_by=self.doc_user,
        )
        self.assertEqual(
            self.consultation1.diagnoses.filter(
                diagnosis_type=Diagnosis.DiagnosisType.SECONDARY
            ).count(),
            2,
        )
        self.assertIn(sec1, self.consultation1.diagnoses.all())
        self.assertIn(sec2, self.consultation1.diagnoses.all())

    # 4. Duplicate primary diagnosis rejection
    def test_duplicate_primary_diagnosis_rejected(self):
        """Verify that only one PRIMARY diagnosis is permitted per consultation."""
        Diagnosis.objects.create(
            consultation=self.consultation1,
            diagnosis_name="First Primary Dx",
            diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
            recorded_by=self.doc_user,
        )
        dup = Diagnosis(
            consultation=self.consultation1,
            diagnosis_name="Second Primary Dx",
            diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
            recorded_by=self.doc_user,
        )
        with self.assertRaises((ValidationError, IntegrityError)):
            dup.save()

    # 5. Empty diagnosis name rejection
    def test_empty_diagnosis_name_rejected(self):
        """Verify that an empty or whitespace-only diagnosis name raises ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            Diagnosis.objects.create(
                consultation=self.consultation1,
                diagnosis_name="   ",
                diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
                recorded_by=self.doc_user,
            )
        self.assertIn("diagnosis_name", ctx.exception.message_dict)

    # 6. Diagnosis linked to the correct consultation
    def test_diagnosis_linked_to_correct_consultation(self):
        """Verify relational integrity between diagnosis and consultation."""
        dx = Diagnosis.objects.create(
            consultation=self.consultation1,
            diagnosis_name="Type 2 Diabetes Mellitus",
            diagnosis_code="E11",
            diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
            recorded_by=self.doc_user,
        )
        self.assertEqual(dx.consultation, self.consultation1)
        self.assertIn(dx, self.consultation1.diagnoses.all())

    # 7. Diagnosis patient and doctor derived correctly
    def test_diagnosis_patient_and_doctor_derived(self):
        """Verify that patient and doctor are derived accurately from consultation."""
        dx = Diagnosis.objects.create(
            consultation=self.consultation1,
            diagnosis_name="Migraine without aura",
            diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
            recorded_by=self.doc_user,
        )
        self.assertEqual(dx.patient, self.patient1)
        self.assertEqual(dx.doctor, self.doctor)

    # 8. Unauthorized diagnosis modification / recording protection
    def test_unauthorized_user_cannot_record_diagnosis(self):
        """Verify that users without the DOCTOR role cannot be recorded as the diagnosing clinician."""
        with self.assertRaises(ValidationError) as ctx_rec:
            Diagnosis.objects.create(
                consultation=self.consultation1,
                diagnosis_name="Hypertension",
                diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
                recorded_by=self.receptionist_user,
            )
        self.assertIn("recorded_by", ctx_rec.exception.message_dict)

        with self.assertRaises(ValidationError) as ctx_adm:
            Diagnosis.objects.create(
                consultation=self.consultation1,
                diagnosis_name="Hypertension",
                diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
                recorded_by=self.admin_user,
            )
        self.assertIn("recorded_by", ctx_adm.exception.message_dict)

    # 9. Patient timeline retrieves consultations correctly
    def test_patient_timeline_retrieves_consultations(self):
        """Verify that patient timeline includes recorded consultations."""
        timeline = get_patient_timeline(self.patient1)
        self.assertEqual(timeline["patient"], self.patient1)
        self.assertEqual(len(timeline["consultations"]), 1)
        self.assertEqual(timeline["consultations"][0], self.consultation1)

    # 10. Patient timeline includes walk-in consultations
    def test_patient_timeline_includes_walk_in_consultations(self):
        """Verify walk-in consultations without appointments are included in the timeline."""
        self.assertIsNone(self.consultation1.appointment)
        timeline = get_patient_timeline(self.patient1)
        self.assertIn(self.consultation1, timeline["consultations"])

    # 11. Patient timeline retrieves diagnoses correctly
    def test_patient_timeline_retrieves_diagnoses(self):
        """Verify that diagnoses associated with consultations are present in the timeline."""
        dx1 = Diagnosis.objects.create(
            consultation=self.consultation1,
            diagnosis_name="Essential Hypertension",
            diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
            recorded_by=self.doc_user,
        )
        dx2 = Diagnosis.objects.create(
            consultation=self.consultation1,
            diagnosis_name="Dyslipidemia",
            diagnosis_type=Diagnosis.DiagnosisType.SECONDARY,
            recorded_by=self.doc_user,
        )
        timeline = get_patient_timeline(self.patient1)
        c = timeline["consultations"][0]
        diagnoses = list(c.diagnoses.all())
        self.assertEqual(len(diagnoses), 2)
        self.assertIn(dx1, diagnoses)
        self.assertIn(dx2, diagnoses)

    # 12. Patient timeline retrieves issued prescriptions and medicine items
    def test_patient_timeline_retrieves_prescriptions_and_items(self):
        """Verify that prescriptions and items linked to consultations are in the timeline."""
        rx = Prescription.objects.create(
            consultation=self.consultation1,
            general_instructions="Take with warm water",
        )
        item = PrescriptionItem.objects.create(
            prescription=rx,
            medicine_name="Amlodipine",
            dosage_form=PrescriptionItem.DosageForm.TABLET,
            strength="5 mg",
            dosage="1 tablet",
            frequency="OD",
            duration=30,
        )
        rx.issue(issued_by=self.doc_user)

        timeline = get_patient_timeline(self.patient1)
        c = timeline["consultations"][0]
        self.assertTrue(hasattr(c, "prescription"))
        self.assertEqual(c.prescription, rx)
        items = list(c.prescription.items.all())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0], item)

    # 13. Patient timeline retrieves medical history and allergies
    def test_patient_timeline_retrieves_medical_history_and_allergies(self):
        """Verify that medical histories and allergies are retrieved in the timeline."""
        mh = MedicalHistory.objects.create(
            patient=self.patient1,
            condition="Childhood Asthma",
            diagnosed_date=date(1995, 6, 1),
        )
        al = Allergy.objects.create(
            patient=self.patient1,
            allergen="Penicillin",
            severity=Allergy.Severity.SEVERE,
            reaction="Anaphylaxis",
        )
        timeline = get_patient_timeline(self.patient1)
        self.assertEqual(len(timeline["medical_histories"]), 1)
        self.assertEqual(timeline["medical_histories"][0], mh)
        self.assertEqual(len(timeline["allergies"]), 1)
        self.assertEqual(timeline["allergies"][0], al)

    # 14. Timeline ordering is newest first
    def test_timeline_ordering_is_newest_first(self):
        """Verify that consultations in timeline are strictly ordered newest-first."""
        c_older = self.consultation1
        c_newer = Consultation.objects.create(
            patient=self.patient1,
            doctor=self.doctor,
            chief_complaint="Follow-up visit",
            status=Consultation.Status.FINALIZED,
            consultation_date=timezone.now(),
        )
        timeline = get_patient_timeline(self.patient1)
        consultations = timeline["consultations"]
        self.assertEqual(len(consultations), 2)
        self.assertEqual(consultations[0], c_newer)
        self.assertEqual(consultations[1], c_older)

    # 15. Records belonging to another patient are not included
    def test_records_belonging_to_another_patient_excluded(self):
        """Verify strict isolation: no data from other patients leaks into the timeline."""
        c2 = Consultation.objects.create(
            patient=self.patient2,
            doctor=self.doctor,
            chief_complaint="Other patient problem",
            status=Consultation.Status.FINALIZED,
        )
        Diagnosis.objects.create(
            consultation=c2,
            diagnosis_name="Other Patient Diagnosis",
            diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
            recorded_by=self.doc_user,
        )
        MedicalHistory.objects.create(
            patient=self.patient2,
            condition="Other Patient Condition",
        )
        Allergy.objects.create(
            patient=self.patient2,
            allergen="Sulfa drugs",
            severity=Allergy.Severity.MILD,
        )

        timeline1 = get_patient_timeline(self.patient1)
        self.assertNotIn(c2, timeline1["consultations"])
        for c in timeline1["consultations"]:
            self.assertEqual(c.patient, self.patient1)
        for mh in timeline1["medical_histories"]:
            self.assertEqual(mh.patient, self.patient1)
        for al in timeline1["allergies"]:
            self.assertEqual(al.patient, self.patient1)

    # 16. Existing consultations and prescriptions remain intact
    def test_existing_consultations_and_prescriptions_remain_intact(self):
        """Verify existing consultation and prescription records maintain integrity."""
        self.assertEqual(Consultation.objects.filter(pk=self.consultation1.pk).count(), 1)
        self.assertEqual(self.consultation1.status, Consultation.Status.FINALIZED)

    # 17. Diagnosis Admin configuration
    def test_diagnosis_admin_configuration(self):
        """Verify Diagnosis is properly registered in Django Admin."""
        self.assertIn(Diagnosis, admin.site._registry)
        d_admin = admin.site._registry[Diagnosis]
        self.assertIsInstance(d_admin, DiagnosisAdmin)

        self.assertIn("diagnosis_name", d_admin.list_display)
        self.assertIn("diagnosis_type", d_admin.list_display)
        self.assertIn("get_patient_name", d_admin.list_display)
        self.assertIn("get_doctor_name", d_admin.list_display)

        self.assertIn("diagnosis_type", d_admin.list_filter)
        self.assertIn("diagnosis_name", d_admin.search_fields)
        self.assertIn("diagnosis_code", d_admin.search_fields)


class DoctorConsultationWorkflowTests(TestCase):
    """
    Automated test suite for Doctor Portal - Consultation, Case-Taking,
    Vital Signs, Diagnoses, and Patient Timeline (Step 10C).
    """

    def setUp(self):
        self.client = Client()

        # Department
        self.dept = Department.objects.create(name="Internal Medicine", is_active=True)

        # Doctor 1
        self.doc_user1 = User.objects.create_user(
            username="dr_watson",
            email="watson@clinic.test",
            password="SecurePass123!",
            first_name="John",
            last_name="Watson",
            role=User.Role.DOCTOR,
        )
        self.doctor1 = DoctorProfile.objects.create(
            user=self.doc_user1,
            department=self.dept,
            specialization="General Practice",
            qualification="MBBS, MD",
            is_active=True,
        )

        # Doctor 2
        self.doc_user2 = User.objects.create_user(
            username="dr_moriarty",
            email="moriarty@clinic.test",
            password="SecurePass123!",
            first_name="James",
            last_name="Moriarty",
            role=User.Role.DOCTOR,
        )
        self.doctor2 = DoctorProfile.objects.create(
            user=self.doc_user2,
            department=self.dept,
            specialization="Forensic Medicine",
            qualification="MBBS, MD",
            is_active=True,
        )

        # Patient
        self.patient = Patient.objects.create(
            first_name="Sherlock",
            last_name="Holmes",
            date_of_birth=date(1980, 1, 6),
            gender=Patient.Gender.MALE,
            contact_number="9876500111",
            is_active=True,
        )

        self.tomorrow = timezone.localdate() + timedelta(days=1)
        self.appointment = Appointment.objects.create(
            patient=self.patient,
            doctor=self.doctor1,
            appointment_date=self.tomorrow,
            start_time=time(10, 0),
            end_time=time(10, 30),
            reason="Unexplained respiratory episodes",
            status=Appointment.Status.SCHEDULED,
        )

    # 11. Doctor can start a consultation for their appointment
    def test_doctor_can_start_consultation_for_appointment(self):
        self.client.login(username="dr_watson", password="SecurePass123!")
        response = self.client.get(reverse("appointments:start_consultation", args=[self.appointment.pk]), follow=True)
        self.assertEqual(response.status_code, 200)

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.IN_PROGRESS)

        consultation = Consultation.objects.filter(appointment=self.appointment).first()
        self.assertIsNotNone(consultation)
        self.assertEqual(consultation.doctor, self.doctor1)
        self.assertEqual(consultation.patient, self.patient)
        self.assertEqual(consultation.status, Consultation.Status.DRAFT)

    # 12. Existing consultation is retrieved instead of duplicated
    def test_existing_consultation_retrieved_not_duplicated(self):
        self.client.login(username="dr_watson", password="SecurePass123!")
        # Start once
        self.client.get(reverse("appointments:start_consultation", args=[self.appointment.pk]))
        self.assertEqual(Consultation.objects.filter(appointment=self.appointment).count(), 1)

        # Start again
        self.client.get(reverse("appointments:start_consultation", args=[self.appointment.pk]))
        self.assertEqual(Consultation.objects.filter(appointment=self.appointment).count(), 1)

    # 13. Patient and doctor relationships remain strictly correct
    def test_patient_and_doctor_relationships_remain_correct(self):
        self.client.login(username="dr_watson", password="SecurePass123!")
        self.client.get(reverse("appointments:start_consultation", args=[self.appointment.pk]))
        consultation = Consultation.objects.get(appointment=self.appointment)
        self.assertEqual(consultation.patient_id, self.patient.id)
        self.assertEqual(consultation.doctor_id, self.doctor1.id)

    # 14. Draft consultation can be edited
    def test_draft_consultation_can_be_edited(self):
        consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor1,
            chief_complaint="Initial symptom note",
            status=Consultation.Status.DRAFT,
        )
        self.client.login(username="dr_watson", password="SecurePass123!")
        edit_data = {
            "chief_complaint": "Updated persistent cough and fever",
            "history_of_present_illness": "Symptoms worsening over past 3 days",
            "physical_examination": "Chest clear on auscultation",
            "treatment_plan": "Rest and hydration",
            "action": "save_draft",
        }
        response = self.client.post(reverse("consultations:edit", args=[consultation.pk]), edit_data, follow=True)
        self.assertEqual(response.status_code, 200)

        consultation.refresh_from_db()
        self.assertEqual(consultation.chief_complaint, "Updated persistent cough and fever")
        self.assertEqual(consultation.history_of_present_illness, "Symptoms worsening over past 3 days")

    # 15. Finalized consultation protections remain active
    def test_finalized_consultation_protections_active(self):
        consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor1,
            chief_complaint="Original complaint",
            status=Consultation.Status.FINALIZED,
        )
        self.client.login(username="dr_watson", password="SecurePass123!")

        # Attempt to modify without amendment notes
        invalid_data = {
            "chief_complaint": "Silently modified complaint",
            "action": "save_draft",
        }
        response = self.client.post(reverse("consultations:edit", args=[consultation.pk]), invalid_data)
        consultation.refresh_from_db()
        self.assertEqual(consultation.chief_complaint, "Original complaint")

        # Modifying WITH amendment notes is permitted
        valid_amendment_data = {
            "chief_complaint": "Corrected complaint",
            "amendment_notes": "Correction per lab findings",
            "action": "save_draft",
        }
        self.client.post(reverse("consultations:edit", args=[consultation.pk]), valid_amendment_data)
        consultation.refresh_from_db()
        self.assertEqual(consultation.chief_complaint, "Corrected complaint")

    # 16. Walk-in consultation workflow works where authorized
    def test_walk_in_consultation_creation(self):
        self.client.login(username="dr_watson", password="SecurePass123!")
        post_data = {
            "patient": self.patient.pk,
            "chief_complaint": "Acute sudden onset headaches",
        }
        response = self.client.post(reverse("consultations:create"), post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        walk_in_consult = Consultation.objects.filter(
            patient=self.patient,
            doctor=self.doctor1,
            appointment__isnull=True,
            chief_complaint="Acute sudden onset headaches",
        ).first()
        self.assertIsNotNone(walk_in_consult)
        self.assertEqual(walk_in_consult.status, Consultation.Status.DRAFT)

    # 17. Vital signs save correctly
    def test_vital_signs_save_correctly(self):
        consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor1,
            chief_complaint="Hypertension monitoring",
            status=Consultation.Status.DRAFT,
        )
        self.client.login(username="dr_watson", password="SecurePass123!")
        post_data = {
            "chief_complaint": "Hypertension monitoring",
            "systolic_bp": "130",
            "diastolic_bp": "85",
            "pulse_rate": "76",
            "temperature": "36.8",
            "spo2": "99.0",
            "height": "180.0",
            "weight": "81.00",
            "action": "save_draft",
        }
        self.client.post(reverse("consultations:edit", args=[consultation.pk]), post_data)

        vitals = VitalSign.objects.filter(consultation=consultation).first()
        self.assertIsNotNone(vitals)
        self.assertEqual(vitals.systolic_bp, 130)
        self.assertEqual(vitals.diastolic_bp, 85)
        self.assertEqual(vitals.pulse_rate, 76)
        self.assertEqual(vitals.temperature, Decimal("36.8"))

    # 18. BMI calculates automatically
    def test_bmi_calculates_automatically(self):
        consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor1,
            chief_complaint="Physical fitness assessment",
            status=Consultation.Status.DRAFT,
        )
        # Height 180cm, Weight 81kg -> BMI = 81 / (1.8^2) = 25.00
        vitals = VitalSign.objects.create(
            consultation=consultation,
            height=Decimal("180.0"),
            weight=Decimal("81.00"),
        )
        self.assertEqual(vitals.bmi, Decimal("25.00"))

    # 19. Invalid measurements are rejected
    def test_invalid_vital_measurements_rejected(self):
        consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor1,
            chief_complaint="Vitals validation test",
            status=Consultation.Status.DRAFT,
        )
        self.client.login(username="dr_watson", password="SecurePass123!")
        post_data = {
            "chief_complaint": "Vitals validation test",
            "systolic_bp": "20",  # Below minimum 40
            "diastolic_bp": "80",
            "action": "save_draft",
        }
        response = self.client.post(reverse("consultations:edit", args=[consultation.pk]), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(VitalSign.objects.filter(consultation=consultation).exists())

    # 20. Partial vitals are supported
    def test_partial_vitals_supported(self):
        consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor1,
            chief_complaint="Quick BP check",
            status=Consultation.Status.DRAFT,
        )
        self.client.login(username="dr_watson", password="SecurePass123!")
        post_data = {
            "chief_complaint": "Quick BP check",
            "systolic_bp": "120",
            "diastolic_bp": "80",
            # other vitals blank
            "action": "save_draft",
        }
        self.client.post(reverse("consultations:edit", args=[consultation.pk]), post_data)
        vitals = VitalSign.objects.filter(consultation=consultation).first()
        self.assertIsNotNone(vitals)
        self.assertEqual(vitals.systolic_bp, 120)
        self.assertIsNone(vitals.pulse_rate)
        self.assertIsNone(vitals.height)

    # 21. Primary diagnosis can be added
    def test_primary_diagnosis_can_be_added(self):
        consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor1,
            chief_complaint="Diagnostic review",
            status=Consultation.Status.DRAFT,
        )
        self.client.login(username="dr_watson", password="SecurePass123!")
        diag_data = {
            "diagnosis_name": "Acute Bronchitis",
            "diagnosis_code": "J20.9",
            "diagnosis_type": Diagnosis.DiagnosisType.PRIMARY,
            "description": "Mild wheezing",
            "action": "add_diagnosis",
        }
        self.client.post(reverse("consultations:edit", args=[consultation.pk]), diag_data, follow=True)

        diag = Diagnosis.objects.filter(consultation=consultation, diagnosis_type="PRIMARY").first()
        self.assertIsNotNone(diag)
        self.assertEqual(diag.diagnosis_name, "Acute Bronchitis")
        self.assertEqual(diag.recorded_by, self.doc_user1)

    # 22. Multiple secondary diagnoses can be added
    def test_multiple_secondary_diagnoses_added(self):
        consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor1,
            chief_complaint="Multi-comorbidity case",
            status=Consultation.Status.DRAFT,
        )
        self.client.login(username="dr_watson", password="SecurePass123!")

        # Add Secondary 1
        self.client.post(
            reverse("consultations:edit", args=[consultation.pk]),
            {
                "diagnosis_name": "Seasonal Allergic Rhinitis",
                "diagnosis_type": Diagnosis.DiagnosisType.SECONDARY,
                "action": "add_diagnosis",
            },
        )
        # Add Secondary 2
        self.client.post(
            reverse("consultations:edit", args=[consultation.pk]),
            {
                "diagnosis_name": "Mild Dehydration",
                "diagnosis_type": Diagnosis.DiagnosisType.SECONDARY,
                "action": "add_diagnosis",
            },
        )
        secondary_count = Diagnosis.objects.filter(consultation=consultation, diagnosis_type="SECONDARY").count()
        self.assertEqual(secondary_count, 2)

    # 23. Duplicate primary diagnoses are rejected
    def test_duplicate_primary_diagnosis_rejected(self):
        consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor1,
            chief_complaint="One primary diagnosis test",
            status=Consultation.Status.DRAFT,
        )
        # Create first primary
        Diagnosis.objects.create(
            consultation=consultation,
            diagnosis_name="Primary 1",
            diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
            recorded_by=self.doc_user1,
        )
        self.client.login(username="dr_watson", password="SecurePass123!")
        # Attempt second primary via form
        response = self.client.post(
            reverse("consultations:edit", args=[consultation.pk]),
            {
                "diagnosis_name": "Primary 2",
                "diagnosis_type": Diagnosis.DiagnosisType.PRIMARY,
                "action": "add_diagnosis",
            },
            follow=True,
        )
        self.assertEqual(Diagnosis.objects.filter(consultation=consultation, diagnosis_type="PRIMARY").count(), 1)

    # 24. Finalize consultation works
    def test_finalize_consultation_workflow(self):
        consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor1,
            chief_complaint="Pre-op check",
            status=Consultation.Status.DRAFT,
        )
        self.client.login(username="dr_watson", password="SecurePass123!")
        response = self.client.post(reverse("consultations:finalize", args=[consultation.pk]), follow=False)
        self.assertEqual(response.status_code, 302)

        consultation.refresh_from_db()
        self.assertEqual(consultation.status, Consultation.Status.FINALIZED)
        self.assertIsNotNone(consultation.finalized_at)

    # 35. Consultations list and detail view render with 200 OK
    def test_consultation_list_and_detail_render(self):
        consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor1,
            chief_complaint="Regular checkup",
            status=Consultation.Status.FINALIZED,
        )
        self.client.login(username="dr_watson", password="SecurePass123!")

        # List view
        r_list = self.client.get(reverse("consultations:list"))
        self.assertEqual(r_list.status_code, 200)
        self.assertContains(r_list, "Regular checkup")

        # Detail view
        r_detail = self.client.get(reverse("consultations:detail", args=[consultation.pk]))
        self.assertEqual(r_detail.status_code, 200)
        self.assertContains(r_detail, "Sherlock Holmes")

