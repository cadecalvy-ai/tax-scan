"""Turn tax_engine results into rounded form lines, then draw the 1040 and schedules.

Rounding rule: each schedule line is rounded once, and every total on the 1040
is the sum of the rounded lines it is built from, so the printed return always
foots. generate.py checks the printed totals against the engine (within $3).
"""
from draw import Pdf, LEFT, RIGHT, BOX_X, money

R = round


def ss_wages(w, year):
    """W-2 box 3: wages plus pre-tax 401(k) deferrals, capped at the wage base."""
    from tax_engine import SS_WAGE_BASE
    return min(w["wages"] + w.get("k401", 0), SS_WAGE_BASE[year])


# =====================================================================
# Model: every line value the PDFs will print
# =====================================================================
def build(p, r, year):
    from tax_engine import SS_WAGE_BASE
    f = {}          # form name -> {line: value}
    L = {}          # Form 1040
    agi_key = "11a" if year == 2025 else "11"
    qbi_key = "13a" if year == 2025 else "13"

    # ---- Schedule C / SE --------------------------------------------
    sc = p.get("sch_c")
    if sc:
        e = sc["expenses"]
        tot = sum(e.values())
        f["Sch C"] = {"1": sc["gross"], "7": sc["gross"], "28": tot, "29": sc["gross"] - tot, "31": sc["gross"] - tot}
        for k, line in EXP_LINES.items():
            if e.get(k):
                f["Sch C"][line] = e[k]
    if r["se_tax"]:
        net = r["schc_net"]
        se = {"2": net, "3": net, "4a": R(0.9235 * net)}
        se["4c"] = se["6"] = se["4a"]
        se["7"] = SS_WAGE_BASE[year]
        se["8a"] = sum(ss_wages(w, year) for w in p.get("w2s", []) if w["who"] == sc.get("who", "t"))
        se["9"] = max(0, se["7"] - se["8a"])
        se["10"] = R(0.124 * min(se["6"], se["9"]))
        se["11"] = R(0.029 * se["6"])
        se["12"] = se["10"] + se["11"]
        se["13"] = R(se["12"] / 2)
        f["Sch SE"] = se

    # ---- Schedule E -------------------------------------------------
    rentals, k1 = p.get("rentals", []), p.get("k1")
    if rentals or k1:
        e = {"props": []}
        for x, net in zip(rentals, r["rental_nets"]):
            exp = sum(x["expenses"].values()) + x["depreciation"]
            e["props"].append({"3": x["rents"], **{RENT_LINES[k]: v for k, v in x["expenses"].items()},
                               "18": x["depreciation"], "20": exp, "21": net})
        if rentals:
            e["23a"] = sum(x["rents"] for x in rentals)
            e["23c"] = sum(x["expenses"].get("mortgage", 0) for x in rentals)
            e["23d"] = sum(x["depreciation"] for x in rentals)
            e["23e"] = sum(pr["20"] for pr in e["props"])
            e["24"] = sum(n for n in r["rental_nets"] if n > 0)
            e["25"] = sum(n for n in r["rental_nets"] if n < 0)
            e["26"] = e["24"] + e["25"]
        if k1:
            e["28k"] = e["29a"] = e["30"] = e["32"] = k1["ordinary"]
        e["41"] = e.get("26", 0) + e.get("32", 0)
        f["Sch E"] = e

    # ---- Schedule 1 -------------------------------------------------
    s1 = {"3": r["schc_net"], "5": f.get("Sch E", {}).get("41", 0), "7": r["unemployment"]}
    s1["10"] = s1["3"] + s1["5"] + s1["7"]
    s1["13"] = r["hsa_deduction"]
    s1["15"] = f.get("Sch SE", {}).get("13", 0)
    s1["16"] = r["sep"]
    s1["20"] = r["ira_deduction"]
    s1["26"] = s1["13"] + s1["15"] + s1["16"] + s1["20"]
    if s1["10"] or s1["26"]:
        f["Sch 1"] = s1

    # ---- Schedule B / D / 8949 --------------------------------------
    if r["interest"] > 1500 or r["ord_div"] > 1500:
        f["Sch B"] = {"2": r["interest"], "4": r["interest"], "6": r["ord_div"]}
    b = p.get("brokerage") or {}
    rows = []
    hs, bs = p.get("home_sale"), p.get("biz_sale")
    if hs:
        rows.append({"desc": "Main home — " + hs["address"], "acq": hs["acquired"], "sold": hs["sold"],
                     "proceeds": hs["price"] - hs["selling_costs"], "cost": hs["basis"], "code": "H",
                     "adj": -min(hs["exclusion"], r["home_gain"]), "gain": r["home_taxable"]})
    if bs:
        rows.append({"desc": bs["desc"], "acq": bs["acquired"], "sold": bs["sold"], "proceeds": bs["proceeds"],
                     "cost": bs["basis"], "code": "", "adj": 0, "gain": r["biz_gain"]})
    if rows:
        f["8949"] = {"rows": rows, "2_proceeds": sum(x["proceeds"] for x in rows),
                     "2_cost": sum(x["cost"] for x in rows), "2_adj": sum(x["adj"] for x in rows),
                     "2_gain": sum(x["gain"] for x in rows)}
    if b or rows or r["cg_dist"]:
        d = {}
        if b.get("st"):
            d["1a_cost"] = b.get("st_basis", 0)
            d["1a_proceeds"] = d["1a_cost"] + b["st"]
            d["1a_gain"] = b["st"]
        d["7"] = b.get("st", 0)
        if b.get("lt"):
            d["8a_cost"] = b.get("lt_basis", 0)
            d["8a_proceeds"] = d["8a_cost"] + b["lt"]
            d["8a_gain"] = b["lt"]
        if rows:
            d["10_proceeds"], d["10_cost"] = f["8949"]["2_proceeds"], f["8949"]["2_cost"]
            d["10_adj"], d["10_gain"] = f["8949"]["2_adj"], f["8949"]["2_gain"]
        d["13"] = r["cg_dist"]
        d["15"] = b.get("lt", 0) + d.get("10_gain", 0) + d["13"]
        d["16"] = d["7"] + d["15"]
        f["Sch D"] = d

    # ---- Schedule A -------------------------------------------------
    it = p.get("itemized")
    if it and r["itemizes"]:
        a = {"5a": it["state_income_tax"], "5b": it["property_tax"]}
        a["5d"] = a["5a"] + a["5b"]
        a["5e"] = R(r["salt_allowed"])
        a["7"] = a["5e"]
        a["8a"] = a["8e"] = a["10"] = it.get("mortgage", 0)
        a["11"] = it.get("charity_cash", 0)
        a["12"] = it.get("charity_noncash", 0)
        a["14"] = a["11"] + a["12"]
        a["17"] = a["7"] + a["10"] + a["14"]
        f["Sch A"] = a

    # ---- 1040 income ------------------------------------------------
    L["1a"] = L["1z"] = r["wages"]
    L["2a"], L["2b"] = r["tax_exempt_int"], r["interest"]
    L["3a"], L["3b"] = r["qual_div"], r["ord_div"]
    L["4a"], L["4b"] = r["ira_gross"], r["ira_taxable"]
    L["5a"], L["5b"] = r["pen_gross"], r["pen_taxable"]
    L["6a"], L["6b"] = r["ss_total"], R(r["ss_taxable"])
    L["7"] = f["Sch D"]["16"] if "Sch D" in f else R(r["line7"])
    L["8"] = s1["10"]
    L["9"] = L["1z"] + L["2b"] + L["3b"] + L["4b"] + L["5b"] + L["6b"] + L["7"] + L["8"]
    L["10"] = s1["26"]
    L[agi_key] = L["9"] - L["10"]
    agi = L[agi_key]
    if year == 2025:
        L["11b"] = agi

    # ---- deductions -------------------------------------------------
    L["12"] = f["Sch A"]["17"] if "Sch A" in f else R(r["deduction"])
    L[qbi_key] = R(r["qbi"])
    if L[qbi_key]:
        qbi_base = r["schc_net"] - s1["15"] - r["sep"] + r["k1_ord"]
        f["8995"] = {"2": qbi_base, "4": qbi_base, "5": R(0.2 * qbi_base),
                     "11": agi - L["12"], "12": R(r["pref"]), "15": L[qbi_key]}
        f["8995"]["13"] = max(0, f["8995"]["11"] - f["8995"]["12"])
        f["8995"]["14"] = R(0.2 * f["8995"]["13"])
        f["8995"]["10"] = f["8995"]["5"]
    if year == 2025:
        L["13b"] = R(r["senior_ded"])
        if L["13b"]:
            thr = 150000 if r["status"] == "mfj" else 75000
            f["Sch 1-A"] = {"n": r["n65"], "34": agi, "35": thr, "36": max(0, agi - thr),
                            "37": R(0.06 * max(0, agi - thr)), "38": L["13b"]}
    L["14"] = L["12"] + L[qbi_key] + L.get("13b", 0)
    L["15"] = max(0, agi - L["14"])

    # ---- tax --------------------------------------------------------
    L["16"] = R(r["tax"])
    L["17"] = 0
    if p.get("iso_spread"):
        salt = f["Sch A"]["7"] if "Sch A" in f else 0
        amt = {"1": L["15"], "2a": salt, "2i": p["iso_spread"]}
        amt["4"] = amt["1"] + amt["2a"] + amt["2i"]
        amt["5"] = R(r["amt_exemption"])
        amt["6"] = max(0, amt["4"] - amt["5"])
        amt["7"] = amt["9"] = R(r["tmt"])
        amt["10"] = L["16"]
        amt["11"] = max(0, amt["9"] - amt["10"])
        f["6251"] = amt
        L["17"] = amt["11"]
    L["18"] = L["16"] + L["17"]
    L["19"] = min(R(r["ctc"]), L["18"])
    L["20"] = 0
    L["21"] = L["19"] + L["20"]
    L["22"] = max(0, L["18"] - L["21"])

    # ---- other taxes (Schedule 2) -----------------------------------
    s2 = {"2": L["17"], "3": L["17"], "4": f.get("Sch SE", {}).get("12", 0), "8": 0, "12": 0}
    if r["early_penalty"]:
        f["5329"] = {"1": r["early_dist"], "2": 0, "3": r["early_dist"], "4": R(0.1 * r["early_dist"])}
        s2["8"] = f["5329"]["4"]
    if r["niit"] > 0.5:
        n = {"1": r["interest"], "2": r["ord_div"], "4a": 0, "5a": L["7"], "5b": -r.get("biz_gain", 0)}
        if not p.get("rental_active"):
            n["4a"] = max(0, r["rental_net"])
        n["4c"] = n["4a"]
        n["5d"] = max(0, n["5a"] + n["5b"])
        n["8"] = n["1"] + n["2"] + n["4c"] + n["5d"]
        n["12"] = n["8"]
        n["13"] = agi
        n["14"] = 250000 if r["status"] == "mfj" else 200000
        n["15"] = max(0, n["13"] - n["14"])
        n["16"] = min(n["12"], n["15"])
        n["17"] = R(0.038 * n["16"])
        f["8960"] = n
        s2["12"] = n["17"]
    s2["21"] = s2["4"] + s2["8"] + s2["12"]
    if s2["3"] or s2["21"]:
        f["Sch 2"] = s2
    L["23"] = s2["21"]
    L["24"] = L["22"] + L["23"]

    # ---- payments ---------------------------------------------------
    L["25a"] = r["wh_w2"]
    L["25b"] = R(r["wh_1099"])
    L["25c"] = 0
    L["25d"] = L["25a"] + L["25b"] + L["25c"]
    L["26"] = R(r["est"])
    L["27"] = 0
    L["28"] = R(r["actc"])
    L["29"] = 0
    L["31"] = 0
    L["32"] = L["27"] + L["28"] + L["29"] + L["31"]
    L["33"] = L["25d"] + L["26"] + L["32"]
    diff = L["33"] - L["24"]
    L["34"] = L["35a"] = max(0, diff)
    L["36"] = 0
    L["38"] = r["penalty"] if diff < 0 else 0
    L["37"] = max(0, -diff) + L["38"]

    # ---- other forms ------------------------------------------------
    if p.get("iso"):
        f["3921"] = p["iso"]
    if p.get("backdoor"):
        f["8606"] = p["backdoor"]
    hsa = [w for w in p.get("w2s", []) if w.get("hsa")]
    if hsa or r["hsa_deduction"]:
        limit = {2025: 8550, 2024: 8300}[year]
        emp = sum(w["hsa"] for w in hsa)
        f["8889"] = {"who": hsa[0]["who"] if hsa else "t", "2": r["hsa_deduction"], "3": limit, "6": limit,
                     "8": limit, "9": emp, "11": emp, "12": max(0, limit - emp),
                     "13": min(r["hsa_deduction"], max(0, limit - emp))}
    f["1040"] = L
    return f


