# PulseCare — Outpatient Clinic Management and Patient Case-Taking System

> **A Comprehensive, Role-Based Healthcare Case-Taking Platform Engineered with Django, Python, MySQL, and Bootstrap 5.**
> *Academic Submission: Final-Year B.Tech Computer Science & Engineering Capstone Project.*

---

## 1. Project Overview

**PulseCare** is a robust, web-based Electronic Medical Record (EMR) and Outpatient Clinic Management platform designed to digitize and optimize clinical consultations, appointment workflows, and administrative oversight. The system addresses critical inefficiencies in traditional ambulatory healthcare—such as paper record attrition, prescription illegibility, double-booking collisions, and the lack of verifiable audit trails—by providing an integrated, secure, and intuitive web application.

---

## 2. Problem Statement

In many outpatient clinics and community health centers, patient case-taking and operational coordination remain hindered by fragmented, paper-heavy workflows:
- **Scheduling Conflicts**: Multiple front-desk operators frequently book patients into the same slot due to the lack of real-time transactional locking.
- **Diagnostic Inconsistency**: Free-text diagnostic notes frequently lack standardized ICD-10 medical terminology, impeding clinical auditing and epidemiological analysis.
- **Prescription Ambiguity**: Hand-written prescriptions contribute significantly to medication dispensing errors and lack structured tracking.
- **Lack of Accountability**: Unsecured physical records fail to record who created, reviewed, or amended clinical data, violating healthcare accountability standards.

---

## 3. Project Objectives

- **Role-Based Workflows**: Implement strict Role-Based Access Control (RBAC) across three distinct healthcare personas: **Administrator**, **Doctor**, and **Receptionist**.
- **Clinical Data Integrity**: Enforce automatic generation of unique Medical Record Numbers (MRNs), standardized vital signs tracking with live Body Mass Index (BMI) computation, and ICD-10 diagnostic classifications.
- **Concurrency Protection**: Prevent appointment double-booking using database row-level locking (`select_for_update`) wrapped inside ACID transactions.
- **Medical-Legal Record Immutability**: Provide consultation finalization mechanisms that lock clinical notes and associated prescriptions against retrospective tampering.
- **Accountability & Governance**: Maintain an append-only, tamper-evident audit trail capturing authentication, patient intake, appointment scheduling, and case finalizations.
- **Operational Intelligence**: Deliver real-time analytics dashboards and secure, formula-injection-safe CSV reports for administrative oversight.

---

## 4. Key Features

### Authentication & Self-Service User Onboarding
- **Self-Service Staff Registration**: Accessible at `/accounts/signup/`, allowing new staff to register as Receptionist, Doctor, or Administrator with instant role-specific routing.
- **Dynamic Doctor Profile Generation**: Intelligently renders additional clinical fields (Department, Specialization, Medical Qualifications, Contact Number) when the Doctor role is selected, creating the User and `DoctorProfile` atomically in a single transaction.

### Receptionist Portal (Front-Desk Operations)
- **Patient Registration**: Streamlined demographic intake with automatic generation of unique Medical Record Numbers (`MRN-YYYYMMDD-XXXX`).
- **Patient Directory & Live Search**: Rapid patient lookup by name, MRN, or phone number with pagination and detailed demographic profiles.
- **Appointment Booking Engine**: Real-time slot allocation filtered by specialty department and active doctor, protected against concurrent double-booking.

### Doctor Portal (Clinical Case-Taking & EMR)
- **Outpatient Queue**: Real-time queue displaying today's scheduled consultations and direct walk-in arrivals.
- **Comprehensive Case-Taking Interface**: Structured recording of Chief Complaints, History of Present Illness (HPI), Past Medical History, and Physical Examination findings.
- **Vital Signs & Automated BMI**: Clinical entry of BP, Pulse, SpO2, Temperature, Height, and Weight, featuring instant client-side and server-side BMI computation ($\text{kg/m}^2$) with clinical categorization.
- **ICD-10 Diagnostic Formulation**: Structured coding with strict enforcement of at most one `PRIMARY` diagnosis and multiple `SECONDARY` co-morbidities.
- **Prescription Builder**: Dynamic multi-item prescription formulation (drug name, strength, dosage, frequency, duration, intake timing, special instructions).
- **Medical-Legal Finalization**: Permanent consultation and prescription lock upon finalization.

