"""HTML reports: one page per client, plus a ranked batch summary (HTML and CSV)."""
import csv
import html
from pathlib import Path

from .privacy import mask_ssn

CSS = """
:root { --ink:#1d2433; --muted:#5b6476; --line:#e2e5ec; --bg:#f6f7f9; --card:#fff;
        --high:#1f7a4d; --med:#b7791f; --low:#8a8f98; --warn:#9b2c2c; }
* { box-sizing: border-box; }
body { font: 14px/1.45 -apple-system, Segoe UI, Roboto, Arial, sans-serif; color: var(--ink); background: var(--bg);
       margin: 0; padding: 24px 16px; }
main { max-width: 1040px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 4px; } h2 { font-size: 16px; margin: 28px 0 8px; }
.sub { color: var(--muted); margin-bottom: 16px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }
.card .k { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
.card .v { font-size: 30px; font-weight: 700; margin-top: 2px; }
.card .n { color: var(--muted); font-size: 13px; }
.fit-high { color: var(--high); } .fit-med { color: var(--med); } .fit-low { color: var(--low); }
.g-A, .g-B { color: var(--high); } .g-C { color: var(--med); } .g-D, .g-F { color: var(--low); }
table { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--line);
        border-radius: 10px; overflow: hidden; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { background: #eef0f4; font-size: 12px; text-transform: uppercase; letter-spacing: .03em; color: var(--muted); }
td.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
.src { color: var(--muted); font-size: 12px; }
ul.tp li { margin: 4px 0; }
.warn { color: var(--warn); }
.pill { display: inline-block; padding: 1px 8px; border-radius: 99px; font-size: 12px; background: #eef0f4; }
.wrap { overflow-x: auto; }
a { color: #2b5bb8; }
@media (max-width: 700px) { .sigcol { display: none; } }
@media print { body { background: #fff; } .card, table { break-inside: avoid; } }
"""


def esc(x):
    return html.escape(mask_ssn(x))


def money(v):
    return "" if v is None else f"${v:,.0f}"


def page(title, body):
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width, initial-scale=1'><title>{esc(title)}</title><style>{CSS}</style></head>"
            f"<body><main>{body}</main></body></html>")


def client_html(r):
    if r["status"] != "graded":
        body = (f"<h1>{esc(r['client'])}</h1><p class='sub'>Not graded</p>"
                f"<p class='warn'>{esc(r['reason'])}</p>")
        return page(r["client"], body)
    s = r["scores"]
    names = " & ".join(r["names"]) or r["client"]
    ages = ", ".join(f"{n} {a}" for n, a in r["ages"])
    out = [f"<h1>{esc(names)}</h1>",
           f"<div class='sub'>{esc(r['client'])} &middot; Tax year {r['year']} &middot; {esc(r['filing_status'])}"
           f"{' &middot; ' + esc(ages) if ages else ''} &middot; Prior year on file: {r['prior_year'] or 'no'}"
           f" &middot; Consent: {esc(r['consent'])}</div>",
           "<div class='cards'>",
           f"<div class='card'><div class='k'>AUM fit</div><div class='v fit-{s['aum_fit']}'>{s['aum_score']:.0f}"
           f"<span style='font-size:16px'>/100</span></div><div class='n'>{s['aum_fit'].upper()} fit</div></div>",
           f"<div class='card'><div class='k'>Annuity</div><div class='v g-{s['annuity_grade']}'>{s['annuity_grade']}</div>"
           f"<div class='n'>{s['annuity_points']:.0f} points</div></div>",
           f"<div class='card'><div class='k'>Life insurance</div><div class='v g-{s['life_grade']}'>{s['life_grade']}</div>"
           f"<div class='n'>{s['life_points']:.0f} points</div></div>",
           "</div>"]
    out.append("<h2>Talking points</h2>")
    out.append("<ul class='tp'>" + "".join(f"<li>{esc(t)}</li>" for t in r["talking_points"]) + "</ul>"
               if r["talking_points"] else "<p class='sub'>No signals fired.</p>")
    out.append("<h2>Signals that fired</h2>")
    for prod, title in (("aum", "AUM"), ("annuity", "Annuity"), ("life", "Life")):
        sigs = [x for x in r["signals"] if x["product"] == prod]
        total = sum(x["points"] for x in sigs)
        out.append(f"<h3 style='font-size:14px;margin:14px 0 6px'>{title} &middot; {total:.0f} points</h3>")
        if not sigs:
            out.append("<p class='sub'>None</p>")
            continue
        out.append("<div class='wrap'><table><tr><th>Rule</th><th>Points</th><th>Value</th><th>Detail</th>"
                   "<th>Source (document, line/box)</th></tr>")
        for x in sigs:
            out.append(f"<tr><td>{esc(x['label'])}<div class='src'>{esc(x['id'])}</div></td>"
                       f"<td class='num'>{x['points']:+.0f}</td><td class='num'>{esc(x['value'])}</td>"
                       f"<td>{esc(x['detail'])}</td><td class='src'>{'<br>'.join(esc(s) for s in x['sources'])}</td></tr>")
        out.append("</table></div>")
    raw_aum = sum(x["points"] for x in r["signals"] if x["product"] == "aum")
    if raw_aum > s["aum_score"]:
        out.append(f"<p class='sub'>AUM signals add up to {raw_aum:.0f}; the score is capped at {s['aum_score']:.0f}.</p>")
    out.append("<h2>Validation warnings</h2>")
    out.append("<ul>" + "".join(f"<li class='warn'>{esc(w)}</li>" for w in r["warnings"]) + "</ul>"
               if r["warnings"] else "<p class='sub'>None. Every cross-check agreed.</p>")
    out.append("<h2>Key figures</h2><div class='wrap'><table><tr><th>Figure</th>"
               f"<th>{r['year']}</th><th>Source</th>" + (f"<th>{r['prior_year']}</th>" if r["prior_year"] else "") + "</tr>")
    for row in r["figures"]:
        out.append(f"<tr><td>{esc(row['label'])}</td><td class='num'>{money(row['value'])}</td>"
                   f"<td class='src'>{esc(row['source'])}</td>"
                   + (f"<td class='num'>{money(row['prior'])}</td>" if r["prior_year"] else "") + "</tr>")
    out.append("</table></div>")
    out.append("<h2>Documents read</h2><div class='wrap'><table><tr><th>File</th><th>Pages</th><th>Detected as</th>"
               "<th>Read by</th></tr>")
    for d in r["documents"]:
        out.append(f"<tr><td>{esc(d['doc'])}</td><td class='num'>{d['pages']}</td><td>{esc(d['kinds'])}</td>"
                   f"<td>{'OCR (scan)' if d['ocr'] else 'text'}</td></tr>")
    out.append("</table></div>")
    out.append("<p class='sub' style='margin-top:24px'>Generated locally by the Tax Return Grader. "
               "SSNs are masked. Scores come from config/grader.yaml.</p>")
    return page(names, "".join(out))


