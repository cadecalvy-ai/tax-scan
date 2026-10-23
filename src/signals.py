"""Signal rules and scoring. All thresholds and points come from config/grader.yaml.

Each fired signal records what it is, how many points it adds, the value that
triggered it, and the documents/lines it came from - so every score can be
explained line by line on the report.
"""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher


@dataclass
class Signal:
    id: str               # e.g. "aum.rollover_100k" (matches the answer key)
    product: str          # aum / annuity / life
    group: str            # talking-point key, e.g. "aum.rollover"
    points: float
    label: str            # human description of the rule
    value: object = None
    detail: str = ""
    sources: list = field(default_factory=list)   # list of "Form 1040 line 11a (file p1)" strings


def k(n):
    """150000 -> '150k' (used in signal ids)."""
    return f"{n / 1000:g}k" if n >= 1000 else str(n)


def money(v):
    return f"${v:,.0f}"


def tier(value, tiers):
    """Highest (threshold, points) reached, or None."""
    hit = None
    for th, pts in sorted(tiers):
        if value >= th:
            hit = (th, pts)
    return hit


def where(*facts):
    return [f.where() for f in facts if f is not None]


# ---------------------------------------------------------------------
# Context: people, ages, earnings - shared by the rules
# ---------------------------------------------------------------------
class Ctx:
    def __init__(self, rec, year, figs, prior_year, prior_figs):
        self.rec, self.year, self.f, self.pf = rec, year, figs, prior_figs
        self.yr = rec["years"][year]
        self.pyr = rec["years"].get(prior_year) if prior_year else None
        self.h = self.yr.get("header", {})
        self.profile = rec.get("profile") or {}
        self.src = self.yr["sources"]
        self.forms = self.yr["forms"]

    # filing status ----------------------------------------------------
    def status(self, yr=None):
        yr = yr or self.yr
        s = yr.get("header", {}).get("status")
        if s:
            return s.value
        return self.profile.get("filing_status") if yr is self.yr else None

    # people and ages ---------------------------------------------------
    def people(self):
        """[(role, name, age, source)] for the people on the current return."""
        out = []
        roles = ["taxpayer"] + (["spouse"] if self.status() in ("mfj", "qss") else [])
        prof = {p["role"]: p for p in self.profile.get("people", [])}
        bb = self.h.get("born_before", {})
        for role, box in zip(roles, ("you", "spouse")):
            p = prof.get(role)
            if p and p.get("dob"):
                out.append((role, p["name"], self.year - int(p["dob"][:4]), "Client profile (DOB)"))
            elif bb.get(box) and bb[box].value:
                out.append((role, role, 65, bb[box].where()))
            elif self.src.get("SSA-1099"):
                out.append((role, role, 62, "SSA-1099 on file (age 62+)"))
        return out

    def oldest(self):
        ppl = self.people()
        return max(ppl, key=lambda p: p[2]) if ppl else None

    # dependents ----------------------------------------------------------
    def dependents(self, yr=None):
        yr = yr or self.yr
        deps = yr.get("header", {}).get("dependents")
        if deps is None or (not deps and yr is self.yr and not yr.get("header")):
            return self.profile.get("dependents", []) if yr is self.yr else []
        return deps

    def dob_of(self, name):
        for d in self.profile.get("dependents", []):
            if _same_name(d["name"], name):
                return d.get("dob")
        return None

    # earnings by person ---------------------------------------------------
    def earned_by_person(self):
        """{'taxpayer': $, 'spouse': $} from W-2 box 1 and Schedule C net."""
        tp, sp = self.h.get("taxpayer") or {}, self.h.get("spouse") or {}
        out = {"taxpayer": 0.0, "spouse": 0.0}
        for w in self.src.get("W-2", []):
            out[self._owner(w["ssn"], w.get("employee", ""), tp, sp)] += w["box1"].value or 0
        net = self.f.get("sch_c_net")
        if net > 0:
            out[self._owner(self.yr.get("sch_c_owner_ssn", ""), "", tp, sp)] += net
        return out

    @staticmethod
    def _owner(ssn, name, tp, sp):
        if ssn and sp.get("ssn") and ssn == sp["ssn"].value:
            return "spouse"
        if ssn and tp.get("ssn") and ssn == tp["ssn"].value:
            return "taxpayer"
        if name and sp.get("name") and _same_name(name, sp["name"].value) and not (
                tp.get("name") and _same_name(name, tp["name"].value)):
            return "spouse"
        return "taxpayer"