### Administrator Portal (Governance & Analytics)
- **Executive KPI Dashboard**: Real-time metrics tracking patient volume, daily appointments, completed consultations, and active staff.
- **Clinical Analytics & Visualizations**: Interactive Chart.js charts for departmental workload distribution and weekly consultation trends.
- **Specialty Department & Doctor Management**: Full lifecycle management of clinical departments, specialties, and doctor credentials.
- **Audit Log Explorer**: Filterable, append-only security logs capturing timestamps, user roles, IP addresses, action types, and change metadata.
- **Secure CSV Reporting**: Data export protected against spreadsheet formula injection vulnerabilities.

---

## 5. Technology Stack

| Layer | Component | Details |
| :--- | :--- | :--- |
| **Backend Framework** | Django 5.x / 6.1 (MVT) | Python-based web framework with built-in security middleware. |
| **Programming Language**| Python 3.12+ / 3.14 | Robust object-oriented programming with strong typing. |
| **Primary Database** | MySQL 8.0+ / MariaDB | Relational database with InnoDB engine, ACID transactions, `utf8mb4`. |
| **Testing / Fallback DB**| SQLite3 (In-Memory / File) | High-speed automated unit testing and portable demonstration. |
| **Frontend Framework** | Bootstrap 5.3.3 | Responsive grid, mobile/tablet/desktop adaptive design. |
| **Icons & UI Kit** | Bootstrap Icons 1.11 | Modern clinical iconography. |
| **Data Visualization** | Chart.js | Client-rendered operational and clinical trend charts. |
| **Client Scripting** | Vanilla JavaScript (ES6+) | Formset management, live BMI computation, and UI transitions. |

---

## 6. System Architecture

PulseCare is built on the classic **Model-View-Template (MVT)** architecture:

```
                            +---------------------------------------+
                            |       Client Browser (UI Layer)       |
                            |  Bootstrap 5, Chart.js, Vanilla JS    |
                            +---------------------------------------+
                                                │  HTTP(S) Request
                                                ▼
                            +---------------------------------------+
                            |       Security Middleware Chain       |
                            |  CSRF, Session, Auth, Security Headers|
                            +---------------------------------------+
                                                │
                                                ▼
                            +---------------------------------------+
                            |          URL Dispatcher               |
                            |       config/urls.py (8 Apps)         |
                            +---------------------------------------+
                                                │
                                                ▼
                            +---------------------------------------+
                            |          View / Service Layer         |
                            |  Role Decorators, ModelForms, Services|
                            +---------------------------------------+
                                                │
                                                ▼
                            +---------------------------------------+
                            |          Django ORM (Models)          |
                            |  Validation, Constraints, Triggers    |
                            +---------------------------------------+
                                                │  ACID Transactions
                                                ▼
                            +---------------------------------------+
                            |     Relational Database (MySQL 8.0)   |
                            |     InnoDB Tables, Row-Level Locks    |
                            +---------------------------------------+
```

---

## 7. Application Modules

The project is structured into **8 modular, cohesive Django applications**:

```
Patient Case Taking Software/
├── accounts/          # User authentication, custom User model, roles (Admin, Doctor, Receptionist)
├── departments/       # Medical departments, doctor profiles, qualifications & specialties
├── patients/          # Patient registration, auto-generated MRN, demographic & contact records
├── appointments/      # Appointment booking, concurrency control, status state-machine
├── consultations/     # Clinical case-taking, chief complaints, examination, vitals & diagnoses
├── prescriptions/     # Multi-item medication builder, dosage tracking, printable Rx issuance
├── reports/           # Analytics services, clinic KPIs, trend charts & secure CSV export
├── audit/             # Append-only tamper-evident audit logging of all system events
└── config/            # Core configuration, URL routing, settings, WSGI/ASGI handlers
```

---

## 8. Installation & Setup Instructions

### Prerequisites
- Python 3.12 or newer installed (`python --version`)
- MySQL Server 8.0 or newer (or MariaDB 10.6+)
- Git installed

### 1. Clone the Repository
```bash
git clone https://github.com/<your-username>/patient-case-taking-software.git
cd "patient-case-taking-software"
```

