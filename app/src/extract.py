"""Pull structured figures out of classified pages.

Two techniques, both working on positioned words so text PDFs and OCR'd scans
are handled the same way:

1. Numbered form lines (1040 and schedules): each visual row is matched to a
   form line by its printed description (fuzzy, so OCR typos are fine) plus its
   line number; the amount is the number in the right-hand amount column.
2. Boxed information returns (W-2, 1099s, ...): find the box label, then read
   the value printed inside that box (below the label, before the next box).

Every value is stored as a Fact that remembers where it came from, so the
report can show "Form 1040 line 11a = 288,850 (2025_Form_1040_and_Schedules.pdf p1)".
"""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import numpy as np

from .classify import norm
from .ingest import page_image, rows, tesseract

# ---------------------------------------------------------------------
# Facts and parsing helpers
# ---------------------------------------------------------------------


@dataclass
class Fact:
    value: object
    doc: str
    page: int
    ref: str              # e.g. "Form 1040 line 11a", "W-2 box 1"
    note: str = ""        # e.g. "derived: line 9 - line 10"

    def where(self):
        return f"{self.ref} ({self.doc} p{self.page})" if self.doc else self.ref


def fact(page, ref, value, note=""):
    return Fact(value, page.doc, page.number, ref, note)


_JUNK = "|[]{}=~:;'\"`‘’“”$§_�"
AMOUNT_RE = re.compile(r"^(\()?-?(\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,](\d{2}))?(\))?$")
SSN_RE = re.compile(r"\b(\d{3})[-– ]?(\d{2})[-– ]?(\d{4})\b")
DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def amount(tok):
    """Parse a printed dollar amount; OCR-tolerant (1.234 -> 1234). None if not an amount."""
    t = re.sub(r"^[^\w(\-]+|[^\w)]+$", "", tok).strip("_")   # drop OCR junk (|, [, �) around the number
    t = t.replace("O", "0").replace("o", "0") if re.fullmatch(r"[\dOo,.()]+", t) else t
    if re.fullmatch(r"0\d{1,2}", t):
        return 0          # printed amounts never start with 0; "07" is a zero plus a box-border speck
    m = AMOUNT_RE.match(t)
    if not m or bool(m.group(1)) != bool(m.group(4)):
        return None                      # "1040)" from "(Form 1040)" is not an amount
    whole = int(re.sub(r"[.,]", "", m.group(2)))
    val = whole + (int(m.group(3)) / 100 if m.group(3) else 0)
    return -val if (m.group(1) and m.group(4)) or t.startswith("-") else val


def is_year(v):
    return v is not None and float(v).is_integer() and 2019 <= v <= 2030


def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------
# Checkboxes
# ---------------------------------------------------------------------
def box_checked(page, x0, top, x1, bottom):
    """Is the checkbox inside this region (PDF points) checked?

    Text PDFs: an "X" glyph sits inside the box. Scans: look at the pixels -
    find the box outline, then measure ink in its interior.
    """
    if not page.ocr:
        return any(w.text.strip("[]") in ("X", "x") and x0 <= (w.x0 + w.x1) / 2 <= x1
                   and top <= (w.top + w.bottom) / 2 <= bottom for w in page.words)
    img = page_image(page)
    s = page.scale
    a = np.asarray(img)[int(top * s):int(bottom * s), int(x0 * s):int(x1 * s)] < 128
    if a.size == 0 or not a.any():
        return False
    # Find the square's two vertical edges (columns with a long run of ink), so stray
    # glyphs next to the box don't count. Boxes are roughly 5-10 points wide.
    col = a.sum(axis=0)
    edge_cols = np.nonzero(col >= 4 * s)[0]
    groups = np.split(edge_cols, np.nonzero(np.diff(edge_cols) > 1)[0] + 1) if edge_cols.size else []
    centers = [int(g.mean()) for g in groups if g.size]
    pair = None
    for i in range(len(centers) - 1, 0, -1):
        for j in range(i - 1, -1, -1):
            if 4 * s <= centers[i] - centers[j] <= 11 * s:
                pair = (centers[j], centers[i])
                break
        if pair:
            break
    if pair:
        xa, xb = pair
        ys = np.nonzero(a[:, xa])[0]
        y0, y1 = ys.min(), ys.max()
    else:
        ys, xs = np.nonzero(a)
        y0, y1, xa, xb = ys.min(), ys.max(), xs.min(), xs.max()
    h, w = y1 - y0, xb - xa
    if h < 8 or w < 8:
        return False
    inner = a[y0 + int(h * 0.28):y1 - int(h * 0.28) + 1, xa + int(w * 0.28):xb - int(w * 0.28) + 1]
    return bool(inner.size > 0 and inner.mean() > 0.12)


def checked_before(page, word, gap=13):
    """Checkbox immediately to the left of a label word."""
    return box_checked(page, word.x0 - gap, word.top - 3, word.x0 - 0.5, word.bottom + 3)


# ---------------------------------------------------------------------
# Finding labels
# ---------------------------------------------------------------------
def find_phrase(page, phrase, min_ratio=0.82, region=None, nth=0):
    """Locate a printed phrase. Returns (first_word, last_word) or None.

    region = (x0, top, x1, bottom) to restrict the search.
    """
    target = norm(phrase)
    hits = []
    for row in rows(page.words):
        if region:
            row = [w for w in row if region[0] <= w.x0 <= region[2] and region[1] <= w.top <= region[3]]
        for i in range(len(row)):
            first = norm(row[i].text)
            if not first or first[0] != target[0]:
                continue                     # a label must start at its own first word
            acc = ""
            for j in range(i, min(i + 14, len(row))):
                acc += norm(row[j].text)
                if len(acc) >= len(target):
                    r = similar(acc[:len(target)], target)
                    if r >= min_ratio:
                        hits.append((round(r, 2), row[i], row[j]))
                    break
            else:
                # row ended first (OCR may shorten a word): compare what we have
                if len(acc) >= 0.75 * len(target):
                    r = similar(acc, target)
                    if r >= min_ratio:
                        hits.append((round(r, 2), row[i], row[min(i + 13, len(row) - 1)]))
    hits.sort(key=lambda h: (-h[0], h[1].top, h[1].x0))
    return hits[nth][1:] if len(hits) > nth else None


