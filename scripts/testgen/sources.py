"""Information returns (W-2, 1099s, SSA-1099, K-1, 3921, 1098) and the client profile page.

Each function writes one PDF containing one document. Layouts follow the real
forms' box numbering closely enough for an extractor to key on box labels.
"""
from draw import Pdf, LEFT, RIGHT, W, money

COPY_B = "Copy B\nFor Recipient"


def _title_block(pdf, x, y, w, form, title, year, copy=COPY_B, omb="OMB No. 1545-0000"):
    pdf.cell(x, y, w, 30, "", "")
    pdf.text(x + 4, y - 12, omb, 6)
    pdf.text(x + 4, y - 25, str(year), 13, bold=True)
    pdf.text(x + 4, y - 44, f"Form {form}", 10, bold=True)
    lines = title.split("\n")
    for i, ln in enumerate(lines):
        pdf.text(x + 4, y - 58 - i * 10, ln, 8.5, bold=True)
    cy = y - 58 - len(lines) * 10 - 8
    for i, ln in enumerate(copy.split("\n")):
        pdf.text(x + 4, cy - i * 8, ln, 6.8, bold=i == 0)


def info_return(path, form, title, year, payer_label, payer_lines, payer_tin, recip_label, recip_name, recip_tin,
                recip_addr, rows, account="", copy=COPY_B, note=""):
    """Generic 1099-style layout.

    rows: list of rows; each row is a list of (label, value) cells laid out across the box grid.
    """
    pdf = Pdf(path, f"{year} Form {form} — {recip_name} (fictional)")
    pdf.new_page()
    top = 742
    pdf.text(LEFT, top + 8, "CORRECTED (if checked)  [  ]", 7)
    lx, lw = LEFT, 236
    gx, gw = LEFT + lw, 196
    tx, tw = gx + gw, RIGHT - gx - gw
    pdf.multiline_cell(lx, top, lw, 74, payer_label, payer_lines)
    pdf.cell(lx, top - 74, lw / 2, 26, "PAYER’S TIN" if "PAYER" in payer_label else "FILER’S TIN", payer_tin)
    pdf.cell(lx + lw / 2, top - 74, lw / 2, 26, "RECIPIENT’S TIN", recip_tin)
    pdf.cell(lx, top - 100, lw, 26, recip_label, recip_name)
    street, cityline = recip_addr
    pdf.cell(lx, top - 126, lw, 26, "Street address (including apt. no.)", street)
    pdf.cell(lx, top - 152, lw, 26, "City or town, state or province, country, and ZIP or foreign postal code", cityline)
    pdf.cell(lx, top - 178, lw, 24, "Account number (see instructions)", account)
    _title_block(pdf, tx, top, tw, form, title, year, copy)
    y = top
    for row in rows:
        h = 30
        cw = gw / len(row)
        for i, (label, value) in enumerate(row):
            pdf.cell(gx + i * cw, y, cw, h, label, value, align="right", vsize=9)
        y -= h
    bottom = min(y, top - 202)
    pdf.text(LEFT, bottom - 14, f"Form {form}  (keep for your records)        www.irs.gov/Form{form.replace('-', '')}"
             "        Department of the Treasury — Internal Revenue Service", 6.5)
    if note:
        pdf.text(LEFT, bottom - 30, note, 7.5)
    pdf.save()


def _addr(person_addr):
    street, city, zip_ = person_addr
    return street, f"{city}, MN {zip_}"