EXP_LINES = {"advertising": "8", "car": "9", "depreciation": "13", "insurance": "15", "legal": "17",
             "office": "18", "rent": "20b", "supplies": "22", "taxes": "23", "utilities": "25",
             "wages": "26", "other": "27a"}
EXP_LABELS = {"8": "Advertising", "9": "Car and truck expenses", "13": "Depreciation and section 179 expense",
              "15": "Insurance (other than health)", "17": "Legal and professional services",
              "18": "Office expense", "20b": "Rent or lease — other business property", "22": "Supplies",
              "23": "Taxes and licenses", "25": "Utilities", "26": "Wages (less employment credits)",
              "27a": "Other expenses (from line 48)"}
RENT_LINES = {"insurance": "9", "mortgage": "12", "repairs": "14", "taxes": "16", "utilities": "17"}
RENT_LABELS = {"3": "Rents received", "9": "Insurance", "12": "Mortgage interest paid to banks, etc.",
               "14": "Repairs", "16": "Taxes", "17": "Utilities", "18": "Depreciation expense or depletion",
               "20": "Total expenses. Add lines 5 through 19", "21": "Subtract line 20 from line 3 (income) or (loss)"}


# =====================================================================
# Rendering
# =====================================================================
class ReturnCtx:
    """Names and IDs the renderer needs."""
    def __init__(self, year, status, t, s, deps, address, preparer, ein):
        self.year, self.status, self.t, self.s, self.deps = year, status, t, s, deps
        self.address, self.preparer, self.ein = address, preparer, ein

    @property
    def names(self):
        if self.status == "mfj" and self.s:
            if self.t["last"] == self.s["last"]:
                return f"{self.t['first']} & {self.s['first']} {self.t['last']}"
            return f"{self.t['first']} {self.t['last']} & {self.s['first']} {self.s['last']}"
        return f"{self.t['first']} {self.t['last']}"

    def person(self, who):
        return self.t if who == "t" else self.s


def render_return(path, ctx, p, f):
    year = ctx.year
    pdf = Pdf(path, f"{year} Form 1040 and Schedules — {ctx.names} (fictional)")
    draw_1040(pdf, ctx, p, f)
    order = ["Sch 1", "Sch 1-A", "Sch 2", "Sch A", "Sch B", "Sch C", "Sch D", "Sch E", "Sch SE",
             "8949", "8960", "6251", "5329", "8606", "8889", "8995"]
    for name in order:
        if name in f:
            DRAWERS[name](pdf, ctx, p, f)
    pdf.save()