# ---------------------------------------------------------------------
# 1. Numbered form lines
# ---------------------------------------------------------------------
# (line, description) as printed. Only lines the grader uses or validates.
F1040_2025 = [
    ("1a", "Total amount from Form(s) W-2"), ("1z", "Add lines 1a through 1h"),
    ("7", "Capital gain or (loss)"), ("8", "Additional income from Schedule 1"),
    ("9", "Add lines 1z, 2b, 3b, 4b, 5b, 6b, 7, and 8"), ("10", "Adjustments to income from Schedule 1"),
    ("11a", "Subtract line 10 from line 9. This is your adjusted gross income"),
    ("11b", "Amount from line 11a"), ("12", "Standard deduction or itemized deductions"),
    ("13a", "Qualified business income deduction from Form 8995"), ("13b", "Deductions from Schedule 1-A"),
    ("14", "Add lines 12, 13a, and 13b"), ("15", "Subtract line 14 from line 11b"),
    ("16", "Tax (see instructions)"), ("17", "Amount from Schedule 2, line 3"), ("18", "Add lines 16 and 17"),
    ("19", "Child tax credit or credit for other dependents"), ("20", "Amount from Schedule 3, line 8"),
    ("21", "Add lines 19 and 20"), ("22", "Subtract line 21 from line 18"),
    ("23", "Other taxes, including self-employment tax"), ("24", "Add lines 22 and 23. This is your total tax"),
    ("25a", "Federal income tax withheld from: Form(s) W-2"), ("25b", "Form(s) 1099"),
    ("25c", "Other forms (see instructions)"), ("25d", "Add lines 25a through 25c"),
    ("26", "estimated tax payments and amount applied"), ("27", "Earned income credit"),
    ("28", "Additional child tax credit"), ("29", "American opportunity credit"),
    ("31", "Amount from Schedule 3, line 15"), ("32", "Add lines 27, 28, 29, and 31"),
    ("33", "Add lines 25d, 26, and 32. These are your total payments"),
    ("34", "If line 33 is more than line 24"), ("35a", "Amount of line 34 you want refunded"),
    ("36", "Amount of line 34 you want applied"), ("37", "Subtract line 33 from line 24. This is the amount you owe"),
    ("38", "Estimated tax penalty"),
]
F1040_2024 = [x for x in F1040_2025 if x[0] not in ("11a", "11b", "13a", "13b", "14", "15")] + [
    ("11", "Subtract line 10 from line 9. This is your adjusted gross income"),
    ("13", "Qualified business income deduction from Form 8995"), ("14", "Add lines 12 and 13"),
    ("15", "Subtract line 14 from line 11")]
PAGE1_LINES = {"1a", "1z", "7", "8", "9", "10", "11a", "11"}     # the rest are on page 2


def f1040_specs(year, page_kind):
    specs = F1040_2025 if year >= 2025 else F1040_2024
    on_p1 = page_kind == "1040"
    return [s for s in specs if (s[0] in PAGE1_LINES) == on_p1]
PAIRS = [("2a", "Tax-exempt interest", "2b"), ("3a", "Qualified dividends", "3b"), ("4a", "IRA distributions", "4b"),
         ("5a", "Pensions and annuities", "5b"), ("6a", "Social security benefits", "6b")]

SCHEDULE_LINES = {
    "Sch 1": [("3", "Business income or (loss)"), ("5", "Rental real estate, royalties, partnerships"),
              ("7", "Unemployment compensation"), ("10", "Combine lines 1 through 7 and 9"),
              ("13", "Health savings account deduction"), ("15", "Deductible part of self-employment tax"),
              ("16", "Self-employed SEP, SIMPLE, and qualified plans"), ("20", "IRA deduction"),
              ("26", "Add lines 11 through 23 and 25")],
    "Sch 1-A": [("38", "Total additional deductions")],
    "Sch 2": [("2", "Alternative minimum tax. Attach Form 6251"), ("3", "Add lines 1z and 2"),
              ("4", "Self-employment tax. Attach Schedule SE"), ("8", "Additional tax on IRAs or other tax-favored"),
              ("12", "Net investment income tax. Attach Form 8960"), ("21", "Add lines 4, 7 through 16, and 18")],
    "Sch A": [("5d", "Add lines 5a through 5c"), ("5e", "Enter the smaller of line 5d"),
              ("8a", "Home mortgage interest and points"), ("11", "Gifts by cash or check"),
              ("12", "Other than by cash or check"), ("14", "Add lines 11 through 13"),
              ("17", "Add the amounts in the far right column")],
    "Sch B": [("2", "Add the amounts on line 1"), ("4", "Subtract line 3 from line 2"),
              ("6", "Add the amounts on line 5")],
    "Sch C": [("1", "Gross receipts or sales"), ("28", "Total expenses before expenses for business use"),
              ("31", "Net profit or (loss). Subtract line 30")],
    "Sch D": [("7", "Net short-term capital gain or (loss)"), ("10", "Long-term totals from Form(s) 8949"),
              ("13", "Capital gain distributions"), ("15", "Net long-term capital gain or (loss)"),
              ("16", "Combine lines 7 and 15")],
    "Sch E": [("23a", "Total of all amounts reported on line 3"), ("26", "Total rental real estate and royalty income"),
              ("32", "Total partnership and S corporation income"), ("41", "Total income or (loss). Combine lines 26")],
    "Sch SE": [("12", "Self-employment tax. Add lines 10 and 11"), ("13", "Deduction for one-half of self-employment")],
    "8960": [("12", "Net investment income. Subtract Part II"), ("17", "Net investment income tax for individuals")],
    "6251": [("2i", "Exercise of incentive stock options"), ("4", "Alternative minimum taxable income"),
             ("11", "AMT. Subtract line 10 from line 9")],
    "5329": [("1", "Early distributions includible in income"), ("4", "Additional tax. Enter 10%")],
    "8606": [("1", "Nondeductible contributions to traditional IRAs"), ("16", "Amount converted to Roth IRAs"),
             ("18", "Taxable amount. Subtract line 17 from line 16")],
    "8889": [("2", "HSA contributions you made"), ("9", "Employer contributions made to your HSAs"),
             ("13", "HSA deduction. Enter the smaller")],
    "8995": [("15", "Qualified business income deduction. Enter the smaller")],
}
FORM_NAMES = {"Sch 1": "Schedule 1", "Sch 1-A": "Schedule 1-A", "Sch 2": "Schedule 2", "Sch A": "Schedule A",
              "Sch B": "Schedule B", "Sch C": "Schedule C", "Sch D": "Schedule D", "Sch E": "Schedule E",
              "Sch SE": "Schedule SE"}


