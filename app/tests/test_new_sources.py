"""Farm and small-business papers: 1099-PATR, 1099-MISC, the USDA 1099-G, Schedule F, a profit and loss
statement and a bill of sale. Fixtures are drawn here (fictional), in the test generator's layouts."""
import shutil
import sys

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from src import extract as ex
from src import paths
from src.classify import classify_page
from src.grader import grade_client, load_config
from src.ingest import Page, read_pdf
from tests.harness import CACHE, CLIENTS

sys.path.insert(0, str(paths.APP / "scripts" / "testgen"))
from draw import Pdf  # noqa: E402
from sources import info_return  # noqa: E402

PAYER = "PAYER’S name, street address, city or town, state, ZIP, and telephone no."
RECIP = ("18420 NW County Road 210", "Trenton, MN 64683")
TIN = "000-00-1111"


def patr_pdf(path, year=2025):
    rows = [[("1  Patronage dividends", "3,126.44"), ("7  Qualified payments", "3,126.44")],
            [("2  Nonpatronage distributions", ""), ("8  Investment credit", "")],
            [("3  Per-unit retain allocations", ""), ("9  Work opportunity credit", "")],
            [("4  Federal income tax withheld", ""), ("10  Patron’s AMT adjustment", "")],
            [("5  Redemption of nonqualified notices and retain allocations", "1,410.00"),
             ("11  Other credits and deductions", "")]]
    info_return(path, "1099-PATR", "Taxable Distributions\nReceived From\nCooperatives", year, PAYER,
                ["Heartland Farmers Cooperative", "310 Elevator Road", "Trenton, MN 64683"], "00-4482106",
                "RECIPIENT’S name", "Delbert W Hutchins", TIN, RECIP, rows, account="HFC-M-2291")


def misc_pdf(path, year=2025):
    rows = [[("1  Rents", "2,400.00"), ("7  Payer made direct sales of $5,000 or more  [ ]", "")],
            [("2  Royalties", ""), ("8  Substitute payments in lieu of dividends or interest", "")],
            [("3  Other income", "500.00"), ("9  Crop insurance proceeds", "14,780.00")],
            [("4  Federal income tax withheld", ""), ("10  Gross proceeds paid to an attorney", "")]]
    info_return(path, "1099-MISC", "Miscellaneous\nInformation", year, PAYER,
                ["Prairie Mutual Crop Insurance Company", "900 Insurance Plaza", "Des Moines, IA 50309"], "00-7721103",
                "RECIPIENT’S name", "Delbert W Hutchins", TIN, RECIP, rows)


def usda_g_pdf(path, year=2025):
    rows = [[("1  Unemployment compensation", ""), ("6  Taxable grants", "")],
            [("2  State or local income tax refunds", ""), ("7  Agriculture payments", "6,840.00")],
            [("3  Box 2 amount is for tax year", ""), ("8  If checked, box 2 is trade or business income  [ ]", "")],
            [("4  Federal income tax withheld", ""), ("9  Market gain", "")]]
    info_return(path, "1099-G", "Certain\nGovernment\nPayments", year, PAYER,
                ["U.S. Dept. of Agriculture - Farm Service Agency", "1320 E 9th Street", "Trenton, MN 64683"],
                "00-6651007", "RECIPIENT’S name", "Delbert W Hutchins", TIN, RECIP, rows)


