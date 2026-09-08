import os
import sys
import csv
import random
import hashlib
from datetime import datetime, timedelta

# Add backend directory to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, "backend"))

from app.database import engine, Base, SessionLocal
from app.models.user import User
from app.models.shared_account import SharedAccount
from app.models.authorization import SharedAccountAuthorization
from app.models.system_log import SystemLog
from app.models.privileged_action import PrivilegedAction
from app.services.event_processor import EventProcessor, calculate_event_hash

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Synthetic Hospital Users (18 users across roles and departments)
USERS_DATA = [
    {"employee_id": "EMP001", "full_name": "Dr. Arun Kumar", "role": "Senior Consultant", "workforce_type": "Visiting Consultant", "department": "Cardiology", "active": True},
    {"employee_id": "EMP002", "full_name": "Dr. Priya Menon", "role": "Chief Radiologist", "workforce_type": "Visiting Consultant", "department": "Radiology", "active": True},
    {"employee_id": "EMP003", "full_name": "Ravi Kumar", "role": "Radiology Technologist", "workforce_type": "Permanent Staff", "department": "Radiology", "active": True},
    {"employee_id": "EMP004", "full_name": "Meena Joseph", "role": "Senior Lab Technician", "workforce_type": "Permanent Staff", "department": "Laboratory", "active": True},
    {"employee_id": "EMP005", "full_name": "Karthik Raj", "role": "Radiology Resident Intern", "workforce_type": "Intern", "department": "Radiology", "active": True},
    {"employee_id": "EMP006", "full_name": "Suresh Babu", "role": "Systems Infrastructure Specialist", "workforce_type": "Outsourced Technician", "department": "IT Support", "active": True},
    {"employee_id": "EMP007", "full_name": "Ananya Sharma", "role": "Clinical Pharmacist", "workforce_type": "Permanent Staff", "department": "Pharmacy", "active": True},
    {"employee_id": "EMP008", "full_name": "Dr. Rajesh Varma", "role": "Consultant Pathologist", "workforce_type": "Visiting Consultant", "department": "Laboratory", "active": True},
    {"employee_id": "EMP009", "full_name": "Deepa Nair", "role": "Senior Billing Officer", "workforce_type": "Permanent Staff", "department": "Billing", "active": True},
    {"employee_id": "EMP010", "full_name": "Vikram Singh", "role": "Billing Associate", "workforce_type": "Intern", "department": "Billing", "active": True},
    {"employee_id": "EMP011", "full_name": "Sister Mary Thomas", "role": "Head Nurse Supervisor", "workforce_type": "Permanent Staff", "department": "Ward", "active": True},
    {"employee_id": "EMP012", "full_name": "Sunil Patil", "role": "Staff Nurse", "workforce_type": "Permanent Staff", "department": "Ward", "active": True},
    {"employee_id": "EMP013", "full_name": "Pooja Hegde", "role": "Pharmacy Assistant", "workforce_type": "Intern", "department": "Pharmacy", "active": True},
    {"employee_id": "EMP014", "full_name": "Dinesh Chandran", "role": "Biomedical Equipment Specialist", "workforce_type": "Outsourced Technician", "department": "Laboratory", "active": True},
    {"employee_id": "EMP015", "full_name": "Dr. Kavita Desai", "role": "Consultant Cardiologist", "workforce_type": "Visiting Consultant", "department": "Cardiology", "active": True},
    {"employee_id": "EMP016", "full_name": "Naveen George", "role": "Network & Security Analyst", "workforce_type": "Outsourced Technician", "department": "IT Support", "active": True},
    {"employee_id": "EMP017", "full_name": "Lakshmi Narayanan", "role": "Radiology Staff Assistant", "workforce_type": "Permanent Staff", "department": "Radiology", "active": True},
    {"employee_id": "EMP018", "full_name": "Rohan Gupta", "role": "Former Lab Assistant", "workforce_type": "Permanent Staff", "department": "Laboratory", "active": False}, # Inactive user test
]

