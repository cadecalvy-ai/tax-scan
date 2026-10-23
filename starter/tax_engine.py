"""Simplified federal tax engine for generating FICTIONAL test returns.

Numbers are internally consistent and close to real 2024/2025 rules, but this
is NOT tax software. It exists only so the sample returns look and add up
like real ones.
"""
import math

INF = float("inf")

BRACKETS = {
    2025: {
        "single": [(11925, .10), (48475, .12), (103350, .22), (197300, .24), (250525, .32), (626350, .35), (INF, .37)],
        "mfj":    [(23850, .10), (96950, .12), (206700, .22), (394600, .24), (501050, .32), (751600, .35), (INF, .37)],
        "hoh":    [(17000, .10), (64850, .12), (103350, .22), (197300, .24), (250500, .32), (626350, .35), (INF, .37)],
    },
    2024: {
        "single": [(11600, .10), (47150, .12), (100525, .22), (191950, .24), (243725, .32), (609350, .35), (INF, .37)],
        "mfj":    [(23200, .10), (94300, .12), (201050, .22), (383900, .24), (487450, .32), (731200, .35), (INF, .37)],
        "hoh":    [(16550, .10), (63100, .12), (100500, .22), (191950, .24), (243700, .32), (609350, .35), (INF, .37)],
    },
}
CG_THRESH = {  # (top of 0% bracket, top of 15% bracket)
    2025: {"single": (48350, 533400), "mfj": (96700, 600050), "hoh": (64750, 566700)},
    2024: {"single": (47025, 518900), "mfj": (94050, 583750), "hoh": (63000, 551350)},
}
STD = {2025: {"single": 15750, "mfj": 31500, "hoh": 23625},
       2024: {"single": 14600, "mfj": 29200, "hoh": 21900}}
ADDL_65 = {2025: {"single": 2000, "hoh": 2000, "mfj": 1600},
           2024: {"single": 1950, "hoh": 1950, "mfj": 1550}}
SS_WAGE_BASE = {2025: 176100, 2024: 168600}
CTC = {2025: 2200, 2024: 2000}
ACTC_MAX = {2025: 1700, 2024: 1700}
AMT_EX = {2025: {"single": (88100, 626350), "mfj": (137000, 1252700)},
          2024: {"single": (85700, 609350), "mfj": (133300, 1218700)}}
AMT_28 = {2025: 239100, 2024: 232600}


def age_at(dob, year):
    return year - int(dob[:4])


def bracket_tax(income, brackets):
    tax, lower = 0.0, 0.0
    for top, rate in brackets:
        if income <= lower:
            break
        tax += (min(income, top) - lower) * rate
        lower = top
    return tax


def regular_tax(ti, pref, status, year):
    """Tax using the qualified dividends / capital gain worksheet logic."""
    pref = max(0.0, min(pref, ti))
    ordinary = ti - pref
    tax = bracket_tax(ordinary, BRACKETS[year][status])
    t0, t15 = CG_THRESH[year][status]
    at0 = max(0.0, min(ti, t0) - ordinary)
    at15 = max(0.0, min(ti, t15) - max(ordinary, t0))
    at20 = max(0.0, pref - at0 - at15)
    return tax + at15 * .15 + at20 * .20


def ss_taxable(ss, other_income, status):
    if ss <= 0:
        return 0.0
    b1, b2 = (32000, 44000) if status == "mfj" else (25000, 34000)
    prov = other_income + 0.5 * ss
    if prov <= b1:
        return 0.0
    if prov <= b2:
        return min(0.5 * ss, 0.5 * (prov - b1))
    return min(0.85 * ss, 0.85 * (prov - b2) + min(0.5 * ss, 0.5 * (b2 - b1)))