def page2_header(pdf, ctx, page):
    pdf.text(LEFT, pdf.y, f"Form 1040 ({ctx.year})", 8, bold=True)
    pdf.text(RIGHT, pdf.y, f"Page {page}", 8, bold=True, align="right")
    pdf.hline(pdf.y - 4, width=1)
    pdf.y -= 18


def draw_1040(pdf, ctx, p, f):
    L, year = f["1040"], ctx.year
    born = "January 2, 1961" if year == 2025 else "January 2, 1960"
    pdf.new_page()
    pdf.form_header("1040", "U.S. Individual Income Tax Return", year,
                    extra=f"For the year Jan. 1–Dec. 31, {year}, or other tax year beginning ____, ending ____")
    # filing status
    pdf.text(LEFT, pdf.y, "Filing Status", 8, bold=True)
    x = LEFT + 70
    for code, label in [("single", "Single"), ("mfj", "Married filing jointly"), ("mfs", "Married filing separately (MFS)"),
                        ("hoh", "Head of household (HOH)"), ("qss", "Qualifying surviving spouse (QSS)")]:
        pdf.checkbox(x, pdf.y, ctx.status == code, label, 6.5)
        x += {"single": 45, "mfj": 95, "mfs": 118, "hoh": 102, "qss": 0}[code]
    pdf.y -= 12
    pdf.hline(pdf.y)
    pdf.y -= 10

    # names and address
    t, s = ctx.t, ctx.s if ctx.status == "mfj" else None
    def name_row(lbl1, first, lbl2, last, lbl3, ssn):
        y = pdf.y
        pdf.text(LEFT, y, lbl1, 5.8); pdf.text(LEFT + 4, y - 10, first, 9)
        pdf.text(LEFT + 200, y, lbl2, 5.8); pdf.text(LEFT + 204, y - 10, last, 9)
        pdf.text(RIGHT - 120, y, lbl3, 5.8); pdf.text(RIGHT - 116, y - 10, ssn, 9, bold=True)
        pdf.hline(y - 14)
        pdf.y -= 22
    name_row("Your first name and middle initial", t["first"], "Last name", t["last"], "Your social security number", t["ssn"])
    if s:
        last = s["last"] + (f"   — DECEASED {s['died']}" if s.get("died") else "")
        name_row("If joint return, spouse’s first name and middle initial", s["first"], "Last name", last,
                 "Spouse’s social security number", s["ssn"])
    else:
        name_row("If joint return, spouse’s first name and middle initial", "", "Last name", "",
                 "Spouse’s social security number", "")
    street, city, zip_ = ctx.address
    name_row("Home address (number and street)", street, "City, town, or post office", city,
             "State      ZIP code", f"MN         {zip_}")

    pdf.text(LEFT, pdf.y, f"Digital Assets  At any time during {year}, did you: (a) receive (as a reward, award, or payment); "
             "or (b) sell, exchange, or otherwise dispose of a digital asset?", 6.3)
    pdf.checkbox(RIGHT - 60, pdf.y, False, "Yes", 6.5)
    pdf.checkbox(RIGHT - 28, pdf.y, True, "No", 6.5)
    pdf.y -= 12
    pdf.hline(pdf.y)
    pdf.y -= 10
    pdf.text(LEFT, pdf.y, "Standard Deduction", 7, bold=True)
    pdf.text(LEFT + 80, pdf.y, "Someone can claim:", 6.5)
    pdf.checkbox(LEFT + 150, pdf.y, False, "You as a dependent", 6.5)
    pdf.checkbox(LEFT + 250, pdf.y, False, "Your spouse as a dependent", 6.5)
    pdf.y -= 12
    t65 = int(t["dob"][:4]) < year - 64
    s65 = bool(s) and int(s["dob"][:4]) < year - 64
    pdf.text(LEFT, pdf.y, "Age/Blindness", 7, bold=True)
    pdf.text(LEFT + 80, pdf.y, "You:", 6.5, bold=True)
    pdf.checkbox(LEFT + 100, pdf.y, t65, f"Were born before {born}", 6.5)
    pdf.checkbox(LEFT + 222, pdf.y, False, "Are blind", 6.5)
    pdf.text(LEFT + 280, pdf.y, "Spouse:", 6.5, bold=True)
    pdf.checkbox(LEFT + 310, pdf.y, s65, f"Was born before {born}", 6.5)
    pdf.checkbox(LEFT + 430, pdf.y, False, "Is blind", 6.5)
    pdf.y -= 10
    pdf.hline(pdf.y)
    pdf.y -= 10

    # dependents table
    pdf.text(LEFT, pdf.y, "Dependents", 7.5, bold=True)
    pdf.text(LEFT, pdf.y - 9, "(see instructions)", 5.8)
    cols = [LEFT + 80, LEFT + 240, LEFT + 325, LEFT + 405, LEFT + 465]
    heads = ["(1) First name     Last name", "(2) Social security number", "(3) Relationship to you",
             "(4) Child tax credit", "Credit for other dep."]
    for x, h in zip(cols, heads):
        pdf.text(x, pdf.y, h, 5.8, bold=True)
    pdf.y -= 12
    deps = ctx.deps + [None] * max(0, 4 - len(ctx.deps))
    for d in deps:
        if d:
            kid = year - int(d["dob"][:4]) < 17
            pdf.text(cols[0], pdf.y, f"{d['first']} {d['last']}", 8)
            pdf.text(cols[1], pdf.y, d["ssn"], 8)
            pdf.text(cols[2], pdf.y, d["rel"], 8)
            pdf.checkbox(cols[3] + 20, pdf.y, kid)
            pdf.checkbox(cols[4] + 20, pdf.y, not kid)
        pdf.hline(pdf.y - 3, cols[0], RIGHT, 0.3)
        pdf.y -= 11
    pdf.hline(pdf.y + 4, width=1)
    pdf.y -= 6

    # income
    pdf.text(LEFT, pdf.y, "Income", 8, bold=True)
    pdf.y -= 12
    pdf.line("1a", "Total amount from Form(s) W-2, box 1 (see instructions)", L["1a"])
    for n, lbl in [("1b", "Household employee wages not reported on Form(s) W-2"),
                   ("1c", "Tip income not reported on line 1a (see instructions)"),
                   ("1d", "Medicaid waiver payments not reported on Form(s) W-2"),
                   ("1e", "Taxable dependent care benefits from Form 2441, line 26"),
                   ("1f", "Employer-provided adoption benefits from Form 8839, line 29"),
                   ("1g", "Wages from Form 8919, line 6"),
                   ("1h", "Other earned income (see instructions)"),
                   ("1i", "Nontaxable combat pay election")]:
        pdf.line(n, lbl, 0)
    pdf.line("1z", "Add lines 1a through 1h", L["1z"], show_zero=True)
    pdf.pair("2a", "Tax-exempt interest", L["2a"], "2b", "Taxable interest", L["2b"])
    pdf.pair("3a", "Qualified dividends", L["3a"], "3b", "Ordinary dividends", L["3b"])
    note4 = "QCD" if p.get("qcd") else ""
    note5 = "ROLLOVER" if any(d["code"] == "G" for d in p.get("pension", [])) else ""
    pdf.pair("4a", "IRA distributions", L["4a"], "4b", "Taxable amount", L["4b"], note=note4)
    pdf.pair("5a", "Pensions and annuities", L["5a"], "5b", "Taxable amount", L["5b"], note=note5)
    pdf.pair("6a", "Social security benefits", L["6a"], "6b", "Taxable amount", L["6b"])
    pdf.text(LEFT + 24, pdf.y, "6c  If you elect to use the lump-sum election method, check here (see instructions)", 7)
    pdf.checkbox(BOX_X - 40, pdf.y, False)
    pdf.y -= 13
    pdf.line("7", "Capital gain or (loss). Attach Schedule D if required", L["7"])
    pdf.line("8", "Additional income from Schedule 1, line 10", L["8"])
    pdf.line("9", "Add lines 1z, 2b, 3b, 4b, 5b, 6b, 7, and 8. This is your total income", L["9"], show_zero=True, bold=True)
    pdf.line("10", "Adjustments to income from Schedule 1, line 26", L["10"])
    if year == 2025:
        pdf.line("11a", "Subtract line 10 from line 9. This is your adjusted gross income", L["11a"], show_zero=True, bold=True)
    else:
        pdf.line("11", "Subtract line 10 from line 9. This is your adjusted gross income", L["11"], show_zero=True, bold=True)

    # ---- page 2 ----
    pdf.new_page()
    page2_header(pdf, ctx, 2)
    pdf.text(LEFT, pdf.y + 2, "Tax and Credits", 8, bold=True)
    pdf.y -= 10
    if year == 2025:
        pdf.line("11b", "Amount from line 11a (adjusted gross income)", L["11b"], show_zero=True)
    pdf.line("12", "Standard deduction or itemized deductions (from Schedule A)", L["12"], show_zero=True)
    if year == 2025:
        pdf.line("13a", "Qualified business income deduction from Form 8995 or Form 8995-A", L["13a"])
        pdf.line("13b", "Deductions from Schedule 1-A, line 38", L["13b"])
        pdf.line("14", "Add lines 12, 13a, and 13b", L["14"], show_zero=True)
        pdf.line("15", "Subtract line 14 from line 11b. If zero or less, enter -0-. This is your taxable income",
                 L["15"], show_zero=True, bold=True, size=7)
    else:
        pdf.line("13", "Qualified business income deduction from Form 8995 or Form 8995-A", L["13"])
        pdf.line("14", "Add lines 12 and 13", L["14"], show_zero=True)
        pdf.line("15", "Subtract line 14 from line 11. If zero or less, enter -0-. This is your taxable income",
                 L["15"], show_zero=True, bold=True, size=7)
    pdf.line("16", "Tax (see instructions). Check if any from Form(s): 8814  4972  ____", L["16"], show_zero=True)
    pdf.line("17", "Amount from Schedule 2, line 3", L["17"])
    pdf.line("18", "Add lines 16 and 17", L["18"], show_zero=True)
    pdf.line("19", "Child tax credit or credit for other dependents from Schedule 8812", L["19"])
    pdf.line("20", "Amount from Schedule 3, line 8", L["20"])
    pdf.line("21", "Add lines 19 and 20", L["21"])
    pdf.line("22", "Subtract line 21 from line 18. If zero or less, enter -0-", L["22"], show_zero=True)
    pdf.line("23", "Other taxes, including self-employment tax, from Schedule 2, line 21", L["23"])
    pdf.line("24", "Add lines 22 and 23. This is your total tax", L["24"], show_zero=True, bold=True)
    pdf.y -= 3
    pdf.text(LEFT, pdf.y + 2, "Payments", 8, bold=True)
    pdf.y -= 10
    pdf.line("25a", "Federal income tax withheld from: Form(s) W-2", L["25a"], indent=8)
    pdf.line("25b", "Form(s) 1099", L["25b"], indent=8)
    pdf.line("25c", "Other forms (see instructions)", L["25c"], indent=8)
    pdf.line("25d", "Add lines 25a through 25c", L["25d"], show_zero=True)
    pdf.line("26", f"{year} estimated tax payments and amount applied from {year - 1} return", L["26"])
    pdf.line("27", "Earned income credit (EIC)", L["27"])
    pdf.line("28", "Additional child tax credit from Schedule 8812", L["28"])
    pdf.line("29", "American opportunity credit from Form 8863, line 8", L["29"])
    pdf.line("31", "Amount from Schedule 3, line 15", L["31"])
    pdf.line("32", "Add lines 27, 28, 29, and 31. These are your total other payments and refundable credits", L["32"], size=7)
    pdf.line("33", "Add lines 25d, 26, and 32. These are your total payments", L["33"], show_zero=True, bold=True)
    pdf.y -= 3
    pdf.text(LEFT, pdf.y + 2, "Refund", 8, bold=True)
    pdf.y -= 10
    pdf.line("34", "If line 33 is more than line 24, subtract line 24 from line 33. This is the amount you overpaid",
             L["34"], size=6.8)
    pdf.line("35a", "Amount of line 34 you want refunded to you", L["35a"])
    pdf.line("36", f"Amount of line 34 you want applied to your {year + 1} estimated tax", L["36"])
    pdf.text(LEFT, pdf.y + 2, "Amount You Owe", 8, bold=True)
    pdf.y -= 10
    pdf.line("37", "Subtract line 33 from line 24. This is the amount you owe", L["37"], bold=True)
    pdf.line("38", "Estimated tax penalty (see instructions)", L["38"])
    pdf.y -= 6
    pdf.hline(pdf.y, width=1)
    pdf.y -= 12
    pdf.text(LEFT, pdf.y, "Sign Here", 8, bold=True)
    pdf.text(LEFT + 70, pdf.y, "Under penalties of perjury, I declare that I have examined this return and accompanying schedules "
             "and statements ... (signature not reproduced on sample)", 6)
    pdf.y -= 14
    pdf.text(LEFT + 70, pdf.y, "Your occupation:", 6.5)
    pdf.text(LEFT + 130, pdf.y, ctx.t.get("occupation", ""), 8)
    if s:
        pdf.text(LEFT + 300, pdf.y, "Spouse’s occupation:", 6.5)
        pdf.text(LEFT + 375, pdf.y, s.get("occupation", ""), 8)
    pdf.y -= 14
    pdf.hline(pdf.y + 6)
    prep = ctx.preparer
    pdf.text(LEFT, pdf.y - 2, "Paid Preparer Use Only", 7.5, bold=True)
    pdf.text(LEFT + 110, pdf.y - 2, f"Preparer: {prep['name']}   PTIN {prep['ptin']}   Firm: {prep['firm']}   "
             f"Firm EIN {prep['ein']}   Phone {prep['phone']}", 6.5)


