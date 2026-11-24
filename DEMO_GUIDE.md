# PulseCare Clinic Management & Patient Case-Taking System
## Final-Year B.Tech CSE College Demonstration & Viva Guide

---

## 1. Project Overview

**PulseCare** is an enterprise-grade Outpatient Clinic Management and Patient Case-Taking System engineered to digitize, streamline, and secure the end-to-end clinical workflow of modern healthcare facilities. 

In traditional outpatient settings, paper records and disjointed spreadsheets lead to scheduling collisions, transcription errors, illegible prescriptions, and compromised patient history tracking. PulseCare solves these challenges by providing a unified, role-based platform that enforces strict clinical data integrity, concurrency protection, and medical-legal immutability while delivering an intuitive user experience for administrators, receptionists, and doctors.

### Key Problem Statements Addressed:
1. **Double-Booking & Slot Contention**: Eliminated via database row-level locking during simultaneous appointment bookings.
2. **Medical Error Prevention**: Enforced standard ICD-10 diagnostic coding, mandatory vital signs recording, automated BMI calculation, and structured multi-item prescription formulation.
3. **Medico-Legal Compliance**: Implemented irreversible consultation finalization locking to prevent retrospective modification of clinical case notes.
4. **Accountability & Governance**: Append-only tamper-evident audit logging capturing every authentication event, clinical consultation, appointment scheduling, and administrative update.

---

## 2. Technology Stack

PulseCare is architected using industry-standard enterprise web technologies following the classic Model-View-Template (MVT) design pattern:

| Layer | Technology | Details / Rationale |
| :--- | :--- | :--- |
| **Backend Language** | Python 3.12+ / 3.14 | Strong type hinting, enterprise stability, comprehensive standard library. |
| **Web Framework** | Django 5.x / 6.1 (MVT) | Robust ORM, built-in security controls (CSRF, XSS, Clickjacking, SQLi protection). |
| **Production Database** | MySQL 8.0+ / MariaDB | Relational database with InnoDB engine, ACID transactions, `utf8mb4` Unicode. |
| **Testing / Portable DB**| SQLite3 (In-Memory/File)| Fast unit test execution and isolated sandbox development. |
| **Frontend Framework** | Bootstrap 5.3.3 | Responsive grid layout, mobile/tablet/desktop adaptive, accessible design tokens. |
| **Icons & UI Kit** | Bootstrap Icons 1.11 | Clean clinical vector icons for responsive touch targets. |
| **Data Visualization** | Chart.js | Dynamic, interactive charts for administrative operational and clinical analytics. |
| **Client Scripting** | Vanilla JavaScript (ES6+) | Lightweight dynamic formset management (prescriptions), auto-BMI calculation, and AJAX. |

---

## 3. System Architecture

PulseCare adopts Django's **Model-View-Template (MVT)** architectural pattern with modular separation of concerns.

```
                              +---------------------------------------+
                              |         Web Browser / Client          |
                              |   (Desktop / Tablet / Mobile UI)      |
                              +---------------------------------------+
                                                 |
                                         HTTP / HTTPS (WSGI)
                                                 |
                              +---------------------------------------+
                              |          Django Core Engine           |
                              |  +---------------------------------+  |
                              |  | Security Middleware Pipeline    |  |
                              |  | (CSRF, Authentication, Headers) |  |
                              |  +---------------------------------+  |
                              +---------------------------------------+
                                                 |
                      +--------------------------+--------------------------+
                      |                                                     |
       +------------------------------+                       +------------------------------+
       |   Role-Based View Handlers   |                       |    Reusable Core Services    |
       |  - accounts / auth views     |                       |  - audit.services            |
       |  - receptionist workflows    |                       |  - reports.services          |
       |  - doctor clinical portals   |                       |  - appointment validation    |
       |  - administrator analytics   |                       +------------------------------+
       +------------------------------+                                     |
                      |                                                     |
                      +--------------------------+--------------------------+
                                                 |
                              +---------------------------------------+
                              |              Django ORM               |
                              | (Model Layer, ModelForms & Validators)|
                              +---------------------------------------+
                                                 |
                                   Raw SQL Queries / Transactions
                                    (select_for_update, atomic)
                                                 |
                              +---------------------------------------+
                              |         Relational Database           |
                              |       (MySQL 8.0 / InnoDB)            |
                              +---------------------------------------+
```