# Shared Accounts
SHARED_ACCOUNTS_DATA = [
    {"username": "radiology_shared", "system_name": "PACS / RIS Core", "department": "Radiology", "account_type": "DEPARTMENTAL_WORKSTATION", "status": "ACTIVE", "risk_level": "HIGH"},
    {"username": "lab_shared", "system_name": "Laboratory Information System (LIS)", "department": "Laboratory", "account_type": "DEPARTMENTAL_WORKSTATION", "status": "ACTIVE", "risk_level": "HIGH"},
    {"username": "pharmacy_shared", "system_name": "Pharmacy Dispensing & Inventory", "department": "Pharmacy", "account_type": "CLINICAL_PORTAL", "status": "ACTIVE", "risk_level": "HIGH"},
    {"username": "billing_shared", "system_name": "Hospital Revenue & Invoicing POS", "department": "Billing", "account_type": "FINANCIAL_TERMINAL", "status": "ACTIVE", "risk_level": "MEDIUM"},
    {"username": "ward_shared", "system_name": "Inpatient Ward Clinical EMR", "department": "Ward", "account_type": "NURSE_STATION", "status": "ACTIVE", "risk_level": "HIGH"},
    {"username": "admin_shared", "system_name": "Hospital Enterprise Administration", "department": "IT Support", "account_type": "SYSTEM_ADMIN", "status": "ACTIVE", "risk_level": "CRITICAL"},
]

# Privileged Actions Catalog
PRIVILEGED_ACTIONS_DATA = [
    {"action_name": "VIEW_PATIENT_RECORD", "sensitivity_level": "HIGH", "description": "Access detailed electronic protected health information (ePHI)"},
    {"action_name": "EDIT_PATIENT_RECORD", "sensitivity_level": "CRITICAL", "description": "Alter medical history, clinical notes, or admission demographics"},
    {"action_name": "EXPORT_PATIENT_RECORD", "sensitivity_level": "CRITICAL", "description": "Bulk export or download of clinical health records"},
    {"action_name": "MODIFY_LAB_RESULT", "sensitivity_level": "CRITICAL", "description": "Change clinical diagnostic test values or reference ranges"},
    {"action_name": "APPROVE_LAB_RESULT", "sensitivity_level": "HIGH", "description": "Sign off and officially release laboratory diagnostic reports"},
    {"action_name": "MODIFY_PRESCRIPTION", "sensitivity_level": "CRITICAL", "description": "Adjust medication dosage, drug compound, or prescription route"},
    {"action_name": "DISPENSE_MEDICATION", "sensitivity_level": "HIGH", "description": "Authorize medication release from central pharmacy storage"},
    {"action_name": "CHANGE_USER_ROLE", "sensitivity_level": "CRITICAL", "description": "Elevate or alter system role permissions and access rights"},
    {"action_name": "CHANGE_SYSTEM_CONFIGURATION", "sensitivity_level": "CRITICAL", "description": "Modify critical infrastructure, PACS routing, or audit settings"},
    {"action_name": "DELETE_RECORD", "sensitivity_level": "CRITICAL", "description": "Purge or soft-delete patient or billing transaction records"},
]

NON_SENSITIVE_ACTIONS = [
    "USER_LOGIN",
    "USER_LOGOUT",
    "PING_HEALTHCHECK",
    "SEARCH_PATIENT_INDEX",
    "VIEW_ROSTER_SCHEDULE",
    "REFRESH_DASHBOARD",
    "PRINT_RECEIPT_SLIP",
    "QUERY_BED_AVAILABILITY",
]