def form_name(kind):
    return FORM_NAMES.get(kind, f"Form {kind}")


def _label_norm(tok):
    """OCR-tolerant line number: 'lla' -> '11a', '1B' -> '18', 'I5' -> '15'."""
    t = tok.strip(_JUNK + "().,")
    if not t:
        return ""
    t = t.replace("l", "1").replace("I", "1").replace("|", "1").replace("O", "0").replace("o", "0")
    t = re.sub(r"(?<=\d)B$", "8", t).replace("S", "5")
    return t.lower()


GENERIC = ("addlines", "subtractline", "combinelines", "amountfrom", "addtheamounts", "enterthesmaller")
LABEL_ALIASES = {"12": "12e", "27": "27a"}     # the final 2025 Form 1040 prints these line numbers


def match_lines(page, specs, threshold=0.78):
    """Assign rows of a page to form lines. Returns {line: row_words}.

    A row matches a line when its printed description is similar to the
    expected wording; a matching line number adds weight. Generic wording
    ("Add lines ...") needs a near-exact match unless the line number agrees.
    """
    found, used = {}, set()
    candidates = []
    for r_i, row in enumerate(rows(page.words)):
        if not row:
            continue
        # Real returns often print margin text ("Qualifying", "Tax and") before the line number,
        # so also try starting at a line-number-looking word among the first few on the left.
        starts = [0] + [i for i, w in enumerate(row[1:5], 1)
                        if w.x0 < page.width * 0.3 and re.fullmatch(r"\d{1,2}[a-z]?", _label_norm(w.text))]
        desc_all = norm(" ".join(w.text for w in row))
        for st in starts:
            lab = _label_norm(row[st].text)
            desc = norm(" ".join(w.text for w in row[st + 1:]))
            for line, phrase in specs:
                key = norm(phrase)
                sim = max(similar(desc[:len(key) + 2], key), similar(desc_all[:len(key) + 2], key) - 0.05)
                label_ok = lab == line.lower() or lab == LABEL_ALIASES.get(line.lower())
                s = sim + (0.15 if label_ok else 0)
                need = 0.93 if key.startswith(GENERIC) and not label_ok else threshold
                if sim >= need or (label_ok and s >= threshold):
                    candidates.append((s, r_i, line, row))
    for s, r_i, line, row in sorted(candidates, key=lambda c: -c[0]):
        if line in found or r_i in used:
            continue
        found[line] = row
        used.add(r_i)
    return found


def row_amount(page, row, min_x_frac=0.80):
    """Amount printed in the right-hand amount column of a row (0 if blank)."""
    nums = [(w, amount(w.text)) for w in row if w.x1 >= page.width * min_x_frac]
    nums = [(w, v) for w, v in nums if v is not None and not is_year(v)]
    return reocr_amount(page, *nums[-1]) if nums else 0


def parse_lines(page, kind, specs, out):
    """Fill out[line] = Fact for every spec line found on the page.

    Rows are matched by their wording first. As a fallback, a line can be found by the
    line number printed just left of its amount box ("25a  10,630."), which helps when
    the wording sits on a different row (as with 1040 line 25a on the real form).
    """
    for line, row in match_lines(page, specs).items():
        out[line] = fact(page, f"{form_name(kind)} line {line}", row_amount(page, row))
    boxed = _boxed_labels(page)
    for line, _ in specs:
        hit = boxed.get(line.lower()) or boxed.get(LABEL_ALIASES.get(line.lower(), ""))
        if hit is None:
            continue
        v = reocr_amount(page, *hit)
        if line not in out or (not out[line].value and v):
            out[line] = fact(page, f"{form_name(kind)} line {line}", v)


def _boxed_labels(page):
    """{line number: (amount word, value)} where a line number is printed right before its amount.

    Covers both the main amount column and the inner column used by sub-lines (1040 25a-25c).
    """
    out = {}
    for row in rows(page.words):
        for i, w in enumerate(row[:-1]):
            if not page.width * 0.55 <= w.x0 <= page.width * 0.86:
                continue
            lab = _label_norm(w.text)
            if not re.fullmatch(r"\d{1,2}[a-z]?", w.text.strip()) or lab in out:
                continue                 # a clean line number only (OCR junk like "20." doesn't count)
            if i and row[i - 1].text.lower().strip("(") in ("schedule", "form", "line", "box", "lines"):
                continue                 # "Schedule 2 (Form 1040)" is a title, not line 2
            nxt = row[i + 1]
            v = amount(nxt.text)
            looks_like_money = re.search(r"[.,]", nxt.text) or len(re.sub(r"\D", "", nxt.text)) >= 3
            if (v is not None and not is_year(v) and nxt.x0 - w.x1 < 120 and looks_like_money
                    and nxt.x1 >= page.width * 0.70):
                out[lab] = (nxt, v)
    return out


def parse_pairs(page, out):
    """1040 lines 2a/2b ... 6a/6b printed side by side on one row."""
    for a, phrase, b in PAIRS:
        hit = match_lines(page, [(a, phrase)], threshold=0.72)
        if a not in hit:
            continue
        row = hit[a]
        left = [w for w in row if page.width * 0.42 <= w.x1 <= page.width * 0.64]
        av = [(w, amount(w.text)) for w in left]
        av = [(w, v) for w, v in av if v is not None]
        out[a] = fact(page, f"Form 1040 line {a}", reocr_amount(page, *av[-1]) if av else 0)
        out[b] = fact(page, f"Form 1040 line {b}", row_amount(page, row))


# ---------------------------------------------------------------------
# 1040 page 1 header: filing status, names, 65+ boxes, dependents
# ---------------------------------------------------------------------
STATUS_WORDS = [("single", "Single", None), ("mfj", "Married", "jointly"), ("mfs", "Married", "separately"),
                ("hoh", "Head", None), ("qss", "Qualifying", None)]