def schf_pdf(path, year=2025, coop=(0, 0), ag=(6840, 6840), crop=(0, 0)):
    """One Schedule F page. coop/ag/crop are (amount received, taxable amount) pairs."""
    pdf = Pdf(path, f"{year} Schedule F (fictional)")
    pdf.new_page()
    pdf.form_header("SCHEDULE F", "Profit or Loss From Farming", year,
                    extra="Attach to Form 1040.   Attachment Sequence No. 14")
    pdf.names_row("Delbert W and Carol Ann Hutchins", TIN)
    pdf.section("Part I    Farm Income — Cash Method")
    pdf.line("1a", "Sales of purchased livestock and other resale items", 151875)
    pdf.line("1b", "Cost or other basis of purchased livestock or other items reported on line 1a", 0)
    pdf.line("1c", "Subtract line 1b from line 1a", 151875)
    pdf.line("2", "Sales of livestock, produce, grains, and other products you raised", 0)
    pdf.pair("3a", "Cooperative distributions (Form(s) 1099-PATR)", coop[0], "3b", "Taxable amount", coop[1])
    pdf.pair("4a", "Agricultural program payments (see instructions)", ag[0], "4b", "Taxable amount", ag[1])
    pdf.pair("6a", f"Amount received in {year}", crop[0], "6b", "Taxable amount", crop[1])
    pdf.line("7", "Custom hire (machine work) income", 0)
    pdf.line("8", "Other income, including federal and state gasoline or fuel tax credit or refund", 6840)
    pdf.line("9", "Gross income. Add amounts in the right column (lines 1c, 2, 3b, 4b, 5a, 5c, 6b, 6d, 7, and 8)",
             151875 + coop[1] + ag[1] + crop[1] + 6840)
    pdf.section("Part II    Farm Expenses")
    pdf.line("33", "Total expenses. Add lines 10 through 32f", 217803)
    pdf.line("34", "Net farm profit or (loss). Subtract line 33 from line 9",
             151875 + coop[1] + ag[1] + crop[1] + 6840 - 217803, show_zero=True)
    pdf.save()


def _canvas(path):
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle("Sample training document (fictional)")
    return c


def pnl_pdf(path, business="Fire & Smoke Tacos", year=2025, income=148920, cogs=56220, expenses=62712.13):
    c, (w, h) = _canvas(path), letter
    y = h - 60

    def put(label, value=None, x=82, size=9, bold=False, center=False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        (c.drawCentredString(w / 2, y, label) if center else c.drawString(x, y, label))
        if value is not None:
            c.drawRightString(560, y, value)
        y -= 14 if size < 11 else 18

    put(business, size=13, bold=True, center=True)
    put("PROFIT AND LOSS", size=11, bold=True, center=True)
    put(f"January - December {year}", center=True)
    put("TOTAL", x=520, size=8, bold=True)
    net = income - cogs - expenses
    for label, v, bold in [("Income", None, True), ("Food Sales", income - 6310, False), ("Beverage Sales", 6310, False),
                           ("Total Income", income, True), ("Cost of Goods Sold", None, True),
                           ("Food & Ingredients", cogs, False), ("Total Cost of Goods Sold", cogs, True),
                           ("GROSS PROFIT", income - cogs, True), ("Expenses", None, True),
                           ("Commissary Kitchen Rent", 7200, False), ("Truck Fuel", expenses - 7200, False),
                           ("Total Expenses", expenses, True), ("NET OPERATING INCOME", net, True)]:
        put(label, None if v is None else f"{v:,.2f}", x=82 if bold else 96, bold=bold)
    put("NET INCOME", f"${net:,.2f}", bold=True)
    c.setFont("Helvetica", 7)
    c.drawString(200, 40, f"Cash Basis  Tuesday, January 6, {year + 1} 03:41 PM GMT-06:00")
    c.save()


def bill_pdf(path, price=44500, financed=30000, date="March 22, 2025", in_service="April 5, 2025"):
    c, (w, h) = _canvas(path), letter
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w / 2, h - 60, "BILL OF SALE")
    c.setFont("Helvetica", 10)
    c.drawCentredString(w / 2, h - 80, "Motor Vehicle / Equipment — As Is, Where Is")
    y = h - 125
    c.setFont("Helvetica-Bold", 9)
    c.drawString(44, y, "SELLER")
    c.drawString(316, y, "BUYER")
    c.setFont("Helvetica", 9)
    for left, right in [("Desert Ridge Mobile Kitchens, LLC", "Ethan J. Fournier"),
                        ("4410 Commerce Road", "7730 N Prospect Avenue"), ("Dallas, TX 75207", "Gladstone, MO 64118")]:
        y -= 12
        c.drawString(44, y, left)
        c.drawString(316, y, right)
    y -= 40
    c.setFont("Helvetica-Bold", 9)
    c.drawString(44, y, "DESCRIPTION OF PROPERTY")
    c.setFont("Helvetica", 9)
    for line in ["2018 step van, converted mobile kitchen (14 ft)", "VIN: SAMPLE0000000001   Odometer: 71,420 mi",
                 "Equipment included: flat top, fryer, 2 refrigerators, generator"]:
        y -= 12
        c.drawString(44, y, line)
    y -= 30
    c.setFont("Helvetica-Bold", 9)
    c.drawString(42, y, "TERMS OF SALE")
    c.setFont("Helvetica", 9)
    for label, v in [("Purchase price", price), ("Missouri sales tax paid at DMV", 3024.5),
                     ("Title and registration fees", 380), ("Down payment (cash)", price - financed),
                     ("Amount financed — Prairie Equipment Finance", financed)]:
        y -= 17
        c.drawString(44, y, label)
        c.drawRightString(560, y, f"${v:,.2f}")
    y -= 24
    c.setFont("Helvetica", 8)
    c.drawString(36, y, "The seller conveys the above property to the buyer as-is, free of liens.")
    y -= 11
    c.drawString(36, y,
                 f"The buyer acknowledges inspection and acceptance. Truck was placed in service on {in_service}.")
    y -= 40
    c.setFont("Helvetica", 9)
    c.drawString(36, y, "Seller signature: R. Tolliver")
    c.drawString(326, y, "Buyer signature: Ethan Fournier")
    y -= 20
    c.drawString(36, y, f"Date: {date}")
    c.drawString(326, y, f"Date: {date}")
    c.save()