# ---------------------------------------------------------------------
def w2_pdf(path, year, w, emp, ein, address, emp_addr):
    from tax_engine import SS_WAGE_BASE
    box3 = min(w["wages"] + w.get("k401", 0), SS_WAGE_BASE[year])
    box5 = w["wages"] + w.get("k401", 0)
    box4 = round(box3 * 0.062, 2)
    box6 = round(box5 * 0.0145 + max(0, box5 - 200000) * 0.009, 2)
    state_wh = round(w["wages"] * 0.0545)
    codes = [("D", w["k401"])] if w.get("k401") else []
    if w.get("hsa"):
        codes.append(("W", w["hsa"]))

    pdf = Pdf(path, f"{year} Form W-2 — {emp['first']} {emp['last']} (fictional)")
    pdf.new_page()
    top, L, M, Rr = 742, LEFT, LEFT + 270, RIGHT
    half = (Rr - M) / 2
    pdf.cell(L, top, 270, 24, "a  Employee’s social security number", emp["ssn"], vsize=10)
    pdf.cell(M, top, Rr - M, 24, "OMB No. 1545-0029", "")
    pdf.text(M + 110, top - 16, "Safe, accurate, FAST! Use e-file", 7, bold=True)
    y = top - 24
    pdf.cell(L, y, 270, 24, "b  Employer identification number (EIN)", ein)
    pdf.multiline_cell(L, y - 24, 270, 56, "c  Employer’s name, address, and ZIP code",
                       [w["employer"], emp_addr[0], emp_addr[1]])
    pdf.cell(L, y - 80, 270, 22, "d  Control number", "")
    pdf.cell(L, y - 102, 270, 26, "e  Employee’s first name and initial      Last name      Suff.",
             f"{emp['first']} {emp['last']}")
    street, cityline = _addr(address)
    pdf.multiline_cell(L, y - 128, 270, 46, "f  Employee’s address and ZIP code", [street, cityline])
    right = [
        (("1  Wages, tips, other compensation", money(w["wages"])), ("2  Federal income tax withheld", money(w.get("fed_wh", 0), True))),
        (("3  Social security wages", money(box3)), ("4  Social security tax withheld", f"{box4:,.2f}")),
        (("5  Medicare wages and tips", money(box5)), ("6  Medicare tax withheld", f"{box6:,.2f}")),
        (("7  Social security tips", ""), ("8  Allocated tips", "")),
        (("9", ""), ("10  Dependent care benefits", "")),
        (("11  Nonqualified plans", ""), ("12a  See instructions for box 12", "")),
        (("13", ""), ("12b", "")),
        (("14  Other", ""), ("12c", "")),
        (("", ""), ("12d", "")),
    ]
    ry = y
    for (l1, v1), (l2, v2) in right:
        pdf.cell(M, ry, half, 19.5, l1, v1, align="right", vsize=8.5)
        pdf.cell(M + half, ry, half, 19.5, l2, v2, align="right", vsize=8.5)
        ry -= 19.5
    # box 12 codes
    for i, (code, amt) in enumerate(codes[:4]):
        cy = y - 5 * 19.5 - i * 19.5
        pdf.text(M + half + 50, cy - 15, f"{code}", 9, bold=True)
        pdf.text(M + half + 64, cy - 15, "|", 9)
        pdf.text(Rr - 4, cy - 15, money(amt), 8.5, align="right")
    # box 13 checkboxes
    by = y - 6 * 19.5 - 15
    pdf.checkbox(M + 14, by + 4, False, "", 6)
    pdf.checkbox(M + 54, by + 4, w.get("ret_plan", False), "", 6)
    pdf.checkbox(M + 98, by + 4, False, "", 6)
    pdf.text(M + 4, by - 4, "Statutory employee   Retirement plan   Third-party sick pay", 4.8)
    # state row
    sy = y - 9 * 19.5 - 8
    cols = [("15  State", "MN", 40), ("Employer’s state ID number", f"0000{ein[-4:]}", 110),
            ("16  State wages, tips, etc.", money(w["wages"]), 100), ("17  State income tax", money(state_wh), 90),
            ("18  Local wages, tips, etc.", "", 80), ("19  Local income tax", "", 60), ("20  Locality name", "", 60)]
    x = L
    for lbl, val, cw in cols:
        cw = cw * (Rr - L) / 540
        pdf.cell(x, sy, cw, 26, lbl, val, align="right" if val and val != "MN" else "left", vsize=8.5)
        x += cw
    pdf.text(L, sy - 42, "Form", 7)
    pdf.text(L + 22, sy - 44, "W-2", 18, bold=True)
    pdf.text(L + 70, sy - 42, "Wage and Tax Statement", 11, bold=True)
    pdf.text(L + 330, sy - 42, str(year), 18, bold=True)
    pdf.text(Rr, sy - 38, "Department of the Treasury—Internal Revenue Service", 6.5, align="right")
    pdf.text(L, sy - 58, "Copy B—To Be Filed With Employee’s FEDERAL Tax Return.", 7.5, bold=True)
    pdf.text(L, sy - 68, "This information is being furnished to the Internal Revenue Service.", 6.5)
    pdf.save()


