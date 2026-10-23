"""Generate the 24 FICTIONAL test clients into inputs/test_clients/.

Run from the project root:
    .venv\\Scripts\\python scripts\\testgen\\generate.py

Steps per client: compute each year with starter/tax_engine.py (compute() then
assign_payments()), build rounded form lines, check that everything reconciles,
draw the PDFs, then turn the scan clients' PDFs into image-only scans.
Finally write answer_key.csv / answer_key.json and a reconciliation report.
"""
import copy
import csv
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT / "starter")]

import numpy as np                                  # noqa: E402
from PIL import Image, ImageFilter                  # noqa: E402
from tax_engine import compute, assign_payments    # noqa: E402

import returns                                      # noqa: E402
import sources                                      # noqa: E402
from specs import CLIENTS                           # noqa: E402

OUT = ROOT / "inputs" / "test_clients"
PDFTOPPM = shutil.which("pdftoppm") or next(
    (str(p) for p in (Path.home() / "AppData/Local/Microsoft/WinGet/Packages").glob("*Poppler*/**/pdftoppm.exe")), None)

AREA = {"Mankato": "507", "Woodbury": "651", "Edina": "952", "Minneapolis": "612", "Rochester": "507", "Duluth": "218",
        "Plymouth": "763", "St. Cloud": "320", "Lakeville": "952", "Stillwater": "651", "Owatonna": "507",
        "Maple Grove": "763", "Brainerd": "218", "Winona": "507", "Northfield": "507", "Moorhead": "218",
        "Eden Prairie": "952", "Bemidji": "218", "Alexandria": "320", "Savage": "952", "Willmar": "320",
        "Minnetonka": "952"}
PAYER_STREETS = ["100 Commerce Way", "2200 Granite Blvd", "45 Riverfront Plaza", "880 Industrial Pkwy",
                 "1500 Lakeshore Dr", "310 Main St", "77 Harbor View Rd", "4100 Prairie Center Dr",
                 "620 Mill Pond Ln", "1250 Ridgewood Ave", "999 Summit Ave", "18 Depot St"]
PAYER_CITIES = [("Minneapolis", "55402"), ("St. Paul", "55101"), ("Rochester", "55901"), ("Duluth", "55802"),
                ("Bloomington", "55420"), ("St. Cloud", "56301"), ("Mankato", "56001"), ("Eagan", "55121")]
PREPARER = {"name": "Sample Preparer (fictional)", "ptin": "P00000000", "firm": "Lakeside Sample Tax Office (fictional)",
            "ein": "00-0000001", "phone": "612-555-0100"}


class Registry:
    """Gives each fictional payer a stable EIN, address, and phone."""
    def __init__(self):
        self.eins, self.n = {}, 1001

    def ein(self, name):
        if name not in self.eins:
            self.eins[name] = f"00-000{self.n}"
            self.n += 1
        return self.eins[name]

    def addr(self, name, city=None, zip_=None):
        k = int(self.ein(name)[-4:])
        if not city:
            city, zip_ = PAYER_CITIES[k % len(PAYER_CITIES)]
        return [PAYER_STREETS[k % len(PAYER_STREETS)], f"{city}, MN {zip_}   555-01{k % 100:02d}"]


REG = Registry()


def slug(s, n=28):
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s[:n].rstrip("_")


def assign_ids(c):
    num = int(c["id"][1:])
    c["t"]["ssn"] = f"000-00-{num:02d}01"
    if c["spouse"]:
        c["spouse"]["ssn"] = f"000-00-{num:02d}02"
    for y in c["years"].values():
        if y.get("spouse"):
            y["spouse"]["ssn"] = f"000-00-{num:02d}03"
    seen = {}
    for y in sorted(c["years"]):
        for d in c["years"][y]["dependents"]:
            key = (d["first"], d["dob"])
            if key not in seen:
                seen[key] = f"000-00-{num:02d}{11 + len(seen)}"
            d["ssn"] = seen[key]
    city = c["address"][1]
    c["phone"] = f"{AREA.get(city, '612')}-555-01{num:02d}"
    c["email"] = f"{c['t']['first']}.{c['t']['last']}@example.com".lower()
    c["folder"] = f"{c['id']}_{c['t']['last']}_{c['t']['first']}"


