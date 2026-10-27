"""Tax Return Grader - command line.

    python -m src.grader ../inputs/clients --out ../outputs/<run>      (run from the app folder)

Easiest: double-click "Grade My Clients.bat" in the main folder.

<folder> is either one client folder (PDFs inside) or a folder of client
folders. For each client: read the PDFs (OCR for scans), extract the figures,
cross-check them, evaluate the signal rules in config/grader.yaml, and write
an HTML report. A ranked summary.csv / summary.html covers the batch, and
export.html (printable) / results.xlsx (Excel) put everything in one place.

Runs entirely on this computer. No client data is sent anywhere.
"""
import argparse
import json
import logging
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import yaml

from . import export, paths, report
from .brief import build_brief
from .privacy import consent_from_file, mask_ssn
from .record import build_record
from .signals import evaluate, score
from .validate import analyze_year, check_context

DEFAULT_CONFIG = paths.CONFIG
log = logging.getLogger("grader")

FIGURE_ROWS = [("agi", "Adjusted gross income"), ("total_income", "Total income"), ("wages", "Wages"),
               ("interest", "Taxable interest"), ("dividends", "Ordinary dividends"), ("cap_gain", "Capital gain"),
               ("ira_gross", "IRA distributions"), ("pen_gross", "Pensions and annuities"),
               ("ss", "Social Security benefits"), ("sch_c_net", "Schedule C net profit"),
               ("sch_f_net", "Schedule F net farm profit"),
               ("k1_ordinary", "S-corp K-1 income"), ("sch_e_total", "Schedule E total"),
               ("taxable_income", "Taxable income"), ("total_tax", "Total tax"), ("niit", "NIIT"), ("amt", "AMT"),
               ("charity", "Itemized charity"), ("refund", "Refund"), ("owed", "Amount owed")]


TITLES = {"dr", "mr", "mrs", "ms", "miss", "prof"}


def first_name(name):
    """'Dr. Samuel Adeyemi' -> 'Samuel' (role placeholders like 'spouse' pass through)."""
    words = [w for w in name.split() if w.lower().strip(".") not in TITLES]
    return words[0] if words else name


def load_config(path=None):
    return yaml.safe_load(Path(path or DEFAULT_CONFIG).read_text(encoding="utf-8"))


def check_consent(folder):
    """(allowed, explanation). Real clients need consent_7216: true; fictional test clients are exempt."""
    ok, why = consent_from_file(folder)
    if ok is not None:
        return ok, why
    # No client.yaml: only fictional test data may be graded. Peek at the profile summary only.
    from .classify import classify_page
    from .extract import parse_profile
    from .ingest import read_pdf
    for pdf in sorted(Path(folder).glob("*.pdf")):
        if "profile" not in pdf.name.lower():
            continue
        pages = read_pdf(pdf)
        if pages and classify_page(pages[0], pdf.name) == "profile" and parse_profile(pages[0])["test_client"]:
            return True, "fictional test client (exempt)"
    return False, ("no IRC §7216 consent on file. Add client.yaml with 'consent_7216: true' to the client "
                   "folder once the client's written consent is on file.")