def int_1099(path, year, payer, ein, payer_addr, recip, recip_tin, address, amount, acct):
    rows = [[("1  Interest income", money(amount, True))],
            [("2  Early withdrawal penalty", ""), ("3  Interest on U.S. Savings Bonds\nand Treasury obligations", "")],
            [("4  Federal income tax withheld", ""), ("5  Investment expenses", "")],
            [("6  Foreign tax paid", ""), ("7  Foreign country", "")],
            [("8  Tax-exempt interest", ""), ("9  Specified private activity\nbond interest", "")]]
    info_return(path, "1099-INT", "Interest\nIncome", year, "PAYER’S name, street address, city or town, state, ZIP, and telephone no.",
                [payer, *payer_addr], ein, "RECIPIENT’S name", recip, recip_tin, _addr(address), rows, acct)


def div_1099(path, year, payer, ein, payer_addr, recip, recip_tin, address, ordinary, qual, capdist, acct):
    rows = [[("1a  Total ordinary dividends", money(ordinary, True))],
            [("1b  Qualified dividends", money(qual, True))],
            [("2a  Total capital gain distr.", money(capdist)), ("2b  Unrecap. Sec. 1250 gain", "")],
            [("3  Nondividend distributions", ""), ("4  Federal income tax withheld", "")],
            [("5  Section 199A dividends", ""), ("6  Investment expenses", "")],
            [("7  Foreign tax paid", ""), ("8  Foreign country", "")]]
    info_return(path, "1099-DIV", "Dividends and\nDistributions", year,
                "PAYER’S name, street address, city or town, state, ZIP, and telephone no.",
                [payer, *payer_addr], ein, "RECIPIENT’S name", recip, recip_tin, _addr(address), rows, acct)


def r_1099(path, year, d, payer_addr, ein, recip, recip_tin, address, acct):
    total = d["code"] in ("7", "G", "4", "1") and d["gross"] == d["box2a"]
    rows = [[("1  Gross distribution", money(d["gross"], True))],
            [("2a  Taxable amount", money(d["box2a"], True))],
            [("2b  Taxable amount\nnot determined  [ ]", ""), ("Total\ndistribution  [" + ("X" if total else " ") + "]", "")],
            [("3  Capital gain (included\nin box 2a)", ""), ("4  Federal income tax\nwithheld", money(d.get("wh", 0), True))],
            [("5  Employee contributions/\nDesignated Roth contrib.", ""), ("6  Net unrealized\nappreciation", "")],
            [("7  Distribution\ncode(s)", d["code"]), ("IRA/\nSEP/\nSIMPLE   [" + ("X" if d.get("ira") else " ") + "]", "")],
            [("14  State tax withheld", ""), ("15  State/Payer’s state no.", "MN")]]
    note = f"Plan / account description: {d['plan']}" if d.get("plan") else ""
    info_return(path, "1099-R", "Distributions From\nPensions, Annuities,\nRetirement or\nProfit-Sharing Plans,\nIRAs, etc.",
                year, "PAYER’S name, street address, city or town, state, ZIP, and telephone no.",
                [d["payer"], *payer_addr], ein, "RECIPIENT’S name", recip, recip_tin, _addr(address), rows, acct,
                copy="Copy B\nReport this income\non your federal\ntax return.", note=note)


def g_1099(path, year, payer, ein, payer_addr, recip, recip_tin, address, amount, wh):
    rows = [[("1  Unemployment compensation", money(amount, True))],
            [("2  State or local income tax refunds,\ncredits, or offsets", "")],
            [("3  Box 2 amount is for tax year", ""), ("4  Federal income tax withheld", money(wh, True))],
            [("5  RTAA payments", ""), ("6  Taxable grants", "")],
            [("10a  State", "MN"), ("11  State income tax withheld", "")]]
    info_return(path, "1099-G", "Certain\nGovernment\nPayments", year,
                "PAYER’S name, street address, city or town, state, ZIP, and telephone no.",
                [payer, *payer_addr], ein, "RECIPIENT’S name", recip, recip_tin, _addr(address), rows)