# ---------------------------------------------------------------------
def sched_page(pdf, ctx, form, title, seq):
    pdf.new_page()
    pdf.form_header(form, title, ctx.year, extra=f"Attach to Form 1040.   Attachment Sequence No. {seq}")
    pdf.names_row(ctx.names, ctx.t["ssn"])


def draw_sch1(pdf, ctx, p, f):
    s = f["Sch 1"]
    sched_page(pdf, ctx, "SCHEDULE 1", "Additional Income and Adjustments to Income", "01")
    pdf.section("Part I    Additional Income")
    pdf.line("1", "Taxable refunds, credits, or offsets of state and local income taxes", 0)
    pdf.line("2a", "Alimony received", 0)
    pdf.line("3", "Business income or (loss). Attach Schedule C", s["3"])
    pdf.line("4", "Other gains or (losses). Attach Form 4797", 0)
    pdf.line("5", "Rental real estate, royalties, partnerships, S corporations, trusts, etc. Attach Schedule E", s["5"], size=7)
    pdf.line("6", "Farm income or (loss). Attach Schedule F", 0)
    pdf.line("7", "Unemployment compensation", s["7"])
    pdf.line("8z", "Other income", 0)
    pdf.line("9", "Total other income. Add lines 8a through 8z", 0)
    pdf.line("10", "Combine lines 1 through 7 and 9. This is your additional income. Enter here and on Form 1040, line 8",
             s["10"], show_zero=True, size=6.6)
    pdf.section("Part II    Adjustments to Income")
    pdf.line("11", "Educator expenses", 0)
    pdf.line("13", "Health savings account deduction. Attach Form 8889", s["13"])
    pdf.line("15", "Deductible part of self-employment tax. Attach Schedule SE", s["15"])
    pdf.line("16", "Self-employed SEP, SIMPLE, and qualified plans", s["16"])
    pdf.line("17", "Self-employed health insurance deduction", 0)
    pdf.line("20", "IRA deduction", s["20"])
    pdf.line("21", "Student loan interest deduction", 0)
    pdf.line("26", "Add lines 11 through 23 and 25. These are your adjustments to income. Enter here and on Form 1040, line 10",
             s["26"], show_zero=True, size=6.4)