### Architectural Highlights:
- **Zero Heavy Single-Page Framework Overhead**: Renders performant server-side HTML with Bootstrap 5, minimizing client payload and eliminating hydration latency.
- **Service Layer Pattern**: Complex business logic (audit event emission, aggregated reporting, slot overlap checks) is decoupled into dedicated service modules (`services.py`).
- **Defense in Depth**: Strict server-side permission decorators (`@role_required`, `RoleRequiredMixin`) ensure that front-end UI hide/show logic is never relied upon for authorization.

---

## 4. Application Modules

The project is structured into **8 modular, highly-cohesive Django applications**:

```
Patient Case Taking Software/
├── accounts/          # Custom User model, authentication, role decorators & management commands
├── departments/       # Medical departments, doctor profiles, qualifications & specialties
├── patients/          # Patient registration, auto-generated MRN, demographic & contact records
├── appointments/      # Slot scheduling, concurrency locking, status workflow & calendar queries
├── consultations/     # Clinical case-taking, chief complaints, examination, vitals & diagnoses
├── prescriptions/     # Medication management, structured dosage builder, PDF/printable issuance
├── reports/           # Analytics services, clinic KPIs, trend charts & secure CSV export
├── audit/             # Tamper-evident append-only audit trail logging system events
└── config/            # Project settings, root URL dispatch, WSGI/ASGI configurations
```

---

## 5. User Roles and Permissions Matrix

PulseCare enforces strict **Role-Based Access Control (RBAC)** across three distinct clinical operational personas:

| Capability / Workflow | Administrator | Receptionist | Doctor |
| :--- | :---: | :---: | :---: |
| **System Login & Dashboard** | Yes (System Overview) | Yes (Front-Desk) | Yes (Outpatient Queue) |
| **Department Management (CRUD)** | Full Access | No Access | Read-Only |
| **Doctor Profile Management** | Full Access | View Roster | Edit Own Profile |
| **Staff Account Creation** | Full Access | No Access | No Access |
| **Patient Registration & Editing** | Read-Only | Full Access | Read-Only |
| **Patient Medical Records (EMR)** | No Access (Confidential) | Demographics Only | Full Clinical History |
| **Appointment Booking & Rescheduling** | View All | Full Access | View Assigned Queue |
| **Clinical Consultation Form** | No Access | No Access | Full Access (Assigned) |
| **Vital Signs & Diagnosis Entry** | No Access | No Access | Full Access |
| **Finalize Consultation** | No Access | No Access | Full Access (Locks Record)|
| **Prescription Formulation & Issuance**| No Access | No Access | Full Access |
| **Audit Log Explorer** | Full Access | No Access | No Access |
| **Operational & Analytics Reports** | Full Access + CSV Export | No Access | No Access |

---

## 6. Database Schema & Relational Model

The database is designed in Third Normal Form (3NF) to guarantee referential integrity and prevent data anomalies.

```
 +------------------+            +--------------------+            +--------------------+
 | accounts.User    | 1        1 | departments.       | 1        * | appointments.      |
 | (Role: ADMIN,    |------------| DoctorProfile      |------------| Appointment        |
 |  DOCTOR,         |            +--------------------+            | (Date, Time,       |
 |  RECEPTIONIST)   |                      | 1                     |  Status: SCHEDULED,|
 +------------------+                      |                       |  COMPLETED, etc.)  |
                                           |                       +--------------------+
 +------------------+                      |                                 | 1
 | patients.Patient | 1                    | *                               |
 | (MRN: Unique,    |----------------------+---------------------------------+ 0..1
 |  Name, DOB,      |                      |
 |  Blood Group)    |                      | 1
 +------------------+                      |
          | 1                              |
          |                                |
          | *                              | *
+-----------------------------------------------------+
| consultations.Consultation                          |
| (Appointment: OneToOne optional, Patient: FK,       |
|  Doctor: FK, Status: DRAFT / FINALIZED,             |
|  Chief Complaints, History, Examination, Treatment) |
+-----------------------------------------------------+
          | 1                              | 1
          |                                |
          | 1..*                           | 0..1
+--------------------+           +--------------------+
| consultations.     |           | prescriptions.     |
| VitalSign          |           | Prescription       |
| (BP, Pulse, Temp,  |           | (Instructions,     |
|  Weight, Height,   |           |  Status: DRAFT /   |
|  Computed BMI)     |           |  ISSUED)           |
+--------------------+           +--------------------+
          | 1                              | 1
          |                                |
          | 1..*                           | 1..*
+--------------------+           +--------------------+
| consultations.     |           | prescriptions.     |
| Diagnosis          |           | PrescriptionItem   |
| (ICD-10 Code, Name,|           | (Medicine Name,    |
|  Type: PRIMARY /   |           |  Dosage, Frequency,|
|  SECONDARY)        |           |  Duration, Route)  |
+--------------------+           +--------------------+
```

