"""
Forensic Compliance Audit Package Test Suite (Review 3 — Work Package R3.2)
Hospital Shared-Account Elimination & Accountable Action Attribution PoC

Verifies:
  1. Valid Case Package Generation
  2. JSON Schema Validity & Serialization
  3. Required Top-Level Sections (12 Sections)
  4. Evidence Preservation & Non-Invention
  5. Chronological Timeline Ordering
  6. Missing Telemetry Explicit Handling
  7. Ambiguous Attribution Preservation
  8. Escalated Case Details
  9. Non-Escalated Case Details
  10. Cryptographic Audit Chain Verification
  11. Exclusion of Secrets & Credentials
  12. PDF Generation & Execution
  13. PDF Header & File Validity (%PDF-)
  14. Error Handling for Nonexistent Event/Case
  15. Deterministic Export
  16. State Immutability (Attribution Results & DB Unchanged)
"""

import os
import sys
import json
import pytest
from datetime import datetime

# Ensure backend and workspace root in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.forensic_package import ForensicAuditPackageGenerator, REPORTLAB_AVAILABLE
from app.database import SessionLocal
from app.models.attribution_result import AttributionResult
from app.models.system_log import SystemLog


@pytest.fixture(scope="module")
def generator():
    """Shared generator instance with active DB session."""
    return ForensicAuditPackageGenerator()


# ---------------------------------------------------------------------------
# Test 1: Valid Case Package Generation
# ---------------------------------------------------------------------------
def test_valid_case_package_generation(generator):
    """Verify package generates successfully for known event EVT-00001."""
    pkg = generator.generate_package("EVT-00001")
    assert isinstance(pkg, dict)
    assert pkg["metadata"]["event_id"] == "EVT-00001"
    assert pkg["metadata"]["package_version"] == "1.0.0"


# ---------------------------------------------------------------------------
# Test 2: JSON Schema Validity & Serialization
# ---------------------------------------------------------------------------
def test_json_schema_validity_and_export(generator, tmp_path):
    """Verify JSON export creates a valid parseable JSON file."""
    pkg = generator.generate_package("EVT-00001")
    json_path = os.path.join(tmp_path, "test_pkg.json")
    exported_file = generator.export_json(pkg, output_path=json_path)

    assert os.path.exists(exported_file)
    with open(exported_file, "r", encoding="utf-8") as f:
        reloaded = json.load(f)
    assert reloaded["metadata"]["event_id"] == "EVT-00001"
    assert "event_details" in reloaded


# ---------------------------------------------------------------------------
# Test 3: Required 12 Top-Level Sections
# ---------------------------------------------------------------------------
def test_required_twelve_sections_present(generator):
    """Verify all 12 mandatory compliance sections exist in the generated package."""
    pkg = generator.generate_package("EVT-00001")
    required_sections = [
        "metadata",
        "event_details",
        "candidate_identity",
        "evidence_breakdown",
        "delegation_evidence",
        "session_evidence",
        "telemetry_evidence",
        "chronological_timeline",
        "escalation_details",
        "audit_chain_verification",
        "human_review",
        "limitations_and_disclaimer"
    ]
    for sec in required_sections:
        assert sec in pkg, f"Missing required section: {sec}"


# ---------------------------------------------------------------------------
# Test 4: Evidence Preservation & Accurate Scoring
# ---------------------------------------------------------------------------
def test_evidence_preservation_and_scoring(generator):
    """Verify candidate scores match the underlying attribution engine evaluation."""
    pkg = generator.generate_package("EVT-00001")
    ident = pkg["candidate_identity"]
    breakdown = pkg["evidence_breakdown"]

    assert ident["attribution_status"] == "ATTRIBUTED"
    assert ident["confidence_score"] == 100.0
    assert ident["attributed_user"] is not None
    assert ident["attributed_user"]["full_name"] == "Ravi Kumar"
    assert breakdown["total_achieved_score"] == 100.0
    assert len(breakdown["signals"]) == 5


# ---------------------------------------------------------------------------
# Test 5: Chronological Timeline Ordering
# ---------------------------------------------------------------------------
def test_chronological_timeline_ordering(generator):
    """Verify timeline entries are sorted in ascending chronological order."""
    pkg = generator.generate_package("EVT-00001")
    timeline = pkg["chronological_timeline"]
    assert len(timeline) >= 3

    timestamps = [t["timestamp"] for t in timeline]
    assert timestamps == sorted(timestamps), "Timeline entries must be chronologically ordered"


# ---------------------------------------------------------------------------
# Test 6: Missing Telemetry Handling (No Fabrication)
# ---------------------------------------------------------------------------
def test_missing_telemetry_handling(generator):
    """Verify missing telemetry fields are explicitly flagged as MISSING without fabricated values."""
    # EVT-00019 has device_id == RAD-WS-UNKNOWN
    pkg = generator.generate_package("EVT-00019")
    tel = pkg["telemetry_evidence"]
    assert tel["user_agent"] == "MISSING"
    assert tel["device"]["status"] == "MISSING"


# ---------------------------------------------------------------------------
# Test 7: Ambiguous Attribution Preservation
# ---------------------------------------------------------------------------
def test_ambiguous_attribution_preservation(generator):
    """Verify ambiguous clinical actions (EVT-00115) preserve competing candidates."""
    pkg = generator.generate_package("EVT-00115")
    ident = pkg["candidate_identity"]
    assert ident["attribution_status"] == "AMBIGUOUS"
    assert ident["confidence_level"] == "AMBIGUOUS"
    assert ident["attributed_user"] is None
    assert len(ident["candidates_evaluated"]) >= 2

    # Verify score tie / close contention preserved
    c1 = ident["candidates_evaluated"][0]
    c2 = ident["candidates_evaluated"][1]
    assert abs(c1["total_score"] - c2["total_score"]) <= 5.0