def s_1099(path, year, hs, filer, ein, filer_addr, recip, recip_tin, address):
    rows = [[("1  Date of closing", hs["sold"])],
            [("2  Gross proceeds", money(hs["price"], True))],
            [("3  Address (including city, state, and ZIP code) or legal description", "")],
            [("4  Transferor received or will receive\nproperty or services  [ ]", ""),
             ("5  Transferor is a foreign\nperson  [ ]", "")],
            [("6  Buyer’s part of real estate tax", "")]]
    info_return(path, "1099-S", "Proceeds From\nReal Estate\nTransactions", year,
                "FILER’S name, street address, city or town, state, ZIP, and telephone no.",
                [filer, *filer_addr], ein, "TRANSFEROR’S name", recip, recip_tin, _addr(address), rows,
                note=f"Box 3 property: {hs['address']}")


def nec_1099(path, year, payer, ein, payer_addr, recip, recip_tin, address, amount):
    rows = [[("1  Nonemployee compensation", money(amount, True))],
            [("2  Payer made direct sales totaling $5,000 or more\nof consumer products to recipient for resale  [ ]", "")],
            [("3  Excess golden parachute payments", "")],
            [("4  Federal income tax withheld", "")],
            [("5  State tax withheld", ""), ("6  State/Payer’s state no.", "MN")]]
    info_return(path, "1099-NEC", "Nonemployee\nCompensation", year,
                "PAYER’S name, street address, city or town, state, ZIP, and telephone no.",
                [payer, *payer_addr], ein, "RECIPIENT’S name", recip, recip_tin, _addr(address), rows)


def k_1099(path, year, payer, ein, payer_addr, recip, recip_tin, address, amount):
    rows = [[("1a  Gross amount of payment card/\nthird party network transactions", money(amount, True))],
            [("1b  Card Not Present transactions", ""), ("2  Merchant category code", "4215")],
            [("3  Number of payment transactions", "1,962"), ("4  Federal income tax withheld", "")],
            [("5a  January – 5l December", "see statement")]]
    info_return(path, "1099-K", "Payment Card and\nThird Party\nNetwork\nTransactions", year,
                "FILER’S name, street address, city or town, state, ZIP, and telephone no.",
                [payer, *payer_addr], ein, "PAYEE’S name", recip, recip_tin, _addr(address), rows)


def b_1099(path, year, b, ein, payer_addr, recip, recip_tin, address, acct):
    pdf = Pdf(path, f"{year} Form 1099-B summary — {recip} (fictional)")
    pdf.new_page()
    pdf.text(LEFT, pdf.y, b["broker"], 13, bold=True)
    pdf.text(RIGHT, pdf.y, f"{year} Composite Tax Statement", 11, bold=True, align="right")
    pdf.y -= 14
    for ln in payer_addr:
        pdf.text(LEFT, pdf.y, ln, 8)
        pdf.y -= 10
    pdf.text(LEFT, pdf.y, f"PAYER’S TIN: {ein}", 8)
    pdf.y -= 18
    pdf.text(LEFT, pdf.y, f"RECIPIENT: {recip}", 9, bold=True)
    pdf.text(LEFT + 320, pdf.y, f"RECIPIENT’S TIN: {recip_tin}", 9)
    pdf.y -= 11
    street, cityline = _addr(address)
    pdf.text(LEFT, pdf.y, f"{street}, {cityline}", 8)
    pdf.text(LEFT + 320, pdf.y, f"Account number: {acct}", 8)
    pdf.y -= 22
    pdf.section("Form 1099-B  Proceeds From Broker and Barter Exchange Transactions — Summary of Gains and Losses")
    xs = [LEFT, 230, 310, 390, 470]
    for x, h in zip(xs, ["Term / Form 8949 box", "1d Proceeds", "1e Cost or other basis", "1g Wash sale loss disallowed",
                         "Realized gain or (loss)"]):
        pdf.text(x, pdf.y, h, 6.8, bold=True)
    pdf.y -= 13
    rows = []
    if b.get("st"):
        rows.append(("Short-term — Box A (basis reported to IRS)", b["st_basis"] + b["st"], b["st_basis"], b["st"]))
    if b.get("lt"):
        rows.append(("Long-term — Box D (basis reported to IRS)", b["lt_basis"] + b["lt"], b["lt_basis"], b["lt"]))
    for name, proc, cost, gain in rows:
        pdf.text(xs[0], pdf.y, name, 7.5)
        pdf.text(xs[1] + 70, pdf.y, money(proc, True), 8.5, align="right")
        pdf.text(xs[2] + 70, pdf.y, money(cost, True), 8.5, align="right")
        pdf.text(xs[3] + 70, pdf.y, "0", 8.5, align="right")
        pdf.text(RIGHT, pdf.y, money(gain, True), 8.5, align="right")
        pdf.hline(pdf.y - 3, width=0.3)
        pdf.y -= 13
    tot = [sum(r[i] for r in rows) for i in (1, 2, 3)]
    pdf.text(xs[0], pdf.y, "Total", 8, bold=True)
    pdf.text(xs[1] + 70, pdf.y, money(tot[0], True), 8.5, align="right", bold=True)
    pdf.text(xs[2] + 70, pdf.y, money(tot[1], True), 8.5, align="right", bold=True)
    pdf.text(RIGHT, pdf.y, money(tot[2], True), 8.5, align="right", bold=True)
    pdf.y -= 22
    pdf.text(LEFT, pdf.y, "Box 4 Federal income tax withheld: 0        Box 2 Type of gain or loss: shown by term above", 7.5)
    pdf.y -= 12
    pdf.text(LEFT, pdf.y, "Detail of individual transactions is available in the full statement (not reproduced in sample).", 7)
    pdf.save()