@pytest.fixture(scope="module")
def docs(tmp_path_factory):
    d = tmp_path_factory.mktemp("farm_docs")
    patr_pdf(d / "1099-PATR_Heartland_Coop.pdf")
    misc_pdf(d / "1099-MISC_Crop_Insurance.pdf")
    usda_g_pdf(d / "1099-G_USDA_FSA.pdf")
    schf_pdf(d / "2025_Schedule_F.pdf")
    schf_pdf(d / "2025_Schedule_F_filled.pdf", coop=(4536, 3000), crop=(14780, 14780))
    pnl_pdf(d / "Profit_and_Loss_2025_Fire-and-Smoke-Tacos.pdf")
    bill_pdf(d / "Bill_of_Sale_Food_Truck.pdf")
    return d


def _page(docs, name):
    return read_pdf(docs / name)[0]


def _vals(d):
    return {k: (v.value if hasattr(v, "value") else v) for k, v in d.items()}


# ---------------------------------------------------------------- classification
def test_classify_new_kinds(docs):
    expect = {"1099-PATR_Heartland_Coop.pdf": "1099-PATR", "1099-MISC_Crop_Insurance.pdf": "1099-MISC",
              "1099-G_USDA_FSA.pdf": "1099-G", "2025_Schedule_F.pdf": "Sch F",
              "Profit_and_Loss_2025_Fire-and-Smoke-Tacos.pdf": "P&L", "Bill_of_Sale_Food_Truck.pdf": "Bill of sale"}
    for name, kind in expect.items():
        assert classify_page(_page(docs, name)) == kind, name


def test_filename_hints_for_new_kinds():
    blank = Page("x.pdf", 1, [])
    for name, kind in [("1099-PATR_Coop.pdf", "1099-PATR"), ("1099-MISC_Crop.pdf", "1099-MISC"),
                       ("Profit_and_Loss_2025.pdf", "P&L"), ("PnL_2025.pdf", "P&L"),
                       ("Bill_of_Sale_Truck.pdf", "Bill of sale")]:
        assert classify_page(blank, name) == kind, name