def _same_name(a, b):
    a, b = re.sub(r"[^a-z ]", "", a.lower()).split(), re.sub(r"[^a-z ]", "", b.lower()).split()
    if not a or not b:
        return False
    return SequenceMatcher(None, a[0], b[0]).ratio() > 0.8   # first names


# ---------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------
def evaluate(rec, year, figs, prior_year, prior_figs, cfg):
    c = Ctx(rec, year, figs, prior_year, prior_figs)
    f = figs
    sig = []
    A, N, LF = cfg["aum"], cfg["annuity"], cfg["life"]
    r1099 = c.src.get("1099-R", [])

    def add(id_, product, group, points, label, value=None, detail="", sources=()):
        sig.append(Signal(id_, product, group, points, label, value, detail, list(sources)))

    agi = f.get("agi")
    # ---------------- shared facts
    rollovers = [r for r in r1099 if "G" in str(r["box7"].value)]
    rollover_amt = sum(r["box1"].value or 0 for r in rollovers)
    events, event_src = life_events(c)
    drop = income_drop(c, cfg)
    ss_started = (prior_figs is not None and f.get("ss") > 0 and prior_figs.get("ss") == 0)

    # ================= AUM =================
    t = tier(agi, A["agi"]["tiers"])
    if t:
        add(f"aum.agi_{k(t[0])}", "aum", "aum.agi", t[1], f"AGI ≥ {money(t[0])}", money(agi), "",
            where(f.fact("agi")))
    inv = max(0, f.get("dividends") + f.get("cap_gain"))
    t = tier(inv, A["invest_income"]["tiers"])
    if t:
        add(f"aum.invest_income_{k(t[0])}", "aum", "aum.invest_income", t[1],
            f"Dividends + capital gains ≥ {money(t[0])}", money(inv),
            f"dividends {money(f.get('dividends'))} + capital gain {money(f.get('cap_gain'))}",
            where(f.fact("dividends"), f.fact("cap_gain")))
    t = tier(f.get("interest"), A["interest"]["tiers"])
    if t:
        add(f"aum.interest_{k(t[0])}", "aum", "aum.interest", t[1], f"Taxable interest ≥ {money(t[0])}",
            money(f.get("interest")), "", where(f.fact("interest")))
    if rollover_amt >= A["rollover"]["min"]:
        add(f"aum.rollover_{k(A['rollover']['min'])}", "aum", "aum.rollover", A["rollover"]["points"],
            f"Rollover (1099-R code G) ≥ {money(A['rollover']['min'])}", money(rollover_amt),
            ", ".join(r.get("payer", "") for r in rollovers), [r["box7"].where() for r in rollovers])
    elif f.get("ira_gross") + f.get("pen_gross") > 0 or r1099:
        amt = f.get("ira_gross") + f.get("pen_gross")
        add("aum.retirement_distribution", "aum", "aum.retirement_distribution", A["retirement_distribution"]["points"],
            "IRA / 401(k) / pension distributions present", money(amt), "",
            where(f.fact("ira_gross"), f.fact("pen_gross")))
    death = [r for r in r1099 if "4" in str(r["box7"].value)]
    inh = A["inheritance"]
    jump = (prior_figs is not None and prior_figs.fact("dividends") is not None
            and f.get("dividends") >= inh["min_current_dividends"]
            and f.get("dividends") >= inh["dividend_multiple"] * max(prior_figs.get("dividends"), 1))
    if death or jump:
        why = []
        if death:
            why.append("1099-R code 4 (death) from " + ", ".join(r.get("payer", "") for r in death))
        if jump:
            why.append(f"dividends {money(prior_figs.get('dividends'))} → {money(f.get('dividends'))}")
        add("aum.inheritance", "aum", "aum.inheritance", inh["points"], "Inheritance indicator",
            money(sum(r["box1"].value or 0 for r in death)) if death else money(f.get("dividends")), "; ".join(why),
            [r["box7"].where() for r in death] + (where(f.fact("dividends"), prior_figs.fact("dividends")) if jump else []))
    gains = [(x["gain"].value, x) for x in c.yr["f8949"]]
    sale = max([g for g, _ in gains] + [f.get("sch_d_8949")] + [0])
    if sale >= A["asset_sale"]["min_gain"]:
        best = max(gains, key=lambda g: g[0])[1] if gains else None
        s1099 = c.src.get("1099-S", [])
        detail = (best["desc"] if best else "Schedule D line 10") + (" (1099-S on file)" if s1099 else "")
        add(f"aum.asset_sale_gain_{k(A['asset_sale']['min_gain'])}", "aum", "aum.asset_sale", A["asset_sale"]["points"],
            f"Home or business sale gain ≥ {money(A['asset_sale']['min_gain'])}", money(sale), detail,
            where(best["gain"] if best else f.fact("sch_d_8949")) + [s["box2"].where() for s in s1099])
    niit = max(f.get("niit"), f.get("niit_sch2"))
    if niit > 0:
        add("aum.niit", "aum", "aum.niit", A["niit"]["points"], "Net investment income tax paid", money(niit), "",
            where(f.fact("niit") or f.fact("niit_sch2")))
    amt = max(f.get("amt"), f.get("amt_sch2"))
    iso = c.src.get("3921", [])
    if iso or amt > 0:
        bits = ([f"ISO exercise spread {money(iso[0]['spread'].value)} (Form 3921)"] if iso else []) + \
               ([f"AMT {money(amt)}"] if amt > 0 else [])
        add("aum.stock_comp_amt", "aum", "aum.stock_comp_amt", A["stock_comp_amt"]["points"], "Stock compensation or AMT",
            money(amt) if amt else money(iso[0]["spread"].value), "; ".join(bits),
            where(*(x["spread"] for x in iso)) + where(f.fact("amt") or f.fact("amt_sch2")))
    nrs = A["no_retirement_savings"]
    earned = f.get("wages") + max(0, f.get("sch_c_net")) + max(0, f.get("k1_ordinary"))
    basis = agi if nrs["income_basis"] == "agi" else earned
    deferrals = [cd for w in c.src.get("W-2", []) for cd in w["box12"] if cd in nrs["deferral_codes"]]
    if basis >= nrs["min_income"] and not deferrals and f.get("sep") == 0 and f.get("ira_deduction") == 0:
        add("aum.no_retirement_savings", "aum", "aum.no_retirement_savings", nrs["points"],
            f"Income ≥ {money(nrs['min_income'])} with no retirement savings visible", money(basis),
            "no W-2 box 12 deferral codes, no SEP/SIMPLE or IRA deduction on Schedule 1",
            where(f.fact("wages"), f.fact("sch_c_net"), f.fact("k1_ordinary")))
    if drop:
        add("aum.income_drop", "aum", "aum.income_drop", A["income_drop"]["points"],
            "Income drop / early retirement", drop[0], drop[1], drop[2])
    early = [r for r in r1099 if re.search(r"(^|[^0-9])1([^0-9]|$)", str(r["box7"].value))]
    if early or f.get("early_penalty") > 0:
        amt_e = sum(r["box1"].value or 0 for r in early)
        add("aum.early_withdrawal", "aum", "aum.early_withdrawal", A["early_withdrawal"]["points"],
            "Early withdrawal (1099-R code 1 / Form 5329)", money(amt_e) if early else money(f.get("early_penalty")),
            "", [r["box7"].where() for r in early] + where(f.fact("early_penalty")))

    # ================= Annuity =================
    old = c.oldest()
    if old:
        t = tier(old[2], N["age"]["tiers"])
        if t:
            add(f"annuity.age_{t[0]}", "annuity", "annuity.age", t[1], f"Age {t[0]}+", old[2],
                f"{old[1]}, {old[2]}", [old[3]])
    pi = f.get("ira_taxable") + f.get("pen_taxable")
    if pi > 0:
        add("annuity.pension_ira_income", "annuity", "annuity.pension_ira_income", N["pension_ira_income"]["points"],
            "Taxable pension or IRA income", money(pi), "", where(f.fact("ira_taxable"), f.fact("pen_taxable")))
    t = tier(f.get("interest"), N["interest"]["tiers"])
    if t:
        add(f"annuity.interest_{k(t[0])}", "annuity", "annuity.interest", t[1], f"Taxable interest ≥ {money(t[0])}",
            money(f.get("interest")), "", where(f.fact("interest")))
    start = N["bracket_24"]["start"].get(year, N["bracket_24"]["start"][max(N["bracket_24"]["start"])])
    st = c.status() or "single"
    if f.get("taxable_income") >= start.get(st, start["single"]):
        add("annuity.bracket_24", "annuity", "annuity.bracket_24", N["bracket_24"]["points"],
            "Taxable income in the 24% bracket or higher", money(f.get("taxable_income")),
            f"24% bracket starts at {money(start.get(st, start['single']))} ({st})", where(f.fact("taxable_income")))
    reasons, rsrc = [], []
    if ss_started:
        reasons.append("Social Security started")
        rsrc += where(f.fact("ss"), prior_figs.fact("ss") if prior_figs else None)
    if rollovers:
        reasons.append(f"rollover of {money(rollover_amt)}")
        rsrc += [r["box7"].where() for r in rollovers]
    if "widowhood" in events:
        reasons.append("widowhood")
        rsrc += event_src.get("widowhood", [])
    if drop:
        reasons.append("income drop" if "early" not in drop[1] else "early retirement")
        rsrc += drop[2]
    if reasons:
        add("annuity.transition", "annuity", "annuity.transition", N["transition"]["points"], "Transition",
            "; ".join(reasons), "; ".join(reasons), rsrc)
    if old and old[2] >= N["rmd_age"]["age"] and f.get("ira_gross") > 0:
        add("annuity.rmd_age", "annuity", "annuity.rmd_age", N["rmd_age"]["points"],
            f"RMD age ({N['rmd_age']['age']}+) with IRA distributions", old[2], "", [old[3]] + where(f.fact("ira_gross")))

    # ================= Life =================
    deps = c.dependents()
    if deps:
        d = LF["dependents"]
        pts = d["base"] + d["per_dependent"] * min(len(deps), d["max_counted"])
        add("life.dependents", "life", "life.dependents", pts, "Dependents claimed", len(deps),
            ", ".join(x["name"] for x in deps), [deps[0]["fact"].where()] if "fact" in deps[0] else ["Client profile"])
    if c.status() == "mfj":
        e = c.earned_by_person()
        tot = sum(e.values())
        if tot > 0 and max(e.values()) / tot >= LF["single_earner"]["share"]:
            who = max(e, key=e.get)
            add("life.single_earner", "life", "life.single_earner", LF["single_earner"]["points"],
                f"Single-earner MFJ (one spouse ≥ {LF['single_earner']['share']:.0%} of earned income)",
                f"{max(e.values()) / tot:.0%}", f"{who} earns {money(e[who])} of {money(tot)}",
                [w["box1"].where() for w in c.src.get("W-2", [])] + where(f.fact("sch_c_net")))
    biz = max(f.get("sch_c_net"), f.get("k1_ordinary"))
    if biz >= LF["business_owner"]["min"]:
        kind = "Schedule C" if f.get("sch_c_net") >= f.get("k1_ordinary") else "S-corp K-1"
        add("life.business_owner", "life", "life.business_owner", LF["business_owner"]["points"],
            f"Business owner (Sch C or K-1 ≥ {money(LF['business_owner']['min'])})", money(biz),
            f"{kind} income {money(biz)}", where(f.fact("sch_c_net") if kind == "Schedule C" else f.fact("k1_ordinary")))
    t = tier(agi, LF["income"]["tiers"])
    if t:
        add(f"life.income_{k(t[0])}", "life", "life.income", t[1], f"Income ≥ {money(t[0])}", money(agi), "",
            where(f.fact("agi")))
    for i, ev in enumerate(events):
        add(f"life.life_event_{ev}", "life", "life.life_event", LF["life_event"]["points"] if i == 0 else 0,
            "Life event (counted once)", ev.replace("_", " "), events[ev], event_src.get(ev, []))
    ao = LF["age_over"]
    if old and old[2] > ao["age"]:
        add(f"life.age_over_{ao['age']}", "life", "life.age_over", ao["points"], f"Age over {ao['age']}", old[2], "",
            [old[3]])
    return sig