def generate_all():
    print("Initializing Database Schema...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # 1. Insert Users
    print("Seeding Users...")
    users = []
    for u_data in USERS_DATA:
        u = User(**u_data, created_at=datetime(2026, 8, 1, 9, 0, 0))
        db.add(u)
        users.append(u)
    db.commit()

    user_map = {u.employee_id: u for u in db.query(User).all()}

    # 2. Insert Shared Accounts
    print("Seeding Shared Accounts...")
    shared_accs = []
    for sa_data in SHARED_ACCOUNTS_DATA:
        sa = SharedAccount(**sa_data, created_at=datetime(2026, 8, 1, 9, 0, 0))
        db.add(sa)
        shared_accs.append(sa)
    db.commit()

    sa_map = {sa.username: sa for sa in db.query(SharedAccount).all()}

    # 3. Insert Privileged Actions
    print("Seeding Privileged Actions...")
    for pa_data in PRIVILEGED_ACTIONS_DATA:
        pa = PrivilegedAction(**pa_data)
        db.add(pa)
    db.commit()

    # 4. Generate Delegations (At least 25 realistic records across multiple days)
    print("Seeding Delegations...")
    # Base timeline: Sept 1 to Sept 7, 2026
    start_date = datetime(2026, 9, 1, 0, 0, 0)

    delegations_data = [
        # Radiology Shifts (Day 1 - Sept 1)
        {"sa": "radiology_shared", "emp": "EMP003", "from_h": (start_date + timedelta(days=0, hours=8)), "to_h": (start_date + timedelta(days=0, hours=16)), "reason": "Morning Radiology Tech Shift", "approver": "Dr. Priya Menon", "status": "ACTIVE"},
        {"sa": "radiology_shared", "emp": "EMP002", "from_h": (start_date + timedelta(days=0, hours=14)), "to_h": (start_date + timedelta(days=0, hours=18)), "reason": "Specialist CT/MRI Review Shift (Overlap with Tech)", "approver": "Medical Director", "status": "ACTIVE"},
        
        # Radiology Shifts (Day 2 - Sept 2)
        {"sa": "radiology_shared", "emp": "EMP003", "from_h": (start_date + timedelta(days=1, hours=8)), "to_h": (start_date + timedelta(days=1, hours=16)), "reason": "Morning Radiology Shift", "approver": "Dr. Priya Menon", "status": "ACTIVE"},
        {"sa": "radiology_shared", "emp": "EMP005", "from_h": (start_date + timedelta(days=1, hours=16)), "to_h": (start_date + timedelta(days=1, hours=23)), "reason": "Evening Resident On-Call Shift", "approver": "Dr. Priya Menon", "status": "ACTIVE"},
        
        # Radiology Shifts (Day 3 - Sept 3: Multiple overlapping interns/techs to test ambiguous baseline)
        {"sa": "radiology_shared", "emp": "EMP003", "from_h": (start_date + timedelta(days=2, hours=9)), "to_h": (start_date + timedelta(days=2, hours=17)), "reason": "Day Ultrasound & X-Ray Shift", "approver": "Dr. Priya Menon", "status": "ACTIVE"},
        {"sa": "radiology_shared", "emp": "EMP005", "from_h": (start_date + timedelta(days=2, hours=10)), "to_h": (start_date + timedelta(days=2, hours=15)), "reason": "Resident Fluoroscopy Training Shift", "approver": "Dr. Priya Menon", "status": "ACTIVE"},
        {"sa": "radiology_shared", "emp": "EMP017", "from_h": (start_date + timedelta(days=2, hours=11)), "to_h": (start_date + timedelta(days=2, hours=14)), "reason": "Emergency Trauma Overflow Support", "approver": "Dr. Priya Menon", "status": "ACTIVE"},

        # Laboratory Shifts
        {"sa": "lab_shared", "emp": "EMP004", "from_h": (start_date + timedelta(days=0, hours=7)), "to_h": (start_date + timedelta(days=0, hours=15)), "reason": "Morning Diagnostic Batch Processing", "approver": "Dr. Rajesh Varma", "status": "ACTIVE"},
        {"sa": "lab_shared", "emp": "EMP008", "from_h": (start_date + timedelta(days=0, hours=11)), "to_h": (start_date + timedelta(days=0, hours=14)), "reason": "Histopathology Report Sign-off Shift", "approver": "Medical Director", "status": "ACTIVE"},
        {"sa": "lab_shared", "emp": "EMP004", "from_h": (start_date + timedelta(days=1, hours=7)), "to_h": (start_date + timedelta(days=1, hours=15)), "reason": "Morning Lab Shift", "approver": "Dr. Rajesh Varma", "status": "ACTIVE"},
        {"sa": "lab_shared", "emp": "EMP014", "from_h": (start_date + timedelta(days=1, hours=13)), "to_h": (start_date + timedelta(days=1, hours=17)), "reason": "Analyzer Calibration & Maintenance", "approver": "Dr. Rajesh Varma", "status": "ACTIVE"},

        # Pharmacy Shifts
        {"sa": "pharmacy_shared", "emp": "EMP007", "from_h": (start_date + timedelta(days=0, hours=8)), "to_h": (start_date + timedelta(days=0, hours=16)), "reason": "General Outpatient Pharmacy Shift", "approver": "Chief Pharmacist", "status": "ACTIVE"},
        {"sa": "pharmacy_shared", "emp": "EMP013", "from_h": (start_date + timedelta(days=0, hours=14)), "to_h": (start_date + timedelta(days=0, hours=20)), "reason": "Evening Inpatient Dispensing Shift", "approver": "Ananya Sharma", "status": "ACTIVE"},
        {"sa": "pharmacy_shared", "emp": "EMP007", "from_h": (start_date + timedelta(days=1, hours=8)), "to_h": (start_date + timedelta(days=1, hours=16)), "reason": "Outpatient Pharmacy Shift", "approver": "Chief Pharmacist", "status": "ACTIVE"},
        {"sa": "pharmacy_shared", "emp": "EMP013", "from_h": (start_date + timedelta(days=1, hours=15)), "to_h": (start_date + timedelta(days=1, hours=21)), "reason": "Evening Dispensing Shift", "approver": "Ananya Sharma", "status": "ACTIVE"},

        # Billing Shifts
        {"sa": "billing_shared", "emp": "EMP009", "from_h": (start_date + timedelta(days=0, hours=8)), "to_h": (start_date + timedelta(days=0, hours=16)), "reason": "Discharge Counter Shift", "approver": "Finance Head", "status": "ACTIVE"},
        {"sa": "billing_shared", "emp": "EMP010", "from_h": (start_date + timedelta(days=0, hours=12)), "to_h": (start_date + timedelta(days=0, hours=20)), "reason": "Afternoon Cashier & Settlement", "approver": "Finance Head", "status": "ACTIVE"},
        {"sa": "billing_shared", "emp": "EMP009", "from_h": (start_date + timedelta(days=1, hours=8)), "to_h": (start_date + timedelta(days=1, hours=16)), "reason": "Discharge Counter Shift", "approver": "Finance Head", "status": "ACTIVE"},

        # Ward Shifts
        {"sa": "ward_shared", "emp": "EMP011", "from_h": (start_date + timedelta(days=0, hours=7)), "to_h": (start_date + timedelta(days=0, hours=15)), "reason": "Ward A Supervisor Shift", "approver": "Nursing Director", "status": "ACTIVE"},
        {"sa": "ward_shared", "emp": "EMP012", "from_h": (start_date + timedelta(days=0, hours=15)), "to_h": (start_date + timedelta(days=0, hours=23)), "reason": "Ward A Night Monitoring Shift", "approver": "Sister Mary Thomas", "status": "ACTIVE"},
        {"sa": "ward_shared", "emp": "EMP011", "from_h": (start_date + timedelta(days=1, hours=7)), "to_h": (start_date + timedelta(days=1, hours=15)), "reason": "Ward A Supervisor Shift", "approver": "Nursing Director", "status": "ACTIVE"},
        {"sa": "ward_shared", "emp": "EMP012", "from_h": (start_date + timedelta(days=1, hours=15)), "to_h": (start_date + timedelta(days=1, hours=23)), "reason": "Ward A Evening Shift", "approver": "Sister Mary Thomas", "status": "ACTIVE"},

        # Admin Shared Shifts
        {"sa": "admin_shared", "emp": "EMP006", "from_h": (start_date + timedelta(days=0, hours=10)), "to_h": (start_date + timedelta(days=0, hours=14)), "reason": "PACS Server Security Patching Window", "approver": "IT Director", "status": "ACTIVE"},
        {"sa": "admin_shared", "emp": "EMP016", "from_h": (start_date + timedelta(days=1, hours=11)), "to_h": (start_date + timedelta(days=1, hours=13)), "reason": "Firewall & Role Policy Audit", "approver": "IT Director", "status": "ACTIVE"},

        # Expired Delegation Examples (to test expired authorization rule)
        {"sa": "radiology_shared", "emp": "EMP017", "from_h": (start_date - timedelta(days=5, hours=8)), "to_h": (start_date - timedelta(days=5, hours=16)), "reason": "Previous Month Temporary Shift", "approver": "Dr. Priya Menon", "status": "EXPIRED"},
        {"sa": "lab_shared", "emp": "EMP018", "from_h": (start_date - timedelta(days=20, hours=8)), "to_h": (start_date - timedelta(days=20, hours=16)), "reason": "Terminated Associate Access", "approver": "Dr. Rajesh Varma", "status": "REVOKED"},
    ]

    for d in delegations_data:
        sa_obj = sa_map[d["sa"]]
        user_obj = user_map[d["emp"]]
        auth = SharedAccountAuthorization(
            shared_account_id=sa_obj.id,
            user_id=user_obj.id,
            authorized_from=d["from_h"],
            authorized_until=d["to_h"],
            reason=d["reason"],
            approved_by=d["approver"],
            status=d["status"]
        )
        db.add(auth)
    db.commit()

    # 5. Generate Realistic System Logs (350+ events with >120 sensitive actions)
    print("Generating 360+ System Logs...")
    logs = []
    event_counter = 1

    # Device & IP profiles for hospital zones
    dept_configs = {
        "Radiology": {
            "ips": ["192.168.10.21", "192.168.10.22", "192.168.10.35"],
            "devices": ["RAD-WS-01", "RAD-WS-02", "RAD-PACS-01"],
            "system": "PACS_CORE_01",
            "sensitive": ["VIEW_PATIENT_RECORD", "EDIT_PATIENT_RECORD", "EXPORT_PATIENT_RECORD"],
            "targets": ["SYN-PAT-1082", "SYN-PAT-1083", "SYN-PAT-1090", "SYN-SCAN-904", "SYN-SCAN-905"]
        },
        "Laboratory": {
            "ips": ["192.168.20.14", "192.168.20.15", "192.168.20.18"],
            "devices": ["LAB-PC-01", "LAB-PC-02", "LAB-ANALYZER-03"],
            "system": "LIS_SERVER_02",
            "sensitive": ["MODIFY_LAB_RESULT", "APPROVE_LAB_RESULT", "VIEW_PATIENT_RECORD"],
            "targets": ["SYN-LAB-4401", "SYN-LAB-4402", "SYN-CBC-881", "SYN-PAT-1102"]
        },
        "Pharmacy": {
            "ips": ["192.168.30.10", "192.168.30.12"],
            "devices": ["PHARM-TERM-01", "PHARM-DISP-02"],
            "system": "PHARMACY_IS",
            "sensitive": ["MODIFY_PRESCRIPTION", "DISPENSE_MEDICATION", "VIEW_PATIENT_RECORD"],
            "targets": ["SYN-RX-5011", "SYN-RX-5012", "SYN-PAT-1205", "SYN-DRUG-991"]
        },
        "Billing": {
            "ips": ["192.168.40.5", "192.168.40.6"],
            "devices": ["BILL-DESK-01", "BILL-POS-02"],
            "system": "BILLING_SYS",
            "sensitive": ["DELETE_RECORD", "VIEW_PATIENT_RECORD"],
            "targets": ["SYN-INV-7701", "SYN-INV-7702", "SYN-PAT-1082"]
        },
        "Ward": {
            "ips": ["192.168.50.15", "192.168.50.16"],
            "devices": ["WARD-STN-01", "WARD-TAB-03"],
            "system": "WARD_EMR",
            "sensitive": ["VIEW_PATIENT_RECORD", "EDIT_PATIENT_RECORD"],
            "targets": ["SYN-BED-201", "SYN-BED-202", "SYN-PAT-1301", "SYN-PAT-1302"]
        },
        "IT Support": {
            "ips": ["192.168.99.10", "192.168.99.11"],
            "devices": ["IT-ADMIN-01", "SOC-TERM-02"],
            "system": "HOSPITAL_CORE_ADMIN",
            "sensitive": ["CHANGE_USER_ROLE", "CHANGE_SYSTEM_CONFIGURATION", "DELETE_RECORD"],
            "targets": ["SYN-CFG-ROLES", "SYN-CFG-PACS-GW", "SYN-AUDIT-LOGS"]
        }
    }

    # Session sequences for key scenarios
    # SCENARIO 1: Ravi Kumar on radiology_shared morning shift (Day 1: 08:50 to 12:00)
    sess_id_1 = "SESS-EMP003-RAD-901"
    cur_time = start_date + timedelta(days=0, hours=8, minutes=50)
    logs.append({
        "event_id": f"EVT-{event_counter:05d}",
        "timestamp": cur_time,
        "username": "radiology_shared",
        "session_id": sess_id_1,
        "source_system": "PACS_CORE_01",
        "source_ip": "192.168.10.21",
        "device_id": "RAD-WS-01",
        "action": "USER_LOGIN",
        "target_type": "SESSION",
        "target_id": sess_id_1,
        "success": True
    })
    event_counter += 1

    for minute_offset, act, target_t, target_id in [
        (12, "VIEW_PATIENT_RECORD", "PATIENT_RECORD", "SYN-PAT-1082"),
        (25, "EDIT_PATIENT_RECORD", "PATIENT_RECORD", "SYN-PAT-1082"),
        (40, "EXPORT_PATIENT_RECORD", "PATIENT_RECORD", "SYN-PAT-1082"),
        (55, "SEARCH_PATIENT_INDEX", "QUERY", "SYN-QUERY-001"),
        (75, "VIEW_PATIENT_RECORD", "PATIENT_RECORD", "SYN-PAT-1083"),
        (90, "EDIT_PATIENT_RECORD", "PATIENT_RECORD", "SYN-PAT-1083"),
        (110, "VIEW_ROSTER_SCHEDULE", "SCHEDULE", "RAD-SCHED-01"),
        (130, "EXPORT_PATIENT_RECORD", "PATIENT_RECORD", "SYN-PAT-1083"),
    ]:
        cur_time += timedelta(minutes=minute_offset)
        logs.append({
            "event_id": f"EVT-{event_counter:05d}",
            "timestamp": cur_time,
            "username": "radiology_shared",
            "session_id": sess_id_1,
            "source_system": "PACS_CORE_01",
            "source_ip": "192.168.10.21",
            "device_id": "RAD-WS-01",
            "action": act,
            "target_type": target_t,
            "target_id": target_id,
            "success": True
        })
        event_counter += 1

    # SCENARIO 2: Overlapping shift on Day 1 afternoon (Dr. Priya Menon joins while Ravi is also authorized)
    # Dr. Priya uses RAD-WS-02 from IP 192.168.10.22 with session SESS-EMP002-RAD-902
    sess_id_2 = "SESS-EMP002-RAD-902"
    cur_time = start_date + timedelta(days=0, hours=14, minutes=10)
    for minute_offset, act, target_t, target_id in [
        (0, "USER_LOGIN", "SESSION", sess_id_2),
        (5, "VIEW_PATIENT_RECORD", "PATIENT_RECORD", "SYN-PAT-1090"),
        (18, "EDIT_PATIENT_RECORD", "PATIENT_RECORD", "SYN-PAT-1090"),
        (35, "MODIFY_LAB_RESULT", "LAB_REPORT", "SYN-SCAN-904"),
        (50, "EXPORT_PATIENT_RECORD", "PATIENT_RECORD", "SYN-PAT-1090"),
    ]:
        cur_time += timedelta(minutes=minute_offset)
        logs.append({
            "event_id": f"EVT-{event_counter:05d}",
            "timestamp": cur_time,
            "username": "radiology_shared",
            "session_id": sess_id_2,
            "source_system": "PACS_CORE_01",
            "source_ip": "192.168.10.22",
            "device_id": "RAD-WS-02",
            "action": act,
            "target_type": target_t,
            "target_id": target_id,
            "success": True
        })
        event_counter += 1

    # SCENARIO 3: Direct User Logins (Dr. Arun Kumar and Suresh Babu direct accounts)
    cur_time = start_date + timedelta(days=0, hours=10, minutes=0)
    for minute_offset, act in [(0, "USER_LOGIN"), (15, "VIEW_PATIENT_RECORD"), (30, "EDIT_PATIENT_RECORD")]:
        cur_time += timedelta(minutes=minute_offset)
        logs.append({
            "event_id": f"EVT-{event_counter:05d}",
            "timestamp": cur_time,
            "username": "EMP001",  # Dr. Arun Kumar
            "session_id": "SESS-DIR-EMP001",
            "source_system": "CARDIOLOGY_HIS",
            "source_ip": "192.168.60.10",
            "device_id": "CARDIO-WS-01",
            "action": act,
            "target_type": "PATIENT_RECORD",
            "target_id": "SYN-PAT-2001",
            "success": True
        })
        event_counter += 1

    # SCENARIO 4: Missing Session ID Event (Resilience test: session_id is None)
    cur_time = start_date + timedelta(days=0, hours=11, minutes=30)
    logs.append({
        "event_id": f"EVT-{event_counter:05d}",
        "timestamp": cur_time,
        "username": "radiology_shared",
        "session_id": None,  # Intentionally missing session ID
        "source_system": "PACS_CORE_01",
        "source_ip": "192.168.10.21",
        "device_id": "RAD-WS-01",
        "action": "VIEW_PATIENT_RECORD",
        "target_type": "PATIENT_RECORD",
        "target_id": "SYN-PAT-1082",
        "success": True
    })
    event_counter += 1

    # SCENARIO 5: Expired Delegation Event (Event during a time when NO active delegation existed)
    cur_time = start_date + timedelta(days=0, hours=3, minutes=15) # 3 AM: no active delegation
    logs.append({
        "event_id": f"EVT-{event_counter:05d}",
        "timestamp": cur_time,
        "username": "radiology_shared",
        "session_id": "SESS-ROGUE-01",
        "source_system": "PACS_CORE_01",
        "source_ip": "192.168.10.99",
        "device_id": "RAD-WS-UNKNOWN",
        "action": "EXPORT_PATIENT_RECORD",
        "target_type": "PATIENT_RECORD",
        "target_id": "SYN-PAT-9999",
        "success": True
    })
    event_counter += 1

    # SCENARIO 6: Multi-Day Batch Generation across All Hospital Shared Accounts
    # Day 1 to Day 4 batches
    departments = ["Laboratory", "Pharmacy", "Billing", "Ward", "IT Support", "Radiology"]
    shared_account_names = {
        "Laboratory": "lab_shared",
        "Pharmacy": "pharmacy_shared",
        "Billing": "billing_shared",
        "Ward": "ward_shared",
        "IT Support": "admin_shared",
        "Radiology": "radiology_shared",
    }

    dept_authorized_users = {
        "Laboratory": ["EMP004", "EMP008"],
        "Pharmacy": ["EMP007", "EMP013"],
        "Billing": ["EMP009", "EMP010"],
        "Ward": ["EMP011", "EMP012"],
        "IT Support": ["EMP006", "EMP016"],
        "Radiology": ["EMP003", "EMP005", "EMP017"],
    }

    random.seed(42)  # Deterministic seed for reproducible evaluation

    for day in range(4):
        for dept in departments:
            cfg = dept_configs[dept]
            sa_name = shared_account_names[dept]
            users_list = dept_authorized_users[dept]

            # 2 to 3 sessions per day per department
            for s_idx in range(2):
                chosen_user_emp = users_list[s_idx % len(users_list)]
                session_code = f"SESS-{chosen_user_emp}-{dept[:3].upper()}-D{day}S{s_idx}"
                base_hour = 8 + s_idx * 5
                sess_time = start_date + timedelta(days=day, hours=base_hour, minutes=random.randint(5, 20))
                device = random.choice(cfg["devices"])
                ip = random.choice(cfg["ips"])

                # Session login
                logs.append({
                    "event_id": f"EVT-{event_counter:05d}",
                    "timestamp": sess_time,
                    "username": sa_name,
                    "session_id": session_code,
                    "source_system": cfg["system"],
                    "source_ip": ip,
                    "device_id": device,
                    "action": "USER_LOGIN",
                    "target_type": "SESSION",
                    "target_id": session_code,
                    "success": True
                })
                event_counter += 1

                # 4 to 8 actions in this session (mix of sensitive and non-sensitive)
                for a_idx in range(random.randint(5, 7)):
                    sess_time += timedelta(minutes=random.randint(4, 25))
                    is_sens = random.random() < 0.65  # 65% sensitive to exceed 120 sensitive actions
                    if is_sens:
                        action_name = random.choice(cfg["sensitive"])
                    else:
                        action_name = random.choice(NON_SENSITIVE_ACTIONS)

                    target_id = random.choice(cfg["targets"])
                    target_type = "PATIENT_RECORD" if "PATIENT" in action_name else ("LAB_RESULT" if "LAB" in action_name else "TRANSACTION")

                    logs.append({
                        "event_id": f"EVT-{event_counter:05d}",
                        "timestamp": sess_time,
                        "username": sa_name,
                        "session_id": session_code,
                        "source_system": cfg["system"],
                        "source_ip": ip,
                        "device_id": device,
                        "action": action_name,
                        "target_type": target_type,
                        "target_id": target_id,
                        "success": True
                    })
                    event_counter += 1

    print(f"Total synthetic log events planned: {len(logs)}")

    # Ingest logs through EventProcessor
    print("Ingesting events and executing attribution pipeline...")
    for l_data in logs:
        EventProcessor.process_raw_event(db, l_data)

    # Export all tables to CSV in data/
    print("Exporting data to CSV files in data/...")
    # 1. users.csv
    with open(os.path.join(DATA_DIR, "users.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "employee_id", "full_name", "role", "workforce_type", "department", "active", "created_at"])
        for u in db.query(User).all():
            writer.writerow([u.id, u.employee_id, u.full_name, u.role, u.workforce_type, u.department, u.active, u.created_at])

    # 2. shared_accounts.csv
    with open(os.path.join(DATA_DIR, "shared_accounts.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "username", "system_name", "department", "account_type", "status", "risk_level", "created_at"])
        for sa in db.query(SharedAccount).all():
            writer.writerow([sa.id, sa.username, sa.system_name, sa.department, sa.account_type, sa.status, sa.risk_level, sa.created_at])

    # 3. delegations.csv
    with open(os.path.join(DATA_DIR, "delegations.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "shared_account_id", "user_id", "authorized_from", "authorized_until", "reason", "approved_by", "status"])
        for d in db.query(SharedAccountAuthorization).all():
            writer.writerow([d.id, d.shared_account_id, d.user_id, d.authorized_from, d.authorized_until, d.reason, d.approved_by, d.status])

    # 4. privileged_actions.csv
    with open(os.path.join(DATA_DIR, "privileged_actions.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "action_name", "sensitivity_level", "description"])
        for pa in db.query(PrivilegedAction).all():
            writer.writerow([pa.id, pa.action_name, pa.sensitivity_level, pa.description])

    # 5. system_logs.csv
    with open(os.path.join(DATA_DIR, "system_logs.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "event_id", "timestamp", "username", "session_id", "source_system", "source_ip", "device_id", "action", "target_type", "target_id", "success", "raw_event_hash", "received_at", "processing_status"])
        for sl in db.query(SystemLog).all():
            writer.writerow([sl.id, sl.event_id, sl.timestamp, sl.username, sl.session_id, sl.source_system, sl.source_ip, sl.device_id, sl.action, sl.target_type, sl.target_id, sl.success, sl.raw_event_hash, sl.received_at, sl.processing_status])

    db.close()
    print("Synthetic data generation and database ingestion successfully completed.")


if __name__ == "__main__":
    generate_all()
