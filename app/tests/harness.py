"""Shared test harness: grade every fictional test client once and compare with the answer key."""
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from src import paths  # noqa: E402

ROOT = paths.ROOT
CLIENTS = paths.SAMPLE_CLIENTS
CACHE = paths.APP / ".pytest_cache" / "ocr"          # OCR cache for fictional data only
GRADES = "ABCDF"


def answer_key():
    data = json.loads((CLIENTS / "answer_key.json").read_text(encoding="utf-8"))
    return {c["id"]: c for c in data["clients"]}


def _grade(folder):
    from src.grader import grade_client, load_config
    return Path(folder).name[:3], grade_client(folder, load_config(), str(CACHE))


def grade_all(workers=6):
    folders = sorted(p for p in CLIENTS.iterdir() if p.is_dir() and p.name[:1] == "C")
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return dict(ex.map(_grade, folders))


def in_band(grade, band):
    lo, hi = (band.split("-") + [band])[:2]
    return GRADES.index(lo) <= GRADES.index(grade) <= GRADES.index(hi)


# ---------------------------------------------------------------------
# Extraction comparison: returns a list of (field, expected, got) mismatches
# ---------------------------------------------------------------------
from src.extract import SCHEDULE_LINES  # noqa: E402

SOURCE_FIELDS = {   # answer-key source type -> (extracted kind, [(truth field, extracted field)])
    "w2": ("W-2", [("box1", "box1"), ("box2", "box2")]),
    "1099_int": ("1099-INT", [("box1", "box1")]),
    "1099_div": ("1099-DIV", [("box1a", "box1a"), ("box1b", "box1b"), ("box2a", "box2a")]),
    "1099_r": ("1099-R", [("box1", "box1"), ("box2a", "box2a"), ("box4", "box4"), ("box7", "box7"),
                          ("ira_sep_simple", "ira")]),
    "ssa_1099": ("SSA-1099", [("box5", "box5"), ("box6", "box6")]),
}


def compare_year(truth, yr, has_sources=True):
    """Compare one extracted year against the answer key's truth block.

    has_sources=False for prior years: the test data has the 2024 return but not
    the 2024 W-2s/1099s, so only the return itself is compared.
    """
    from src.classify import RETURN_KINDS
    bad, n = [], 0

    def check(name, exp, got):
        nonlocal n
        n += 1
        if exp != got:
            bad.append((name, exp, got))

    L = yr["f1040"]
    for line, exp in truth["form_1040"].items():
        got = L[line].value if line in L else "missing"
        check(f"1040 line {line}", exp, got)
    h = yr["header"]
    check("filing status", truth["filing_status"], h["status"].value if h.get("status") else None)
    check("born-before (you)", truth["born_before_checkbox"]["you"], bool(h["born_before"]["you"].value)
          if "you" in h.get("born_before", {}) else None)
    if truth["spouse"]:
        check("born-before (spouse)", truth["born_before_checkbox"]["spouse"], bool(h["born_before"]["spouse"].value)
              if "spouse" in h.get("born_before", {}) else None)
        check("spouse deceased", bool(truth["spouse"]["deceased"]),
              bool(h.get("spouse") and h["spouse"].get("deceased")))
    check("dependent count", len(truth["dependents"]), len(h.get("dependents", [])))
    for form, lines in truth["schedules"].items():
        if form not in RETURN_KINDS:
            continue                                  # e.g. Form 3921 is a source document, not attached
        if form not in yr["forms"]:
            check(f"{form} present", True, False)
            continue
        for line, _ in SCHEDULE_LINES.get(form, []):
            if line in lines and isinstance(lines[line], (int, float)):
                f = yr["forms"][form].get(line)
                check(f"{form} line {line}", round(lines[line]), f.value if f else "missing")
    if not has_sources:
        return bad, n
    for tkey, (kind, fields) in SOURCE_FIELDS.items():
        docs = truth["sources"].get(tkey, [])
        got = yr["sources"].get(kind, [])
        check(f"{kind} count", len(docs), len(got))
        for tf, gf in fields:
            exp = sorted(str(d[tf]) for d in docs)
            act = sorted(str(g[gf].value if hasattr(g[gf], "value") else g[gf]) for g in got)
            if tf in ("box1", "box2", "box4", "box5", "box6", "box1a", "box1b", "box2a"):
                act = sorted(str(round(float(x))) for x in act)
            check(f"{kind} {tf}", exp, act)
    if "w2" in truth["sources"]:
        exp = sorted(json.dumps(d["box12"], sort_keys=True) for d in truth["sources"]["w2"])
        act = sorted(json.dumps({k: v.value for k, v in g["box12"].items()}, sort_keys=True)
                     for g in yr["sources"].get("W-2", []))
        check("W-2 box 12 codes", exp, act)
        check("W-2 box 13", sorted(d["box13_retirement_plan"] for d in truth["sources"]["w2"]),
              sorted(bool(g["box13_retirement"].value) for g in yr["sources"].get("W-2", [])))
    k1 = truth["sources"].get("k1_1120s")
    if k1:
        g = yr["sources"].get("K-1", [{}])[0]
        check("K-1 box 1", k1["box1"], g.get("box1").value if g.get("box1") else None)
        check("K-1 final", k1["final"], bool(g.get("final").value) if g.get("final") else None)
    for tkey, kind, tf, gf in [("1099_s", "1099-S", "box2", "box2"), ("1099_g", "1099-G", "box1", "box1"),
                               ("1099_g", "1099-G", "box4", "box4"), ("3921", "3921", "spread", "spread")]:
        if tkey in truth["sources"]:
            g = yr["sources"].get(kind, [{}])[0]
            check(f"{kind} {tf}", truth["sources"][tkey][tf], g.get(gf).value if g.get(gf) else None)
    return bad, n