### Relational Model Guarantees:
1. **Unique MRN**: `Patient.medical_record_number` uses an auto-generated unique identifier (`MRN-YYYYMMDD-XXXX`).
2. **1-to-1 Optional Relationship**: `Appointment` and `Consultation` maintain a strictly optional 1:1 relationship allowing scheduled visits while accommodating emergency walk-in consultations.
3. **Primary Diagnosis Constraint**: Each consultation is constrained to exactly one `PRIMARY` diagnosis; additional co-morbidities are stored as `SECONDARY`.
4. **Cascade Prevention**: Critical records (patients, consultations, audit entries) use `models.PROTECT` or `models.SET_NULL` to prevent catastrophic accidental data loss.

---

## 7. Main Workflow (The Clinical Journey)

PulseCare models the exact real-world journey of an outpatient clinic visit:

```
[ Step 1: Reception Desk ]
Patient arrives -> Receptionist registers patient -> Unique MRN is generated.
Receptionist selects Department & Doctor -> Books available time slot.
                           │
                           ▼
[ Step 2: Doctor Outpatient Queue ]
Doctor logs into Portal -> Today's Queue shows patient in "SCHEDULED" state.
Doctor clicks "Start Consultation" -> System initializes Consultation workspace.
                           │
                           ▼
[ Step 3: Clinical Case-Taking ]
Doctor records Chief Complaint, Present Illness, Physical Examination findings.
Doctor inputs Vital Signs: Systolic/Diastolic BP, Heart Rate, SpO2, Temperature.
Doctor enters Height (cm) & Weight (kg) -> BMI is automatically calculated & classified.
                           │
                           ▼
[ Step 4: Medical Diagnosis (ICD-10) ]
Doctor assigns Primary Diagnosis with standardized ICD-10 code (e.g., I10 - Essential Hypertension).
Optionally adds Secondary Diagnoses (e.g., E11.9 - Type 2 Diabetes Mellitus).
                           │
                           ▼
[ Step 5: Prescription Builder ]
Doctor builds prescription with dynamic medication rows: Drug name, Dosage, Frequency, Duration.
Prescription is saved and Issued -> Generates clean, printable clinical Rx.
                           │
                           ▼
[ Step 6: Consultation Finalization ]
Doctor reviews comprehensive case notes and clicks "Finalize Consultation".
System locks the Consultation and Prescription permanently -> State becomes READ-ONLY.
Appointment status transitions automatically to "COMPLETED".
                           │
                           ▼
[ Step 7: Administrative Oversight & Audit Logging ]
Administrator accesses Dashboard -> Views updated KPI metrics & departmental breakdown.
Administrator navigates to Audit Explorer -> Verifies immutable timestamped log of each action.
Administrator downloads Operational CSV report -> Verifies clean data formatting.
```

---

## 8. How to Start the Application

### 8.1 Setup & Environment Verification
Ensure Python 3.12+ is installed and your virtual environment is active:

```bash
# Windows (PowerShell)
cd "d:\Projects\Patient Case Taking Software"
.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate
```

### 8.2 Database Preparation
Ensure database migrations are applied:

```bash
python manage.py migrate
```

### 8.3 Populate Safe Demonstration Data
Run the custom idempotent seeding command:

```bash
python manage.py seed_demo_data
```
*(Optional flag `--reset-passwords` can be supplied to reset credentials at any time).*

### 8.4 Launch Development Web Server
```bash
python manage.py runserver 127.0.0.1:8000
```
Open your browser and navigate to: `http://127.0.0.1:8000/accounts/login/`

---

## 9. Demo Login Instructions

The `seed_demo_data` command creates ready-to-use accounts for all three roles:

