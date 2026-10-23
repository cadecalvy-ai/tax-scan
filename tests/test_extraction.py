"""Extraction accuracy on every test client and year, including the scans.

Compares every 1040 line, the header (filing status, 65+ boxes, dependents,
deceased spouse), the schedule lines the grader reads, and the source-document
boxes against the answer key's `truth` block.
"""
import pytest

from tests.harness import answer_key, compare_year

CASES = [(cid, year) for cid, c in answer_key().items() for year in c["truth"]]


@pytest.mark.parametrize("cid,year", CASES, ids=[f"{c}-{y}" for c, y in CASES])
def test_extraction(results, key, cid, year):
    r = results[cid]
    assert r["status"] == "graded", r.get("reason")
    yr = r["_record"]["years"].get(int(year))
    assert yr is not None, f"{year} return not found"
    bad, n = compare_year(key[cid]["truth"][year], yr, has_sources=(year == "2025"))
    assert not bad, f"{len(bad)}/{n} fields wrong:\n" + "\n".join(f"  {f}: expected {e} got {g}" for f, e, g in bad)


@pytest.mark.parametrize("cid", sorted(answer_key()))
def test_profile(results, key, cid):
    rec = results[cid]["_record"]
    prof = rec["profile"]
    assert prof and prof["test_client"]
    t = key[cid]["truth"]["2025"]
    assert len(prof["dependents"]) == len(t["dependents"])
    assert sorted(d["dob"] for d in prof["dependents"]) == sorted(d["dob"] for d in t["dependents"])
    ages = sorted(2025 - int(p["dob"][:4]) for p in prof["people"])
    assert ages == sorted(key[cid]["ages"])


@pytest.mark.parametrize("cid", sorted(answer_key()))
def test_agi_used_for_grading(results, key, cid):
    """The reconciled AGI (what scoring uses) must equal the true AGI."""
    assert results[cid]["_figs"].get("agi") == key[cid]["agi_2025"]
    if key[cid]["agi_2024"] is not None:
        assert results[cid]["_pfigs"].get("agi") == key[cid]["agi_2024"]