def ssa_1099(path, year, person, address, amount, wh):
    pdf = Pdf(path, f"{year} Form SSA-1099 — {person['first']} {person['last']} (fictional)")
    pdf.new_page()
    top = 742
    pdf.text(LEFT, top, f"FORM SSA-1099 — SOCIAL SECURITY BENEFIT STATEMENT", 11, bold=True)
    pdf.text(RIGHT, top, str(year), 14, bold=True, align="right")
    pdf.text(LEFT, top - 12, "PART OF YOUR SOCIAL SECURITY BENEFITS SHOWN IN BOX 5 MAY BE TAXABLE INCOME.", 7)
    y = top - 22
    pdf.cell(LEFT, y, 300, 26, "Box 1. Name", f"{person['first']} {person['last']}")
    pdf.cell(LEFT + 300, y, RIGHT - LEFT - 300, 26, "Box 2. Beneficiary’s Social Security Number", person["ssn"])
    y -= 26
    pdf.cell(LEFT, y, 180, 30, f"Box 3. Benefits Paid in {year}", money(amount, True), align="right")
    pdf.cell(LEFT + 180, y, 180, 30, f"Box 4. Benefits Repaid to SSA in {year}", "NONE", align="right")
    pdf.cell(LEFT + 360, y, RIGHT - LEFT - 360, 30, f"Box 5. Net Benefits for {year} (Box 3 minus Box 4)",
             money(amount, True), align="right")
    y -= 30
    desc = [f"Paid by check or direct deposit           {money(amount, True)}",
            f"Total Additions                                  {money(amount, True)}"]
    pdf.multiline_cell(LEFT, y, 360, 56, "DESCRIPTION OF AMOUNT IN BOX 3", desc)
    pdf.multiline_cell(LEFT + 360, y, RIGHT - LEFT - 360, 56, "DESCRIPTION OF AMOUNT IN BOX 4", ["NONE"])
    y -= 56
    pdf.cell(LEFT, y, 360, 26, "Box 6. Voluntary Federal Income Tax Withheld", money(wh, True), align="right")
    pdf.cell(LEFT + 360, y, RIGHT - LEFT - 360, 26, "Box 8. Claim Number (Use this number if you need to contact SSA)",
             person["ssn"] + "A")
    y -= 26
    street, cityline = _addr(address)
    pdf.multiline_cell(LEFT, y, 360, 44, "Box 7. Address", [street, cityline])
    y -= 60
    pdf.text(LEFT, y, "DO NOT RETURN THIS FORM TO SSA OR IRS.  Form SSA-1099-SM", 7)
    pdf.save()