# ---------------------------------------------------------------------
def run_year(c, year):
    """Engine run for one client-year. Returns (p, r, forms, ctx)."""
    p = copy.deepcopy(c["years"][year])
    spouse = p.get("spouse", c["spouse"])
    p["dob"] = c["t"]["dob"]
    if p["status"] == "mfj":
        p["sdob"] = spouse["dob"]
    r = compute(p, year)
    target = p.get("pay_ratio", 1.0) * r["total_tax"]
    if p.get("fill_1099r_wh"):
        need = target - sum(s.get("wh", 0) for s in p.get("ss", [])) - p.get("est_payments", 0)
        dists = [d for d in p.get("ira_dist", []) + p.get("pension", []) if d["code"] != "G"]
        tot = sum(d["gross"] for d in dists)
        for d in dists:
            d["wh"] = max(0, round(need * d["gross"] / tot))
    if p.get("est_share"):
        p["est_payments"] = round(target * p["est_share"], -2)
    r = assign_payments(p, r)
    f = returns.build(p, r, year)
    people = {"t": c["t"], "s": spouse if p["status"] == "mfj" else None}
    ctx = returns.ReturnCtx(year, p["status"], c["t"], people["s"], p["dependents"], c["address"], PREPARER, REG.ein)
    return p, r, f, ctx


def reconcile(c, year, p, r, f):
    """Return a list of (check, expected, actual, ok) rows."""
    L = f["1040"]
    agi = L["11a" if year == 2025 else "11"]
    rows = []

    def chk(name, exp, act, tol=0):
        rows.append((name, round(exp), round(act), abs(exp - act) <= tol))

    chk("AGI = line 9 - line 10", L["9"] - L["10"], agi)
    chk("AGI vs engine", r["agi"], agi, 2)
    chk("Taxable income vs engine", r["taxable_income"], L["15"], 3)
    chk("Total tax vs engine", r["total_tax"], L["24"], 3)
    chk("Refund vs engine", r["refund"], L["34"], 4)
    chk("Amount owed vs engine", r["owed"], L["37"], 4)
    chk("Line 9 = sum of income lines",
        sum(L[k] for k in ["1z", "2b", "3b", "4b", "5b", "6b", "7", "8"]), L["9"])
    chk("W-2 box 1 total = line 1a", sum(w["wages"] for w in p.get("w2s", [])), L["1a"])
    chk("W-2 box 2 total = line 25a", sum(w.get("fed_wh", 0) for w in p.get("w2s", [])), L["25a"])
    chk("1099-INT box 1 total = line 2b", sum(a for _, a in p.get("interest", [])), L["2b"])
    chk("1099-DIV box 1a total = line 3b", sum(d[1] for d in p.get("dividends", [])), L["3b"])
    chk("1099-DIV box 1b total = line 3a", sum(d[2] for d in p.get("dividends", [])), L["3a"])
    chk("1099-R (IRA) box 1 total = line 4a", sum(d["gross"] for d in p.get("ira_dist", [])), L["4a"])
    chk("1099-R (plans) box 1 total = line 5a", sum(d["gross"] for d in p.get("pension", [])), L["5a"])
    chk("SSA-1099 box 5 total = line 6a", sum(s["amount"] for s in p.get("ss", [])), L["6a"])
    chk("1099 withholding total = line 25b",
        sum(d.get("wh", 0) for d in p.get("ira_dist", []) + p.get("pension", []) + p.get("ss", []))
        + p.get("unemployment_wh", 0), L["25b"])
    if "Sch 1" in f:
        s1 = f["Sch 1"]
        chk("Schedule 1 line 10 = line 8", s1["10"], L["8"])
        chk("Schedule 1 line 26 = line 10", s1["26"], L["10"])
    if "Sch C" in f:
        chk("Schedule C line 31 = Schedule 1 line 3", f["Sch C"]["31"], f["Sch 1"]["3"])
    if "Sch D" in f:
        chk("Schedule D line 16 = line 7", f["Sch D"]["16"], L["7"])
    if "Sch B" in f:
        chk("Schedule B line 4 = line 2b", f["Sch B"]["4"], L["2b"])
        chk("Schedule B line 6 = line 3b", f["Sch B"]["6"], L["3b"])
    if "Sch 2" in f:
        chk("Schedule 2 line 21 = line 23", f["Sch 2"]["21"], L["23"])
    if "Sch A" in f:
        chk("Schedule A line 17 = line 12", f["Sch A"]["17"], L["12"])
    if p.get("nec") or p.get("k_1099"):
        chk("1099-NEC + 1099-K totals = Sch C line 1",
            sum(a for _, a in p.get("nec", []) + p.get("k_1099", [])), f["Sch C"]["1"])
    chk("Payments line 33 = 25d + 26 + 32", L["25d"] + L["26"] + L["32"], L["33"])
    return rows


