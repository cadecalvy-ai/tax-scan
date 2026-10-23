"""HTML reports: a ranked summary and one profile page per client, plus summary.csv.

Pages are self-contained (inline CSS, no external requests) and share the Tax Scan
look. Score pills on the ranking link straight to the matching section of the
client's profile (#aum, #annuity, #life). The top bar has a <!--NAV--> slot that
the local web app and the Netlify build fill with navigation links.
"""
import csv
import html
from pathlib import Path

from .privacy import mask_ssn

CSS = """
:root { --bg:#f6f7fb; --ink:#0e1020; --ink-2:#4a5068; --ink-3:#8a90a6; --line:#e6e8f0; --card:#fff; --chip:#f1f2f8;
        --accent:#5b4cf0; --accent-2:#8b5cf6; --mint:#14b8a6;
        --good:#0f9f6e; --good-bg:#e3f6ee; --mid:#b26b00; --mid-bg:#fff1d6; --low:#6b7186; --low-bg:#eef0f5;
        --bad:#d64045; --shadow:0 1px 2px rgba(14,16,32,.04), 0 16px 40px -24px rgba(40,36,110,.25); }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0a0b14; --ink:#eef0fb; --ink-2:#aab0c8; --ink-3:#6f7590; --line:#23263a; --card:#14162a; --chip:#1c1f35;
          --good:#3ddc97; --good-bg:#0f3327; --mid:#f5b445; --mid-bg:#3a2a0b; --low:#9aa0b8; --low-bg:#1f2236;
          --bad:#ff6b70; --shadow:0 1px 2px rgba(0,0,0,.4), 0 20px 50px -30px rgba(0,0,0,.7); }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
       font:15px/1.5 ui-sans-serif,-apple-system,"Segoe UI Variable Text","Segoe UI",Inter,Roboto,system-ui,sans-serif;
       -webkit-font-smoothing:antialiased; }
a { color:inherit; }
.top { position:sticky; top:0; z-index:5; backdrop-filter:blur(12px); -webkit-backdrop-filter:blur(12px);
       background:color-mix(in srgb, var(--bg) 82%, transparent); border-bottom:1px solid var(--line); }
.top-in { max-width:1080px; margin:0 auto; padding:14px 20px; display:flex; align-items:center; justify-content:space-between; gap:12px; }
.brand { display:flex; align-items:center; gap:9px; font-weight:700; text-decoration:none; }
.mark { width:26px; height:26px; border-radius:8px; display:grid; place-items:center;
        background:linear-gradient(135deg,var(--accent),var(--accent-2)); }
.navlinks { display:flex; gap:16px; font-size:14px; color:var(--ink-2); flex-wrap:wrap; justify-content:flex-end; }
.navlinks a { text-decoration:none; } .navlinks a:hover { color:var(--accent); }
main { max-width:1080px; margin:0 auto; padding:28px 20px 60px; }
h1 { font-size:clamp(28px,4vw,40px); letter-spacing:-.03em; margin:0; line-height:1.1; }
h2 { font-size:18px; letter-spacing:-.01em; margin:36px 0 12px; }
.sub { color:var(--ink-2); margin-top:6px; }
.muted { color:var(--ink-3); }
.banner { background:var(--mid-bg); color:var(--mid); border-radius:12px; padding:10px 14px; font-size:13px; margin-bottom:18px; }

/* pills */
.pill { display:inline-flex; align-items:center; gap:6px; padding:5px 11px; border-radius:999px; font-weight:700; font-size:13px;
        text-decoration:none; white-space:nowrap; border:1px solid transparent; transition:transform .12s, box-shadow .15s; }
a.pill:hover { transform:translateY(-1px); box-shadow:0 6px 14px -8px rgba(0,0,0,.35); }
.pill small { font-weight:600; opacity:.75; font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
.p-good { background:var(--good-bg); color:var(--good); } .p-mid { background:var(--mid-bg); color:var(--mid); }
.p-low { background:var(--low-bg); color:var(--low); }
.tag { display:inline-block; padding:3px 9px; border-radius:8px; background:var(--chip); color:var(--ink-2); font-size:12px; margin:2px 4px 2px 0; }

/* ranking */
.stats { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:22px 0 8px; }
.stat { background:var(--card); border:1px solid var(--line); border-radius:16px; padding:14px 16px; box-shadow:var(--shadow); }
.stat b { display:block; font-size:26px; letter-spacing:-.02em; }
.stat span { color:var(--ink-3); font-size:13px; }
.list { background:var(--card); border:1px solid var(--line); border-radius:20px; box-shadow:var(--shadow); overflow:hidden; margin-top:18px; }
.lh, .row { display:grid; grid-template-columns:44px minmax(180px,1.6fr) 130px 104px 104px minmax(160px,1.4fr); gap:12px; align-items:center; padding:14px 18px; }
.lh { font-size:12px; text-transform:uppercase; letter-spacing:.05em; color:var(--ink-3); border-bottom:1px solid var(--line); padding-top:12px; padding-bottom:12px; }
.row { border-bottom:1px solid var(--line); }
.row:last-child { border-bottom:0; }
.row:hover { background:color-mix(in srgb, var(--chip) 60%, transparent); }
.rank { font-weight:700; color:var(--ink-3); font-variant-numeric:tabular-nums; }
.who a { font-weight:650; text-decoration:none; } .who a:hover { color:var(--accent); }
.who .muted { font-size:12px; display:block; }
.sigs { font-size:12px; color:var(--ink-3); }
.row .lbl { display:none; }
.skip { color:var(--bad); }

/* profile */
.head { display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
.avatar { width:56px; height:56px; border-radius:18px; display:grid; place-items:center; color:#fff; font-weight:800; font-size:20px;
          background:linear-gradient(135deg,var(--accent),var(--accent-2)); flex:none; }
.meta { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
.scores { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin-top:24px; }
.score { background:var(--card); border:1px solid var(--line); border-radius:20px; padding:18px 20px; box-shadow:var(--shadow);
         text-decoration:none; display:block; scroll-margin-top:80px; }
.score:target, section:target .sec-card { outline:2px solid var(--accent); outline-offset:2px; }
.score .k { font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--ink-3); font-weight:600; }
.score .v { font-size:44px; font-weight:800; letter-spacing:-.04em; line-height:1.1; margin:4px 0 8px; }
.score .v small { font-size:16px; color:var(--ink-3); font-weight:600; letter-spacing:0; }
.bar { height:7px; border-radius:99px; background:var(--chip); overflow:hidden; margin-top:10px; }
.bar i { display:block; height:100%; border-radius:inherit; background:linear-gradient(90deg,var(--accent),var(--mint)); }
.c-good { color:var(--good); } .c-mid { color:var(--mid); } .c-low { color:var(--low); }
.tps { list-style:none; padding:0; margin:0; display:grid; gap:8px; }
.tps li { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:12px 14px 12px 40px; position:relative; }
.tps li::before { content:""; position:absolute; left:16px; top:18px; width:10px; height:10px; border-radius:50%;
                  background:linear-gradient(135deg,var(--accent),var(--mint)); }
section { scroll-margin-top:80px; }
.sec-card { background:var(--card); border:1px solid var(--line); border-radius:18px; box-shadow:var(--shadow); overflow:hidden; }
.sec-head { display:flex; justify-content:space-between; align-items:center; gap:10px; }
.sig { display:grid; grid-template-columns:1fr auto; gap:6px 14px; padding:14px 18px; border-top:1px solid var(--line); }
.sig:first-child { border-top:0; }
.sig .rule { font-weight:600; }
.sig .detail { color:var(--ink-2); font-size:14px; grid-column:1 / -1; }
.sig .src { color:var(--ink-3); font-size:12px; grid-column:1 / -1; }
.sig .right { display:flex; gap:6px; align-items:center; }
.empty { padding:16px 18px; color:var(--ink-3); }
.warnbox li { color:var(--bad); margin:4px 0; }
.ok { color:var(--good); }
table { width:100%; border-collapse:collapse; }
th, td { text-align:left; padding:10px 16px; border-top:1px solid var(--line); vertical-align:top; }
th { font-size:12px; text-transform:uppercase; letter-spacing:.05em; color:var(--ink-3); border-top:0; background:var(--chip); }
td.num { text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }
td.src { color:var(--ink-3); font-size:12px; }
.wrap { overflow-x:auto; }
.foot { color:var(--ink-3); font-size:12px; margin-top:30px; }

@media (max-width: 820px) {
  .stats { grid-template-columns:repeat(2,1fr); }
  .lh { display:none; }
  .row { grid-template-columns:36px 1fr; gap:8px 10px; }
  .row > :nth-child(n+3) { grid-column:2; }
  .row .pills-m { display:flex; gap:6px; flex-wrap:wrap; }
  .row .lbl { display:inline; }
  .scores { grid-template-columns:1fr; }
}
@media print { .top { display:none; } body { background:#fff; } .score, .sec-card, .list { box-shadow:none; break-inside:avoid; } }
"""