| Role | Username | Password | Purpose in Demonstration |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin_demo` | `AdminDemo2026!` | Clinic KPI dashboard, department/doctor management, audit explorer, CSV export. |
| **Receptionist** | `rec_sarah` | `ReceptionPass2026!` | Front-desk operations: registering new patients, searching MRN, booking appointments. |
| **Receptionist (Alt)**| `rec_michael` | `ReceptionPass2026!` | Secondary receptionist demonstrating multi-user front-desk concurrency. |
| **Doctor (General)**| `dr_sharma` | `DoctorDemo2026!` | Internal Medicine: Outpatient queue, case-taking, vitals, ICD-10, prescriptions. |
| **Doctor (Cardio)** | `dr_patel` | `DoctorDemo2026!` | Cardiology specialist: specialized cardiac evaluations and consultations. |
| **Doctor (Peds)**   | `dr_verma` | `DoctorDemo2026!` | Pediatric specialist: developmental and pediatric case-taking. |
| **Doctor (Ortho)**  | `dr_khan` | `DoctorDemo2026!` | Orthopedics specialist: musculoskeletal cases and physical examinations. |

---

## 10. Step-by-Step Demonstration Sequence (10-15 Minute Viva Flow)

Follow this structured sequence to demonstrate all core capabilities seamlessly to your evaluators:

### Act I: The Receptionist Workflow (Front-Desk)
1. **Login**: Navigate to `/accounts/login/` and sign in as `rec_sarah` (Password: `ReceptionPass2026!`).
2. **Dashboard Overview**: Show quick action cards: "Register Patient", "Book Appointment", "Search Directory".
3. **Register New Patient**:
   - Click **Register New Patient**.
   - Enter fictional data (e.g., First Name: *Aarav*, Last Name: *Mehta*, DOB: *1990-05-15*, Gender: *Male*, Phone: *9820011223*, Blood Group: *O+*).
   - Submit the form -> Highlight the automatically generated **Medical Record Number (MRN)** formatted as `MRN-YYYYMMDD-XXXX`.
4. **Patient Search & Directory**:
   - Click **Patients Directory**. Use the instant search bar to search by name or MRN.
   - Click on the patient to show demographic profile and empty clinical history.
5. **Book an Appointment**:
   - Click **Book Appointment**.
   - Select Patient (*Aarav Mehta*), Department (*General Medicine*), Doctor (*Dr. Rajesh Sharma*).
   - Select appointment date (*Today*) and choose a morning or afternoon slot.
   - Enter reason for visit: *"Persistent fatigue, mild fever and headache"*.
   - Submit -> Demonstrate status badge displayed as `SCHEDULED`.
6. **Logout**: Click user menu -> **Logout**.

### Act II: The Doctor Workflow (Clinical Care & Case-Taking)
1. **Login**: Sign in as `dr_sharma` (Password: `DoctorDemo2026!`).
2. **Outpatient Queue**:
   - Show the Doctor Dashboard: Active queue shows today's scheduled appointments.
   - Point out patient *Aarav Mehta* listed with reason for visit.
3. **Start Consultation**:
   - Click **Start Consultation** next to Aarav Mehta.
   - Point out the unified clinical case-taking interface with pre-linked patient details.
4. **Clinical Documentation**:
   - Fill in **Chief Complaints**: *"Persistent low-grade fever for 4 days, body ache, mild cough."*
   - Fill in **History of Present Illness**: *"Onset 4 days ago after travel. No chills or rigors."*
   - Fill in **Physical Examination**: *"Clear breath sounds, throat mild erythema, abdomen soft."*
5. **Record Vital Signs & Automated BMI**:
   - Enter Systolic BP (`120`), Diastolic BP (`80`), Heart Rate (`76`), Temperature (`99.2`), SpO2 (`98`).
   - Enter Height (`175` cm) and Weight (`72` kg).
   - Observe live calculated BMI (`23.5` kg/m²) and classification: *"Normal weight"*.
6. **Enter ICD-10 Diagnosis**:
   - Add Primary Diagnosis: Code `R50.9` — Description: *"Fever, unspecified"*.
   - Add Secondary Diagnosis: Code `R05` — Description: *"Cough"*.
7. **Formulate Prescription**:
   - Add Medicine 1: *Paracetamol 650mg* | Dosage: *1 tablet* | Frequency: *Three times daily after food* | Duration: *5 days*.
   - Add Medicine 2: *Cetirizine 10mg* | Dosage: *1 tablet* | Frequency: *Once daily at bedtime* | Duration: *5 days*.
   - Enter instructions: *"Drink plenty of warm fluids. Return if fever persists beyond 3 days."*
8. **Finalize & Lock**:
   - Click **Finalize Consultation**.
   - Highlight the confirmation dialog warning that finalized records are immutable.
   - Confirm -> Status changes to `FINALIZED`.
   - Show that input fields are now disabled (read-only) and the prescription is issued with a clean printable preview.
9. **Logout**: Log out of the doctor session.

### Act III: The Administrator Workflow (Analytics & Governance)
1. **Login**: Sign in as `admin_demo` (Password: `AdminDemo2026!` ).
2. **Executive Dashboard**:
   - Point out high-level KPI stat cards: Total Patients, Appointments Today, Completed Consultations, Active Doctors.
   - Show the interactive Chart.js graphs displaying department breakdown and weekly volume.
3. **Clinic Management**:
   - Navigate to **Departments**: View active clinical specialties; demonstrate adding or toggling active status.
   - Navigate to **Doctors**: View active doctor roster with qualifications, license numbers, and assigned departments.
4. **Audit Trail Inspection**:
   - Navigate to **Audit Logs**.
   - Show how every action taken during Act I and Act II was automatically logged:
     - Receptionist login event.
     - Patient registration event.
     - Appointment booking event.
     - Doctor login event.
     - Consultation creation and finalization events.
   - Filter by actor (`dr_sharma`) or action type (`CONSULTATION_FINALIZE`).
5. **Operational Reports & CSV Export**:
   - Navigate to **Reports**.
   - Select date range and click **Download CSV Export**.
   - Open or inspect the downloaded file to demonstrate complete operational metrics.
6. **Conclusion**: Conclude the walkthrough.

---

## 11. Important Technical Highlights for Viva Defense

Be prepared to explain these architectural mechanisms if asked by project examiners:

1. **Double-Booking & Slot Contention Prevention**:
   - *Technical Mechanism*: Utilizes database row-level locking via Django's `select_for_update()` inside a `transaction.atomic()` block during appointment booking.
   - *Result*: Guarantees that two receptionists attempting to book the same doctor for the same time slot simultaneously cannot both succeed; one receives an immediate slot unavailable error.

2. **Automated Body Mass Index (BMI) Calculation**:
   - *Formula*: $\text{BMI} = \frac{\text{Weight (kg)}}{(\text{Height (m)})^2}$
   - *Implementation*: Dual validation — computed client-side in JavaScript for instant clinical feedback and recalculated/verified server-side inside `VitalSign.clean()` before persistence.

3. **Medical-Legal Record Immutability**:
   - *Technical Mechanism*: `Consultation` model enforces a state-machine pattern. Once status transitions to `FINALIZED`, the model's `clean()` and `save()` methods reject any edits to clinical notes, vitals, diagnoses, or attached prescriptions.
   - *Compliance*: Satisfies healthcare electronic health record (EHR) data preservation mandates.

4. **Tamper-Evident Append-Only Audit Logging**:
   - *Implementation*: Dedicated `AuditLog` model in `audit` app with timestamp, actor foreign key, action category, IP address, and JSON metadata changes.
   - *Security*: The model disallows `UPDATE` and `DELETE` queries at the application and ORM level.

5. **Formula Injection (CSV Injection) Sanitization**:
   - *Security Defense*: When exporting clinical and operational data to CSV, all string fields are sanitized to prepend a single quote if the field begins with `=, +, -, @` to prevent malicious spreadsheet formula execution in Microsoft Excel.

6. **Defensive Web Architecture**:
   - CSRF protection enabled on all POST forms via `{% csrf_token %}`.
   - Strict XSS escaping via Django's templating engine.
   - Parameterized SQL queries preventing SQL Injection across all searches.
   - Strict password hashers using PBKDF2 with SHA-256.

---

## 12. Known Limitations & Future Enhancements

For realistic academic defense, acknowledge these boundaries and outline the evolutionary roadmap:

1. **Scope Boundary (Outpatient vs. Inpatient)**:
   - *Current*: Designed specifically for Outpatient Departments (OPD), ambulatory care, and private clinics.
   - *Future Roadmap*: Inpatient Department (IPD) module incorporating bed allocation, ward occupancy tracking, nursing shift rounds, and operation theatre scheduling.

2. **Third-Party Telephony & Messaging Gateways**:
   - *Current*: System generates notification data models internally without sending external SMS/WhatsApp reminders.
   - *Future Roadmap*: Integration with Twilio or WhatsApp Business API for automated SMS appointment reminders and prescription PDF delivery.

3. **Digital Diagnostic Imaging (PACS / DICOM)**:
   - *Current*: Focuses on clinical case notes, vital signs, and diagnostic codes.
   - *Future Roadmap*: DICOM image viewer integration for X-Ray, CT, and MRI scan uploads and viewing directly within the consultation interface.

4. **Pharmacy Inventory & Billing Ledger**:
   - *Current*: Outlines medications, dosages, and instructions for patient use.
   - *Future Roadmap*: Direct integration with pharmacy stock dispensing and patient billing/insurance claim processing.

---

*PulseCare Clinic Management System — Prepared for B.Tech Computer Science & Engineering Final Evaluation (2026).*