def draw_sch1a(pdf, ctx, p, f):
    a = f["Sch 1-A"]
    sched_page(pdf, ctx, "SCHEDULE 1-A", "Additional Deductions", "1A")
    pdf.text(LEFT, pdf.y, "Parts II–IV (no tax on tips, no tax on overtime, car loan interest): not applicable for this return.", 7)
    pdf.y -= 16
    pdf.section("Part V    Enhanced Deduction for Seniors")
    pdf.text(LEFT, pdf.y, f"Number of individuals on this return born before January 2, 1961: {a['n']}", 7.5)
    pdf.y -= 14
    pdf.line("34", "Modified adjusted gross income (Form 1040, line 11b)", a["34"], show_zero=True)
    pdf.line("35", "Enter $150,000 if married filing jointly; otherwise $75,000", a["35"], show_zero=True)
    pdf.line("36", "Subtract line 35 from line 34. If zero or less, enter -0-", a["36"], show_zero=True)
    pdf.line("37", "Multiply line 36 by 6% (0.06); deduction is $6,000 per qualifying individual less this amount", a["37"],
             show_zero=True, size=7)
    pdf.line("38", "Total additional deductions. Enter here and on Form 1040, line 13b", a["38"], show_zero=True, bold=True)


def draw_sch2(pdf, ctx, p, f):
    s = f["Sch 2"]
    sched_page(pdf, ctx, "SCHEDULE 2", "Additional Taxes", "02")
    pdf.section("Part I    Tax")
    pdf.line("1z", "Additions to tax (excess advance premium tax credit, etc.)", 0)
    pdf.line("2", "Alternative minimum tax. Attach Form 6251", s["2"])
    pdf.line("3", "Add lines 1z and 2. Enter here and on Form 1040, line 17", s["3"], show_zero=True)
    pdf.section("Part II    Other Taxes")
    pdf.line("4", "Self-employment tax. Attach Schedule SE", s["4"])
    pdf.line("8", "Additional tax on IRAs or other tax-favored accounts. Attach Form 5329", s["8"])
    pdf.line("11", "Additional Medicare Tax. Attach Form 8959", 0)
    pdf.line("12", "Net investment income tax. Attach Form 8960", s["12"])
    pdf.line("21", "Add lines 4, 7 through 16, and 18. These are your total other taxes. Enter on Form 1040, line 23",
             s["21"], show_zero=True, size=6.8)


def draw_scha(pdf, ctx, p, f):
    a, it = f["Sch A"], p["itemized"]
    sched_page(pdf, ctx, "SCHEDULE A", "Itemized Deductions", "07")
    pdf.section("Medical and Dental Expenses")
    pdf.line("4", "Medical and dental expenses after 7.5% of AGI limit", 0)
    pdf.section("Taxes You Paid")
    pdf.line("5a", "State and local income taxes or general sales taxes", a["5a"])
    pdf.line("5b", "State and local real estate taxes", a["5b"])
    pdf.line("5c", "State and local personal property taxes", 0)
    pdf.line("5d", "Add lines 5a through 5c", a["5d"])
    pdf.line("5e", "Enter the smaller of line 5d or the SALT limit (limit reduced for MAGI over $500,000)", a["5e"], size=7)
    pdf.line("7", "Add lines 5e and 6", a["7"])
    pdf.section("Interest You Paid")
    pdf.line("8a", f"Home mortgage interest and points reported on Form 1098 ({it.get('lender', '')})", a["8a"], size=7)
    pdf.line("8e", "Add lines 8a through 8c", a["8e"])
    pdf.line("10", "Add lines 8e and 9", a["10"])
    pdf.section("Gifts to Charity")
    pdf.line("11", "Gifts by cash or check", a["11"])
    pdf.line("12", "Other than by cash or check", a["12"])
    pdf.line("14", "Add lines 11 through 13", a["14"])
    pdf.section("Total Itemized Deductions")
    pdf.line("17", "Add the amounts in the far right column for lines 4 through 16. Also enter on Form 1040, line 12",
             a["17"], bold=True, size=6.8)


def draw_schb(pdf, ctx, p, f):
    b = f["Sch B"]
    sched_page(pdf, ctx, "SCHEDULE B", "Interest and Ordinary Dividends", "08")
    pdf.section("Part I    Interest")
    pdf.text(LEFT, pdf.y, "1   List name of payer", 7.5, bold=True)
    pdf.y -= 13
    for payer, amt in p.get("interest", []):
        pdf.line("1", payer, amt, indent=10)
    pdf.line("2", "Add the amounts on line 1", b["2"], show_zero=True)
    pdf.line("4", "Subtract line 3 from line 2. Enter the result here and on Form 1040, line 2b", b["4"], show_zero=True)
    pdf.section("Part II    Ordinary Dividends")
    pdf.text(LEFT, pdf.y, "5   List name of payer", 7.5, bold=True)
    pdf.y -= 13
    for d in p.get("dividends", []):
        pdf.line("5", d[0], d[1], indent=10)
    pdf.line("6", "Add the amounts on line 5. Enter the total here and on Form 1040, line 3b", b["6"], show_zero=True)
    pdf.section("Part III    Foreign Accounts and Trusts")
    pdf.text(LEFT, pdf.y, "7a  At any time during the year, did you have a financial interest in or signature authority over a "
             "financial account located in a foreign country?", 6.8)
    pdf.checkbox(RIGHT - 60, pdf.y, False, "Yes", 6.5)
    pdf.checkbox(RIGHT - 28, pdf.y, True, "No", 6.5)
    pdf.y -= 13


def draw_schc(pdf, ctx, p, f):
    c, sc = f["Sch C"], p["sch_c"]
    sched_page(pdf, ctx, "SCHEDULE C", "Profit or Loss From Business (Sole Proprietorship)", "09")
    owner = ctx.person(sc.get("who", "t"))
    pdf.text(LEFT, pdf.y, f"Name of proprietor: {owner['first']} {owner['last']}    SSN: {owner['ssn']}", 8)
    pdf.y -= 12
    pdf.text(LEFT, pdf.y, f"A  Principal business or profession: {sc['activity']}", 8)
    pdf.text(LEFT + 330, pdf.y, f"B  Code: {sc['naics']}", 8)
    pdf.y -= 12
    pdf.text(LEFT, pdf.y, f"C  Business name: {sc['name']}", 8)
    pdf.text(LEFT + 330, pdf.y, f"D  EIN: {ctx.ein(sc['name'])}", 8)
    pdf.y -= 12
    pdf.text(LEFT, pdf.y, "F  Accounting method: (1) [X] Cash    G  Did you materially participate? [X] Yes", 8)
    pdf.y -= 16
    pdf.section("Part I    Income")
    pdf.line("1", "Gross receipts or sales", c["1"])
    pdf.line("7", "Gross income. Add lines 5 and 6", c["7"])
    pdf.section("Part II    Expenses")
    for line in ["8", "9", "13", "15", "17", "18", "20b", "22", "23", "25", "26", "27a"]:
        if line in c:
            pdf.line(line, EXP_LABELS[line], c[line])
    pdf.line("28", "Total expenses before expenses for business use of home. Add lines 8 through 27b", c["28"], show_zero=True)
    pdf.line("29", "Tentative profit or (loss). Subtract line 28 from line 7", c["29"], show_zero=True)
    pdf.line("31", "Net profit or (loss). Subtract line 30 from line 29. Enter on Schedule 1, line 3 and Schedule SE, line 2",
             c["31"], show_zero=True, bold=True, size=6.5)


