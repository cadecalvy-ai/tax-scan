"""Read every PDF in one client folder and assemble a per-year record."""
import re
from collections import defaultdict
from pathlib import Path

from . import extract as ex
from .classify import CONTEXT_KINDS, RETURN_KINDS, SOURCE_KINDS, classify_page, doc_year, page_year
from .ingest import read_pdf


def new_year():
    return {"f1040": {}, "header": {}, "forms": {}, "sch_e_nets": [], "f8949": [],
            "sources": defaultdict(list), "sch_c_owner_ssn": "",
            "context": {"care_providers": [], "pnl": [], "asset_purchases": []}}   # cross-checks and talking points only


def build_record(folder, cache_dir=None, files=None):
    """Return a dict describing everything found in the folder's PDFs."""
    folder = Path(folder)
    rec = {"folder": folder.name, "profile": None, "years": {}, "docs": [], "warnings": []}
    for pdf in files or sorted(folder.glob("*.pdf")):
        try:
            pages = read_pdf(pdf, cache_dir)
        except Exception as e:                      # unreadable file: report it, keep going
            rec["warnings"].append(f"Could not read {pdf.name}: {e}")
            continue
        kinds = [classify_page(p, pdf.name) for p in pages]
        for p, k in zip(pages, kinds):
            rec["docs"].append({"doc": pdf.name, "page": p.number, "kind": k, "ocr": p.ocr})
        if any(k in RETURN_KINDS for k in kinds):
            _read_return(rec, pdf, pages, kinds)
        elif any(k in SOURCE_KINDS for k in kinds):
            year = doc_year(pages) or _year_from_name(pdf.name)
            if not year:
                rec["warnings"].append(f"{pdf.name}: could not tell which tax year this document is for")
                continue
            yr = rec["years"].setdefault(year, new_year())
            # A brokerage consolidated statement repeats its DIV/INT/B figures on detail pages;
            # take them once, from the summary table.
            covered = set()
            for p, k in zip(pages, kinds):
                if k == "1099-CONSOL":
                    for kind, d in ex.parse_consolidated(p).items():
                        yr["sources"][kind].append(d)
                        covered.add(kind)
            for p, k in zip(pages, kinds):
                if k in SOURCE_KINDS and k != "1099-CONSOL" and k not in covered:
                    yr["sources"][k].append(ex.parse_source(p, k))
        elif "profile" in kinds:
            rec["profile"] = ex.parse_profile(pages[kinds.index("profile")])
        elif any(k in CONTEXT_KINDS for k in kinds):
            _read_context(rec, pdf, pages, kinds)
        else:
            rec["warnings"].append(f"{pdf.name}: document type not recognized; skipped")
    return rec


def _read_context(rec, pdf, pages, kinds):
    """Supporting papers (a P&L, a bill of sale): kept with the year they describe, for cross-checks and talking points."""
    for p, k in zip(pages, kinds):
        if k == "P&L":
            d = ex.parse_pnl(p)
            if d["income"].value is None and d["net"].value is None:
                continue                                 # a detail page with no totals
            slot = "pnl"
        elif k == "Bill of sale":
            d = ex.parse_bill_of_sale(p)
            if d["price"].value is None:
                continue
            slot = "asset_purchases"
        else:
            continue
        year = d["year"] or doc_year(pages) or _year_from_name(pdf.name)
        if not year:
            rec["warnings"].append(f"{pdf.name}: could not tell which year this document is for")
            continue
        rec["years"].setdefault(year, new_year())["context"][slot].append(d)


def _year_from_name(name):
    m = re.search(r"(20[12]\d)", name)
    return int(m.group(1)) if m else None


def _read_return(rec, pdf, pages, kinds):
    year = None
    for p, k in zip(pages, kinds):
        if k == "1040":
            year = page_year(p)
            break
    year = year or next((page_year(p) for p in pages if page_year(p)), None) or _year_from_name(pdf.name)
    if not year:
        rec["warnings"].append(f"{pdf.name}: could not tell which tax year this return is for")
        return
    yr = rec["years"].setdefault(year, new_year())
    for p, k in zip(pages, kinds):
        if k == "1040":
            yr["header"] = ex.parse_1040_header(p)
            ex.parse_lines(p, "1040", ex.f1040_specs(year, k), yr["f1040"])
            ex.parse_pairs(p, yr["f1040"])
        elif k == "1040 p2":
            ex.parse_lines(p, "1040", ex.f1040_specs(year, k), yr["f1040"])
            bb = ex.parse_born_before(p)       # the final 2025 form has the 65+ boxes on page 2
            if bb:
                yr["header"].setdefault("born_before", {}).update(bb)
        elif k in ex.SCHEDULE_LINES or k in ("8949",):
            form = yr["forms"].setdefault(k, {})
            found = {}
            if k in ex.SCHEDULE_LINES:
                ex.parse_lines(p, k, ex.SCHEDULE_LINES[k], found)
            for line, f in found.items():          # multi-page forms: keep the first non-zero value
                if line not in form or (not form[line].value and f.value):
                    form[line] = f
            if k == "Sch E":
                yr["sch_e_nets"] += ex.sch_e_property_nets(p)
            if k == "Sch F":
                ex.parse_pairs(p, form, ex.SCHF_PAIRS, "Sch F")
            if k == "8949":
                yr["f8949"] += ex.f8949_rows(p)
            if k == "2441":
                yr["context"]["care_providers"] += ex.parse_2441_providers(p)
            if k == "Sch C":
                for r in ex.rows(p.words):
                    t = " ".join(w.text for w in r)
                    if "proprietor" in t.lower():
                        m = ex.SSN_RE.search(t)
                        if m:
                            yr["sch_c_owner_ssn"] = "-".join(m.groups())
        elif k == "Prep summary":
            yr["context"].update(ex.parse_prep_info(p))
        elif k == "State summary":
            yr["context"].update(ex.parse_state_summary(p))
        elif k in RETURN_KINDS:
            yr["forms"].setdefault(k, {})              # present, nothing to read (e.g. 8949 continuation)