# ---------------------------------------------------------------------
def render_sources(c, year, p, ctx, folder):
    """Draw one PDF per source document. Returns [(filename, description)]."""
    docs = []
    addr = c["address"]
    people = {"t": ctx.t, "s": ctx.s}
    joint = ctx.names
    tin = ctx.t["ssn"]

    def name_of(who):
        x = people[who]
        return f"{x['first']} {x['last']}"

    def out(kind, who_name, payer):
        fn = f"{year}_{kind}_{slug(payer)}_{slug(who_name.split()[0], 12)}.pdf"
        return folder / fn, fn

    for w in p.get("w2s", []):
        path, fn = out("W-2", name_of(w["who"]), w["employer"])
        emp_addr = [REG.addr(w["employer"], w["emp_city"], w["emp_zip"])[0], f"{w['emp_city']}, MN {w['emp_zip']}"]
        sources.w2_pdf(path, year, w, people[w["who"]], REG.ein(w["employer"]), addr, emp_addr)
        docs.append((fn, f"Form W-2 from {w['employer']}"))
    for i, (payer, amt) in enumerate(p.get("interest", [])):
        path, fn = out("1099-INT", joint, payer)
        sources.int_1099(path, year, payer, REG.ein(payer), REG.addr(payer), joint, tin, addr, amt,
                         f"XXXX{4100 + i * 37 + int(c['id'][1:])}")
        docs.append((fn, f"Form 1099-INT from {payer}"))
    for payer, od, qd, cg in p.get("dividends", []):
        path, fn = out("1099-DIV", joint, payer)
        sources.div_1099(path, year, payer, REG.ein(payer), REG.addr(payer), joint, tin, addr, od, qd, cg,
                         f"XXXX{5200 + int(c['id'][1:])}")
        docs.append((fn, f"Form 1099-DIV from {payer}"))
    if p.get("brokerage"):
        b = p["brokerage"]
        path, fn = out("1099-B", joint, b["broker"])
        sources.b_1099(path, year, b, REG.ein(b["broker"]), REG.addr(b["broker"]), joint, tin, addr,
                       f"XXXX{5200 + int(c['id'][1:])}")
        docs.append((fn, f"Form 1099-B summary from {b['broker']}"))
    for d in p.get("ira_dist", []) + p.get("pension", []):
        who = people[d["who"]]
        path, fn = out("1099-R", name_of(d["who"]), d["payer"])
        sources.r_1099(path, year, d, REG.addr(d["payer"]), REG.ein(d["payer"]), name_of(d["who"]), who["ssn"], addr,
                       f"XXXX{6300 + int(c['id'][1:])}")
        docs.append((fn, f"Form 1099-R from {d['payer']} (code {d['code']})"))
    for s in p.get("ss", []):
        path, fn = out("SSA-1099", name_of(s["who"]), "Social_Security")
        sources.ssa_1099(path, year, people[s["who"]], addr, s["amount"], s.get("wh", 0))
        docs.append((fn, f"Form SSA-1099 for {name_of(s['who'])}"))
    if p.get("unemployment"):
        payer = "North Star State Unemployment Insurance Office (fictional)"
        path, fn = out("1099-G", name_of("t"), "Unemployment_Insurance")
        sources.g_1099(path, year, payer, REG.ein(payer), REG.addr(payer, "St. Paul", "55101"), name_of("t"), tin, addr,
                       p["unemployment"], p.get("unemployment_wh", 0))
        docs.append((fn, "Form 1099-G (unemployment compensation)"))
    if p.get("home_sale"):
        hs = p["home_sale"]
        path, fn = out("1099-S", joint, hs["settlement_agent"])
        sources.s_1099(path, year, hs, hs["settlement_agent"], REG.ein(hs["settlement_agent"]),
                       REG.addr(hs["settlement_agent"], "Stillwater", "55082"), joint, tin, addr)
        docs.append((fn, f"Form 1099-S from {hs['settlement_agent']}"))
    for payer, amt in p.get("nec", []):
        path, fn = out("1099-NEC", name_of("t"), payer)
        sources.nec_1099(path, year, payer, REG.ein(payer), REG.addr(payer, "Moorhead", "56560"),
                         name_of("t"), tin, addr, amt)
        docs.append((fn, f"Form 1099-NEC from {payer}"))
    for payer, amt in p.get("k_1099", []):
        path, fn = out("1099-K", name_of("t"), payer)
        sources.k_1099(path, year, payer, REG.ein(payer), REG.addr(payer), name_of("t"), tin, addr, amt)
        docs.append((fn, f"Form 1099-K from {payer}"))
    if p.get("k1"):
        k1 = p["k1"]
        path, fn = out("K-1_1120S", name_of(k1["who"]), k1["corp"])
        sources.k1_1120s(path, year, k1, REG.ein(k1["corp"]), REG.addr(k1["corp"], addr[1], addr[2]),
                         people[k1["who"]], addr)
        docs.append((fn, f"Schedule K-1 (Form 1120-S) from {k1['corp']}" + (" — FINAL" if k1.get("final") else "")))
    if p.get("iso"):
        iso = p["iso"]
        path, fn = out("3921", name_of("t"), iso["company"])
        sources.f3921(path, year, iso, REG.ein(iso["company"]), REG.addr(iso["company"]), people["t"], addr)
        docs.append((fn, f"Form 3921 (ISO exercise) from {iso['company']}"))
    it = p.get("itemized")
    if it and it.get("lender"):
        path, fn = out("1098", joint, it["lender"])
        sources.f1098(path, year, it, REG.ein(it["lender"]), REG.addr(it["lender"]), joint, tin, addr)
        docs.append((fn, f"Form 1098 from {it['lender']}"))
    return docs