def draw_schd(pdf, ctx, p, f):
    d = f["Sch D"]
    sched_page(pdf, ctx, "SCHEDULE D", "Capital Gains and Losses", "12")

    def row(num, label, proceeds, cost, adj, gain):
        pdf.need(14)
        y = pdf.y
        pdf.text(LEFT, y, num, 7.5, bold=True)
        pdf.text(LEFT + 24, y, label, 6.8)
        for x, v in zip([300, 370, 440, 510], [proceeds, cost, adj, gain]):
            pdf.c.rect(x, y - 3, 66, 12)
            pdf.text(x + 63, y, money(v), 8, align="right")
        pdf.y -= 13

    def heads():
        for x, h in zip([300, 370, 440, 510], ["(d) Proceeds", "(e) Cost", "(g) Adjustments", "(h) Gain or (loss)"]):
            pdf.text(x + 2, pdf.y, h, 6, bold=True)
        pdf.y -= 11

    pdf.section("Part I    Short-Term Capital Gains and Losses — Generally Assets Held One Year or Less")
    heads()
    row("1a", "Short-term totals from Form 1099-B (basis reported to IRS)",
        d.get("1a_proceeds"), d.get("1a_cost"), None, d.get("1a_gain"))
    pdf.line("7", "Net short-term capital gain or (loss). Combine lines 1a through 6 in column (h)", d["7"], show_zero=True)
    pdf.section("Part II    Long-Term Capital Gains and Losses — Generally Assets Held More Than One Year")
    heads()
    row("8a", "Long-term totals from Form 1099-B (basis reported to IRS)",
        d.get("8a_proceeds"), d.get("8a_cost"), None, d.get("8a_gain"))
    row("10", "Long-term totals from Form(s) 8949, Box F checked",
        d.get("10_proceeds"), d.get("10_cost"), d.get("10_adj"), d.get("10_gain"))
    pdf.line("13", "Capital gain distributions", d["13"])
    pdf.line("15", "Net long-term capital gain or (loss). Combine lines 8a through 14 in column (h)", d["15"], show_zero=True)
    pdf.section("Part III    Summary")
    pdf.line("16", "Combine lines 7 and 15 and enter the result. Also enter on Form 1040, line 7", d["16"], show_zero=True, bold=True)


def draw_sche(pdf, ctx, p, f):
    e = f["Sch E"]
    rentals, k1 = p.get("rentals", []), p.get("k1")
    sched_page(pdf, ctx, "SCHEDULE E", "Supplemental Income and Loss", "13")
    cols = [330, 410, 490]

    def prop_block(props, rents, letters):
        pdf.section("Part I    Income or Loss From Rental Real Estate and Royalties")
        for letter, x in zip(letters, rents):
            pdf.text(LEFT, pdf.y, f"1a  Physical address of property {letter}: {x['address']}", 7.5)
            pdf.text(LEFT + 400, pdf.y, "1b Type: 1 (Single/Multi-family)", 6.5)
            pdf.y -= 11
        pdf.text(LEFT + 24, pdf.y, "Properties:", 7, bold=True)
        for letter, x in zip(letters, cols):
            pdf.text(x + 35, pdf.y, letter, 8, bold=True, align="center")
        pdf.y -= 12
        for line in ["3", "9", "12", "14", "16", "17", "18", "20", "21"]:
            vals = [pr.get(line) for pr in props]
            if line in ("9", "12", "14", "16", "17") and not any(vals):
                continue
            pdf.need(14)
            pdf.text(LEFT, pdf.y, line, 7.5, bold=True)
            pdf.text(LEFT + 24, pdf.y, RENT_LABELS[line], 6.8)
            for x, v in zip(cols, vals):
                pdf.c.rect(x, pdf.y - 3, 76, 12)
                pdf.text(x + 73, pdf.y, money(v, show_zero=line in ("20", "21")), 8, align="right")
            pdf.y -= 13

    if rentals:
        prop_block(e["props"][:3], rentals[:3], "ABC"[:len(rentals[:3])])
        pdf.y -= 4
        pdf.line("23a", "Total of all amounts reported on line 3 for all rental properties", e["23a"])
        pdf.line("23c", "Total of all amounts reported on line 12 for all properties", e["23c"])
        pdf.line("23d", "Total of all amounts reported on line 18 for all properties", e["23d"])
        pdf.line("23e", "Total of all amounts reported on line 20 for all properties", e["23e"])
        pdf.line("24", "Income. Add positive amounts shown on line 21", e["24"])
        pdf.line("25", "Losses. Add royalty losses from line 21 and rental real estate losses", e["25"])
        pdf.line("26", "Total rental real estate and royalty income or (loss). Combine lines 24 and 25", e["26"], show_zero=True)
    if k1:
        pdf.section("Part II    Income or Loss From Partnerships and S Corporations")
        pdf.text(LEFT, pdf.y, "28  (a) Name", 6.5, bold=True)
        pdf.text(LEFT + 230, pdf.y, "(b) P/S", 6.5, bold=True)
        pdf.text(LEFT + 270, pdf.y, "(d) EIN", 6.5, bold=True)
        pdf.text(LEFT + 340, pdf.y, "(k) Nonpassive income from Schedule K-1", 6.5, bold=True)
        pdf.y -= 11
        pdf.text(LEFT + 6, pdf.y, "A  " + k1["corp"], 8)
        pdf.text(LEFT + 236, pdf.y, "S", 8)
        pdf.text(LEFT + 270, pdf.y, ctx.ein(k1["corp"]), 8)
        pdf.text(RIGHT - 3, pdf.y, money(k1["ordinary"]), 8.5, align="right")
        pdf.y -= 14
        pdf.line("29a", "Totals (nonpassive income)", e["29a"])
        pdf.line("30", "Add columns (h) and (k) of line 29a", e["30"])
        pdf.line("32", "Total partnership and S corporation income or (loss). Combine lines 30 and 31", e["32"], show_zero=True)
    pdf.section("Part V    Summary")
    pdf.line("41", "Total income or (loss). Combine lines 26, 32, 37, and 39. Enter on Schedule 1, line 5", e["41"],
             show_zero=True, bold=True)
    if len(rentals) > 3:
        sched_page(pdf, ctx, "SCHEDULE E", "Supplemental Income and Loss (continuation — additional properties)", "13")
        extra = e["props"][3:]
        prop_block(extra, rentals[3:], "ABC"[:len(extra)])
        pdf.text(LEFT, pdf.y - 4, "Totals for these properties are included on lines 23a–26 of the first Schedule E.", 7)
        pdf.y -= 14


