"""Cross-check the extracted figures and pick the best-supported value for each.

A return states most numbers more than once: the 1040 line, the schedule that
feeds it, the source documents behind it, and the arithmetic (AGI = line 9 -
line 10). For each key figure we collect every available reading and use the
value most of them agree on (ties go to the 1040 line). Every disagreement is
recorded as a warning on the report - nothing is corrected silently.
"""
from .extract import Fact


def _money(v):
    return f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)


class Figures:
    """Chosen value + provenance for each key figure of one tax year."""

    def __init__(self):
        self.facts = {}          # name -> Fact (the chosen one)
        self.warnings = []

    def get(self, name, default=0):
        f = self.facts.get(name)
        return f.value if f is not None else default

    def fact(self, name):
        return self.facts.get(name)


def _sum_fact(items, field, ref, cond=lambda s: True):
    """Sum a field across source documents; None if there are no such documents."""
    chosen = [s for s in items if cond(s)]
    if not chosen:
        return None
    total = sum((s[field].value or 0) for s in chosen)
    docs = ", ".join(sorted({s["doc"] for s in chosen}))
    return Fact(total, docs, 0, f"{ref} total ({len(chosen)} doc{'s' if len(chosen) > 1 else ''})")


def _derived(value, ref):
    return Fact(value, "", 0, ref, "derived")


def reconcile(name, label, cands, figs, tol):
    """Pick the value most candidates agree on; warn about the rest."""
    cands = [c for c in cands if c is not None and isinstance(c.value, (int, float))]
    if not cands:
        return
    groups = []
    for c in cands:
        for g in groups:
            if abs(g[0].value - c.value) <= tol:
                g.append(c)
                break
        else:
            groups.append([c])
    best = max(groups, key=lambda g: (len(g), g is groups[0]))
    figs.facts[name] = next((c for c in best if c.note != "derived"), best[0])   # cite a printed line if possible
    if len(groups) > 1:
        parts = "; ".join(f"{c.ref} = {_money(c.value)}" for g in groups for c in g)
        figs.warnings.append(f"{label}: sources disagree ({parts}). Used {_money(best[0].value)}, "
                             f"supported by {len(best)} of {len(cands)}.")