# ---------------------------------------------------------------- information returns
def test_1099_patr_boxes(docs):
    d = _vals(ex.parse_source(_page(docs, "1099-PATR_Heartland_Coop.pdf"), "1099-PATR"))
    assert (d["box1"], d["box2"], d["box3"], d["box4"], d["box5"], d["box7"]) == (3126.44, 0, 0, 0, 1410, 3126.44)
    assert round(d["taxable"], 2) == 4536.44            # boxes 1 + 2 + 3 + 5 -> Schedule F line 3a
    assert d["payer"].startswith("Heartland Farmers Cooperative")
    assert d["ssn"] == TIN


def test_1099_misc_boxes(docs):
    d = _vals(ex.parse_source(_page(docs, "1099-MISC_Crop_Insurance.pdf"), "1099-MISC"))
    assert (d["box1"], d["box2"], d["box3"], d["box4"], d["box9"], d["box10"]) == (2400, 0, 500, 0, 14780, 0)
    assert d["payer"].startswith("Prairie Mutual")


def test_usda_1099_g_box_7(docs):
    d = _vals(ex.parse_source(_page(docs, "1099-G_USDA_FSA.pdf"), "1099-G"))
    assert (d["box1"], d["box4"], d["box7"]) == (0, 0, 6840)


# ---------------------------------------------------------------- Schedule F
def _schf(docs, name):
    page = _page(docs, name)
    out = {}
    ex.parse_lines(page, "Sch F", ex.SCHEDULE_LINES["Sch F"], out)
    ex.parse_pairs(page, out, ex.SCHF_PAIRS, "Sch F")
    return {k: v.value for k, v in out.items()}, out


def test_schedule_f_lines(docs):
    got, facts = _schf(docs, "2025_Schedule_F.pdf")
    assert {k: got[k] for k in ("1c", "2", "3a", "3b", "4a", "4b", "6a", "6b", "7", "9", "33", "34")} == {
        "1c": 151875, "2": 0, "3a": 0, "3b": 0, "4a": 6840, "4b": 6840, "6a": 0, "6b": 0, "7": 0,
        "9": 165555, "33": 217803, "34": -52248}
    assert facts["34"].ref == "Schedule F line 34"


def test_schedule_f_pairs_keep_received_and_taxable_apart(docs):
    got, _ = _schf(docs, "2025_Schedule_F_filled.pdf")
    assert (got["3a"], got["3b"], got["6a"], got["6b"]) == (4536, 3000, 14780, 14780)


# ---------------------------------------------------------------- supporting papers
def test_profit_and_loss(docs):
    d = _vals(ex.parse_pnl(_page(docs, "Profit_and_Loss_2025_Fire-and-Smoke-Tacos.pdf")))
    assert d["business"] == "Fire & Smoke Tacos" and d["year"] == 2025
    assert (d["income"], d["cogs"], d["gross_profit"], d["expenses"]) == (148920, 56220, 92700, 62712.13)
    assert round(d["net"], 2) == 29987.87               # "NET INCOME $29,987.87", not NET OPERATING INCOME


def test_bill_of_sale(docs):
    d = _vals(ex.parse_bill_of_sale(_page(docs, "Bill_of_Sale_Food_Truck.pdf")))
    assert d["description"] == "2018 step van, converted mobile kitchen (14 ft)"
    assert d["seller"] == "Desert Ridge Mobile Kitchens, LLC" and d["buyer"] == "Ethan J. Fournier"
    assert d["date"] == "2025-03-22" and d["in_service"] == "2025-04-05" and d["year"] == 2025
    assert (d["price"], d["sales_tax"], d["down_payment"], d["financed"]) == (44500, 3024.5, 14500, 30000)


# ---------------------------------------------------------------- end to end
def _client(tmp_path, cid):
    """A copy of a fictional sample client (text PDFs, so no OCR), to add documents to."""
    src = next(CLIENTS.glob(f"{cid}_*"))
    dst = tmp_path / cid
    shutil.copytree(src, dst)
    return dst