def draw_schse(pdf, ctx, p, f):
    s = f["Sch SE"]
    sched_page(pdf, ctx, "SCHEDULE SE", "Self-Employment Tax", "17")
    owner = ctx.person(p["sch_c"].get("who", "t"))
    pdf.text(LEFT, pdf.y, f"Name of person with self-employment income: {owner['first']} {owner['last']}   SSN {owner['ssn']}", 8)
    pdf.y -= 16
    pdf.section("Part I    Self-Employment Tax")
    pdf.line("2", "Net profit or (loss) from Schedule C, line 31", s["2"])
    pdf.line("3", "Combine lines 1a, 1b, and 2", s["3"])
    pdf.line("4a", "If line 3 is more than zero, multiply line 3 by 92.35% (0.9235)", s["4a"])
    pdf.line("4c", "Combine lines 4a and 4b", s["4c"])
    pdf.line("6", "Add lines 4c and 5b", s["6"])
    pdf.line("7", "Maximum amount of combined wages and self-employment earnings subject to social security tax", s["7"], size=7)
    pdf.line("8a", "Total social security wages and tips (from Form(s) W-2)", s["8a"])
    pdf.line("9", "Subtract line 8d from line 7. If zero or less, enter -0-", s["9"], show_zero=True)
    pdf.line("10", "Multiply the smaller of line 6 or line 9 by 12.4% (0.124)", s["10"], show_zero=True)
    pdf.line("11", "Multiply line 6 by 2.9% (0.029)", s["11"])
    pdf.line("12", "Self-employment tax. Add lines 10 and 11. Enter here and on Schedule 2, line 4", s["12"], bold=True)
    pdf.line("13", "Deduction for one-half of self-employment tax. Multiply line 12 by 50%. Enter on Schedule 1, line 15",
             s["13"], size=6.8)


def draw_8949(pdf, ctx, p, f):
    e = f["8949"]
    sched_page(pdf, ctx, "Form 8949", "Sales and Other Dispositions of Capital Assets", "12A")
    pdf.section("Part II    Long-Term. Transactions involving capital assets you held more than 1 year")
    pdf.checkbox(LEFT, pdf.y, False, "(D) reported on 1099-B, basis reported", 6.5)
    pdf.checkbox(LEFT + 170, pdf.y, False, "(E) basis not reported", 6.5)
    pdf.checkbox(LEFT + 270, pdf.y, True, "(F) Long-term transactions not reported to you on Form 1099-B", 6.5)
    pdf.y -= 16
    heads = ["(a) Description of property", "(b) Acquired", "(c) Sold", "(d) Proceeds", "(e) Cost or basis",
             "(f) Code", "(g) Adjustment", "(h) Gain or (loss)"]
    xs = [LEFT, 238, 284, 330, 392, 452, 476, 530]
    for x, h in zip(xs, heads):
        pdf.text(x, pdf.y, h, 5.6, bold=True)
    pdf.y -= 12
    for r in e["rows"]:
        desc = r["desc"] if len(r["desc"]) < 48 else r["desc"][:47] + "…"
        pdf.text(xs[0], pdf.y, desc, 6.6)
        pdf.text(xs[1], pdf.y, r["acq"], 6.6)
        pdf.text(xs[2], pdf.y, r["sold"], 6.6)
        pdf.text(xs[3] + 58, pdf.y, money(r["proceeds"]), 7, align="right")
        pdf.text(xs[4] + 56, pdf.y, money(r["cost"]), 7, align="right")
        pdf.text(xs[5] + 4, pdf.y, r["code"], 7)
        pdf.text(xs[6] + 50, pdf.y, money(r["adj"]), 7, align="right")
        pdf.text(RIGHT, pdf.y, money(r["gain"], True), 7, align="right")
        pdf.hline(pdf.y - 3, width=0.3)
        pdf.y -= 12
    pdf.y -= 2
    pdf.text(LEFT, pdf.y, "2  Totals. Add the amounts in columns (d), (e), (g), and (h). Enter on Schedule D, line 10", 6.8, bold=True)
    pdf.text(xs[3] + 58, pdf.y - 11, money(e["2_proceeds"]), 7.5, align="right")
    pdf.text(xs[4] + 56, pdf.y - 11, money(e["2_cost"]), 7.5, align="right")
    pdf.text(xs[6] + 50, pdf.y - 11, money(e["2_adj"]), 7.5, align="right")
    pdf.text(RIGHT, pdf.y - 11, money(e["2_gain"], True), 7.5, align="right", bold=True)
    pdf.y -= 26
    if any(r["code"] == "H" for r in e["rows"]):
        pdf.text(LEFT, pdf.y, "Code H: sale of main home — section 121 exclusion ($500,000 married filing jointly) entered "
                 "as a negative adjustment in column (g).", 6.8)
        pdf.y -= 12


def draw_8960(pdf, ctx, p, f):
    n = f["8960"]
    sched_page(pdf, ctx, "Form 8960", "Net Investment Income Tax—Individuals, Estates, and Trusts", "72")
    pdf.section("Part I    Investment Income")
    pdf.line("1", "Taxable interest (see instructions)", n["1"])
    pdf.line("2", "Ordinary dividends (see instructions)", n["2"])
    pdf.line("4a", "Rental real estate, royalties, partnerships, S corporations, trusts, etc.", n["4a"])
    pdf.line("4c", "Combine lines 4a and 4b", n["4c"])
    pdf.line("5a", "Net gain or loss from disposition of property", n["5a"])
    pdf.line("5b", "Net gain or loss from disposition of property that is not subject to net investment income tax", n["5b"], size=7)
    pdf.line("5d", "Combine lines 5a through 5c", n["5d"])
    pdf.line("8", "Total investment income. Combine lines 1, 2, 3, 4c, 5d, 6, and 7", n["8"], show_zero=True)
    pdf.section("Part II    Investment Expenses Allocable to Investment Income and Modifications")
    pdf.line("11", "Total deductions and modifications", 0)
    pdf.section("Part III    Tax Computation")
    pdf.line("12", "Net investment income. Subtract Part II, line 11, from Part I, line 8", n["12"], show_zero=True)
    pdf.line("13", "Modified adjusted gross income (see instructions)", n["13"], show_zero=True)
    pdf.line("14", "Threshold based on filing status (see instructions)", n["14"], show_zero=True)
    pdf.line("15", "Subtract line 14 from line 13. If zero or less, enter -0-", n["15"], show_zero=True)
    pdf.line("16", "Enter the smaller of line 12 or line 15", n["16"], show_zero=True)
    pdf.line("17", "Net investment income tax for individuals. Multiply line 16 by 3.8% (0.038). Enter on Schedule 2, line 12",
             n["17"], bold=True, size=6.8)


def draw_6251(pdf, ctx, p, f):
    a = f["6251"]
    sched_page(pdf, ctx, "Form 6251", "Alternative Minimum Tax—Individuals", "32")
    pdf.section("Part I    Alternative Minimum Taxable Income (See instructions for how to complete each line.)")
    pdf.line("1", "Enter the amount from Form 1040, line 15, if more than zero", a["1"], show_zero=True)
    pdf.line("2a", "If filing Schedule A, enter the taxes from Schedule A, line 7", a["2a"])
    pdf.line("2i", "Exercise of incentive stock options (excess of AMT income over regular tax income)", a["2i"])
    pdf.line("4", "Alternative minimum taxable income. Combine lines 1 through 3", a["4"], show_zero=True)
    pdf.section("Part II    Alternative Minimum Tax (AMT)")
    pdf.line("5", "Exemption (see instructions for phase-out)", a["5"], show_zero=True)
    pdf.line("6", "Subtract line 5 from line 4. If zero or less, enter -0-", a["6"], show_zero=True)
    pdf.line("7", "Tentative minimum tax computation (Part III used: capital gains / qualified dividends)", a["7"], show_zero=True)
    pdf.line("9", "Tentative minimum tax. Subtract line 8 from line 7", a["9"], show_zero=True)
    pdf.line("10", "Regular tax (Form 1040, line 16) minus foreign tax credit", a["10"], show_zero=True)
    pdf.line("11", "AMT. Subtract line 10 from line 9. If zero or less, enter -0-. Enter on Schedule 2, line 2", a["11"],
             show_zero=True, bold=True)