def parse_1040_header(page):
    h = {"taxpayer": {}, "spouse": None, "dependents": [], "born_before": {}}
    all_rows = rows(page.words)
    # filing status: the "Filing Status" row and the few rows under it (the real form spreads the
    # five boxes over three rows); look at each status label's checkbox
    fs_i = next((i for i, r in enumerate(all_rows) if "filingstatus" in norm(" ".join(w.text for w in r))), None)
    if fs_i is not None:
        top = all_rows[fs_i][0].top
        block = [r for r in all_rows[fs_i:fs_i + 5] if r[0].top - top < 40]
        for code, first, second in STATUS_WORDS:
            for r in block:
                hit = next((i for i, w in enumerate(r) if similar(norm(w.text), norm(first)) >= 0.7 and (
                    not second or any(similar(norm(x.text), second) > 0.7 for x in r[i + 1:i + 4]))), None)
                if hit is not None and checked_before(page, r[hit]):
                    h["status"] = fact(page, "Form 1040 filing status", code)
    h["born_before"] = parse_born_before(page)
    # names and SSNs: value rows under "Your first name" and "spouse's first name" labels
    for i, r in enumerate(all_rows):
        t = norm(" ".join(w.text for w in r))
        target = "taxpayer" if t.startswith("yourfirstname") else ("spouse" if "spousesfirstname" in t else None)
        if not target or i + 1 >= len(all_rows):
            continue
        vals = all_rows[i + 1]
        vt = " ".join(w.text for w in vals)
        if "address" in norm(vt) and "home" in norm(vt):
            continue                              # no spouse line filled in
        ssn = SSN_RE.search(vt)
        name_words = [w.text for w in vals if w.x1 < page.width * 0.72 and not SSN_RE.search(w.text)]
        dec = re.search(r"DECEASED\s*(\d{1,2}/\d{1,2}/\d{4})?", vt, re.I)
        if dec:
            name_words = name_words[:name_words.index(next(x for x in name_words if "DECEASED" in x.upper()))]
            name_words = [x for x in name_words if x not in ("—", "-", "--")]
        if not name_words and not ssn:
            continue
        person = {"name": fact(page, f"Form 1040 {target} name", " ".join(name_words)),
                  "ssn": fact(page, f"Form 1040 {target} SSN", "-".join(ssn.groups()) if ssn else "")}
        if dec:
            person["deceased"] = fact(page, "Form 1040 spouse deceased", dec.group(1) or "yes")
        h[target] = person
    # dependents: the final 2025 form lists them in columns ("Dependent 1", "Dependent 2", ...);
    # older layouts use one row per dependent
    cols = parse_dependent_columns(page, all_rows)
    if cols is not None:
        h["dependents"] = cols
        return h
    in_deps = False
    for r in all_rows:
        t = " ".join(w.text for w in r)
        nt = norm(t)
        if nt.startswith("dependents"):
            in_deps = True
            continue
        if in_deps and nt.startswith("income"):
            break
        if in_deps:
            m = SSN_RE.search(t)
            if m:
                ssn_w = next(w for w in r if SSN_RE.search(w.text) or w.text.startswith(m.group(1)))
                name = " ".join(w.text for w in r if page.width * 0.15 <= w.x0 and w.x1 <= ssn_w.x0)
                rel = " ".join(w.text for w in r if ssn_w.x1 < w.x0 < page.width * 0.72)
                h["dependents"].append({"name": name, "ssn": "-".join(m.groups()), "relationship": rel,
                                        "fact": fact(page, "Form 1040 dependents table", name)})
    return h


def parse_born_before(page):
    """65+ boxes ("Were born before January 2, ..."): the word right before each "born" has the checkbox.

    On the final 2025 Form 1040 these sit on page 2, so this runs on both pages.
    """
    out = {}
    for r in rows(page.words):
        t = norm(" ".join(w.text for w in r))
        if "bornbefore" in t or "bombefore" in t:
            borns = [i for i, w in enumerate(r) if norm(w.text) in ("born", "bom")]
            if len(borns) == 1:            # one row per person ("You: ... / Spouse: ...")
                who = "spouse" if "spouse" in t[:t.find("born")] else "you"
                pairs = [(who, borns[0])]
            else:
                pairs = list(zip(("you", "spouse"), borns))
            for who, i in pairs:
                if i > 0 and who not in out:
                    out[who] = fact(page, f"Form 1040 born-before box ({who})", checked_before(page, r[i - 1]))
    return out


def parse_dependent_columns(page, all_rows):
    """Dependents table laid out in columns. Returns a list, or None if this layout isn't used."""
    head = next((r for r in all_rows if sum(1 for w in r if w.text == "Dependent") >= 2), None)
    if not head:
        return None
    xs = [w.x0 for w in head if w.text == "Dependent"]
    bounds = [x - 12 for x in xs] + [page.width]

    def row_for(tag):
        return next((r for r in all_rows if r[0].top > head[0].top and r[0].top - head[0].top < 120
                     and any(w.text == tag for w in r[:3])), [])

    def col(r, k):
        return " ".join(w.text for w in r if bounds[k] <= w.x0 < bounds[k + 1])

    first, last, ssn_r, rel = row_for("(1)"), row_for("(2)"), row_for("(3)"), row_for("(4)")
    deps = []
    for k in range(len(xs)):
        m = SSN_RE.search(col(ssn_r, k))
        name = f"{col(first, k)} {col(last, k)}".strip()
        if m or name:
            deps.append({"name": name, "ssn": "-".join(m.groups()) if m else "", "relationship": col(rel, k),
                         "fact": fact(page, "Form 1040 dependents table", name)})
    return deps


# ---------------------------------------------------------------------
# Schedule E per-property nets and Form 8949 rows
# ---------------------------------------------------------------------
def sch_e_property_nets(page):
    hit = match_lines(page, [("21", "Subtract line 20 from line 3 (income) or (loss)")])
    if "21" not in hit:
        return []
    vals = [amount(w.text) for w in hit["21"] if w.x0 > page.width * 0.45]
    return [fact(page, "Schedule E line 21", v) for v in vals if v is not None]


def f8949_rows(page):
    out = []
    for r in rows(page.words):
        t = " ".join(w.text for w in r)
        dates = DATE_RE.findall(t)
        if len(dates) >= 2:
            first_date_x = next(w.x0 for w in r if DATE_RE.search(w.text))
            desc = " ".join(w.text for w in r if w.x1 <= first_date_x)
            nums = [amount(w.text) for w in r if w.x0 > first_date_x and not DATE_RE.search(w.text)]
            nums = [v for v in nums if v is not None]
            if nums:
                out.append({"desc": desc, "proceeds": fact(page, "Form 8949 column (d)", nums[0]),
                            "gain": fact(page, "Form 8949 column (h)", nums[-1])})
    return out


# ---------------------------------------------------------------------
# 2. Boxed information returns
# ---------------------------------------------------------------------
BOXNUM_RE = re.compile(r"^(\d{1,2}[a-z]?|[a-f])$")


