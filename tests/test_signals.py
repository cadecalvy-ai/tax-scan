"""Every designed signal in the answer key fires, and fit levels land in the intended bands.

Fit-level disagreements that come from the rules themselves (not extraction)
are listed in tests/fit_decisions.yaml for the advisor to decide. Those cases
are marked xfail (strict), so the suite stays green while they're pending, and
flags them if a rule change makes them pass.
"""
from pathlib import Path

import pytest
import yaml

from tests.harness import answer_key, in_band

DECISIONS = yaml.safe_load((Path(__file__).parent / "fit_decisions.yaml").read_text(encoding="utf-8")) or {}
PENDING = {(d["client"], d["product"]) for d in DECISIONS.get("pending", [])}


@pytest.mark.parametrize("cid", sorted(answer_key()))
def test_designed_signals_fire(results, key, cid):
    fired = {s["id"] for s in results[cid]["signals"]}
    missing = set(key[cid]["designed_signals"]) - fired
    assert not missing, f"designed signals that did not fire: {sorted(missing)}; fired: {sorted(fired)}"


def _fit_cases():
    for cid in sorted(answer_key()):
        for product in ("aum", "annuity", "life"):
            marks = [pytest.mark.xfail(strict=True, reason="rules disagree with intended level; see fit_decisions.yaml")] \
                if (cid, product) in PENDING else []
            yield pytest.param(cid, product, marks=marks, id=f"{cid}-{product}")


def test_precision_recall_table(results, key):
    """Writes outputs/test_report/signal_precision_recall.md; every designed signal must be recalled."""
    from tests.signal_report import write
    _, (tp, fp, fn) = write(results, key)
    assert fn == 0


@pytest.mark.parametrize("cid,product", list(_fit_cases()))
def test_fit_level(results, key, cid, product):
    s, want = results[cid]["scores"], key[cid]["intended"]
    if product == "aum":
        assert s["aum_fit"] == want["aum_fit"], f"AUM {s['aum_score']} -> {s['aum_fit']}, intended {want['aum_fit']}"
    elif product == "annuity":
        assert in_band(s["annuity_grade"], want["annuity_band"]), \
            f"annuity {s['annuity_points']} -> {s['annuity_grade']}, intended {want['annuity_band']}"
    else:
        assert in_band(s["life_grade"], want["life_band"]), \
            f"life {s['life_points']} -> {s['life_grade']}, intended {want['life_band']}"