def life_events(c):
    """{event: detail} and {event: [sources]} for marriage, new_baby, divorce, widowhood."""
    ev, src = {}, {}
    cur = c.status()
    now_sp = c.h.get("spouse") or {}
    if now_sp.get("deceased"):
        ev["widowhood"] = f"spouse deceased {now_sp['deceased'].value}"
        src["widowhood"] = [now_sp["deceased"].where()]
    if c.pyr is not None:
        prev = c.status(c.pyr)
        prev_h = c.pyr.get("header", {})
        prev_sp = prev_h.get("spouse") or {}
        st_src = [x.where() for x in (prev_h.get("status"), c.h.get("status")) if x is not None]
        if prev in ("single", "hoh", "mfs") and cur == "mfj":
            ev["marriage"] = f"filing status {prev.upper()} → MFJ"
            src["marriage"] = st_src
        if prev == "mfj" and cur in ("single", "hoh", "mfs", "qss"):
            if prev_sp.get("deceased") or cur == "qss":
                ev["widowhood"] = f"MFJ → {cur.upper()}; spouse deceased " + (
                    prev_sp["deceased"].value if prev_sp.get("deceased") else "")
                src["widowhood"] = st_src + ([prev_sp["deceased"].where()] if prev_sp.get("deceased") else [])
            else:
                ev["divorce"] = f"filing status MFJ → {cur.upper()}"
                src["divorce"] = st_src
    babies = []
    for d in c.dependents():
        dob = c.dob_of(d["name"])
        if dob and int(dob[:4]) == c.year:
            babies.append(f"{d['name']} born {dob}")
    if not babies and c.pyr is not None:
        before = {x["name"] for x in c.dependents(c.pyr)}
        babies = [f"{d['name']} (new dependent)" for d in c.dependents()
                  if d["name"] not in before and (c.dob_of(d["name"]) or "0")[:4] >= str(c.year - 1)]
    if babies:
        ev["new_baby"] = "; ".join(babies)
        src["new_baby"] = ["Form 1040 dependents table", "Client profile (DOB)"]
    order = ["marriage", "new_baby", "divorce", "widowhood"]
    return {k: ev[k] for k in order if k in ev}, src