def cell_value(page, label, kind="money", down=34, width=None, min_ratio=0.8, nth=0):
    """Value printed in the box whose label starts with `label`.

    Searches below the label, from the label's left edge to the next box label on
    the same row (or `width` points). Returns (value, word) or (None, None).
    """
    hit = find_phrase(page, label, min_ratio=min_ratio, nth=nth)
    if not hit and re.match(r"^\d{1,2}[a-z]?\s", label):
        # OCR often garbles the tiny box number ("1a" -> "ta"); try the words alone
        hit = find_phrase(page, label.split(" ", 1)[1], min_ratio=min_ratio, nth=nth)
        if hit:
            left = [w for w in page.words if abs(w.mid_y - hit[0].mid_y) < 3 and 0 < hit[0].x0 - w.x1 < 8]
            hit = (left[0], hit[1]) if left else hit
    if not hit:
        return None, None
    first, last = hit
    same_row = sorted((w for w in page.words if abs(w.mid_y - first.mid_y) < 3 and w.x0 > last.x1 + 2),
                      key=lambda w: w.x0)
    nxt = [w.x0 for i, w in enumerate(same_row) if BOXNUM_RE.match(w.text) and w.x0 - last.x1 > 12
           and not (i and same_row[i - 1].text.lower().strip(".()") in ("box", "line"))]
    # "Box 6. Voluntary..." style labels (SSA-1099) also start the next box
    nxt += [w.x0 for i, w in enumerate(same_row[:-1]) if w.text == "Box" and w.x0 - last.x1 > 12
            and re.fullmatch(r"\d{1,2}\.", same_row[i + 1].text)]
    right = min(nxt) - 2 if nxt else first.x0 + (width or 230)
    if width:
        right = min(right, first.x0 + width)
    region = [w for w in page.words if first.x0 - 6 <= w.x0 and w.x1 <= right + 4
              and first.bottom - 1 < w.top < first.top + down and w not in (first, last)]
    if kind == "money" and page.ocr:
        region = _join_split_numbers(region)
    cands = []
    for w in region:
        v = _as_kind(w.text, kind)
        if v is None:
            continue
        if kind == "money" and _is_label_number(page, w):
            continue
        cands.append((w, v))
    if not cands:
        return None, None
    # nearest value below the label; among values on that line, the right-most (amounts are right-aligned)
    w, v = min(cands, key=lambda c: (round(c[0].top / 3), -c[0].x1))
    if kind == "money":
        v = reocr_amount(page, w, v)
    return v, w


PIECE_RE = re.compile(r"[\d,.'’]+")


def _join_split_numbers(words):
    """OCR sometimes splits one amount into pieces: '7,' + '000', or '6' + "'" + '418' + '.' + '52'.

    Runs of number fragments sitting side by side (even slightly off the line) are joined
    into one word; a stray apostrophe is read as a comma.
    """
    from .ingest import Word
    pieces = sorted((w for w in words if PIECE_RE.fullmatch(w.text)), key=lambda w: w.x0)
    used, joined = set(), []
    for a in pieces:
        if id(a) in used:
            continue
        run = [a]
        while True:
            last = run[-1]
            nxt = next((b for b in pieces if id(b) not in used and b not in run and b.x0 > last.x0
                        and -9 < b.x0 - last.x1 < 4 and abs(b.mid_y - a.mid_y) < 11), None)
            if not nxt:
                break
            run.append(nxt)
        if len(run) > 1:
            text = "".join(w.text for w in run).replace("'", ",").replace("’", ",")
            if re.search(r"\d", text):
                used |= {id(w) for w in run}
                joined.append(Word(text, run[0].x0, min(w.top for w in run), run[-1].x1, max(w.bottom for w in run)))
    return [w for w in words if id(w) not in used] + joined


def reocr_amount(page, word, value):
    """On scans, re-read an amount from a tight crop with a digits-only whitelist.

    Full-page OCR sometimes swaps similar digits (6/8) or glues a box border onto
    a number ("0" -> "07"). The crop is read at two magnifications; the value that
    at least two of the three readings agree on wins, otherwise the original stays.
    """
    if not page.ocr or value is None:
        return value
    pytesseract = tesseract()
    img, s = page_image(page), page.scale
    crop = img.crop((int((word.x0 - 3) * s), int((word.top - 6) * s),     # generous vertical margin:
                     int((word.x1 + 3) * s), int((word.bottom + 6) * s)))  # tight crops misread 5 as 9
    if crop.width < 4 or crop.height < 4:
        return value
    reads = [value]
    for mag in (1, 3):
        t = pytesseract.image_to_string(crop.resize((crop.width * mag, crop.height * mag)),
                                        config="--psm 7 -c tessedit_char_whitelist=0123456789,.()-").strip()
        reads.append(amount(t))
    for v in reads:
        if v is not None and sum(1 for x in reads if x == v) >= 2:
            return v
    return value


def _is_label_number(page, w):
    """A short number that is part of a label ("7 Distribution", "Box 7.") rather than a value."""
    t = w.text.strip(".")
    if not re.fullmatch(r"\d{1,2}[a-z]?", t):
        return False
    for x in page.words:
        if abs(x.mid_y - w.mid_y) >= 2.5 or x is w:
            continue
        if 0 < x.x0 - w.x1 < 10 and re.match(r"[A-Za-z(]", x.text):
            return True                      # followed by label text
        if 0 < w.x0 - x.x1 < 8 and x.text.lower().strip("()") in ("box", "line"):
            return True                      # "Box 7"
    return False


def _as_kind(text, kind):
    if kind == "money":
        v = amount(text)
        return None if v is None or is_year(v) else v
    if kind == "ssn":
        m = SSN_RE.search(text)
        return "-".join(m.groups()) if m else None
    if kind == "code":
        t = text.strip(_JUNK + ".,")
        return t if re.fullmatch(r"[0-9A-HJ-NPR-Z]{1,2}", t) else None
    if kind == "date":
        m = DATE_RE.search(text)
        return m.group(0) if m else None
    if kind == "price":
        v = amount(text.replace("$", ""))
        return v
    return text


def money(page, form, box, label, **kw):
    v, _ = cell_value(page, label, **kw)
    return fact(page, f"{form} box {box}", v if v is not None else 0,
                "" if v is not None else "not found/blank")


CODES_1099R = "1234567ABDEFGHJKLMNPQRSTUW"