def draw_5329(pdf, ctx, p, f):
    a = f["5329"]
    who = next(d["who"] for d in p.get("ira_dist", []) + p.get("pension", []) if d["code"] == "1")
    person = ctx.person(who)
    sched_page(pdf, ctx, "Form 5329", "Additional Taxes on Qualified Plans (Including IRAs) and Other Tax-Favored Accounts", "29")
    pdf.text(LEFT, pdf.y, f"Filed for: {person['first']} {person['last']}   SSN {person['ssn']}", 8)
    pdf.y -= 16
    pdf.section("Part I    Additional Tax on Early Distributions")
    pdf.line("1", "Early distributions includible in income (see instructions)", a["1"])
    pdf.line("2", "Early distributions included on line 1 that are not subject to the additional tax", a["2"], show_zero=True)
    pdf.line("3", "Amount subject to additional tax. Subtract line 2 from line 1", a["3"])
    pdf.line("4", "Additional tax. Enter 10% (0.10) of line 3. Include this amount on Schedule 2, line 8", a["4"], bold=True)


def draw_8606(pdf, ctx, p, f):
    for who, amt in f["8606"].items():
        person = ctx.person(who)
        sched_page(pdf, ctx, "Form 8606", "Nondeductible IRAs", "48")
        pdf.text(LEFT, pdf.y, f"Name if married, file a separate form for each spouse: {person['first']} {person['last']}   "
                 f"SSN {person['ssn']}", 8)
        pdf.y -= 16
        pdf.section("Part I    Nondeductible Contributions to Traditional IRAs and Distributions From Traditional IRAs")
        for line, lbl, v in [("1", "Nondeductible contributions to traditional IRAs for the year", amt),
                             ("2", "Total basis in traditional IRAs (prior years)", 0),
                             ("3", "Add lines 1 and 2", amt),
                             ("5", "Subtract line 4 from line 3", amt),
                             ("6", "Value of all traditional, SEP, and SIMPLE IRAs as of December 31", 0),
                             ("8", "Net amount converted from traditional IRAs to Roth IRAs during the year", amt),
                             ("9", "Add lines 6, 7, and 8", amt),
                             ("10", "Divide line 5 by line 9 (decimal)", None),
                             ("11", "Multiply line 8 by line 10. This is the nontaxable portion of the conversion", amt),
                             ("13", "Add lines 11 and 12. This is the nontaxable portion of all distributions", amt),
                             ("14", "Subtract line 13 from line 3. This is your total basis in traditional IRAs", 0)]:
            if line == "10":
                pdf.line(line, lbl, None, note="1.000")
            else:
                pdf.line(line, lbl, v, show_zero=True)
        pdf.section("Part II    Conversions From Traditional, SEP, or SIMPLE IRAs to Roth IRAs")
        pdf.line("16", "Amount converted to Roth IRAs", amt)
        pdf.line("17", "Enter the amount from line 11 (basis in conversion)", amt)
        pdf.line("18", "Taxable amount. Subtract line 17 from line 16. Include on Form 1040, line 4b", 0, show_zero=True, bold=True)


def draw_8889(pdf, ctx, p, f):
    h = f["8889"]
    person = ctx.person(h["who"])
    sched_page(pdf, ctx, "Form 8889", "Health Savings Accounts (HSAs)", "52")
    pdf.text(LEFT, pdf.y, f"Name of HSA beneficiary: {person['first']} {person['last']}   SSN {person['ssn']}", 8)
    pdf.y -= 16
    pdf.section("Part I    HSA Contributions and Deduction")
    pdf.text(LEFT, pdf.y, "1   Coverage under a high-deductible health plan (HDHP) during the year:", 7.5)
    pdf.checkbox(LEFT + 300, pdf.y, False, "Self-only", 7)
    pdf.checkbox(LEFT + 360, pdf.y, True, "Family", 7)
    pdf.y -= 13
    pdf.line("2", "HSA contributions you made for the year (do not include employer contributions)", h["2"], show_zero=True)
    pdf.line("3", "Contribution limit (family coverage)", h["3"])
    pdf.line("6", "Line 3 after spouse allocation", h["6"])
    pdf.line("8", "Add lines 6 and 7", h["8"])
    pdf.line("9", "Employer contributions made to your HSAs (Form W-2, box 12, code W)", h["9"])
    pdf.line("11", "Add lines 9 and 10", h["11"])
    pdf.line("12", "Subtract line 11 from line 8. If zero or less, enter -0-", h["12"], show_zero=True)
    pdf.line("13", "HSA deduction. Enter the smaller of line 2 or line 12. Enter on Schedule 1, line 13", h["13"],
             show_zero=True, bold=True)
    pdf.section("Part II    HSA Distributions")
    pdf.line("14a", "Total distributions you received in the year from all HSAs (Form 1099-SA)", 0, show_zero=True)


def draw_8995(pdf, ctx, p, f):
    q = f["8995"]
    sched_page(pdf, ctx, "Form 8995", "Qualified Business Income Deduction Simplified Computation", "55")
    pdf.text(LEFT, pdf.y, "1   (a) Trade, business, or aggregation name", 7, bold=True)
    pdf.text(LEFT + 260, pdf.y, "(b) Taxpayer identification number", 7, bold=True)
    pdf.text(RIGHT, pdf.y, "(c) Qualified business income", 7, bold=True, align="right")
    pdf.y -= 12
    items = []
    if p.get("sch_c"):
        items.append((p["sch_c"]["name"], q["2"] - (p["k1"]["ordinary"] if p.get("k1") else 0)))
    if p.get("k1"):
        items.append((p["k1"]["corp"], p["k1"]["ordinary"]))
    for i, (name, amt) in enumerate(items):
        pdf.text(LEFT + 6, pdf.y, f"{'iii'[:i + 1]}  {name}", 8)
        pdf.text(LEFT + 260, pdf.y, ctx.ein(name), 8)
        pdf.text(RIGHT - 3, pdf.y, money(amt), 8.5, align="right")
        pdf.y -= 12
    pdf.y -= 2
    pdf.line("2", "Total qualified business income or (loss). Combine lines 1i through 1v, column (c)", q["2"])
    pdf.line("4", "Total qualified business income. Combine lines 2 and 3", q["4"])
    pdf.line("5", "Qualified business income component. Multiply line 4 by 20% (0.20)", q["5"])
    pdf.line("10", "Qualified business income deduction before the income limitation. Add lines 5 and 9", q["10"])
    pdf.line("11", "Taxable income before qualified business income deduction", q["11"])
    pdf.line("12", "Enter your net capital gain, if any, increased by any qualified dividends", q["12"], show_zero=True)
    pdf.line("13", "Subtract line 12 from line 11. If zero or less, enter -0-", q["13"], show_zero=True)
    pdf.line("14", "Income limitation. Multiply line 13 by 20% (0.20)", q["14"], show_zero=True)
    pdf.line("15", "Qualified business income deduction. Enter the smaller of line 10 or line 14. Also enter on Form 1040, line 13a"
             if ctx.year == 2025 else
             "Qualified business income deduction. Enter the smaller of line 10 or line 14. Also enter on Form 1040, line 13",
             q["15"], bold=True, size=6.6)


DRAWERS = {"Sch 1": draw_sch1, "Sch 1-A": draw_sch1a, "Sch 2": draw_sch2, "Sch A": draw_scha, "Sch B": draw_schb,
           "Sch C": draw_schc, "Sch D": draw_schd, "Sch E": draw_sche, "Sch SE": draw_schse, "8949": draw_8949,
           "8960": draw_8960, "6251": draw_6251, "5329": draw_5329, "8606": draw_8606, "8889": draw_8889,
           "8995": draw_8995}