def compute(p, year):
    """Return a dict of every figure needed to render the return."""
    st = p["status"]
    r = {"year": year, "status": st}
    persons = ["t"] + (["s"] if st == "mfj" else [])
    ages = {"t": age_at(p["dob"], year)}
    if st == "mfj":
        ages["s"] = age_at(p["sdob"], year)
    r["ages"] = ages
    r["n65"] = sum(1 for k in persons if ages[k] >= 65)

    w2s = p.get("w2s", [])
    r["wages"] = sum(w["wages"] for w in w2s)
    r["tax_exempt_int"] = p.get("muni", 0)
    r["interest"] = sum(a for _, a in p.get("interest", []))
    divs = p.get("dividends", [])
    r["ord_div"] = sum(d[1] for d in divs)
    r["qual_div"] = sum(d[2] for d in divs)
    r["cg_dist"] = sum(d[3] if len(d) > 3 else 0 for d in divs)

    iras = p.get("ira_dist", [])
    r["ira_gross"] = sum(d["gross"] for d in iras)
    r["ira_taxable"] = sum(d["taxable"] for d in iras)
    pens = p.get("pension", [])
    r["pen_gross"] = sum(d["gross"] for d in pens)
    r["pen_taxable"] = sum(d["taxable"] for d in pens)
    r["early_dist"] = sum(d["taxable"] for d in iras + pens if d["code"] == "1")
    r["ss_total"] = sum(s["amount"] for s in p.get("ss", []))

    b = p.get("brokerage") or {}
    st_gain = b.get("st", 0)
    lt_gain = b.get("lt", 0) + r["cg_dist"]
    hs = p.get("home_sale")
    if hs:
        hs_gain = hs["price"] - hs["selling_costs"] - hs["basis"]
        hs_taxable = max(0, hs_gain - hs["exclusion"])
        r["home_gain"], r["home_taxable"] = hs_gain, hs_taxable
        lt_gain += hs_taxable
    bs = p.get("biz_sale")
    if bs:
        r["biz_gain"] = bs["proceeds"] - bs["basis"]
        lt_gain += r["biz_gain"]
    net_cg = st_gain + lt_gain
    r["st_gain"], r["lt_gain"] = st_gain, lt_gain
    r["line7"] = max(net_cg, -3000)

    sc = p.get("sch_c")
    schc_net = (sc["gross"] - sum(sc["expenses"].values())) if sc else 0
    r["schc_net"] = schc_net
    se_tax = half_se = 0.0
    if schc_net > 400:
        se_base = 0.9235 * schc_net
        owner_wages = sum(w["wages"] + w.get("k401", 0) for w in w2s if w["who"] == sc.get("who", "t"))
        room = max(0, SS_WAGE_BASE[year] - owner_wages)
        se_tax = 0.124 * min(se_base, room) + 0.029 * se_base
        half_se = se_tax / 2
    r["se_base"] = 0.9235 * schc_net if schc_net > 400 else 0
    r["se_tax"], r["half_se"] = se_tax, half_se
    k1 = p.get("k1")
    r["k1_ord"] = k1["ordinary"] if k1 else 0
    rentals = p.get("rentals", [])
    r["rental_nets"] = [x["rents"] - sum(x["expenses"].values()) - x["depreciation"] for x in rentals]
    r["rental_net"] = sum(r["rental_nets"])
    r["unemployment"] = p.get("unemployment", 0)
    r["sch1_income"] = schc_net + r["k1_ord"] + r["rental_net"] + r["unemployment"]

    r["sep"] = sc.get("sep", 0) if sc else 0
    r["hsa_deduction"] = p.get("hsa_direct", 0)
    r["ira_deduction"] = p.get("ira_deduction", 0)
    r["adjustments"] = half_se + r["sep"] + r["hsa_deduction"] + r["ira_deduction"]

    non_ss = (r["wages"] + r["interest"] + r["ord_div"] + r["ira_taxable"] + r["pen_taxable"]
              + r["line7"] + r["sch1_income"] - r["adjustments"] + r["tax_exempt_int"])
    r["ss_taxable"] = ss_taxable(r["ss_total"], non_ss, st)
    r["total_income"] = (r["wages"] + r["interest"] + r["ord_div"] + r["ira_taxable"] + r["pen_taxable"]
                         + r["ss_taxable"] + r["line7"] + r["sch1_income"])
    r["agi"] = r["total_income"] - r["adjustments"]

    std = STD[year][st] + ADDL_65[year][st] * r["n65"]
    r["std"] = std
    it = p.get("itemized")
    r["itemized_total"] = 0
    if it:
        salt_cap = 10000
        if year == 2025:
            salt_cap = max(10000, 40000 - 0.30 * max(0, r["agi"] - 500000))
        r["salt_paid"] = it["state_income_tax"] + it["property_tax"]
        r["salt_allowed"] = min(r["salt_paid"], salt_cap)
        r["mortgage_int"] = it.get("mortgage", 0)
        r["charity"] = it.get("charity_cash", 0) + it.get("charity_noncash", 0)
        r["itemized_total"] = r["salt_allowed"] + r["mortgage_int"] + r["charity"]
    r["itemizes"] = r["itemized_total"] > std
    r["deduction"] = r["itemized_total"] if r["itemizes"] else std

    pref = r["qual_div"] + max(0.0, min(r["line7"], lt_gain))
    r["pref"] = pref
    qbi_base = schc_net - half_se - r["sep"] + r["k1_ord"]
    r["qbi"] = max(0.0, min(0.2 * qbi_base, 0.2 * max(0.0, r["agi"] - r["deduction"] - pref))) if qbi_base > 0 else 0.0

    r["senior_ded"] = 0.0
    if year == 2025 and r["n65"]:
        thr = 150000 if st == "mfj" else 75000
        per = max(0.0, 6000 - 0.06 * max(0.0, r["agi"] - thr))
        r["senior_ded"] = per * r["n65"]

    r["taxable_income"] = max(0.0, r["agi"] - r["deduction"] - r["qbi"] - r["senior_ded"])
    r["tax"] = regular_tax(r["taxable_income"], pref, st, year)

    r["amt"] = 0.0
    if p.get("iso_spread"):
        key = "mfj" if st == "mfj" else "single"
        ex, phase = AMT_EX[year][key]
        amti = r["taxable_income"] + p["iso_spread"] + (r.get("salt_allowed", 0) if r["itemizes"] else 0)
        ex = max(0.0, ex - 0.25 * max(0.0, amti - phase))
        base = max(0.0, amti - ex)
        pref_amt = min(pref, base)
        ord_amt = base - pref_amt
        tmt = 0.26 * min(ord_amt, AMT_28[year]) + 0.28 * max(0.0, ord_amt - AMT_28[year])
        tmt += regular_tax(base, pref_amt, st, year) - bracket_tax(base - pref_amt, BRACKETS[year][st])
        r["amti"], r["amt_exemption"], r["tmt"] = amti, ex, tmt
        r["amt"] = max(0.0, tmt - r["tax"])
    r["line18"] = r["tax"] + r["amt"]

    kids = [d for d in p.get("dependents", []) if age_at(d["dob"], year) < 17]
    others = [d for d in p.get("dependents", []) if age_at(d["dob"], year) >= 17]
    r["ctc_kids"], r["odc"] = len(kids), len(others)
    credit = CTC[year] * len(kids) + 500 * len(others)
    thr = 400000 if st == "mfj" else 200000
    credit = max(0.0, credit - 50 * math.ceil(max(0.0, r["agi"] - thr) / 1000))
    r["ctc"] = min(credit, r["line18"])
    leftover_child = max(0.0, min(credit, CTC[year] * len(kids)) - r["ctc"])
    earned = r["wages"] + max(0, schc_net - half_se)
    r["actc"] = min(leftover_child, ACTC_MAX[year] * len(kids), max(0.0, 0.15 * (earned - 2500)))
    r["line22"] = max(0.0, r["line18"] - r["ctc"])

    nii = r["interest"] + r["ord_div"] + max(0.0, r["line7"] - r.get("biz_gain", 0)) + max(0.0, r["rental_net"])
    if p.get("rental_active"):
        nii -= max(0.0, r["rental_net"])
    niit_thr = 250000 if st == "mfj" else 200000
    r["nii"] = nii
    r["niit"] = 0.038 * max(0.0, min(nii, r["agi"] - niit_thr))
    r["early_penalty"] = 0.10 * r["early_dist"]
    r["other_taxes"] = r["se_tax"] + r["niit"] + r["early_penalty"]
    r["total_tax"] = r["line22"] + r["other_taxes"]
    return r