def analyze_year(year, yr, tol=1):
    """Return Figures for one tax year of a client record."""
    L, forms, src = yr["f1040"], yr["forms"], yr["sources"]
    figs = Figures()

    def line(k):
        return L.get(k)

    def form(f, k):
        return forms.get(f, {}).get(k)

    def val(f):
        return f.value if f is not None else None

    def combo(ref, *parts, sign=None):
        if any(p is None for p in parts):
            return None
        sign = sign or [1] * len(parts)
        return _derived(sum(s * p.value for s, p in zip(sign, parts)), ref)

    agi_key = "11a" if year >= 2025 else "11"
    w2, r1099 = src.get("W-2", []), src.get("1099-R", [])

    reconcile("wages", "Wages (line 1a)",
              [line("1a"), line("1z"), _sum_fact(w2, "box1", "W-2 box 1")], figs, tol)
    reconcile("interest", "Taxable interest (line 2b)",
              [line("2b"), form("Sch B", "4"), form("Sch B", "2"), _sum_fact(src.get("1099-INT", []), "box1", "1099-INT box 1")],
              figs, tol)
    reconcile("dividends", "Ordinary dividends (line 3b)",
              [line("3b"), form("Sch B", "6"), _sum_fact(src.get("1099-DIV", []), "box1a", "1099-DIV box 1a")], figs, tol)
    reconcile("qual_div", "Qualified dividends (line 3a)",
              [line("3a"), _sum_fact(src.get("1099-DIV", []), "box1b", "1099-DIV box 1b")], figs, tol)
    reconcile("ira_gross", "IRA distributions (line 4a)",
              [line("4a"), _sum_fact(r1099, "box1", "1099-R box 1 (IRA box checked)", lambda s: s["ira"].value)], figs, tol)
    reconcile("ira_taxable", "Taxable IRA distributions (line 4b)", [line("4b")], figs, tol)
    reconcile("pen_gross", "Pensions and annuities (line 5a)",
              [line("5a"), _sum_fact(r1099, "box1", "1099-R box 1 (plans)", lambda s: not s["ira"].value)], figs, tol)
    reconcile("pen_taxable", "Taxable pensions (line 5b)", [line("5b")], figs, tol)
    reconcile("ss", "Social Security (line 6a)",
              [line("6a"), _sum_fact(src.get("SSA-1099", []), "box5", "SSA-1099 box 5")], figs, tol)
    reconcile("cap_gain", "Capital gain (line 7)", [line("7"), form("Sch D", "16")], figs, tol)
    reconcile("sch1_income", "Schedule 1 income (line 8)", [line("8"), form("Sch 1", "10")], figs, tol)
    parts = [line(k) for k in ("1z", "2b", "3b", "4b", "5b", "6b", "7", "8")]
    reconcile("total_income", "Total income (line 9)",
              [line("9"), combo("sum of lines 1z, 2b, 3b, 4b, 5b, 6b, 7, 8", *parts)], figs, tol)
    reconcile("adjustments", "Adjustments (line 10)", [line("10"), form("Sch 1", "26")], figs, tol)
    reconcile("k1_ordinary", "S-corp income (K-1 box 1)",
              [_sum_fact(src.get("K-1", []), "box1", "K-1 box 1"), form("Sch E", "32")], figs, tol)
    reconcile("agi", "AGI",
              [line(agi_key), line("11b"), combo("line 9 - line 10", line("9"), line("10"), sign=[1, -1])], figs, tol)
    reconcile("deduction", "Deduction (line 12)", [line("12"), form("Sch A", "17")], figs, tol)
    agi = figs.fact("agi")
    ti_calc = None
    if agi is not None and line("14") is not None:
        ti_calc = _derived(max(0, agi.value - line("14").value), "AGI - line 14")
    reconcile("taxable_income", "Taxable income (line 15)", [line("15"), ti_calc], figs, tol)
    reconcile("other_taxes", "Other taxes (line 23)", [line("23"), form("Sch 2", "21")], figs, tol)
    reconcile("total_tax", "Total tax (line 24)",
              [line("24"), combo("line 22 + line 23", line("22"), line("23"))], figs, tol)
    reconcile("w2_withholding", "W-2 withholding (line 25a)",
              [line("25a"), _sum_fact(w2, "box2", "W-2 box 2")], figs, tol)
    reconcile("payments", "Total payments (line 33)",
              [line("33"), combo("lines 25d + 26 + 32", line("25d"), line("26"), line("32"))], figs, tol)
    for k, name in (("34", "refund"), ("37", "owed"), ("26", "estimated_payments")):
        if line(k) is not None:
            figs.facts[name] = line(k)

    # Schedules / forms the signals use directly
    for name, f, k in [("sch_c_net", "Sch C", "31"), ("sch_e_total", "Sch E", "41"), ("sch_e_scorp", "Sch E", "32"),
                       ("niit", "8960", "17"), ("niit_sch2", "Sch 2", "12"), ("amt", "6251", "11"),
                       ("amt_sch2", "Sch 2", "2"), ("early_penalty", "5329", "4"), ("sep", "Sch 1", "16"),
                       ("ira_deduction", "Sch 1", "20"), ("charity", "Sch A", "14"), ("sch_d_8949", "Sch D", "10")]:
        if form(f, k) is not None:
            figs.facts[name] = form(f, k)

    missing = [k for k in ("1a", "2b", "3b", "7", "9", agi_key, "15", "24", "33") if k not in L]
    if L and missing:
        figs.warnings.append(f"Form 1040 lines not found: {', '.join(missing)} (value taken from other sources if any)")
    if not L:
        figs.warnings.append(f"No {year} Form 1040 found; figures come from source documents only")
    return figs
