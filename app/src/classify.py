"""Decide what each page is (1040 page, which schedule, which information return).

Matching is on normalized text (lowercase letters and digits only) so it
tolerates OCR noise in spacing and punctuation.

- 1040-family pages (the 1040 and its schedules/forms) are identified from the
  title area at the top of the page, because their titles also appear as
  references inside other forms (e.g. 1040 line 12 says "itemized deductions").
- Information returns (W-2, 1099s, ...) are identified from anywhere on the page.
- If nothing matches, the file name is used as a hint.
"""
import re
from collections import Counter


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


TITLE_KINDS = [  # matched against the top ~13% of the page; first match wins
    ("1040 p2",  ["form1040202", "page2"]),                 # all keys must match for this one
    ("1040",     ["individualincometaxreturn"]),
    ("Sch 1-A",  ["additionaldeductions"]),
    ("Sch 1",    ["additionalincomeandadjustments"]),
    ("5329",     ["additionaltaxesonqualifiedplans"]),
    ("Sch 2",    ["additionaltaxes"]),
    ("Sch A",    ["itemizeddeductions"]),
    ("Sch B",    ["interestandordinarydividends"]),
    ("Sch C",    ["profitorlossfrombusiness"]),
    ("Sch D",    ["capitalgainsandlosses"]),
    ("Sch E",    ["supplementalincomeandloss"]),
    ("Sch SE",   ["selfemploymenttax"]),
    ("8949",     ["salesandotherdispositions"]),
    ("8960",     ["netinvestmentincometax"]),
    ("6251",     ["alternativeminimumtax"]),
    ("8606",     ["nondeductibleiras"]),
    ("8889",     ["healthsavingsaccounts"]),
    ("8995",     ["qualifiedbusinessincomededuction"]),
]
ALL_KEYS = {"1040 p2"}

BODY_KINDS = [  # matched against the whole page
    ("profile",  ["clientprofilesummary", "clientinformationsheet"]),
    ("K-1",      ["shareholdersshareofincome", "schedulek1form1120s"]),
    ("W-2",      ["wageandtaxstatement"]),
    ("SSA-1099", ["socialsecuritybenefitstatement", "formssa1099"]),
    ("1099-R",   ["form1099r", "distributionsfrompensions"]),
    ("1099-INT", ["form1099int"]),
    ("1099-DIV", ["form1099div"]),
    ("1099-B",   ["form1099b", "proceedsfrombroker"]),
    ("1099-G",   ["form1099g"]),
    ("1099-NEC", ["form1099nec", "nonemployeecompensation"]),
    ("1099-K",   ["form1099k", "thirdpartynetwork"]),
    ("1099-S",   ["form1099s", "realestatetransactions"]),
    ("3921",     ["form3921", "incentivestockoption"]),
    ("1098",     ["form1098", "mortgageintereststatement"]),
]

FILENAME_HINTS = [("W-2", "w2"), ("1099-R", "1099r"), ("1099-INT", "1099int"), ("1099-DIV", "1099div"),
                  ("1099-B", "1099b"), ("1099-G", "1099g"), ("1099-S", "1099s"), ("1099-NEC", "1099nec"),
                  ("1099-K", "1099k"), ("SSA-1099", "ssa1099"), ("K-1", "k1"), ("3921", "3921"), ("1098", "1098"),
                  ("profile", "profile")]

SOURCE_KINDS = {"W-2", "SSA-1099", "1099-R", "1099-INT", "1099-DIV", "1099-B", "1099-G", "1099-S", "1099-NEC",
                "1099-K", "K-1", "3921", "1098", "1099-CONSOL"}
RETURN_KINDS = {k for k, _ in TITLE_KINDS}


def classify_page(page, filename=""):
    body = norm(page.text)
    if "clientprofilesummary" in body or "clientinformationsheet" in body:
        return "profile"
    top_text = " ".join(w.text for w in page.words if w.top < page.height * 0.13)
    top = norm(top_text)
    # State returns (e.g. Missouri MO-1040) share federal wording; skip them.
    if "departmentofrevenue" in top or "departmentofrevenue" in body[:600]:
        return "state"
    # Continuation pages of schedules: "Schedule D (Form 1040) 2025 ... Page 2"
    m = re.match(r"\s*Schedule\s+(1-A|SE|[123ABCDE])\s*\(Form 1040\)", top_text, re.I)
    if m:
        kind = f"Sch {m.group(1).upper()}"
        return kind if kind in RETURN_KINDS else "unknown"
    for kind, keys in TITLE_KINDS:
        hit = all(k in top for k in keys) if kind in ALL_KEYS else any(k in top for k in keys)
        if kind == "1040 p2" and not re.match(r"\s*Form\s+1040\s*\(", top_text):
            hit = False                  # e.g. "Schedule 8812 (Form 1040) 2025 ... Page 2"
        if hit:
            return kind
    # Brokerage "consolidated 1099" summary: DIV, INT and B in one table
    if "consolidated" in body and ("form1099taxreportingstatement" in body or "consolidatedform1099" in body):
        return "1099-CONSOL"
    for kind, keys in BODY_KINDS:
        if any(k in body for k in keys):
            return kind
    if "taxandcredits" in body or "thisisyourtotaltax" in body:
        return "1040 p2"
    f = norm(filename)
    for kind, key in FILENAME_HINTS:
        if key in f:
            return kind
    return "unknown"


def page_year(page):
    """Tax year printed in the page's title area (most common 2019-2030 token there)."""
    years = Counter()
    for w in page.words:
        if w.top < page.height * 0.13:
            for y in re.findall(r"(20[12]\d)", w.text):
                years[int(y)] += 1
    return max(years.items(), key=lambda kv: (kv[1], kv[0]))[0] if years else None


def doc_year(pages):
    """Year for an information return.

    An explicit "Tax Year 2025" / "calendar year 2025" wins. Otherwise the most common
    standalone year, ignoring form revision dates such as "(Rev. January 2024)".
    """
    text = " ".join(w.text for p in pages for w in p.words)
    m = re.search(r"(?:tax\s*year|calendar\s*year)\s*(20[12]\d)", text, re.I)
    if m:
        return int(m.group(1))
    years = Counter()
    for p in pages:
        ws = p.words
        for i, w in enumerate(ws):
            m = re.fullmatch(r"\(?(20[12]\d)\)?", w.text)
            if m and not any("rev" in x.text.lower() for x in ws[max(0, i - 3):i]):
                years[int(m.group(1))] += 1
    return max(years.items(), key=lambda kv: (kv[1], kv[0]))[0] if years else None
