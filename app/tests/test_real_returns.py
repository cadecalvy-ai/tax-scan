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


EXPECTED_CONTEXT = {   # from each return's General Information page, state summary, and Form 2441
    "RIA01_Whitfield_Raymond": {"federal_marginal": 24.0, "state_name": "Kansas", "state_tax": 18441},
    "RIA03_Lindqvist_Patricia": {"federal_marginal": 22.0, "state_name": "Kansas", "state_tax": 5106},
    "RIA04_Boyle_Jared": {"federal_marginal": 22.0, "state_name": "Missouri", "state_tax": 4558},
    "RIA05_Brennan_Walter": {"federal_marginal": 12.0, "state_name": "Missouri", "state_tax": 891},
}


@pytest.mark.parametrize("client", sorted(EXPECTED_CONTEXT))
def test_preparer_pages(graded, client):
    if client not in graded:
        pytest.skip("client folder not present")
    ctx = graded[client]["_record"]["years"][2025]["context"]
    got = {k: ctx[k].value for k in EXPECTED_CONTEXT[client] if k in ctx}
    assert got == EXPECTED_CONTEXT[client]


def test_child_care_from_2441(graded):
    if "RIA04_Boyle_Jared" not in graded:
        pytest.skip("client folder not present")
    yr = graded["RIA04_Boyle_Jared"]["_record"]["years"][2025]
    assert [(p["name"], p["paid"].value) for p in yr["context"]["care_providers"]] == [("Little Acorns Learning", 9600)]
    assert yr["forms"]["2441"]["26"].value == yr["f1040"]["1e"].value == 5000