def grade_client(folder, cfg, cache_dir=None, files=None):
    folder = Path(folder)
    allowed, why = check_consent(folder)
    if not allowed:
        return {"client": folder.name, "status": "not graded", "reason": why}
    rec = build_record(folder, cache_dir, files)
    years = sorted(y for y, yr in rec["years"].items() if yr["f1040"] or yr["sources"])
    if not years:
        return {"client": folder.name, "status": "not graded", "reason": "no tax documents recognized",
                "warnings": rec["warnings"]}
    with_1040 = [y for y in years if rec["years"][y]["f1040"]]
    year = max(with_1040 or years)
    prior = year - 1 if (year - 1) in rec["years"] and rec["years"][year - 1]["f1040"] else None
    tol = cfg.get("validation", {}).get("tolerance", 1)
    figs = analyze_year(year, rec["years"][year], tol)
    pfigs = analyze_year(prior, rec["years"][prior], tol) if prior else None
    sigs = evaluate(rec, year, figs, prior, pfigs, cfg)
    scores = score(sigs, cfg)

    warnings = list(rec["warnings"]) + figs.warnings + ([f"{prior}: {w}" for w in pfigs.warnings] if pfigs else [])
    for y in years:
        if y not in (year, prior) and not rec["years"][y]["f1040"]:
            warnings.append(f"Documents for {y} were found but there is no {y} return; they were not used.")
    if not rec.get("profile"):
        warnings.append("No client profile summary found; ages come from the 1040 checkboxes / SSA-1099 only.")
    if not with_1040:
        warnings.append("No Form 1040 found; grading from source documents only.")

    figures = [{"key": k, "label": lbl, "value": figs.get(k, None),
                "source": figs.fact(k).where() if figs.fact(k) else "",
                "prior": pfigs.get(k, None) if pfigs else None}
               for k, lbl in FIGURE_ROWS if figs.fact(k) is not None]
    yr0 = rec["years"][year]
    n_before = len(figs.warnings)
    check_context(yr0, figs, {s.id for s in sigs}, tol)
    warnings += figs.warnings[n_before:]
    brief = build_brief(sigs, scores, cfg, year, figures, (rec.get("profile") or {}).get("notes"),
                        yr0.get("context"), yr0.get("forms"))

    yr = rec["years"][year]
    h = yr.get("header", {})
    prof = rec.get("profile") or {}
    names = [x["name"] for x in prof.get("people", [])] or [
        p["name"].value for p in (h.get("taxpayer"), h.get("spouse")) if p and p.get("name")]
    from .signals import Ctx
    ages = [(first_name(n), a) for _, n, a, _ in Ctx(rec, year, figs, prior, pfigs).people()]
    status_map = {"single": "Single", "mfj": "Married filing jointly", "mfs": "Married filing separately",
                  "hoh": "Head of household", "qss": "Qualifying surviving spouse"}
    st = h.get("status").value if h.get("status") else prof.get("filing_status")
    docs = {}
    for d in rec["docs"]:
        e = docs.setdefault(d["doc"], {"doc": d["doc"], "pages": 0, "kinds": [], "ocr": False})
        e["pages"] += 1
        e["ocr"] |= d["ocr"]
        if d["kind"] not in e["kinds"]:
            e["kinds"].append(d["kind"])
    return {
        "client": folder.name, "status": "graded", "consent": why, "year": year, "prior_year": prior,
        "names": names, "ages": ages, "filing_status": status_map.get(st, st or "unknown"),
        "scores": scores,
        "signals": [s.__dict__ for s in sigs],
        "brief": brief,
        "talking_points": brief["opener"],
        "warnings": [mask_ssn(w) for w in warnings],
        "figures": figures,
        "documents": [{**d, "kinds": ", ".join(d["kinds"])} for d in docs.values()],
        "_record": rec, "_figs": figs, "_pfigs": pfigs,
    }


def client_folders(path):
    path = Path(path)
    if any(path.glob("*.pdf")):
        return [path]
    return sorted(p for p in path.iterdir() if p.is_dir() and any(p.glob("*.pdf")))


def _work(args):
    folder, cfg, cache = args
    try:
        r = grade_client(folder, cfg, cache)
    except Exception as e:                     # one bad client must not stop the batch
        log.exception("failed on %s", Path(folder).name)
        r = {"client": Path(folder).name, "status": "not graded", "reason": f"error: {e}"}
    for k in ("_record", "_figs", "_pfigs"):
        r.pop(k, None)
    return r


def run(input_path, out_dir, config=None, cache_dir=None, workers=1):
    cfg = load_config(config)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    folders = client_folders(input_path)
    jobs = [(f, cfg, cache_dir) for f in folders]
    if workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_work, jobs))
    else:
        results = [_work(j) for j in jobs]
    for r in results:
        report.write_client(r, out_dir)
    report.write_summary(results, out_dir)
    export.write_export(results, out_dir)
    (out_dir / "results.json").write_text(mask_ssn(json.dumps(results, indent=2, default=str)), encoding="utf-8")
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m src.grader", description="Grade client tax returns (runs locally).")
    ap.add_argument("input", help="a client folder, or a folder of client folders")
    ap.add_argument("--out", default=str(paths.OUTPUTS / "run"), help="output folder (default outputs/run)")
    ap.add_argument("--config", default=None, help="config YAML (default config/grader.yaml)")
    ap.add_argument("--cache", default=None, help="optional folder to cache OCR results (keep it private/local)")
    ap.add_argument("--workers", type=int, default=1, help="clients to process in parallel (default 1)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not Path(a.input).is_dir() or not client_folders(a.input):
        print(f"No client folders with PDFs found in {Path(a.input).resolve()}.\n"
              "Put one folder per client there (see inputs/clients/README.txt), then run again.")
        return 1
    results = run(a.input, a.out, a.config, a.cache, a.workers)
    for r in sorted(results, key=lambda r: -(r.get("scores", {}).get("aum_score", -1))):
        if r["status"] == "graded":
            s = r["scores"]
            print(f"{r['client']:<28} AUM {s['aum_score']:>3.0f} {s['aum_fit']:<4}  Annuity {s['annuity_grade']}  "
                  f"Life {s['life_grade']}  warnings {len(r['warnings'])}")
        else:
            print(f"{r['client']:<28} NOT GRADED: {r['reason']}")
    print(f"\nReports: {Path(a.out) / 'summary.html'}")


if __name__ == "__main__":
    sys.exit(main())