def write_client(r, out_dir):
    f = Path(out_dir) / "clients" / f"{r['client']}.html"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(client_html(r), encoding="utf-8")
    return f


SUMMARY_COLS = ["rank", "client", "names", "year", "aum_score", "aum_fit", "annuity_grade", "annuity_points",
                "life_grade", "life_points", "signals", "warnings", "status"]


def summary_rows(results):
    graded = sorted([r for r in results if r["status"] == "graded"], key=lambda r: -r["scores"]["aum_score"])
    rows = []
    for i, r in enumerate(graded, 1):
        s = r["scores"]
        rows.append({"rank": i, "client": r["client"], "names": " & ".join(r["names"]), "year": r["year"],
                     "aum_score": round(s["aum_score"]), "aum_fit": s["aum_fit"],
                     "annuity_grade": s["annuity_grade"], "annuity_points": round(s["annuity_points"]),
                     "life_grade": s["life_grade"], "life_points": round(s["life_points"]),
                     "signals": "; ".join(x["id"] for x in r["signals"]), "warnings": len(r["warnings"]),
                     "status": "graded"})
    for r in results:
        if r["status"] != "graded":
            rows.append({"rank": "", "client": r["client"], "names": "", "year": "", "aum_score": "", "aum_fit": "",
                         "annuity_grade": "", "annuity_points": "", "life_grade": "", "life_points": "",
                         "signals": "", "warnings": "", "status": f"not graded: {r['reason']}"})
    return rows


def write_summary(results, out_dir):
    out_dir = Path(out_dir)
    rows = summary_rows(results)
    with open(out_dir / "summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SUMMARY_COLS)
        w.writeheader()
        w.writerows(rows)
    body = ["<h1>Client ranking</h1>",
            f"<div class='sub'>{sum(1 for r in rows if r['status'] == 'graded')} graded &middot; ranked by AUM score "
            f"&middot; click a client for the full report</div>",
            "<div class='wrap'><table><tr><th>#</th><th>Client</th><th>AUM</th><th>Annuity</th><th>Life</th>"
            "<th class='sigcol'>Signals</th><th>Warnings</th></tr>"]
    for r in rows:
        if r["status"] != "graded":
            body.append(f"<tr><td></td><td>{esc(r['client'])}</td><td colspan='5' class='warn'>{esc(r['status'])}</td></tr>")
            continue
        sigs = " ".join(f"<span class='pill'>{esc(s)}</span>" for s in r["signals"].split("; ") if s)
        body.append(f"<tr><td class='num'>{r['rank']}</td><td><a href='clients/{esc(r['client'])}.html'>"
                    f"{esc(r['names'] or r['client'])}</a><div class='src'>{esc(r['client'])}</div></td>"
                    f"<td class='num'><b class='fit-{r['aum_fit']}'>{r['aum_score']}</b> {r['aum_fit']}</td>"
                    f"<td class='num'><b class='g-{r['annuity_grade']}'>{r['annuity_grade']}</b> ({r['annuity_points']})</td>"
                    f"<td class='num'><b class='g-{r['life_grade']}'>{r['life_grade']}</b> ({r['life_points']})</td>"
                    f"<td class='sigcol' style='font-size:12px'>{sigs}</td><td class='num'>{r['warnings'] or ''}</td></tr>")
    body.append("</table></div>")
    (out_dir / "summary.html").write_text(page("Client ranking", "".join(body)), encoding="utf-8")