# ---------------------------------------------------------------------------
# Test 8: Escalated Case Details
# ---------------------------------------------------------------------------
def test_escalated_case_details(generator):
    """Verify escalated events contain populated escalation metadata."""
    pkg = generator.generate_package("EVT-00019")
    esc = pkg["escalation_details"]
    assert esc["is_escalated"] is True
    assert esc["priority"] in ["HIGH", "MEDIUM", "LOW"]
    assert esc["current_status"] == "UNATTRIBUTED"
    assert len(esc["recommended_action"]) > 0


# ---------------------------------------------------------------------------
# Test 9: Non-Escalated Case Details
# ---------------------------------------------------------------------------
def test_non_escalated_case_details(generator):
    """Verify standard attributed actions reflect not-escalated status."""
    pkg = generator.generate_package("EVT-00001")
    esc = pkg["escalation_details"]
    assert esc["is_escalated"] is False
    assert esc["current_status"] == "NOT_ESCALATED"


# ---------------------------------------------------------------------------
# Test 10: Cryptographic Audit Chain Verification
# ---------------------------------------------------------------------------
def test_cryptographic_audit_chain_verification(generator):
    """Verify tamper-evident audit record hash linkage is validated."""
    pkg = generator.generate_package("EVT-00001")
    ac = pkg["audit_chain_verification"]
    assert ac["tamper_evident_status"] == "VERIFIED_VALID"
    assert len(ac["record_hash"]) == 64  # SHA-256
    assert ac["algorithm"] == "SHA-256 Linkage"


# ---------------------------------------------------------------------------
# Test 11: Secret & Credential Exclusion
# ---------------------------------------------------------------------------
def test_secret_and_credential_exclusion(generator):
    """Verify package dump contains no passwords, private keys, or API tokens."""
    pkg = generator.generate_package("EVT-00001")
    dumped = json.dumps(pkg).lower()

    forbidden_tokens = [
        "password",
        "secret_key",
        "private_key",
        "bearer ",
        "apikey",
        "api_key",
        "authorization: bearer",
        "database_url"
    ]
    for token in forbidden_tokens:
        assert token not in dumped, f"Disallowed security token '{token}' detected in package dump"


# ---------------------------------------------------------------------------
# Test 12: PDF Generation
# ---------------------------------------------------------------------------
def test_pdf_generation(generator, tmp_path):
    """Verify ReportLab PDF generation creates target PDF file."""
    if not REPORTLAB_AVAILABLE:
        pytest.skip("ReportLab library not available")

    pkg = generator.generate_package("EVT-00001")
    pdf_path = os.path.join(tmp_path, "audit_package.pdf")
    out_file = generator.export_pdf(pkg, output_path=pdf_path)

    assert os.path.exists(out_file)
    assert os.path.getsize(out_file) > 1000


# ---------------------------------------------------------------------------
# Test 13: PDF Header & File Validity (%PDF-)
# ---------------------------------------------------------------------------
def test_pdf_header_and_validity(generator, tmp_path):
    """Verify PDF file conforms to standard PDF-1.4 magic byte header."""
    if not REPORTLAB_AVAILABLE:
        pytest.skip("ReportLab library not available")

    pkg = generator.generate_package("EVT-00019")
    pdf_path = os.path.join(tmp_path, "escalated_audit_package.pdf")
    generator.export_pdf(pkg, output_path=pdf_path)

    with open(pdf_path, "rb") as f:
        header = f.read(5)
    assert header == b"%PDF-", "Generated document must have standard PDF magic header"


# ---------------------------------------------------------------------------
# Test 14: Nonexistent Case Error Handling
# ---------------------------------------------------------------------------
def test_nonexistent_case_raises_value_error(generator):
    """Verify requesting an unknown event raises controlled ValueError."""
    with pytest.raises(ValueError, match="not found"):
        generator.generate_package("NON_EXISTENT_EVT_99999")


# ---------------------------------------------------------------------------
# Test 15: Deterministic Content Verification
# ---------------------------------------------------------------------------
def test_deterministic_content_structure(generator):
    """Verify two sequential package generations for same event produce identical core content."""
    pkg1 = generator.generate_package("EVT-00001")
    pkg2 = generator.generate_package("EVT-00001")

    # Excluding timestamp of generation
    assert pkg1["event_details"] == pkg2["event_details"]
    assert pkg1["candidate_identity"] == pkg2["candidate_identity"]
    assert pkg1["evidence_breakdown"] == pkg2["evidence_breakdown"]
    assert pkg1["delegation_evidence"] == pkg2["delegation_evidence"]


# ---------------------------------------------------------------------------
# Test 16: State Immutability (Attribution & DB Unchanged)
# ---------------------------------------------------------------------------
def test_package_generation_leaves_database_state_intact(generator):
    """Verify package generation is strictly read-only and alters no database rows."""
    db = SessionLocal()
    count_logs_before = db.query(SystemLog).count()
    count_attr_before = db.query(AttributionResult).count()

    # Generate packages for several events
    generator.generate_package("EVT-00001")
    generator.generate_package("EVT-00019")
    generator.generate_package("EVT-00115")

    count_logs_after = db.query(SystemLog).count()
    count_attr_after = db.query(AttributionResult).count()
    db.close()

    assert count_logs_before == count_logs_after == 364
    assert count_attr_before == count_attr_after == 364