def k1_1120s(path, year, k1, corp_ein, corp_addr, person, address):
    pdf = Pdf(path, f"{year} Schedule K-1 (Form 1120-S) — {person['first']} {person['last']} (fictional)")
    pdf.new_page()
    top = 742
    pdf.checkbox(LEFT + 300, top, k1.get("final"), "Final K-1", 8)
    pdf.checkbox(LEFT + 370, top, False, "Amended K-1", 8)
    pdf.text(RIGHT, top, "671121  OMB No. 1545-0123", 7, align="right")
    pdf.text(LEFT, top - 14, "Schedule K-1", 13, bold=True)
    pdf.text(LEFT, top - 26, "(Form 1120-S)", 8)
    pdf.text(LEFT + 120, top - 18, f"{year}", 16, bold=True)
    pdf.text(LEFT, top - 40, "Shareholder’s Share of Income, Deductions, Credits, etc.", 9, bold=True)
    y = top - 52
    lw = 260
    pdf.text(LEFT, y, "Part I   Information About the Corporation", 8, bold=True)
    pdf.cell(LEFT, y - 6, lw, 24, "A  Corporation’s employer identification number", corp_ein)
    pdf.multiline_cell(LEFT, y - 30, lw, 50, "B  Corporation’s name, address, city, state, and ZIP code",
                       [k1["corp"], *corp_addr])
    pdf.cell(LEFT, y - 80, lw, 22, "C  IRS Center where corporation filed return", "Kansas City, MO")
    pdf.cell(LEFT, y - 102, lw, 22, "D  Corporation’s total number of shares", "1,000")
    pdf.text(LEFT, y - 136, "Part II   Information About the Shareholder", 8, bold=True)
    pdf.cell(LEFT, y - 142, lw, 24, "E  Shareholder’s identifying number", person["ssn"])
    street, cityline = _addr(address)
    pdf.multiline_cell(LEFT, y - 166, lw, 50, "F1  Shareholder’s name, address, city, state, and ZIP code",
                       [f"{person['first']} {person['last']}", street, cityline])
    pdf.cell(LEFT, y - 216, lw, 24, "G  Current year allocation percentage", f"{k1['pct']:.4f} %")
    rx, rw = LEFT + lw + 10, RIGHT - LEFT - lw - 10
    pdf.text(rx, y, "Part III   Shareholder’s Share of Current Year Income, Deductions, Credits, etc.", 7, bold=True)
    boxes = [("1  Ordinary business income (loss)", money(k1["ordinary"], True)),
             ("2  Net rental real estate income (loss)", ""),
             ("4  Interest income", ""),
             ("5a  Ordinary dividends", ""),
             ("7  Net short-term capital gain (loss)", ""),
             ("8a  Net long-term capital gain (loss)", ""),
             ("16  Items affecting shareholder basis", f"D  {money(k1.get('distributions', 0), True)}"),
             ("17  Other information", f"V*  STMT (QBI: {money(k1['ordinary'], True)})")]
    by = y - 6
    for lbl, val in boxes:
        pdf.cell(rx, by, rw, 26, lbl, val, align="right")
        by -= 26
    pdf.text(rx, by - 12, "* See attached statement for additional information.", 6.5)
    pdf.save()


def f3921(path, year, iso, corp_ein, corp_addr, person, address):
    spread = (iso["fmv"] - iso["price"]) * iso["shares"]
    rows = [[("1  Date option granted", iso["granted"])],
            [("2  Date option exercised", iso["exercised"])],
            [("3  Exercise price per share", f"$ {iso['price']:.2f}"), ("4  Fair market value per share\non exercise date",
                                                                         f"$ {iso['fmv']:.2f}")],
            [("5  No. of shares transferred", f"{iso['shares']:,}")],
            [("6  If other than TRANSFEROR, name, address, and EIN of corporation whose stock is being transferred", "")]]
    info_return(path, "3921", "Exercise of an\nIncentive Stock\nOption Under\nSection 422(b)", year,
                "TRANSFEROR’S name, street address, city or town, state, ZIP, and telephone no.",
                [iso["company"], *corp_addr], corp_ein, "EMPLOYEE’S name", f"{person['first']} {person['last']}",
                person["ssn"], _addr(address), rows, copy="Copy B\nFor Employee",
                note=f"Spread at exercise (box 4 − box 3) × box 5 = ${spread:,.0f}  (AMT adjustment; not on Form W-2)")