def reocr_char(page, word, whitelist):
    """Re-read one short token on a scan, as a single character from `whitelist`."""
    if not page.ocr:
        return word.text
    pytesseract = tesseract()
    img, s = page_image(page), page.scale
    pad = 3
    crop = img.crop((int((word.x0 - pad) * s), int((word.top - pad) * s),
                     int((word.x1 + pad) * s), int((word.bottom + pad) * s)))
    crop = crop.resize((crop.width * 2, crop.height * 2))
    t = pytesseract.image_to_string(crop, config=f"--psm 10 -c tessedit_char_whitelist={whitelist}").strip()
    return t or word.text


W2_CODES = "ABCDEFGHJKLMNPQRSTVWYZ"


def w2_box12(page, pitch_default=19.5, cell_w=135):
    """W-2 box 12a-12d: {code: Fact(amount)}.

    The four cells are stacked with equal spacing, so any label that survives OCR
    tells us where the others are.
    """
    labs = {}
    for i, lab in enumerate(("12a", "12b", "12c", "12d")):
        hit = find_phrase(page, lab, min_ratio=0.99)
        if hit and norm(hit[0].text) == lab:
            labs[i] = hit[0]
    if not labs:
        return {}
    x0 = sorted(w.x0 for w in labs.values())[len(labs) // 2]
    idx = sorted(labs)
    pitch = ((labs[idx[-1]].top - labs[idx[0]].top) / (idx[-1] - idx[0])) if len(idx) > 1 else pitch_default
    ref_i, ref = idx[0], labs[idx[0]]
    codes = {}
    for i, lab in enumerate(("12a", "12b", "12c", "12d")):
        top = ref.top + (i - ref_i) * pitch
        cell = [w for w in page.words if x0 - 4 <= w.x0 <= x0 + cell_w and top - 3 <= w.top <= top + 17]
        amts = [(w, amount(w.text)) for w in cell if w.x1 > x0 + 90 and amount(w.text) is not None]
        if not amts:
            continue
        aw, av = max(amts, key=lambda a: a[0].x1)
        av = reocr_amount(page, aw, av)
        # the code letter sits between the label and the amount; where exactly varies by form vendor
        code_w = next((w for w in cell if x0 - 2 <= w.x0 <= x0 + 80 and w.top > top + 2
                       and (_as_kind(w.text, "code") or "").isalpha()), None)
        code = _as_kind(code_w.text, "code") if code_w else None
        if page.ocr:
            spot = (code_w.x0 - 1, code_w.top - 3, code_w.x1 + 1, code_w.bottom + 3) if code_w else \
                   (x0 + 43, top - 4, x0 + 55, top + 16)
            code = _read_code(page, *spot) or code
        if code:
            codes[code] = fact(page, f"W-2 box {lab} code {code}", av)
    return codes


def _read_code(page, x0, top, x1, bottom):
    """Majority vote of four whitelisted reads of a small letter-code region on a scan."""
    from collections import Counter
    pytesseract = tesseract()
    img, s = page_image(page), page.scale
    crop = img.crop((int(x0 * s), int(top * s), int(x1 * s), int(bottom * s)))
    reads = [pytesseract.image_to_string(crop.resize((crop.width * m, crop.height * m)),
                                         config=f"--psm {psm} -c tessedit_char_whitelist={W2_CODES}").strip()
             for m in (1, 2) for psm in (7, 10)]
    reads = [r for r in reads if re.fullmatch(f"[{W2_CODES}]{{1,2}}", r)]
    return Counter(reads).most_common(1)[0][0] if reads else None


def recipient_ssn(page):
    for label in ("RECIPIENT’S TIN", "RECIPIENT'S TIN", "TRANSFEROR'S TIN", "Employee's social security number",
                  "Shareholder's identifying number", "Beneficiary's Social Security Number"):
        v, _ = cell_value(page, label, kind="ssn", down=30, min_ratio=0.75)
        if v:
            return v
    m = [SSN_RE.search(w.text) for w in page.words]
    m = [x for x in m if x]
    return "-".join(m[0].groups()) if m else ""


def first_line_below(page, label, width=230, down=30):
    hit = find_phrase(page, label, min_ratio=0.75)
    if not hit:
        return ""
    first = hit[0]
    below = [w for w in page.words if first.x0 - 4 <= w.x0 <= first.x0 + width and first.bottom < w.top < first.top + down]
    if not below:
        return ""
    top_row = min(round(w.top) for w in below)
    return " ".join(w.text for w in sorted(below, key=lambda w: w.x0) if abs(round(w.top) - top_row) <= 3)


def parse_source(page, kind):
    """Return a dict of Facts for one information-return page."""
    d = {"kind": kind, "doc": page.doc, "ssn": recipient_ssn(page)}
    if kind == "W-2":
        d["box1"] = money(page, "W-2", "1", "1 Wages, tips, other compensation", down=17)
        d["box2"] = money(page, "W-2", "2", "2 Federal income tax withheld", down=17)
        d["employer"] = first_line_below(page, "c Employer's name, address, and ZIP code", width=260, down=24)
        d["box12"] = w2_box12(page)
        ret = find_phrase(page, "Retirement plan", min_ratio=0.75) or find_phrase(page, "Retirement", min_ratio=0.75)
        d["box13_retirement"] = fact(page, "W-2 box 13 retirement plan", bool(ret) and box_checked(
            page, ret[0].x0 - 2, ret[0].top - 15, ret[0].x0 + 26, ret[0].top - 1))
        emp = first_line_below(page, "e Employee's first name and initial", width=260, down=26)
        d["employee"] = re.sub(r"\s*Last name.*|\s*Suff\.?", "", emp).strip()
    elif kind == "1099-R":
        d["box1"] = money(page, "1099-R", "1", "1 Gross distribution", down=30, width=195)
        d["box2a"] = money(page, "1099-R", "2a", "2a Taxable amount", down=30, width=195)
        d["box4"] = money(page, "1099-R", "4", "4 Federal income tax", down=30, width=98)
        code, code_w = cell_value(page, "7 Distribution", kind="code", down=30, width=95)
        simple = find_phrase(page, "SIMPLE", min_ratio=0.8)
        if not code and simple:
            # Box 7 is the cell just left of the IRA/SEP/SIMPLE box; read the code printed there.
            s = simple[0]
            near = [w for w in page.words if s.x0 - 100 < w.x0 and w.x1 < s.x0 + 1 and s.top - 22 < w.top < s.bottom + 10]
            near = [(w, _as_kind(w.text, "code")) for w in sorted(near, key=lambda w: -w.x1)]
            code_w, code = next(((w, c) for w, c in near if c), (None, None))
        if code_w is not None and page.ocr:
            code = _as_kind(reocr_char(page, code_w, CODES_1099R), "code") or code
        d["box7"] = fact(page, "1099-R box 7", code or "", "" if code else "not found")
        ira = False
        if simple:
            s = simple[1]
            ira = box_checked(page, s.x1 + 1, s.top - 3, s.x1 + 34, s.bottom + 3)
        d["ira"] = fact(page, "1099-R IRA/SEP/SIMPLE box", ira)
        d["payer"] = first_line_below(page, "PAYER'S name, street address", down=22)
    elif kind == "SSA-1099":
        d["box5"] = money(page, "SSA-1099", "5", "Box 5. Net Benefits", down=32)
        d["box6"] = money(page, "SSA-1099", "6", "Box 6. Voluntary Federal Income Tax Withheld", down=28, width=360)
        v, _ = cell_value(page, "Box 2. Beneficiary", kind="ssn", down=28)
        d["ssn"] = v or d["ssn"]
    elif kind == "1099-INT":
        d["box1"] = money(page, "1099-INT", "1", "1 Interest income", down=30, width=195)
        d["box3"] = money(page, "1099-INT", "3", "3 Interest on U.S. Savings Bonds", down=30, width=98)
        d["taxable"] = Fact((d["box1"].value or 0) + (d["box3"].value or 0), page.doc, page.number,
                            "1099-INT boxes 1 + 3")
        d["payer"] = first_line_below(page, "PAYER'S name, street address", down=22)
    elif kind == "1099-DIV":
        d["box1a"] = money(page, "1099-DIV", "1a", "1a Total ordinary dividends", down=30, width=195)
        d["box1b"] = money(page, "1099-DIV", "1b", "1b Qualified dividends", down=30, width=195)
        d["box2a"] = money(page, "1099-DIV", "2a", "2a Total capital gain distr", down=30, width=98)
        d["payer"] = first_line_below(page, "PAYER'S name, street address", down=22)
    elif kind == "1099-B":
        tot = 0
        for r in rows(page.words):
            t = norm(" ".join(w.text for w in r))
            if t.startswith("total"):
                vals = [amount(w.text) for w in r if amount(w.text) is not None]
                tot = vals[-1] if vals else 0
        d["gain"] = fact(page, "1099-B summary total gain", tot)
    elif kind == "1099-G":
        d["box1"] = money(page, "1099-G", "1", "1 Unemployment compensation", down=30, width=195)
        d["box4"] = money(page, "1099-G", "4", "4 Federal income tax", down=30, width=98)
    elif kind == "1099-S":
        d["box2"] = money(page, "1099-S", "2", "2 Gross proceeds", down=30, width=195)
        date, _ = cell_value(page, "1 Date of closing", kind="date", down=30)
        d["box1"] = fact(page, "1099-S box 1", date or "")
    elif kind == "1099-NEC":
        d["box1"] = money(page, "1099-NEC", "1", "1 Nonemployee compensation", down=30, width=195)
    elif kind == "1099-K":
        d["box1a"] = money(page, "1099-K", "1a", "1a Gross amount of payment card", down=30, width=195)
    elif kind == "K-1":
        d["box1"] = money(page, "K-1 (1120-S)", "1", "1 Ordinary business income (loss)", down=28, width=275)
        fin = find_phrase(page, "Final K-1", min_ratio=0.75)
        d["final"] = fact(page, "K-1 Final K-1 box", bool(fin) and checked_before(page, fin[0]))
        d["corp"] = first_line_below(page, "B Corporation's name, address", width=260, down=24)
    elif kind == "3921":
        price, _ = cell_value(page, "3 Exercise price per share", kind="price", down=30, width=98)
        fmv, _ = cell_value(page, "4 Fair market value per share", kind="price", down=30, width=98)
        shares, _ = cell_value(page, "5 No. of shares transferred", kind="money", down=30, width=195)
        spread = (fmv - price) * shares if None not in (price, fmv, shares) else 0
        d["spread"] = fact(page, "Form 3921 (box 4 - box 3) x box 5", round(spread))
    elif kind == "1098":
        d["box1"] = money(page, "1098", "1", "1 Mortgage interest received", down=30, width=195)
    return d


def parse_consolidated(page):
    """Brokerage 'Consolidated Form 1099' summary table -> {kind: source dict}.

    Rows look like "1a Total ordinary dividends   41,860.32" under section headers
    "FORM 1099-DIV ...", "FORM 1099-INT ...", "FORM 1099-B ...".
    """
    section, vals = None, {}
    for r in rows(page.words):
        nt = norm(" ".join(w.text for w in r))
        for key, kind in (("form1099div", "1099-DIV"), ("form1099int", "1099-INT"), ("form1099b", "1099-B")):
            if nt.startswith(key):
                section = kind
        if not section:
            continue
        nums = [(w, amount(w.text)) for w in r if w.x0 > page.width * 0.6]
        nums = [(w, v) for w, v in nums if v is not None and not is_year(v)]
        if not nums:
            continue
        w, v = nums[-1]
        v = reocr_amount(page, w, v)
        box = next((_label_norm(x.text) for x in r[:4] if re.fullmatch(r"\d{1,2}[a-z]?", _label_norm(x.text))), None)
        term = "st" if nt.startswith("shortterm") else "lt" if nt.startswith("longterm") else ""
        if box:
            vals[(section, term + box)] = fact(page, f"{section} box {box}" + (f" ({term.upper()})" if term else "")
                                               + " (consolidated statement)", v)
    zero = lambda kind, box: vals.get((kind, box), fact(page, f"{kind} box {box}", 0))  # noqa: E731
    out = {}
    if any(k[0] == "1099-DIV" for k in vals):
        out["1099-DIV"] = {"kind": "1099-DIV", "doc": page.doc, "ssn": recipient_ssn(page), "payer": "",
                           "box1a": zero("1099-DIV", "1a"), "box1b": zero("1099-DIV", "1b"),
                           "box2a": zero("1099-DIV", "2a")}
    if any(k[0] == "1099-INT" for k in vals):
        b1, b3 = zero("1099-INT", "1"), zero("1099-INT", "3")
        out["1099-INT"] = {"kind": "1099-INT", "doc": page.doc, "ssn": recipient_ssn(page), "payer": "",
                           "box1": b1, "box3": b3,
                           "taxable": Fact((b1.value or 0) + (b3.value or 0), page.doc, page.number,
                                           "1099-INT boxes 1 + 3 (consolidated statement)")}
    if any(k[0] == "1099-B" for k in vals):
        g = sum((zero("1099-B", t + "1d").value or 0) - (zero("1099-B", t + "1e").value or 0)
                + (zero("1099-B", t + "1g").value or 0) for t in ("st", "lt"))
        out["1099-B"] = {"kind": "1099-B", "doc": page.doc, "ssn": recipient_ssn(page),
                         "gain": fact(page, "1099-B gain (consolidated statement)", g)}
    return out


# ---------------------------------------------------------------------
# Client profile summary (practice-management export)
# ---------------------------------------------------------------------
def _iso(m):
    return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"


NOTES_END = ("documentsprovided", "signature", "sampletraining", "preparerusesonly", "foroffice")


def parse_client_notes(page):
    """Client-written notes and yes/no answers on an intake form. None when the form has neither.

    Layout: a "Questions" table (question | Y/N | comments) and a free-text "Notes" box.
    """
    all_rows = rows(page.words)
    answers, notes, mode, ans_x, com_x = [], [], None, None, None
    for r in all_rows:
        nt = norm(" ".join(w.text for w in r))
        if nt.startswith(NOTES_END):
            mode = None
            continue
        if nt.startswith("questions"):
            mode = "questions"
            continue
        if nt.startswith(("notesfromclient", "clientnotes", "notes")) and len(nt) < 30:
            mode = "notes"
            continue
        if mode == "questions":
            if "comments" in nt and any(w.text in ("Y", "Y/N") for w in r):
                ans_x = min(w.x0 for w in r if w.text in ("Y", "Y/N"))
                com_x = next(w.x0 for w in r if w.text.lower().startswith("comment"))
                continue
            if ans_x is None:
                continue
            q = " ".join(w.text for w in r if w.x1 < ans_x - 2)
            a = next((w.text for w in r if ans_x - 8 <= w.x0 < com_x - 3 and w.text.upper() in
                      ("Y", "N", "YES", "NO")), "")
            c = " ".join(w.text for w in r if w.x0 >= com_x - 2)
            if q and (a or c):
                answers.append({"question": q, "answer": {"Y": "Yes", "N": "No"}.get(a.upper()[:1], a), "comment": c})
        elif mode == "notes":
            notes.append(" ".join(w.text for w in r))
    text = " ".join(notes).strip()
    if not answers and not text:
        return None
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    return {"answers": answers, "notes": sentences, "where": f"{page.doc} p{page.number}"}


def parse_info_sheet(page):
    """'Client Information Sheet' (practice intake form): taxpayer/spouse rows and a dependents table."""
    p = {"people": [], "dependents": [], "test_client": False, "source": "Client information sheet"}
    all_rows = rows(page.words)
    text = norm(page.text)
    if "fictitious" in text and "training" in text:
        p["test_client"] = True
    section = None
    for i, r in enumerate(all_rows):
        nt = norm(" ".join(w.text for w in r))
        if nt in ("taxpayer", "spouse"):
            section = nt
            continue
        if nt.startswith("dependents"):
            section = "dependents"
            continue
        if nt.startswith(("questions", "notes", "mailing", "lastyear")):
            section = None if not nt.startswith("mailing") else section
            if not nt.startswith("mailing"):
                continue
        line = " ".join(w.text for w in r)
        dm = DATE_RE.search(line)
        if not dm or nt.startswith(("fullname", "name")):
            continue
        dob_w = next(w for w in r if DATE_RE.search(w.text))
        ssn_w = next((w for w in r if SSN_RE.search(w.text)), None)
        cut = ssn_w.x0 if ssn_w and ssn_w.x0 < dob_w.x0 else dob_w.x0
        name = " ".join(w.text for w in r if w.x1 <= cut)
        if section in ("taxpayer", "spouse"):
            occ = " ".join(w.text for w in r if w.x0 > dob_w.x1 + 20)
            p["people"].append({"role": section, "name": name, "dob": _iso(dm), "occupation": occ})
            section = None
        elif section == "dependents":
            after = ssn_w.x1 if ssn_w and ssn_w.x0 > dob_w.x0 else dob_w.x1
            rel = " ".join(w.text for w in r if after < w.x0 < page.width * 0.68 and len(w.text) > 1)
            p["dependents"].append({"name": name, "relationship": rel, "dob": _iso(dm)})
    p["notes"] = parse_client_notes(page)
    return p


def parse_profile(page):
    if "clientinformationsheet" in norm(page.text):
        return parse_info_sheet(page)
    p = {"people": [], "dependents": [], "test_client": False}
    section, person = None, None
    for r in rows(page.words):
        t = " ".join(w.text for w in r)
        nt = norm(t)
        if "fictionaltestclient" in nt:
            p["test_client"] = True
        if nt.startswith("filingstatus"):
            v = norm(t.split(")", 1)[-1] if ")" in t else t)
            p["filing_status"] = ("mfj" if "jointly" in v else "mfs" if "separately" in v else
                                  "hoh" if "head" in v else "qss" if "surviving" in v else "single")
        elif nt.startswith("primarytaxpayer") or (nt.startswith("spouse") and section == "household"):
            name = re.sub(r"^(Primary taxpayer|Spouse)\s*", "", t).strip()
            person = {"role": "taxpayer" if nt.startswith("primary") else "spouse", "name": name}
            p["people"].append(person)
        elif nt.startswith("dateofbirth") and person is not None:
            m = DATE_RE.search(t)
            if m:
                person["dob"] = f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
        elif nt.startswith("occupation") and person is not None:
            person["occupation"] = t.split(" ", 1)[1] if " " in t else ""
        elif nt == "household":
            section = "household"
        elif nt == "dependents":
            section, person = "dependents", None
        elif nt in ("contact", "documentsonfile"):
            section = nt
        elif section == "dependents" and DATE_RE.search(t) and not nt.startswith("name"):
            m = DATE_RE.search(t)
            dob_w = next(w for w in r if DATE_RE.search(w.text))
            words = [w.text for w in r if w.x1 < dob_w.x0]
            rel_words = [w.text for w in r if page.width * 0.3 < w.x0 < dob_w.x0]
            name = " ".join(x for x in words if x not in rel_words)
            p["dependents"].append({"name": name, "relationship": " ".join(rel_words),
                                    "dob": f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"})
    return p