# ---------------------------------------------------------------------
def scan_pdf(path, rng):
    """Replace a PDF with an image-only 'scan': 150 dpi gray, slight rotation, noise, blur."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([PDFTOPPM, "-r", "150", "-gray", "-png", str(path), str(Path(tmp) / "pg")],
                       check=True, capture_output=True)   # Poppler warns about missing optional fonts; harmless
        pages = []
        for png in sorted(Path(tmp).glob("pg*.png")):
            im = Image.open(png).convert("L")
            angle = rng.choice([-1, 1]) * rng.uniform(0.4, 1.5)
            im = im.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=255)
            a = np.asarray(im, dtype=np.float32)
            a = a * 0.93 + 10                                    # slightly gray paper, lighter ink
            a += np.random.default_rng(rng.randint(0, 10**6)).normal(0, 9, a.shape)
            im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
            pages.append(im)
        pages[0].save(path, "PDF", resolution=150, save_all=True, append_images=pages[1:])


# ---------------------------------------------------------------------
def truth_for_year(c, year, p, r, f, ctx):
    L = f["1040"]
    t65 = int(ctx.t["dob"][:4]) < year - 64
    s65 = bool(ctx.s) and int(ctx.s["dob"][:4]) < year - 64
    srcs = {
        "w2": [{"who": w["who"], "employer": w["employer"], "box1": w["wages"], "box2": w.get("fed_wh", 0),
                "box12": {k: v for k, v in (("D", w.get("k401", 0)), ("W", w.get("hsa", 0))) if v},
                "box13_retirement_plan": bool(w.get("ret_plan"))} for w in p.get("w2s", [])],
        "1099_int": [{"payer": a, "box1": b} for a, b in p.get("interest", [])],
        "1099_div": [{"payer": d[0], "box1a": d[1], "box1b": d[2], "box2a": d[3]} for d in p.get("dividends", [])],
        "1099_r": [{"who": d["who"], "payer": d["payer"], "box1": d["gross"], "box2a": d["box2a"], "box4": d.get("wh", 0),
                    "box7": d["code"], "ira_sep_simple": d.get("ira", False), "form_1040_line": "4a" if d in p.get("ira_dist", []) else "5a"}
                   for d in p.get("ira_dist", []) + p.get("pension", [])],
        "ssa_1099": [{"who": s["who"], "box5": s["amount"], "box6": s.get("wh", 0)} for s in p.get("ss", [])],
    }
    if p.get("k1"):
        srcs["k1_1120s"] = {"box1": p["k1"]["ordinary"], "final": p["k1"].get("final", False)}
    if p.get("home_sale"):
        srcs["1099_s"] = {"box2": p["home_sale"]["price"]}
    if p.get("unemployment"):
        srcs["1099_g"] = {"box1": p["unemployment"], "box4": p.get("unemployment_wh", 0)}
    if p.get("iso"):
        srcs["3921"] = {"spread": round((p["iso"]["fmv"] - p["iso"]["price"]) * p["iso"]["shares"])}
    forms = {k: v for k, v in f.items() if k != "1040"}
    return {
        "filing_status": p["status"],
        "born_before_checkbox": {"you": t65, "spouse": s65},
        "spouse": ({"name": f"{ctx.s['first']} {ctx.s['last']}", "dob": ctx.s["dob"], "deceased": ctx.s.get("died")}
                   if ctx.s else None),
        "dependents": [{"name": f"{d['first']} {d['last']}", "dob": d["dob"], "age": year - int(d["dob"][:4]),
                        "relationship": d["rel"]} for d in p["dependents"]],
        "form_1040": L,
        "forms_attached": sorted(forms),
        "schedules": forms,
        "sources": srcs,
        "itemized_charity": f.get("Sch A", {}).get("14", 0),
        "qcd": p.get("qcd", 0),
        "engine": {k: round(r[k], 2) for k in ("agi", "taxable_income", "total_tax", "refund", "owed", "niit", "amt")},
    }


def main():
    if not PDFTOPPM:
        sys.exit("pdftoppm not found. Install Poppler (winget install oschwartz10612.Poppler).")
    OUT.mkdir(parents=True, exist_ok=True)
    # Clear old PDFs but keep the folders (OneDrive can lock a folder being deleted).
    for old in OUT.glob("C[0-9][0-9]_*/*.pdf"):
        old.unlink()
    rng = random.Random(20251231)
    key, report, failures = [], [], 0

    for c in CLIENTS:
        assign_ids(c)
        folder = OUT / c["folder"]
        folder.mkdir(exist_ok=True)
        docs, truth, lines_by_year = [], {}, {}
        for year in sorted(c["years"], reverse=True):
            p, r, f, ctx = run_year(c, year)
            fn = f"{year}_Form_1040_and_Schedules.pdf"
            returns.render_return(folder / fn, ctx, p, f)
            attached = ", ".join(k for k in f if k != "1040")
            docs.append((fn, f"{year} Form 1040" + (f" with {attached}" if attached else "")))
            if year == 2025:
                docs += render_sources(c, year, p, ctx, folder)
            rows = reconcile(c, year, p, r, f)
            bad = [x for x in rows if not x[3]]
            failures += len(bad)
            report.append(f"{c['id']} {year}: {len(rows) - len(bad)}/{len(rows)} checks pass"
                          + "".join(f"\n    FAIL {n}: expected {e:,} got {a:,}" for n, e, a, _ in bad))
            truth[str(year)] = truth_for_year(c, year, p, r, f, ctx)
            lines_by_year[year] = f["1040"]

        people = {"t": c["t"], "s": c["spouse"]}
        status = c["years"][2025]["status"]
        docs.sort(key=lambda d: (not d[0][:4].isdigit(), d[0]))
        sources.profile_pdf(folder / "00_Client_Profile_Summary.pdf", c, people,
                            c["years"][2025]["dependents"], status,
                            {"phone": c["phone"], "email": c["email"]}, docs)

        if c.get("scan"):
            for pdf in sorted(folder.glob("*.pdf")):
                is_source = not (pdf.name.startswith("00_") or "Form_1040" in pdf.name)
                if c["scan"] == "all" or is_source:
                    scan_pdf(pdf, rng)

        L25 = lines_by_year[2025]
        names = [f"{c['t']['first']} {c['t']['last']}"] + ([f"{c['spouse']['first']} {c['spouse']['last']}"] if c["spouse"] else [])
        ages = [2025 - int(c["t"]["dob"][:4])] + ([2025 - int(c["spouse"]["dob"][:4])] if c["spouse"] else [])
        key.append({
            "id": c["id"], "folder": c["folder"], "names": names, "ages": ages, "filing_status": status,
            "agi_2025": L25["11a"], "agi_2024": lines_by_year[2024]["11"] if 2024 in lines_by_year else None,
            "has_2024": 2024 in lines_by_year, "scan": c.get("scan") or "none",
            "refund_2025": L25["34"], "amount_owed_2025": L25["37"],
            "designed_signals": c["answer"]["signals"], "narrative": c["answer"]["narrative"],
            "intended": {"aum_fit": c["answer"]["aum"], "annuity_band": c["answer"]["annuity"],
                         "life_band": c["answer"]["life"]},
            "truth": truth,
        })
        print(f"{c['id']} {c['folder']}: AGI {L25['11a']:,}  refund {L25['34']:,}  owed {L25['37']:,}")

    meta = {
        "description": "Answer key for the 24 FICTIONAL test clients. See README.md.",
        "tax_year": 2025,
        "band_definitions": {
            "aum_fit": {"high": "score >= 60", "med": "30 <= score < 60", "low": "score < 30"},
            "grades": {"A": ">= 70", "B": ">= 50", "C": ">= 35", "D": ">= 20", "F": "< 20"},
            "band_format": "'A-B' means grade A or B is acceptable; 'D-F' means D or F.",
        },
        "signal_ids": "product.rule, e.g. aum.rollover_100k, annuity.transition, life.dependents",
    }
    (OUT / "answer_key.json").write_text(json.dumps({"meta": meta, "clients": key}, indent=2), encoding="utf-8")
    with open(OUT / "answer_key.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["id", "names", "ages", "filing_status", "agi_2025", "agi_2024", "has_2024", "scan",
                     "refund_2025", "amount_owed_2025", "designed_signals", "aum_fit", "annuity_band", "life_band",
                     "narrative"])
        for k in key:
            wr.writerow([k["id"], " & ".join(k["names"]), "/".join(map(str, k["ages"])), k["filing_status"],
                         k["agi_2025"], k["agi_2024"] or "", k["has_2024"], k["scan"], k["refund_2025"],
                         k["amount_owed_2025"], ";".join(k["designed_signals"]), k["intended"]["aum_fit"],
                         k["intended"]["annuity_band"], k["intended"]["life_band"], k["narrative"]])
    (OUT / "reconciliation_report.txt").write_text(
        "Reconciliation checks (printed form lines vs. source documents and vs. the tax engine)\n\n"
        + "\n".join(report) + f"\n\nTotal failures: {failures}\n", encoding="utf-8")
    print(f"\nReconciliation failures: {failures}")
    return failures


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