def f1098(path, year, it, lender_ein, lender_addr, recip, recip_tin, address):
    rows = [[("1  Mortgage interest received from payer(s)/borrower(s)", money(it["mortgage"], True))],
            [("2  Outstanding mortgage principal", money(it["principal"], True)),
             ("3  Mortgage origination date", "07/09/2018")],
            [("4  Refund of overpaid interest", ""), ("5  Mortgage insurance premiums", "")],
            [("6  Points paid on purchase of\nprincipal residence", ""), ("7  Address of property same as\npayer’s address  [X]", "")],
            [("10  Other (real estate taxes paid from escrow)", money(it["property_tax"], True))]]
    info_return(path, "1098", "Mortgage\nInterest\nStatement", year,
                "RECIPIENT’S/LENDER’S name, street address, city or town, state, ZIP, and telephone no.",
                [it["lender"], *lender_addr], lender_ein, "PAYER’S/BORROWER’S name", recip, recip_tin,
                _addr(address), rows, copy="Copy B\nFor Payer/Borrower")


# ---------------------------------------------------------------------
def profile_pdf(path, client, people, deps, status, contact, docs):
    status_name = {"single": "Single", "mfj": "Married filing jointly", "hoh": "Head of household"}[status]
    t, s = people["t"], people.get("s")
    pdf = Pdf(path, f"Client Profile Summary — {client['id']} (fictional)")
    pdf.new_page()
    pdf.text(LEFT, pdf.y, "Client Profile Summary", 16, bold=True)
    pdf.text(RIGHT, pdf.y, f"Client ID: {client['id']}", 11, bold=True, align="right")
    pdf.y -= 14
    pdf.text(LEFT, pdf.y, "Exported from practice-management system (Canopy) — Tax year 2025", 8)
    pdf.y -= 11
    pdf.text(LEFT, pdf.y, "Record type: FICTIONAL TEST CLIENT (synthetic data; no IRC §7216 consent applies)", 8, bold=True)
    pdf.y -= 20

    def kv(k, v, x=LEFT, w=140):
        pdf.text(x, pdf.y, k, 8, bold=True)
        pdf.text(x + w, pdf.y, v, 9)

    pdf.section("Household")
    kv("Filing status (2025)", status_name)
    pdf.y -= 16
    for label, p in [("Primary taxpayer", t), ("Spouse", s)]:
        if not p:
            continue
        name = (p.get("title", "") + " " + f"{p['first']} {p['last']}").strip()
        kv(label, name)
        pdf.y -= 12
        kv("    Date of birth", f"{p['dob'][5:7]}/{p['dob'][8:10]}/{p['dob'][:4]}   (age {2025 - int(p['dob'][:4])} at 12/31/2025)")
        pdf.y -= 12
        kv("    SSN", p["ssn"])
        pdf.y -= 12
        kv("    Occupation", p.get("occupation", ""))
        pdf.y -= 16
    pdf.section("Dependents")
    if deps:
        xs = [LEFT, LEFT + 170, LEFT + 260, LEFT + 350, LEFT + 430]
        for x, h in zip(xs, ["Name", "Relationship", "Date of birth", "Age 12/31/2025", "SSN"]):
            pdf.text(x, pdf.y, h, 8, bold=True)
        pdf.y -= 12
        for d in deps:
            vals = [f"{d['first']} {d['last']}", d["rel"], f"{d['dob'][5:7]}/{d['dob'][8:10]}/{d['dob'][:4]}",
                    str(2025 - int(d["dob"][:4])), d["ssn"]]
            for x, v in zip(xs, vals):
                pdf.text(x, pdf.y, v, 9)
            pdf.y -= 12
    else:
        pdf.text(LEFT, pdf.y, "None", 9)
        pdf.y -= 12
    pdf.y -= 6
    pdf.section("Contact")
    street, city, zip_ = client["address"]
    kv("Address", f"{street}, {city}, MN {zip_}")
    pdf.y -= 12
    kv("Phone", contact["phone"])
    pdf.y -= 12
    kv("Email", contact["email"])
    pdf.y -= 18
    pdf.section("Documents on file")
    for name, desc in docs:
        pdf.need(12)
        pdf.text(LEFT, pdf.y, "• " + name, 8)
        pdf.text(LEFT + 300, pdf.y, desc, 8)
        pdf.y -= 11
    pdf.save()
