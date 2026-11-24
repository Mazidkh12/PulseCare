from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse
from .admin import DepartmentAdmin, DoctorProfileAdmin, DoctorProfileAdminForm
from .models import Department, DoctorProfile

User = get_user_model()


class DepartmentAndDoctorProfileTests(TestCase):
    """
    Test suite for Clinic Departments and Doctor Profiles (Step 3).
    """

    def setUp(self):
        # Active Department
        self.cardiology = Department.objects.create(
            name="Cardiology",
            description="Heart and cardiovascular health",
            is_active=True,
        )

        # Inactive Department
        self.dermatology = Department.objects.create(
            name="Dermatology",
            description="Skin, nails, and hair conditions",
            is_active=False,
        )

        # Doctor User
        self.doctor_user = User.objects.create_user(
            username="dr_john_smith",
            email="john.smith@clinic.test",
            password="SecureDoctorPass123!",
            first_name="John",
            last_name="Smith",
            role=User.Role.DOCTOR,
        )

        # Receptionist User
        self.receptionist_user = User.objects.create_user(
            username="receptionist_amy",
            email="amy.pond@clinic.test",
            password="SecureReceptionPass123!",
            first_name="Amy",
            last_name="Pond",
            role=User.Role.RECEPTIONIST,
        )

        # Administrator User
        self.admin_user = User.objects.create_user(
            username="admin_rory",
            email="rory@clinic.test",
            password="SecureAdminPass123!",
            first_name="Rory",
            last_name="Williams",
            role=User.Role.ADMIN,
        )

    # 1. Department Creation
    def test_department_creation(self):
        """Verify that a department can be created with valid fields and string representation."""
        dept = Department.objects.create(
            name="Pediatrics",
            description="Child and infant medical care",
            is_active=True,
        )
        self.assertIsNotNone(dept.pk)
        self.assertEqual(str(dept), "Pediatrics")
        self.assertTrue(dept.is_active)

    # 2. Duplicate Department Name Rejection
    def test_duplicate_department_name_rejected(self):
        """Verify that creating a department with a duplicate name raises IntegrityError."""
        with self.assertRaises(IntegrityError):
            Department.objects.create(name="Cardiology")

    # 3. DoctorProfile Creation for DOCTOR Role
    def test_doctor_profile_creation_for_doctor_role(self):
        """Verify that a doctor profile can be successfully created for a user with DOCTOR role."""
        profile = DoctorProfile.objects.create(
            user=self.doctor_user,
            department=self.cardiology,
            specialization="Interventional Cardiology",
            qualification="MBBS, MD (Cardiology)",
            contact_number="+1-555-0101",
        )
        self.assertIsNotNone(profile.pk)
        self.assertEqual(profile.user, self.doctor_user)
        self.assertEqual(profile.department, self.cardiology)
        self.assertTrue(profile.is_active)
        self.assertIn("Dr. John Smith", str(profile))
        self.assertIn("Cardiology", str(profile))

    # 4. Receptionist / Non-doctor Cannot Receive DoctorProfile
    def test_receptionist_cannot_be_assigned_doctor_profile(self):
        """Verify that assigning a DoctorProfile to a non-doctor user (e.g. Receptionist or Admin) raises ValidationError."""
        # Test Receptionist
        with self.assertRaises(ValidationError) as ctx:
            DoctorProfile.objects.create(
                user=self.receptionist_user,
                department=self.cardiology,
                specialization="General Medicine",
                qualification="BSc",
            )
        self.assertIn("user", ctx.exception.message_dict)

        # Test Admin
        with self.assertRaises(ValidationError) as ctx_admin:
            DoctorProfile.objects.create(
                user=self.admin_user,
                department=self.cardiology,
                specialization="Administration",
                qualification="MHA",
            )
        self.assertIn("user", ctx_admin.exception.message_dict)

    # 5. User Cannot Have Multiple Doctor Profiles
    def test_user_cannot_have_multiple_doctor_profiles(self):
        """Verify that attempting to create more than one DoctorProfile for the same user is rejected."""
        DoctorProfile.objects.create(
            user=self.doctor_user,
            department=self.cardiology,
            specialization="General Cardiology",
            qualification="MBBS",
        )
        with self.assertRaises((ValidationError, IntegrityError)):
            DoctorProfile.objects.create(
                user=self.doctor_user,
                department=self.cardiology,
                specialization="Pediatric Cardiology",
                qualification="MD",
            )

    # 6. Inactive Department Cannot Be Assigned to New Doctor
    def test_inactive_department_cannot_be_assigned_to_new_doctor(self):
        """Verify that an inactive department cannot be assigned to a new doctor profile."""
        new_doctor = User.objects.create_user(
            username="dr_clara_oswald",
            email="clara@clinic.test",
            password="SecureDoctorPass123!",
            first_name="Clara",
            last_name="Oswald",
            role=User.Role.DOCTOR,
        )
        with self.assertRaises(ValidationError) as ctx:
            DoctorProfile.objects.create(
                user=new_doctor,
                department=self.dermatology,  # Inactive department
                specialization="Cosmetic Dermatology",
                qualification="MBBS, MD",
            )
        self.assertIn("department", ctx.exception.message_dict)

    # 7. Existing Doctor Profiles Remain Associated and Department is Protected
    def test_existing_doctor_profiles_remain_associated_and_protected(self):
        """Verify that existing doctor profiles remain associated when department is deactivated, and deletion is protected."""
        profile = DoctorProfile.objects.create(
            user=self.doctor_user,
            department=self.cardiology,
            specialization="Interventional Cardiology",
            qualification="MBBS, MD",
        )

        # Deactivate department
        self.cardiology.is_active = False
        self.cardiology.save()

        # Existing doctor profile remains valid and can update its non-department fields
        profile.refresh_from_db()
        self.assertEqual(profile.department, self.cardiology)
        profile.qualification = "MBBS, MD, FACC"
        profile.save()  # Should succeed without ValidationError

        # Deleting a department with active doctor profile must be blocked by models.PROTECT
        with self.assertRaises(ProtectedError):
            self.cardiology.delete()

    # 8. Django Admin Displays Both Models and Applies Queryset Filters
    def test_django_admin_configuration(self):
        """Verify that Department and DoctorProfile are registered in Django Admin with proper forms and filters."""
        self.assertIn(Department, admin.site._registry)
        self.assertIn(DoctorProfile, admin.site._registry)

        dept_admin = admin.site._registry[Department]
        doc_admin = admin.site._registry[DoctorProfile]

        self.assertIsInstance(dept_admin, DepartmentAdmin)
        self.assertIsInstance(doc_admin, DoctorProfileAdmin)

        # Verify list_display attributes
        self.assertIn("name", dept_admin.list_display)
        self.assertIn("is_active", dept_admin.list_display)
        self.assertIn("get_doctor_name", doc_admin.list_display)
        self.assertIn("department", doc_admin.list_display)

        # Verify Admin Form limits user queryset strictly to users with role=DOCTOR
        form = DoctorProfileAdminForm()
        user_roles = set(form.fields["user"].queryset.values_list("role", flat=True))
        self.assertTrue(user_roles.issubset({"DOCTOR"}))

        # Verify Admin Form limits department queryset to active departments
        dept_active_states = set(form.fields["department"].queryset.values_list("is_active", flat=True))
        self.assertEqual(dept_active_states, {True})


