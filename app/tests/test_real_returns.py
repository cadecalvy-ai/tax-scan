"""Real tax-software returns (the RIA's training set): extracted figures must match the printed 1040.

These files are private and not in GitHub, so the tests skip when the folder isn't on this computer.
Truth comes from scripts/real_return_truth.py (truth.json beside the clients folder).
"""
import json

import pytest

from src import paths
from src.grader import grade_client, load_config

BASE = paths.ROOT / "test clients from ria"
TRUTH = BASE / "truth.json"
CLIENTS = sorted((BASE / "clients").glob("RIA*")) if (BASE / "clients").exists() else []
KEYS = {"agi": "11a", "wages": "1a", "interest": "2b", "dividends": "3b", "taxable_income": "15",
        "total_tax": "24", "ss": "6a", "refund": "34", "w2_withholding": "25a"}
STATUS = {"Married filing jointly": "mfj", "Single": "single", "Head of household": "hoh"}

pytestmark = pytest.mark.skipif(not (CLIENTS and TRUTH.exists()), reason="RIA test returns not on this computer")


@pytest.fixture(scope="module")
def graded():
    cfg = load_config()
    return {d.name: grade_client(d, cfg, str(paths.APP / ".pytest_cache" / "ocr")) for d in CLIENTS}


@pytest.mark.parametrize("client", [d.name for d in CLIENTS])
def test_figures_match_printed_1040(graded, client):
    truth = json.loads(TRUTH.read_text())[client]
    r = graded[client]
    assert r["status"] == "graded"
    figs = r["_figs"]
    bad = {k: (truth[lab], figs.get(k, None)) for k, lab in KEYS.items() if lab in truth and truth[lab] != figs.get(k, None)}
    assert not bad, f"expected vs got: {bad}"
    status = r["_record"]["years"][r["year"]]["header"].get("status")
    assert status is not None and status.value == STATUS[truth["status"]]


@pytest.mark.parametrize("client", [d.name for d in CLIENTS])
def test_ages_come_from_information_sheet(graded, client):
    assert graded[client]["ages"], "no ages found"