### 2. Create and Activate Virtual Environment
```bash
# On Windows (PowerShell):
python -m venv .venv
.venv\Scripts\Activate.ps1

# On Linux / macOS:
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy the sample environment file to create your local `.env`:
```bash
cp .env.example .env
```
Update `.env` with your local database credentials:
```env
DJANGO_SECRET_KEY=your-strong-random-secret-key-here
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

DB_NAME=patient_case_management_db
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_HOST=127.0.0.1
DB_PORT=3306
```

### 5. Create MySQL Database
Log into MySQL and initialize the database:
```sql
CREATE DATABASE patient_case_management_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 6. Apply Database Migrations
```bash
python manage.py migrate
```

### 7. Populate Safe Demonstration Data
Run the idempotent seeding command:
```bash
python manage.py seed_demo_data
```

*(Note: For portable offline demonstration without MySQL, set `DJANGO_DB_ENGINE=sqlite` before running migrations and seeding).*

### 8. Start the Development Server
```bash
python manage.py runserver
```
Access the application at: `http://127.0.0.1:8000/accounts/login/`

---

## 9. Demonstration Login Credentials

The `seed_demo_data` command initializes standard demonstration accounts:

| Persona | Username | Password | Operational Role |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin_demo` | `AdminDemo2026!` | Full system governance, analytics, audit explorer |
| **Receptionist 1** | `rec_sarah` | `ReceptionPass2026!` | Front-desk patient intake & appointment scheduling |
| **Receptionist 2** | `rec_michael` | `ReceptionPass2026!` | Front-desk multi-user concurrency testing |
| **Doctor (General)**| `dr_sharma` | `DoctorDemo2026!` | General Medicine clinical consultations & prescriptions |
| **Doctor (Cardiology)**| `dr_patel` | `DoctorDemo2026!` | Interventional Cardiology consultations |
| **Doctor (Pediatrics)**| `dr_verma` | `DoctorDemo2026!` | Pediatric wellness & child health consultations |
| **Doctor (Orthopedics)**| `dr_khan` | `DoctorDemo2026!` | Musculoskeletal examinations & joint injury management |

For detailed, step-by-step viva walkthrough instructions, refer to [DEMO_GUIDE.md](file:///d:/Projects/Patient%20Case%20Taking%20Software/DEMO_GUIDE.md).

---

## 10. Application Screenshots

*(Screenshots can be added during final thesis assembly)*

| Interface | Description | Placeholder |
| :--- | :--- | :---: |
| **Admin Analytics Dashboard** | Overview of operational KPIs, appointment distribution, and specialty metrics. | `[ Screenshot: Admin Dashboard ]` |
| **Receptionist Directory** | Real-time patient search, auto-generated MRN, and appointment booking form. | `[ Screenshot: Receptionist Portal ]` |
| **Doctor Outpatient Queue** | Today's appointment roster with quick actions to start clinical case consultations. | `[ Screenshot: Doctor Queue ]` |
| **Clinical Case-Taking & Vitals** | Case history documentation with real-time automated Body Mass Index calculation. | `[ Screenshot: Case Taking ]` |
| **Prescription Builder & Issuance**| Multi-item drug formulation with dosage, frequency, and printable preview. | `[ Screenshot: Prescription View ]` |
| **Audit Log Explorer** | Tamper-evident, append-only chronological log of all clinical and administrative actions.| `[ Screenshot: Audit Explorer ]` |

---

## 11. Testing & Quality Assurance

The application contains an automated test suite covering authentication, permissions, models, concurrency, form validation, and reporting:

```bash
# Run Django system sanity check:
python manage.py check

# Run full automated test suite:
python manage.py test
```

**Current Test Metrics**:
- **Total Tests**: **238 automated tests**
- **Passing Status**: **238 passed (100%)**, 0 failures, 0 errors.

---

## 12. Future Scope & Roadmap

1. **Inpatient Department (IPD) Module**: Bed allocation, ward occupancy tracking, and nurse shift vitals recording.
2. **Telemedicine & Automated Messaging**: Integration with Twilio/WhatsApp APIs for automated appointment reminders and digital Rx delivery.
3. **Medical Imaging (PACS / DICOM)**: Direct in-browser viewing of radiological scans (X-Ray, CT, MRI).
4. **Pharmacy & Billing Ledger**: Direct inventory dispensing and automated insurance claim invoice generation.

---

## 13. License

This project is licensed under the **MIT License** for academic, educational, and evaluation purposes.
