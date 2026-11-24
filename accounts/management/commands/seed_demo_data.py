"""
Django Management Command: seed_demo_data

Populates realistic, completely fictional demonstration data for college evaluations,
academic presentations, and viva demonstrations.

Idempotent: Safe to execute multiple times without generating duplicates or corrupting data.
Never uses real patient or personal identifiable information.
"""
from datetime import date, time, timedelta
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from appointments.models import Appointment
from audit.models import AuditLog
from audit.services import log_audit_event
from consultations.models import Consultation, Diagnosis, VitalSign
from departments.models import Department, DoctorProfile
from patients.models import Patient
from prescriptions.models import Prescription, PrescriptionItem

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds idempotent, safe demonstration data for college presentations."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Reset demonstration users' passwords to standard demo credentials.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Initializing safe demonstration data seeding..."))
        reset_passwords = options.get("reset_passwords", False)

        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        day_after = today + timedelta(days=2)

        # ----------------------------------------------------------------------
        # 1. Administrator Account
        # ----------------------------------------------------------------------
        admin_user, created = User.objects.get_or_create(
            username="admin_demo",
            defaults={
                "email": "admin@pulsecare.clinic.test",
                "first_name": "Arthur",
                "last_name": "Pendleton",
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        if created or reset_passwords:
            admin_user.set_password("AdminDemo2026!")
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("Created / Updated Administrator: admin_demo (Password: AdminDemo2026!)"))
        else:
            self.stdout.write("Administrator 'admin_demo' already exists.")

        # ----------------------------------------------------------------------
        # 2. Receptionist Accounts
        # ----------------------------------------------------------------------
        receptionists_data = [
            ("rec_sarah", "Sarah", "Connor", "sarah.connor@pulsecare.clinic.test"),
            ("rec_michael", "Michael", "Scott", "michael.scott@pulsecare.clinic.test"),
        ]
        for username, fname, lname, email in receptionists_data:
            rec_user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": fname,
                    "last_name": lname,
                    "email": email,
                    "role": User.Role.RECEPTIONIST,
                    "is_active": True,
                },
            )
            if created or reset_passwords:
                rec_user.set_password("ReceptionPass2026!")
                rec_user.save()
                self.stdout.write(self.style.SUCCESS(f"Created / Updated Receptionist: {username} (Password: ReceptionPass2026!)"))
            else:
                self.stdout.write(f"Receptionist '{username}' already exists.")

        # ----------------------------------------------------------------------
        # 3. Specialty Clinic Departments
        # ----------------------------------------------------------------------
        departments_data = [
            ("General Medicine", "Comprehensive primary adult outpatient healthcare, preventive triage, and systemic disease management."),
            ("Cardiology", "Cardiovascular health, hypertension management, adult ECG evaluation, and coronary outpatient care."),
            ("Pediatrics", "Infant, child, and adolescent healthcare, developmental assessments, and immunization consultations."),
            ("Orthopedics", "Musculoskeletal trauma, bone and joint care, arthritis treatment, and sports injury consultations."),
        ]
        dept_map = {}
        for name, desc in departments_data:
            dept, _ = Department.objects.get_or_create(
                name=name,
                defaults={"description": desc, "is_active": True},
            )
            dept_map[name] = dept
        self.stdout.write(self.style.SUCCESS(f"Verified {len(dept_map)} active clinical departments."))

        # ----------------------------------------------------------------------
        # 4. Clinical Specialists / Doctor Accounts & Profiles
        # ----------------------------------------------------------------------
        doctors_data = [
            (
                "dr_sharma",
                "Rajesh",
                "Sharma",
                "sharma@pulsecare.clinic.test",
                "General Medicine",
                "Internal Medicine",
                "MBBS, MD (Medicine)",
                "9876500101",
            ),
            (
                "dr_patel",
                "Priya",
                "Patel",
                "patel@pulsecare.clinic.test",
                "Cardiology",
                "Interventional Cardiology",
                "MBBS, MD, DM (Cardiology)",
                "9876500102",
            ),
            (
                "dr_verma",
                "Ananya",
                "Verma",
                "verma@pulsecare.clinic.test",
                "Pediatrics",
                "General Pediatrics",
                "MBBS, MD (Pediatrics)",
                "9876500103",
            ),
            (
                "dr_khan",
                "Tariq",
                "Khan",
                "khan@pulsecare.clinic.test",
                "Orthopedics",
                "Joint Replacement & Trauma",
                "MBBS, MS (Orthopedics)",
                "9876500104",
            ),
        ]
        doc_profile_map = {}
        for username, fname, lname, email, dept_name, spec, qual, phone in doctors_data:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": fname,
                    "last_name": lname,
                    "email": email,
                    "role": User.Role.DOCTOR,
                    "is_active": True,
                },
            )
            if created or reset_passwords:
                user.set_password("DoctorDemo2026!")
                user.save()

            profile, _ = DoctorProfile.objects.get_or_create(
                user=user,
                defaults={
                    "department": dept_map[dept_name],
                    "specialization": spec,
                    "qualification": qual,
                    "contact_number": phone,
                    "is_active": True,
                },
            )
            doc_profile_map[username] = profile
        self.stdout.write(self.style.SUCCESS(f"Verified {len(doc_profile_map)} medical specialists (Password: DoctorDemo2026!)."))

        # ----------------------------------------------------------------------
        # 5. Fictional Patients
        # ----------------------------------------------------------------------
        patients_data = [
            ("Ramesh", "Kumar", date(1978, 6, 15), "MALE", "B+", "9876500001", "ramesh.kumar@example.com", "Flat 402, Sunshine Heights", "New Delhi", "Delhi", "110001"),
            ("Sunita", "Devi", date(1985, 9, 22), "FEMALE", "O+", "9876500002", "sunita.devi@example.com", "H.No 12, Green Park", "New Delhi", "Delhi", "110016"),
            ("Amitabh", "Joshi", date(1962, 11, 4), "MALE", "A+", "9876500003", "amitabh.j@example.com", "B-88, Sector 14", "Gurugram", "Haryana", "122001"),
            ("Pooja", "Sharma", date(1994, 3, 18), "FEMALE", "AB+", "9876500004", "pooja.sharma@example.com", "55-A, Model Town", "Noida", "UP", "201301"),
            ("Master Aarav", "Mehta", date(2018, 7, 25), "MALE", "O-", "9876500005", "parents.mehta@example.com", "Plot 19, Mayur Vihar", "Delhi", "Delhi", "110091"),
        ]
        patient_map = {}
        for fname, lname, dob, gender, blood, phone, email, addr, city, state, pin in patients_data:
            patient = Patient.objects.filter(first_name=fname, last_name=lname).first()
            if not patient:
                patient = Patient.objects.create(
                    first_name=fname,
                    last_name=lname,
                    date_of_birth=dob,
                    gender=gender,
                    blood_group=blood,
                    contact_number=phone,
                    email=email,
                    address=addr,
                    city=city,
                    state=state,
                    pincode=pin,
                    emergency_contact_name=f"{fname}'s Family Contact",
                    emergency_contact_number=phone,
                    is_active=True,
                )
            patient_map[f"{fname}_{lname}"] = patient
        self.stdout.write(self.style.SUCCESS(f"Verified {len(patient_map)} registered patient master records with unique MRNs."))

        # ----------------------------------------------------------------------
        # 6. Appointments & Clinical Consultations
        # ----------------------------------------------------------------------
        p_ramesh = patient_map["Ramesh_Kumar"]
        p_sunita = patient_map["Sunita_Devi"]
        p_amitabh = patient_map["Amitabh_Joshi"]
        p_pooja = patient_map["Pooja_Sharma"]
        p_aarav = patient_map["Master Aarav_Mehta"]

        dr_sharma = doc_profile_map["dr_sharma"]
        dr_patel = doc_profile_map["dr_patel"]
        dr_verma = doc_profile_map["dr_verma"]
        dr_khan = doc_profile_map["dr_khan"]

        # Case 1: Ramesh Kumar -> Dr. Sharma (Completed Visit with Finalized Consultation & Rx)
        apt1 = Appointment.objects.filter(patient=p_ramesh, doctor=dr_sharma).first()
        if not apt1:
            apt1 = Appointment.objects.create(
                patient=p_ramesh,
                doctor=dr_sharma,
                appointment_date=tomorrow,
                start_time=time(10, 0),
                end_time=time(10, 30),
                status=Appointment.Status.COMPLETED,
                reason="Excessive thirst, fatigue, and suspected hyperglycemia review.",
            )
            # Update to yesterday for historical clinical record
            Appointment.objects.filter(pk=apt1.pk).update(appointment_date=yesterday)
            apt1.refresh_from_db()

        consult1 = Consultation.objects.filter(patient=p_ramesh, doctor=dr_sharma).first()
        if not consult1:
            consult1 = Consultation.objects.create(
                patient=p_ramesh,
                doctor=dr_sharma,
                appointment=apt1,
                chief_complaint="Persistent fatigue, polydipsia, and polyuria over the past 3 weeks.",
                history_of_present_illness="Patient reports gradual onset of high thirst and nocturnal frequency. Mild blurred vision on reading. No prior history of diabetic ketoacidosis.",
                past_medical_history="Mild primary hypertension diagnosed 2 years ago, controlled on lifestyle changes.",
                family_history="Strong paternal history of Type 2 Diabetes Mellitus.",
                physical_examination="Patient alert and oriented. BP 130/84 mmHg, PR 78 bpm, lungs clear, no pedal edema.",
                provisional_diagnosis="New-onset Type 2 Diabetes Mellitus.",
                treatment_plan="Dietary carbohydrate restriction, daily 30-minute brisk walk, oral hypoglycemic agents, repeat fasting glucose in 4 weeks.",
                status=Consultation.Status.FINALIZED,
            )
            # Record vitals
            VitalSign.objects.create(
                consultation=consult1,
                temperature="37.0",
                systolic_bp=130,
                diastolic_bp=84,
                pulse_rate=78,
                respiratory_rate=16,
                spo2="98.0",
                height="172.0",
                weight="82.00",
            )
            # Record diagnoses
            Diagnosis.objects.create(
                consultation=consult1,
                diagnosis_name="Type 2 Diabetes Mellitus without complications",
                diagnosis_code="E11.9",
                diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
                description="Elevated fasting plasma glucose and symptomatic polyuria.",
                recorded_by=dr_sharma.user,
            )
            Diagnosis.objects.create(
                consultation=consult1,
                diagnosis_name="Prehypertension",
                diagnosis_code="R03.0",
                diagnosis_type=Diagnosis.DiagnosisType.SECONDARY,
                description="Resting BP 130/84 mmHg, recommend low-sodium diet.",
                recorded_by=dr_sharma.user,
            )
            # Issue Prescription
            rx1 = Prescription.objects.create(
                consultation=consult1,
                status=Prescription.Status.ISSUED,
                general_instructions="Maintain low-glycemic diabetic diet. Avoid refined sugars. Drink 2.5L water daily.",
            )
            PrescriptionItem.objects.create(
                prescription=rx1,
                medicine_name="Metformin Hydrochloride (Glycomet)",
                dosage_form=PrescriptionItem.DosageForm.TABLET,
                strength="500 mg",
                dosage="1 tablet",
                frequency="BD (Twice daily)",
                duration=30,
                intake_timing=PrescriptionItem.IntakeTiming.AFTER_FOOD,
                special_instructions="Take with or immediately after morning and evening meals.",
            )
            PrescriptionItem.objects.create(
                prescription=rx1,
                medicine_name="Glimepiride (Amaryl)",
                dosage_form=PrescriptionItem.DosageForm.TABLET,
                strength="1 mg",
                dosage="1 tablet",
                frequency="OD (Once daily)",
                duration=30,
                intake_timing=PrescriptionItem.IntakeTiming.BEFORE_FOOD,
                special_instructions="Take 15 minutes before breakfast.",
            )

        # Case 2: Sunita Devi -> Dr. Patel (Cardiology Completed Consultation & Rx)
        apt2 = Appointment.objects.filter(patient=p_sunita, doctor=dr_patel).first()
        if not apt2:
            apt2 = Appointment.objects.create(
                patient=p_sunita,
                doctor=dr_patel,
                appointment_date=tomorrow,
                start_time=time(11, 0),
                end_time=time(11, 30),
                status=Appointment.Status.COMPLETED,
                reason="Intermittent exertional retrosternal discomfort.",
            )
            Appointment.objects.filter(pk=apt2.pk).update(appointment_date=yesterday)
            apt2.refresh_from_db()

        consult2 = Consultation.objects.filter(patient=p_sunita, doctor=dr_patel).first()
        if not consult2:
            consult2 = Consultation.objects.create(
                patient=p_sunita,
                doctor=dr_patel,
                appointment=apt2,
                chief_complaint="Substernal chest tightness when climbing stairs, resolving with rest.",
                history_of_present_illness="Symptom onset 2 weeks ago during brisk walking. Relieved within 5 minutes of resting.",
                physical_examination="Cardiovascular: S1 S2 normal, no third heart sound or gallop. Chest bilateral vesicular breath sounds.",
                provisional_diagnosis="Exertional Angina Pectoris.",
                treatment_plan="Resting 12-lead ECG, Treadmill Stress Test (TMT), dual antiplatelet and lipid-lowering therapy.",
                status=Consultation.Status.FINALIZED,
            )
            VitalSign.objects.create(
                consultation=consult2,
                temperature="36.8",
                systolic_bp=128,
                diastolic_bp=82,
                pulse_rate=72,
                respiratory_rate=14,
                spo2="99.0",
                height="158.0",
                weight="62.00",
            )
            Diagnosis.objects.create(
                consultation=consult2,
                diagnosis_name="Atherosclerotic Heart Disease / Angina Pectoris",
                diagnosis_code="I20.9",
                diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
                description="Stable exertional angina; cardiac risk stratification ordered.",
                recorded_by=dr_patel.user,
            )
            rx2 = Prescription.objects.create(
                consultation=consult2,
                status=Prescription.Status.ISSUED,
                general_instructions="Avoid strenuous physical overexertion. Carry emergency Sorbitrate as advised.",
            )
            PrescriptionItem.objects.create(
                prescription=rx2,
                medicine_name="Aspirin Gastro-resistant (Ecosprin)",
                dosage_form=PrescriptionItem.DosageForm.TABLET,
                strength="75 mg",
                dosage="1 tablet",
                frequency="OD (Once daily)",
                duration=30,
                intake_timing=PrescriptionItem.IntakeTiming.AFTER_FOOD,
                special_instructions="Take post-lunch with a full glass of water.",
            )
            PrescriptionItem.objects.create(
                prescription=rx2,
                medicine_name="Atorvastatin (Atorva)",
                dosage_form=PrescriptionItem.DosageForm.TABLET,
                strength="20 mg",
                dosage="1 tablet",
                frequency="OD (Once daily)",
                duration=30,
                intake_timing=PrescriptionItem.IntakeTiming.AFTER_FOOD,
                special_instructions="Take at bedtime.",
            )

        # Case 3: Master Aarav Mehta -> Dr. Verma (Pediatrics Scheduled Upcoming Appointment)
        apt3 = Appointment.objects.filter(patient=p_aarav, doctor=dr_verma).first()
        if not apt3:
            apt3 = Appointment.objects.create(
                patient=p_aarav,
                doctor=dr_verma,
                appointment_date=tomorrow,
                start_time=time(10, 0),
                end_time=time(10, 30),
                status=Appointment.Status.CONFIRMED,
                reason="Routine pediatric wellness checkup and seasonal immunization advice.",
            )

        # Case 4: Pooja Sharma -> Dr. Khan (Orthopedics Scheduled Upcoming Appointment)
        apt4 = Appointment.objects.filter(patient=p_pooja, doctor=dr_khan).first()
        if not apt4:
            apt4 = Appointment.objects.create(
                patient=p_pooja,
                doctor=dr_khan,
                appointment_date=day_after,
                start_time=time(14, 0),
                end_time=time(14, 30),
                status=Appointment.Status.SCHEDULED,
                reason="Right ankle strain after badminton practice; swelling and mild limp.",
            )

        # Case 5: Amitabh Joshi -> Dr. Sharma (Active Draft Walk-In Consultation)
        consult_draft = Consultation.objects.filter(patient=p_amitabh, doctor=dr_sharma).first()
        if not consult_draft:
            consult_draft = Consultation.objects.create(
                patient=p_amitabh,
                doctor=dr_sharma,
                chief_complaint="Seasonal dry cough, mild throat irritation, and sneezing for 4 days.",
                history_of_present_illness="Symptoms aggravated in early mornings. No fever or shortness of breath.",
                status=Consultation.Status.DRAFT,
            )

        self.stdout.write(self.style.SUCCESS("Verified clinical appointments, case consultations, vitals, and prescriptions."))

        # ----------------------------------------------------------------------
        # 7. Audit Log Sample Entries
        # ----------------------------------------------------------------------
        log_audit_event(
            actor=admin_user,
            action=AuditLog.Action.CREATE,
            obj=dept_map["Cardiology"],
            object_label="Created Specialty Department 'Cardiology'",
            metadata={"department": "Cardiology"},
        )
        log_audit_event(
            actor=dr_sharma.user,
            action=AuditLog.Action.FINALIZE_CONSULTATION,
            obj=consult1,
            object_label=f"Finalized Consultation {consult1.pk} for Ramesh Kumar",
            metadata={"consultation_id": consult1.pk, "patient": "Ramesh Kumar"},
        )

        self.stdout.write(self.style.SUCCESS("Verified audit event records."))

        # ----------------------------------------------------------------------
        # Demonstration Credentials Summary
        # ----------------------------------------------------------------------
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.MIGRATE_HEADING("PULSECARE CLINIC — DEMONSTRATION CREDENTIALS SUMMARY"))
        self.stdout.write("=" * 70)
        self.stdout.write(f"1. Administrator : admin_demo     | Password: AdminDemo2026!")
        self.stdout.write(f"2. Receptionist 1: rec_sarah      | Password: ReceptionPass2026!")
        self.stdout.write(f"3. Receptionist 2: rec_michael    | Password: ReceptionPass2026!")
        self.stdout.write(f"4. General Med   : dr_sharma       | Password: DoctorDemo2026!")
        self.stdout.write(f"5. Cardiologist  : dr_patel        | Password: DoctorDemo2026!")
        self.stdout.write(f"6. Pediatrician  : dr_verma        | Password: DoctorDemo2026!")
        self.stdout.write(f"7. Orthopedic    : dr_khan         | Password: DoctorDemo2026!")
        self.stdout.write("=" * 70)
        self.stdout.write(self.style.SUCCESS("Safe demonstration dataset seeded successfully!"))