def test_farm_papers_are_checked_against_schedule_f(tmp_path, docs):
    d = _client(tmp_path, "C01")
    for name in ("1099-PATR_Heartland_Coop.pdf", "1099-MISC_Crop_Insurance.pdf", "1099-G_USDA_FSA.pdf",
                 "2025_Schedule_F.pdf"):
        shutil.copy(docs / name, d)
    r = grade_client(d, load_config(), str(CACHE))
    assert r["status"] == "graded"
    w = "\n".join(r["warnings"])
    assert "not recognized" not in w
    # The preparer left the co-op and crop-insurance money off Schedule F: both get flagged.
    assert "Cooperative distributions (Sch F line 3a): sources disagree" in w and "4,536" in w
    assert "Crop insurance proceeds (Sch F line 6a): sources disagree" in w and "14,780" in w
    # The USDA payment is on line 4a, so no warning for it; rents with no Schedule E are flagged.
    assert "Agricultural program payments" not in w
    assert "1099-MISC rents" in w and "no Schedule E" in w
    assert r["_figs"].get("sch_f_net") == -52248 and r["_figs"].get("ag_payments") == 6840
    kinds = {k for doc in r["documents"] for k in doc["kinds"].split(", ")}
    assert {"1099-PATR", "1099-MISC", "1099-G", "Sch F"} <= kinds
    assert "Schedule F net farm profit" in [f["label"] for f in r["figures"]]
    assert "Farm income (Sch F)" in [s["label"] for s in r["brief"]["snapshot"]]


def test_farm_papers_without_schedule_f(tmp_path, docs):
    d = _client(tmp_path, "C01")
    shutil.copy(docs / "1099-PATR_Heartland_Coop.pdf", d)
    shutil.copy(docs / "1099-MISC_Crop_Insurance.pdf", d)
    w = "\n".join(grade_client(d, load_config(), str(CACHE))["warnings"])
    assert "Cooperative distributions: 1099-PATR" in w and "no Schedule F" in w
    assert "Crop insurance proceeds: 1099-MISC" in w and "no Schedule F" in w


def test_books_and_equipment_purchase_in_brief(tmp_path, docs):
    d = _client(tmp_path, "C05")                        # Schedule C: gross $905,000, net $310,000
    pnl_pdf(d / "Profit_and_Loss_2025.pdf", business="Brightwater Dental PLLC", income=905000, cogs=0, expenses=600000)
    shutil.copy(docs / "Bill_of_Sale_Food_Truck.pdf", d)
    r = grade_client(d, load_config(), str(CACHE))
    w = "\n".join(r["warnings"])
    assert "not recognized" not in w and "Gross receipts" not in w     # P&L sales = Schedule C line 1
    ctx = r["_record"]["years"][2025]["context"]
    assert ctx["pnl"][0]["business"] == "Brightwater Dental PLLC" and ctx["asset_purchases"][0]["price"].value == 44500
    chips = {c["label"]: c for c in r["brief"]["tax_picture"]}
    assert chips["Business books (net income)"]["value"] == "$305,000"
    assert "Schedule C net $310,000" in chips["Business books (net income)"]["sub"]
    assert chips["Equipment purchase"]["value"] == "$44,500"
    assert "March 22, 2025" in chips["Equipment purchase"]["sub"]
    assert "$30,000 financed" in chips["Equipment purchase"]["sub"]
    lines = [c for p in r["brief"]["products"] for t in p["points"] for c in t.get("context", [])]
    assert any("own books" in c for c in lines) and any("Bought 2018 step van" in c for c in lines)


def test_books_that_disagree_with_schedule_c(tmp_path):
    d = _client(tmp_path, "C05")
    pnl_pdf(d / "Profit_and_Loss_2025.pdf", business="Brightwater Dental PLLC", income=900000, cogs=0, expenses=600000)
    w = "\n".join(grade_client(d, load_config(), str(CACHE))["warnings"])
    assert "Gross receipts (Sch C line 1): sources disagree" in w and "905,000" in w and "900,000" in w