def income_drop(c, cfg):
    """(value, detail, sources) if AGI fell enough or wages stopped before 65; else None."""
    if c.pf is None:
        return None
    rule = cfg["aum"]["income_drop"]
    prev, now = c.pf.get("agi"), c.f.get("agi")
    if prev > 0 and (prev - now) / prev * 100 >= rule["min_drop_pct"]:
        pct = (prev - now) / prev * 100
        return (f"{pct:.0f}%", f"AGI {money(prev)} → {money(now)} ({pct:.0f}% drop)",
                where(c.pf.fact("agi"), c.f.fact("agi")))
    old = c.oldest()
    if c.pf.get("wages") > 0 and c.f.get("wages") == 0 and old and old[2] <= rule["early_retirement_max_age"]:
        return ("wages stopped", f"early retirement: wages {money(c.pf.get('wages'))} → $0 at age {old[2]}",
                where(c.pf.fact("wages"), c.f.fact("wages")))
    return None


# ---------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------
def grade(points, cutoffs):
    for g in ("A", "B", "C", "D"):
        if points >= cutoffs[g]:
            return g
    return "F"


def score(signals, cfg):
    aum = min(cfg["aum"]["cap"], sum(s.points for s in signals if s.product == "aum"))
    aum = max(0, aum)
    ann = sum(s.points for s in signals if s.product == "annuity")
    life = sum(s.points for s in signals if s.product == "life")
    b = cfg["bands"]
    fit = "high" if aum >= b["aum"]["high"] else "med" if aum >= b["aum"]["med"] else "low"
    return {"aum_score": aum, "aum_fit": fit,
            "annuity_points": ann, "annuity_grade": grade(ann, b["grades"]),
            "life_points": life, "life_grade": grade(life, b["grades"])}