MARK = ("<svg width='15' height='15' viewBox='0 0 24 24' fill='none' stroke='#fff' stroke-width='2.2' stroke-linecap='round' "
        "stroke-linejoin='round'><path d='M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z'/><path d='M14 3v5h5'/>"
        "<path d='M3 13h18' stroke='#84f1d6'/></svg>")


def esc(x):
    return html.escape(mask_ssn(x))


def money(v):
    return "" if v is None else f"${v:,.0f}"


def page(title, body):
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width, initial-scale=1'><title>{esc(title)} · Tax Scan</title><style>{CSS}</style>"
            f"</head><body><header class='top'><div class='top-in'><span class='brand'><span class='mark'>{MARK}</span>Tax Scan"
            f"</span><nav class='navlinks'><!--NAV--></nav></div></header><main>{body}</main></body></html>")


# ---------------------------------------------------------------------
# pills
# ---------------------------------------------------------------------
def tone_fit(fit):
    return {"high": "good", "med": "mid"}.get(fit, "low")


def tone_grade(g):
    return "good" if g in ("A", "B") else "mid" if g == "C" else "low"


def aum_pill(s, href=None):
    tag = "a" if href else "span"
    h = f" href='{href}#aum'" if href else ""
    return (f"<{tag} class='pill p-{tone_fit(s['aum_fit'])}'{h} title='AUM fit score'>{s['aum_score']:.0f}"
            f"<small>{s['aum_fit']}</small></{tag}>")