class DepartmentAndDoctorPortalWorkflowTests(TestCase):
    """
    Test suite for Step 10D: Department & Doctor Management workflows.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin_pepper",
            email="pepper@clinic.test",
            password="SecurePass123!",
            role=User.Role.ADMIN,
        )
        self.receptionist = User.objects.create_user(
            username="rec_happy",
            email="happy@clinic.test",
            password="SecurePass123!",
            role=User.Role.RECEPTIONIST,
        )
        self.cardiology = Department.objects.create(
            name="Cardiology",
            description="Cardiac specialty",
            is_active=True,
        )
        self.inactive_dept = Department.objects.create(
            name="Endocrinology",
            description="Hormones & glands",
            is_active=False,
        )

    # 12. Administrator can create departments
    def test_admin_can_create_department(self):
        self.client.login(username="admin_pepper", password="SecurePass123!")
        response = self.client.post(
            reverse("departments:department_create"),
            {
                "name": "Orthopedics",
                "description": "Bones and joints care",
                "is_active": True,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Department.objects.filter(name="Orthopedics").exists())

    # 13. Administrator can update departments
    def test_admin_can_update_department(self):
        self.client.login(username="admin_pepper", password="SecurePass123!")
        response = self.client.post(
            reverse("departments:department_edit", args=[self.cardiology.pk]),
            {
                "name": "Cardiology & Vascular",
                "description": "Heart and vascular health",
                "is_active": True,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.cardiology.refresh_from_db()
        self.assertEqual(self.cardiology.name, "Cardiology & Vascular")

    # 14. Duplicate department names are rejected
    def test_duplicate_department_name_rejected(self):
        self.client.login(username="admin_pepper", password="SecurePass123!")
        response = self.client.post(
            reverse("departments:department_create"),
            {
                "name": "Cardiology",
                "description": "Duplicate heart dept",
                "is_active": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    # 15. Department deactivation works
    def test_department_toggle_deactivation(self):
        self.client.login(username="admin_pepper", password="SecurePass123!")
        response = self.client.post(reverse("departments:department_toggle_active", args=[self.cardiology.pk]))
        self.assertEqual(response.status_code, 302)
        self.cardiology.refresh_from_db()
        self.assertFalse(self.cardiology.is_active)

    # 16. Inactive departments cannot be selected for new assignments
    def test_inactive_department_not_in_doctor_creation_choices(self):
        self.client.login(username="admin_pepper", password="SecurePass123!")
        response = self.client.get(reverse("departments:doctor_create"))
        self.assertEqual(response.status_code, 200)
        # Inactive department must NOT be an option in the creation form
        self.assertNotContains(response, f'value="{self.inactive_dept.pk}"')

    # 17. Administrator can create doctor accounts
    def test_admin_can_create_doctor_account(self):
        self.client.login(username="admin_pepper", password="SecurePass123!")
        response = self.client.post(
            reverse("departments:doctor_create"),
            {
                "username": "dr_stephen_strange",
                "email": "strange@clinic.test",
                "first_name": "Stephen",
                "last_name": "Strange",
                "password": "SecureDoctorPass123!",
                "password_confirm": "SecureDoctorPass123!",
                "department": self.cardiology.pk,
                "specialization": "Cardiology",
                "qualification": "MD, PhD",
                "contact_number": "9876500000",
                "is_active": True,
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="dr_stephen_strange")
        self.assertEqual(user.role, User.Role.DOCTOR)
        self.assertTrue(user.check_password("SecureDoctorPass123!"))

    # 18. DoctorProfile is created correctly
    def test_doctor_profile_created_on_save(self):
        self.client.login(username="admin_pepper", password="SecurePass123!")
        self.client.post(
            reverse("departments:doctor_create"),
            {
                "username": "dr_stephen_strange_2",
                "email": "strange2@clinic.test",
                "first_name": "Stephen",
                "last_name": "Strange",
                "password": "SecureDoctorPass123!",
                "password_confirm": "SecureDoctorPass123!",
                "department": self.cardiology.pk,
                "specialization": "Pediatric Cardiology",
                "qualification": "MBBS, MD",
                "contact_number": "9876500001",
                "is_active": True,
            },
        )
        user = User.objects.get(username="dr_stephen_strange_2")
        profile = DoctorProfile.objects.get(user=user)
        self.assertEqual(profile.specialization, "Pediatric Cardiology")
        self.assertEqual(profile.department, self.cardiology)

    # 19. Invalid department assignment is rejected
    def test_invalid_inactive_department_assignment_rejected(self):
        self.client.login(username="admin_pepper", password="SecurePass123!")
        response = self.client.post(
            reverse("departments:doctor_create"),
            {
                "username": "dr_invalid_dept",
                "first_name": "Jane",
                "last_name": "Foster",
                "password": "SecurePass123!",
                "password_confirm": "SecurePass123!",
                "department": self.inactive_dept.pk,
                "specialization": "Endocrinology",
                "qualification": "MBBS",
                "is_active": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="dr_invalid_dept").exists())

    # 20. Duplicate DoctorProfile creation is prevented
    def test_duplicate_doctor_profile_prevented(self):
        doc_user = User.objects.create_user(
            username="dr_unique_person",
            password="SecurePass123!",
            role=User.Role.DOCTOR,
        )
        DoctorProfile.objects.create(
            user=doc_user,
            department=self.cardiology,
            specialization="Cardiology",
            qualification="MBBS",
            is_active=True,
        )
        # Attempting second profile for same user
        dup_profile = DoctorProfile(
            user=doc_user,
            department=self.cardiology,
            specialization="Cardiology",
            qualification="MBBS",
        )
        with self.assertRaises(ValidationError):
            dup_profile.clean()

    # 21. Doctor deactivation works
    def test_doctor_toggle_deactivation(self):
        doc_user = User.objects.create_user(
            username="dr_to_deactivate",
            password="SecurePass123!",
            role=User.Role.DOCTOR,
        )
        profile = DoctorProfile.objects.create(
            user=doc_user,
            department=self.cardiology,
            specialization="Cardiology",
            qualification="MBBS",
            is_active=True,
        )
        self.client.login(username="admin_pepper", password="SecurePass123!")
        response = self.client.post(reverse("departments:doctor_toggle_active", args=[profile.pk]))
        self.assertEqual(response.status_code, 302)
        profile.refresh_from_db()
        self.assertFalse(profile.is_active)
        doc_user.refresh_from_db()
        self.assertFalse(doc_user.is_active)

    # 22. Existing historical records remain intact
    def test_deactivated_doctor_preserves_records(self):
        doc_user = User.objects.create_user(
            username="dr_historical",
            password="SecurePass123!",
            role=User.Role.DOCTOR,
        )
        profile = DoctorProfile.objects.create(
            user=doc_user,
            department=self.cardiology,
            specialization="Cardiology",
            qualification="MBBS",
            is_active=False,
        )
        # Even when inactive, doctor profile remains in database
        self.assertTrue(DoctorProfile.objects.filter(pk=profile.pk).exists())