def assign_payments(p, r):
    """Set W-2 withholding / estimates so the refund or balance due matches pay_ratio."""
    fixed = sum(d.get("wh", 0) for d in p.get("ira_dist", []) + p.get("pension", []) + p.get("ss", []))
    fixed += p.get("unemployment_wh", 0)
    target = p.get("pay_ratio", 1.0) * r["total_tax"]
    est = p.get("est_payments", 0)
    w2s = p.get("w2s", [])
    need = max(0.0, target - fixed - est)
    if w2s:
        tot = sum(w["wages"] for w in w2s) or 1
        for w in w2s:
            w["fed_wh"] = round(need * w["wages"] / tot)
    elif p.get("est_fill"):
        est = round(need, -2)
    r["wh_w2"] = sum(w.get("fed_wh", 0) for w in w2s)
    r["wh_1099"] = fixed
    r["est"] = est
    r["payments"] = r["wh_w2"] + r["wh_1099"] + est + r["actc"]
    diff = r["payments"] - r["total_tax"]
    r["refund"] = max(0.0, diff)
    r["owed"] = max(0.0, -diff)
    r["penalty"] = round(r["owed"] * 0.045) if (r["owed"] > 1000 and p.get("underpayment_penalty")) else 0
    if r["penalty"]:
        r["owed"] += r["penalty"]
    return r