def grade_pill(grade, pts, anchor, label, href=None):
    tag = "a" if href else "span"
    h = f" href='{href}#{anchor}'" if href else ""
    return (f"<{tag} class='pill p-{tone_grade(grade)}'{h} title='{label} grade ({pts:.0f} points)'>{grade}"
            f"<small>{pts:.0f} pts</small></{tag}>")


# ---------------------------------------------------------------------
# client profile
# ---------------------------------------------------------------------
def client_html(r):
    if r["status"] != "graded":
        body = (f"<h1>{esc(r['client'])}</h1><p class='sub'>Not graded</p>"
                f"<p class='skip'>{esc(r['reason'])}</p>")
        return page(r["client"], body)
    s = r["scores"]
    names = " & ".join(r["names"]) or r["client"]
    words = [w for w in (r["names"][0] if r["names"] else r["client"]).split() if not w.endswith(".")]
    initials = (words[0][0] + words[-1][0]) if words else "?"
    meta = [f"Tax year {r['year']}", r["filing_status"]] + [f"{n}, {a}" for n, a in r["ages"]] + \
           [f"Prior year: {r['prior_year'] or 'none'}", f"Consent: {r['consent']}"]
    out = [f"<div class='head'><div class='avatar'>{esc(initials.upper())}</div><div><h1>{esc(names)}</h1>"
           f"<div class='meta'>{''.join(f'<span class=tag>{esc(m)}</span>' for m in meta)}</div></div></div>"]

    out.append("<div class='scores'>"
               f"<a class='score' id='aum' href='#sig-aum'><div class='k'>AUM fit</div>"
               f"<div class='v c-{tone_fit(s['aum_fit'])}'>{s['aum_score']:.0f}<small>/100</small></div>"
               f"{aum_pill(s)}<div class='bar'><i style='width:{min(100, s['aum_score']):.0f}%'></i></div></a>"
               f"<a class='score' id='annuity' href='#sig-annuity'><div class='k'>Annuity</div>"
               f"<div class='v c-{tone_grade(s['annuity_grade'])}'>{s['annuity_grade']}</div>"
               f"{grade_pill(s['annuity_grade'], s['annuity_points'], 'annuity', 'Annuity')}</a>"
               f"<a class='score' id='life' href='#sig-life'><div class='k'>Life insurance</div>"
               f"<div class='v c-{tone_grade(s['life_grade'])}'>{s['life_grade']}</div>"
               f"{grade_pill(s['life_grade'], s['life_points'], 'life', 'Life')}</a>"
               "</div>")

    out.append("<h2>Talking points</h2>")
    out.append("<ul class='tps'>" + "".join(f"<li>{esc(t)}</li>" for t in r["talking_points"]) + "</ul>"
               if r["talking_points"] else "<p class='muted'>No signals fired.</p>")

    for prod, title in (("aum", "AUM signals"), ("annuity", "Annuity signals"), ("life", "Life-insurance signals")):
        sigs = [x for x in r["signals"] if x["product"] == prod]
        total = sum(x["points"] for x in sigs)
        note = ""
        if prod == "aum" and total > s["aum_score"]:
            note = f" <span class='muted' style='font-size:13px;font-weight:400'>(adds to {total:.0f}, capped)</span>"
        out.append(f"<section id='sig-{prod}'><div class='sec-head'><h2>{title}{note}</h2>"
                   f"<span class='pill p-low'>{total:+.0f} pts</span></div><div class='sec-card'>")
        if not sigs:
            out.append("<div class='empty'>None fired.</div>")
        for x in sigs:
            out.append(f"<div class='sig'><div class='rule'>{esc(x['label'])}</div>"
                       f"<div class='right'><span class='tag'>{esc(x['value'])}</span>"
                       f"<span class='pill {'p-good' if x['points'] > 0 else 'p-low'}'>{x['points']:+.0f}</span></div>"
                       + (f"<div class='detail'>{esc(x['detail'])}</div>" if x["detail"] else "")
                       + f"<div class='src'>{' &middot; '.join(esc(s_) for s_ in x['sources'])} &middot; {esc(x['id'])}</div></div>")
        out.append("</div></section>")

    out.append("<section id='warnings'><h2>Validation</h2><div class='sec-card' style='padding:14px 18px'>")
    out.append("<ul class='warnbox' style='margin:0;padding-left:18px'>" + "".join(f"<li>{esc(w)}</li>" for w in r["warnings"])
               + "</ul>" if r["warnings"] else "<span class='ok'>&#10003; Every cross-check agreed.</span>")
    out.append("</div></section>")

    out.append("<section id='figures'><h2>Key figures</h2><div class='sec-card wrap'><table><tr><th>Figure</th>"
               f"<th style='text-align:right'>{r['year']}</th>"
               + (f"<th style='text-align:right'>{r['prior_year']}</th>" if r["prior_year"] else "") + "<th>Source</th></tr>")
    for row in r["figures"]:
        out.append(f"<tr><td>{esc(row['label'])}</td><td class='num'>{money(row['value'])}</td>"
                   + (f"<td class='num'>{money(row['prior'])}</td>" if r["prior_year"] else "")
                   + f"<td class='src'>{esc(row['source'])}</td></tr>")
    out.append("</table></div></section>")

    out.append("<section id='documents'><h2>Documents read</h2><div class='sec-card wrap'><table><tr><th>File</th>"
               "<th>Detected as</th><th style='text-align:right'>Pages</th><th>Read by</th></tr>")
    for d in r["documents"]:
        out.append(f"<tr><td>{esc(d['doc'])}</td><td>{esc(d['kinds'])}</td><td class='num'>{d['pages']}</td>"
                   f"<td>{'OCR (scan)' if d['ocr'] else 'text'}</td></tr>")
    out.append("</table></div></section>")
    out.append("<p class='foot'>Generated on this computer by Tax Scan. SSNs are masked. "
               "Scores come from config/grader.yaml.</p>")
    return page(names, "".join(out))


