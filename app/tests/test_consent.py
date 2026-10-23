"""IRC 7216 consent gate and SSN masking."""
import shutil

from src.grader import grade_client, load_config
from src.privacy import mask_ssn
from src.report import client_html
from tests.harness import CLIENTS


def _copy_return_only(tmp_path):
    """A 'real-looking' client folder: a return but no fictional-test-client profile."""
    src = next(CLIENTS.glob("C01_*"))
    dst = tmp_path / "RealClient"
    dst.mkdir()
    shutil.copy(src / "2025_Form_1040_and_Schedules.pdf", dst)
    return dst


def test_refuses_without_consent(tmp_path):
    r = grade_client(_copy_return_only(tmp_path), load_config())
    assert r["status"] == "not graded"
    assert "7216" in r["reason"]


def test_grades_with_consent(tmp_path):
    d = _copy_return_only(tmp_path)
    (d / "client.yaml").write_text("consent_7216: true\n", encoding="utf-8")
    assert grade_client(d, load_config())["status"] == "graded"


def test_explicit_no_consent_wins_even_for_test_client(tmp_path):
    src = next(CLIENTS.glob("C01_*"))
    d = tmp_path / "C01"
    shutil.copytree(src, d)
    (d / "client.yaml").write_text("consent_7216: false\n", encoding="utf-8")
    assert grade_client(d, load_config())["status"] == "not graded"


def test_test_client_exempt(results):
    assert results["C01"]["consent"].startswith("fictional test client")


def test_ssn_masked_in_report(results):
    page = client_html({k: v for k, v in results["C24"].items() if not k.startswith("_")})
    assert "000-00-2401" not in page
    assert mask_ssn("SSN 000-00-2401") == "SSN ***-**-2401"