def write_client(r, out_dir):
    f = Path(out_dir) / "clients" / f"{r['client']}.html"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(client_html(r), encoding="utf-8")
    return f


# ---------------------------------------------------------------------
# ranking
# ---------------------------------------------------------------------
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


def _short_signal(sid):
    return sid.split(".", 1)[1].replace("_", " ")


def write_summary(results, out_dir):
    out_dir = Path(out_dir)
    rows = summary_rows(results)
    with open(out_dir / "summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SUMMARY_COLS)
        w.writeheader()
        w.writerows(rows)
    graded = [r for r in rows if r["status"] == "graded"]
    n_high = sum(1 for r in graded if r["aum_fit"] == "high")
    n_ann = sum(1 for r in graded if r["annuity_grade"] in ("A", "B"))
    n_life = sum(1 for r in graded if r["life_grade"] in ("A", "B"))
    body = ["<h1>Client ranking</h1>",
            f"<div class='sub'>Ranked by AUM score. Click a name or any pill to open that client&rsquo;s profile.</div>",
            "<div class='stats'>"
            f"<div class='stat'><b>{len(graded)}</b><span>clients graded</span></div>"
            f"<div class='stat'><b class='c-good'>{n_high}</b><span>high AUM fit</span></div>"
            f"<div class='stat'><b>{n_ann}</b><span>annuity A or B</span></div>"
            f"<div class='stat'><b>{n_life}</b><span>life A or B</span></div></div>",
            "<div class='list'><div class='lh'><span>#</span><span>Client</span><span>AUM</span><span>Annuity</span>"
            "<span>Life</span><span>Top signals</span></div>"]
    for r in rows:
        if r["status"] != "graded":
            body.append(f"<div class='row'><span class='rank'>&ndash;</span><div class='who'>{esc(r['client'])}"
                        f"<span class='muted skip'>{esc(r['status'])}</span></div></div>")
            continue
        href = f"clients/{esc(r['client'])}.html"
        s = {"aum_score": r["aum_score"], "aum_fit": r["aum_fit"]}
        sigs = [x for x in r["signals"].split("; ") if x][:4]
        warn = f" &middot; <span class='skip'>{r['warnings']} warning{'s' if r['warnings'] != 1 else ''}</span>" if r["warnings"] else ""
        body.append(
            f"<div class='row'><span class='rank'>{r['rank']}</span>"
            f"<div class='who'><a href='{href}'>{esc(r['names'] or r['client'])}</a>"
            f"<span class='muted'>{esc(r['client'])}{warn}</span></div>"
            f"<div><span class='lbl muted'>AUM </span>{aum_pill(s, href)}</div>"
            f"<div><span class='lbl muted'>Annuity </span>{grade_pill(r['annuity_grade'], r['annuity_points'], 'annuity', 'Annuity', href)}</div>"
            f"<div><span class='lbl muted'>Life </span>{grade_pill(r['life_grade'], r['life_points'], 'life', 'Life', href)}</div>"
            f"<div class='sigs'>{''.join(f'<span class=tag>{esc(_short_signal(x))}</span>' for x in sigs)}</div></div>")
    body.append("</div><p class='foot'>summary.csv in this folder has the same table for Excel.</p>")
    (out_dir / "summary.html").write_text(page("Client ranking", "".join(body)), encoding="utf-8")
