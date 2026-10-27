"""HTML reports: a ranked summary and one conversation brief per client, plus summary.csv.

Pages are self-contained (inline CSS, no external requests) and share the Tax Scan
look. The client page leads with plain-English verdicts and a conversation brief
(what stood out, why it matters, what to ask); the scoring evidence sits in a
collapsible section below. Verdict pills on the ranking link straight to the
matching card on the client page (#aum, #annuity, #life). The top bar has a
<!--NAV--> slot that the local web app and the Netlify build fill with links.
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
       font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI Variable Text","Segoe UI",Inter,Roboto,system-ui,sans-serif;
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
h2 { font-size:19px; letter-spacing:-.015em; margin:40px 0 14px; }
.sub { color:var(--ink-2); margin-top:6px; }
.muted { color:var(--ink-3); }
.banner { background:var(--mid-bg); color:var(--mid); border-radius:12px; padding:10px 14px; font-size:13px; margin-bottom:18px; }
.btn { font:inherit; font-size:14px; font-weight:600; padding:9px 16px; border-radius:12px; cursor:pointer;
       border:1px solid var(--line); background:var(--card); color:var(--ink); }
.btn:hover { border-color:var(--accent); }

/* verdict pills */
.pill { display:inline-flex; align-items:center; gap:6px; padding:5px 12px; border-radius:999px; font-weight:650; font-size:13px;
        text-decoration:none; white-space:nowrap; transition:transform .12s, box-shadow .15s; }
a.pill:hover { transform:translateY(-1px); box-shadow:0 6px 14px -8px rgba(0,0,0,.35); }
.pill .dot { width:7px; height:7px; border-radius:50%; background:currentColor; }
.t-good { background:var(--good-bg); color:var(--good); } .t-mid { background:var(--mid-bg); color:var(--mid); }
.t-low { background:var(--low-bg); color:var(--low); }
.c-good { color:var(--good); } .c-mid { color:var(--mid); } .c-low { color:var(--low); }
.tag { display:inline-block; padding:3px 9px; border-radius:8px; background:var(--chip); color:var(--ink-2); font-size:12px; margin:2px 4px 2px 0; }

/* meter: bar with grade cut-offs */
.meter { position:relative; margin:16px 0 30px; }
.meter .track { height:8px; border-radius:99px; background:var(--chip); overflow:hidden; }
.meter .fill { height:100%; border-radius:inherit; }
.fill.good { background:linear-gradient(90deg,var(--mint),var(--good)); }
.fill.mid { background:linear-gradient(90deg,#f5c56b,var(--mid)); }
.fill.low { background:var(--low); opacity:.55; }
.meter .tick { position:absolute; top:-3px; width:2px; height:14px; background:var(--card); border-radius:2px; }
.meter .tl { position:absolute; top:14px; transform:translateX(-50%); font-size:10.5px; color:var(--ink-3); font-weight:600; }
.mini { width:100%; max-width:120px; margin:6px 0 0; }
.mini .track { height:5px; } .mini .tick, .mini .tl { display:none; }

/* client page */
.head { display:flex; gap:16px; align-items:center; flex-wrap:wrap; justify-content:space-between; }
.who-h { display:flex; gap:16px; align-items:center; }
.avatar { width:56px; height:56px; border-radius:18px; display:grid; place-items:center; color:#fff; font-weight:800; font-size:20px;
          background:linear-gradient(135deg,var(--accent),var(--accent-2)); flex:none; }
.meta { display:flex; flex-wrap:wrap; gap:4px; margin-top:8px; }
.glance { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin-top:26px; }
.pcard { background:var(--card); border:1px solid var(--line); border-radius:20px; padding:18px 20px; box-shadow:var(--shadow);
         scroll-margin-top:80px; }
.pcard:target { outline:2px solid var(--accent); outline-offset:2px; }
.pcard .k { font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--ink-3); font-weight:600; }
.pcard .verdict { font-size:24px; font-weight:750; letter-spacing:-.02em; margin:4px 0 2px; }
.pcard .score { font-size:13px; color:var(--ink-3); }
.pcard .next { font-size:12.5px; color:var(--ink-3); margin:-6px 0 10px; }
.pcard ul { margin:0; padding-left:18px; color:var(--ink-2); font-size:14px; }
.pcard li { margin:3px 0; }
.brief { background:var(--card); border:1px solid var(--line); border-radius:22px; box-shadow:var(--shadow); overflow:hidden; }
.opener { padding:20px 22px; background:linear-gradient(135deg, color-mix(in srgb, var(--accent) 9%, var(--card)),
          color-mix(in srgb, var(--mint) 8%, var(--card))); border-bottom:1px solid var(--line); }
.opener .k { font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--accent); font-weight:700; }
.opener ol { margin:10px 0 0; padding-left:20px; font-size:16px; font-weight:600; }
.opener li { margin:4px 0; }
.prod { padding:20px 22px; border-top:1px solid var(--line); }
.prod:first-of-type { border-top:0; }
.prod-h { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:12px; }
.prod-h h3 { margin:0; font-size:17px; letter-spacing:-.01em; }
.tp { display:grid; grid-template-columns:28px 1fr; gap:4px 12px; padding:12px 0; border-top:1px dashed var(--line); }
.tp:first-of-type { border-top:0; padding-top:4px; }
.tp .n { width:28px; height:28px; border-radius:9px; display:grid; place-items:center; font-weight:700; font-size:13px;
         background:var(--chip); color:var(--accent); }
.tp .hl { font-weight:650; font-size:15.5px; }
.tp .why { color:var(--ink-2); font-size:14.5px; grid-column:2; }
.tp .ask { grid-column:2; margin-top:6px; padding:9px 12px; border-radius:12px; background:var(--chip); font-size:14.5px; }
.tp .ask b { color:var(--accent); font-weight:700; margin-right:6px; }
.lowlist { padding:16px 22px; border-top:1px solid var(--line); color:var(--ink-3); font-size:14px; }
.cnotes { padding:18px 22px; border-bottom:1px solid var(--line); }
.cnotes .k { font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--ink-3); font-weight:700; }
.cnotes blockquote { margin:10px 0 12px; padding:10px 14px; border-left:3px solid var(--mint); background:var(--chip);
                     border-radius:0 12px 12px 0; font-size:15px; font-style:italic; }
.cnotes .qa { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:6px 18px; font-size:13.5px; }
.cnotes .qa div { display:flex; gap:8px; align-items:baseline; flex-wrap:wrap; }
.cnotes .q { color:var(--ink-2); }
.cnotes .a { font-weight:700; } .cnotes .a.y { color:var(--good); } .cnotes .a.n { color:var(--ink-3); }
.cnotes .c { color:var(--ink-3); font-size:12.5px; }
.cnotes .src { color:var(--ink-3); font-size:12px; margin-top:10px; }
.tp .cn { grid-column:2; margin-top:6px; font-size:14px; color:var(--ink-2); font-style:italic; }
.tp .cn b { font-style:normal; color:var(--mint); font-weight:700; margin-right:6px; }
.tp .cx { grid-column:2; margin-top:6px; font-size:14px; color:var(--ink-2); }
.tp .cx b { color:var(--accent); font-weight:700; margin-right:6px; }
.snap .tsub { display:block; color:var(--ink-3); font-size:12px; margin-top:2px; }
.snap { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; }
.snap div { background:var(--card); border:1px solid var(--line); border-radius:16px; padding:14px 16px; }
.snap b { display:block; font-size:22px; letter-spacing:-.02em; }
.snap span { color:var(--ink-3); font-size:13px; }
details.evidence { margin-top:40px; background:var(--card); border:1px solid var(--line); border-radius:18px; }
details.evidence > summary { cursor:pointer; padding:16px 20px; font-weight:650; list-style:none; display:flex;
                             justify-content:space-between; align-items:center; }
details.evidence > summary::after { content:"Show"; font-size:13px; color:var(--accent); font-weight:600; }
details.evidence[open] > summary::after { content:"Hide"; }
details.evidence > summary::-webkit-details-marker { display:none; }
.ev { padding:0 20px 20px; }
.ev h4 { margin:18px 0 8px; font-size:14px; text-transform:uppercase; letter-spacing:.05em; color:var(--ink-3); }
.sig { display:grid; grid-template-columns:1fr auto; gap:4px 14px; padding:10px 0; border-top:1px solid var(--line); }
.sig .src { color:var(--ink-3); font-size:12px; grid-column:1 / -1; }
.warnbox li { color:var(--bad); margin:4px 0; }
.ok { color:var(--good); }
table { width:100%; border-collapse:collapse; }
th, td { text-align:left; padding:9px 12px; border-top:1px solid var(--line); vertical-align:top; font-size:14px; }
th { font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; color:var(--ink-3); border-top:0; background:var(--chip); }
td.num { text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }
td.src { color:var(--ink-3); font-size:12px; }
.wrap { overflow-x:auto; }
.foot { color:var(--ink-3); font-size:12px; margin-top:30px; }

/* ranking */
main.wide { max-width:1240px; }
.stats { display:flex; flex-wrap:wrap; gap:8px 28px; margin:18px 0 6px; color:var(--ink-2); font-size:14px; }
.stats b { font-size:20px; color:var(--ink); margin-right:6px; font-variant-numeric:tabular-nums; }
.stats b.c-good { color:var(--good); }
.list { background:var(--card); border:1px solid var(--line); border-radius:16px; overflow:hidden; margin-top:18px; }
.lh, .row { display:grid; grid-template-columns:34px minmax(200px,1.25fr) repeat(3,minmax(158px,.7fr)) minmax(260px,1.9fr);
            gap:18px; align-items:center; padding:16px 22px; }
.lh { font-size:12px; font-weight:650; color:var(--ink-3); border-bottom:1px solid var(--line); padding-top:11px;
      padding-bottom:11px; background:var(--chip); }
.row { border-bottom:1px solid var(--line); }
.row:last-child { border-bottom:0; }
.row:hover { background:color-mix(in srgb, var(--chip) 50%, transparent); }
.rank { font-weight:650; color:var(--ink-3); font-variant-numeric:tabular-nums; }
.who a { font-weight:650; font-size:15.5px; text-decoration:none; } .who a:hover { color:var(--accent); }
.who .muted { font-size:12.5px; display:block; margin-top:2px; }
.cell .pill { font-size:12.5px; padding:4px 11px; }
.cell .sc { font-size:12px; color:var(--ink-3); margin:4px 0 0 2px; font-variant-numeric:tabular-nums; }
.why-c { font-size:14px; line-height:1.45; }
.why-c .lead { color:var(--ink); font-weight:550; }
.why-c .more { color:var(--ink-3); font-size:13px; margin-top:3px; }
.row .lbl { display:none; }
.row.off { color:var(--ink-3); }
.skip { color:var(--bad); }
.btn.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
a.btn { text-decoration:none; display:inline-block; }
.export { display:flex; justify-content:space-between; align-items:center; gap:16px; flex-wrap:wrap; margin-top:22px;
          background:var(--card); border:1px solid var(--line); border-radius:18px; padding:18px 20px; box-shadow:var(--shadow); }
.export span { display:block; color:var(--ink-3); font-size:13.5px; margin-top:2px; }
.export .ex-btns { display:flex; gap:10px; flex-wrap:wrap; }

@media (max-width: 900px) {
  .glance { grid-template-columns:1fr; }
  .lh { display:none; }
  .row { grid-template-columns:28px repeat(3,1fr); gap:10px 12px; padding:16px; align-items:start; }
  .row .who, .row .why-c { grid-column:2 / -1; }
  .row .cell.first { grid-column:2; }
  .row .lbl { display:block; font-size:11.5px; color:var(--ink-3); margin-bottom:4px; }
}
@media print {
  .top, .noprint, details.evidence { display:none !important; }
  body { background:#fff; font-size:12.5px; } main { padding:0; max-width:none; }
  .pcard, .brief, .snap div, .list, .stat { box-shadow:none; break-inside:avoid; }
  .prod, .tp { break-inside:avoid; } h2 { margin-top:22px; }
  .banner { display:none; }
}
"""

MARK = ("<svg width='15' height='15' viewBox='0 0 24 24' fill='none' stroke='#fff' stroke-width='2.2' stroke-linecap='round' "
        "stroke-linejoin='round'><path d='M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z'/><path d='M14 3v5h5'/>"
        "<path d='M3 13h18' stroke='#84f1d6'/></svg>")


def esc(x):
    return html.escape(mask_ssn(x))


def money(v):
    return "" if v is None else f"${v:,.0f}"


def page(title, body, wide=False):
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width, initial-scale=1'><title>{esc(title)} · Tax Scan</title><style>{CSS}</style>"
            f"</head><body><header class='top'><div class='top-in'><span class='brand'><span class='mark'>{MARK}</span>Tax Scan"
            f"</span><nav class='navlinks'><!--NAV--></nav></div></header>"
            f"<main{' class=wide' if wide else ''}>{body}</main></body></html>")


# ---------------------------------------------------------------------
# building blocks
# ---------------------------------------------------------------------
def verdict_pill(p, href=None):
    tag = "a" if href else "span"
    h = f" href='{href}#{p['key']}'" if href else ""
    return f"<{tag} class='pill t-{p['tone']}'{h} title='{esc(p['score_label'])}'><span class='dot'></span>{esc(p['verdict'])}</{tag}>"


def meter(p, mini=False):
    m = p["meter"]
    ticks = "".join(f"<span class='tick' style='left:calc({pos * 100:.1f}% - 1px)'></span>"
                    f"<span class='tl' style='left:{pos * 100:.1f}%'>{esc(lbl)}</span>" for lbl, pos in m["ticks"])
    return (f"<div class='meter{' mini' if mini else ''}' aria-label='{esc(p['score_label'])}'><div class='track'>"
            f"<div class='fill {p['tone']}' style='width:{m['fill'] * 100:.1f}%'></div></div>{ticks}</div>")


def _products(r):
    return {p["key"]: p for p in r["brief"]["products"]}


# ---------------------------------------------------------------------
# client page: conversation brief
# ---------------------------------------------------------------------
def client_html(r):
    if r["status"] != "graded":
        body = (f"<h1>{esc(r['client'])}</h1><p class='sub'>Not graded</p>"
                f"<p class='skip'>{esc(r['reason'])}</p>")
        return page(r["client"], body)
    b, prods = r["brief"], _products(r)
    names = " & ".join(r["names"]) or r["client"]
    words = [w for w in (r["names"][0] if r["names"] else r["client"]).split() if not w.endswith(".")]
    initials = (words[0][0] + words[-1][0]) if words else "?"
    meta = [f"Tax year {r['year']}", r["filing_status"]] + [f"{n}, {a}" for n, a in r["ages"]]
    out = [f"<div class='head'><div class='who-h'><div class='avatar'>{esc(initials.upper())}</div><div><h1>{esc(names)}</h1>"
           f"<div class='meta'>{''.join(f'<span class=tag>{esc(m)}</span>' for m in meta)}</div></div></div>"
           "<button class='btn noprint' onclick='window.print()'>Print brief</button></div>"]

    # at a glance
    out.append("<div class='glance'>")
    for key in ("aum", "annuity", "life"):
        p = prods[key]
        reasons = ("<ul>" + "".join(f"<li>{esc(x)}</li>" for x in p["reasons"]) + "</ul>") if p["reasons"] \
            else "<p class='muted' style='margin:0;font-size:14px'>Nothing on the return points here.</p>"
        out.append(f"<div class='pcard' id='{key}'><div class='k'>{esc(p['name'])}</div>"
                   f"<div class='verdict c-{p['tone']}'>{esc(p['verdict'])}</div><div class='score'>{esc(p['score_label'])}</div>"
                   f"{meter(p)}" + (f"<div class='next'>{esc(p['next'])}</div>" if p["next"] else "") + f"{reasons}</div>")
    out.append("</div>")

    # conversation brief
    out.append("<h2>Conversation brief</h2><div class='brief'>")
    if b["opener"]:
        out.append(f"<div class='opener'><div class='k'>What stood out on their {r['year']} return</div><ol>"
                   + "".join(f"<li>{esc(x)}</li>" for x in b["opener"]) + "</ol></div>")
    notes = b.get("client_notes")
    if notes:
        out.append("<div class='cnotes'><div class='k'>In the client&rsquo;s own words</div>")
        if notes.get("notes"):
            out.append("<blockquote>" + " ".join(esc(s) for s in notes["notes"]) + "</blockquote>")
        if notes.get("answers"):
            out.append("<div class='qa'>" + "".join(
                f"<div><span class='q'>{esc(a['question'])}</span><span class='a {'y' if a['answer'] == 'Yes' else 'n'}'>"
                f"{esc(a['answer'] or '?')}</span>{('<span class=c>' + esc(a['comment']) + '</span>') if a['comment'] else ''}</div>"
                for a in notes["answers"]) + "</div>")
        out.append(f"<div class='src'>From {esc(notes['where'])}. Client-written and not verified; "
                   "notes don&rsquo;t change any score.</div></div>")
    low = []
    for key in b["order"]:
        p = prods[key]
        if not p["points"]:
            continue
        if p["tone"] == "low":
            low.append(p)
            continue
        out.append(f"<div class='prod'><div class='prod-h'><h3>{esc(p['name'])}</h3>{verdict_pill(p)}</div>")
        for i, t in enumerate(p["points"], 1):
            out.append(f"<div class='tp'><div class='n'>{i}</div><div class='hl'>{esc(t['headline'])}</div>"
                       f"<div class='why'>{esc(t['why'])}</div>"
                       + "".join(f"<div class='cx'><b>From the return</b>{esc(c)}</div>" for c in t.get("context", []))
                       + "".join(f"<div class='cn'><b>Client note</b>&ldquo;{esc(n)}&rdquo;</div>"
                                 for n in t.get("client_notes", []))
                       + (f"<div class='ask'><b>Ask</b>{esc(t['ask'])}</div>" if t["ask"] else "") + "</div>")
        if p["more"]:
            out.append(f"<div class='muted' style='font-size:13px;padding-top:6px'>+{p['more']} more in the evidence below</div>")
        out.append("</div>")
    if low:
        out.append("<div class='lowlist'><b>Lower priority:</b> " + "; ".join(
            f"{esc(p['name'])} ({esc(', '.join(t['headline'] for t in p['points'][:2]))})" for p in low) + "</div>")
    if not b["opener"]:
        out.append("<div class='lowlist'>Nothing on this return points to a conversation right now.</div>")
    out.append("</div>")

    # household snapshot
    if b["snapshot"]:
        out.append("<h2>Household snapshot</h2><div class='snap'>" + "".join(
            f"<div><b>{money(s['value'])}</b><span>{esc(s['label'])}</span></div>" for s in b["snapshot"]) + "</div>")
    if b.get("tax_picture"):
        out.append("<h2>Tax picture <span class='muted' style='font-size:13px;font-weight:400'>from the preparer&rsquo;s "
                   "pages &middot; context only, not scored</span></h2><div class='snap'>" + "".join(
                       f"<div><b>{esc(c['value'])}</b><span>{esc(c['label'])}</span>"
                       f"<span class='tsub'>{esc(c['sub'])}</span></div>" for c in b["tax_picture"]) + "</div>")

    # evidence (collapsed)
    n_warn = len(r["warnings"])
    out.append(f"<details class='evidence'><summary>Evidence behind the scores <span class='muted' style='font-weight:400;"
               f"font-size:13px'>&nbsp;rules, points, sources, {'validation &middot; ' + str(n_warn) + ' warning(s)' if n_warn else 'all checks passed'}"
               f"</span></summary><div class='ev'>")
    for key in ("aum", "annuity", "life"):
        p = prods[key]
        sigs = [x for x in r["signals"] if x["product"] == key]
        out.append(f"<h4>{esc(p['name'])} &middot; {esc(p['score_label'])}</h4>")
        if not sigs:
            out.append("<div class='muted'>No rules fired.</div>")
        for x in sigs:
            out.append(f"<div class='sig'><div>{esc(x['label'])} &mdash; <b>{esc(x['value'])}</b>"
                       + (f" <span class='muted'>({esc(x['detail'])})</span>" if x["detail"] else "")
                       + f"</div><span class='pill {'t-good' if x['points'] > 0 else 't-low'}'>{x['points']:+.0f}</span>"
                       f"<div class='src'>{' &middot; '.join(esc(s_) for s_ in x['sources'])} &middot; {esc(x['id'])}</div></div>")
    out.append("<h4>Validation</h4>")
    out.append("<ul class='warnbox' style='margin:0;padding-left:18px'>" + "".join(f"<li>{esc(w)}</li>" for w in r["warnings"])
               + "</ul>" if r["warnings"] else "<span class='ok'>&#10003; Every cross-check agreed.</span>")
    out.append("<h4>Key figures</h4><div class='wrap'><table><tr><th>Figure</th>"
               f"<th style='text-align:right'>{r['year']}</th>"
               + (f"<th style='text-align:right'>{r['prior_year']}</th>" if r["prior_year"] else "") + "<th>Source</th></tr>")
    for row in r["figures"]:
        out.append(f"<tr><td>{esc(row['label'])}</td><td class='num'>{money(row['value'])}</td>"
                   + (f"<td class='num'>{money(row['prior'])}</td>" if r["prior_year"] else "")
                   + f"<td class='src'>{esc(row['source'])}</td></tr>")
    out.append("</table></div><h4>Documents read</h4><div class='wrap'><table><tr><th>File</th><th>Detected as</th>"
               "<th style='text-align:right'>Pages</th><th>Read by</th></tr>")
    for d in r["documents"]:
        out.append(f"<tr><td>{esc(d['doc'])}</td><td>{esc(d['kinds'])}</td><td class='num'>{d['pages']}</td>"
                   f"<td>{'OCR (scan)' if d['ocr'] else 'text'}</td></tr>")
    out.append(f"</table></div><p class='muted' style='font-size:12px;margin-top:14px'>Consent: {esc(r['consent'])}. "
               f"Prior-year return: {r['prior_year'] or 'none'}. Rules and wording: app/config/grader.yaml.</p></div></details>")
    out.append("<p class='foot'>Prepared on this computer by Tax Scan from the client&rsquo;s tax documents. SSNs are masked. "
               "A starting point for a conversation, not advice.</p>")
    return page(names, "".join(out))


def write_client(r, out_dir):
    f = Path(out_dir) / "clients" / f"{r['client']}.html"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(client_html(r), encoding="utf-8")
    return f


# ---------------------------------------------------------------------
# ranking
# ---------------------------------------------------------------------
SUMMARY_COLS = ["rank", "client", "names", "year", "aum_score", "aum_fit", "aum_verdict", "annuity_grade",
                "annuity_points", "annuity_verdict", "life_grade", "life_points", "life_verdict", "highlights",
                "signals", "warnings", "status"]


def summary_rows(results):
    graded = sorted([r for r in results if r["status"] == "graded"], key=lambda r: -r["scores"]["aum_score"])
    rows = []
    for i, r in enumerate(graded, 1):
        s, p = r["scores"], _products(r)
        rows.append({"rank": i, "client": r["client"], "names": " & ".join(r["names"]), "year": r["year"],
                     "aum_score": round(s["aum_score"]), "aum_fit": s["aum_fit"], "aum_verdict": p["aum"]["verdict"],
                     "annuity_grade": s["annuity_grade"], "annuity_points": round(s["annuity_points"]),
                     "annuity_verdict": p["annuity"]["verdict"],
                     "life_grade": s["life_grade"], "life_points": round(s["life_points"]),
                     "life_verdict": p["life"]["verdict"], "highlights": "; ".join(r["brief"]["opener"]),
                     "signals": "; ".join(x["id"] for x in r["signals"]), "warnings": len(r["warnings"]),
                     "status": "graded", "_r": r})
    for r in results:
        if r["status"] != "graded":
            rows.append({c: "" for c in SUMMARY_COLS} | {"client": r["client"], "status": f"not graded: {r['reason']}"})
    return rows


def write_summary(results, out_dir):
    out_dir = Path(out_dir)
    rows = summary_rows(results)
    with open(out_dir / "summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SUMMARY_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    graded = [r for r in rows if r["status"] == "graded"]
    strong = lambda key: sum(1 for r in graded if _products(r["_r"])[key]["tone"] == "good")  # noqa: E731
    body = ["<h1>Client ranking</h1>",
            "<div class='sub'>Ranked by investment-management fit. Open a client for their conversation brief.</div>",
            "<div class='stats'>"
            f"<span><b>{len(graded)}</b>clients graded</span>"
            f"<span><b class='c-good'>{strong('aum')}</b>strong investment fit</span>"
            f"<span><b class='c-good'>{strong('annuity')}</b>good or strong annuity fit</span>"
            f"<span><b class='c-good'>{strong('life')}</b>good or strong life fit</span></div>",
            "<div class='list'><div class='lh'><span>#</span><span>Client</span><span>Investment mgmt</span>"
            "<span>Annuity</span><span>Life insurance</span><span>What stood out</span></div>"]
    for row in rows:
        if row["status"] != "graded":
            body.append(f"<div class='row off'><span class='rank'>&ndash;</span><div class='who'>{esc(row['client'])}"
                        f"<span class='muted skip'>{esc(row['status'])}</span></div></div>")
            continue
        r = row["_r"]
        p = _products(r)
        href = f"clients/{esc(row['client'])}.html"
        ages = " & ".join(str(a) for _, a in r["ages"])
        meta = [r["filing_status"] or "", f"age{'s' if len(r['ages']) > 1 else ''} {ages}" if ages else ""]
        if row["warnings"]:
            meta.append(f"<span class='skip'>{row['warnings']} to check</span>")
        cells = "".join(f"<div class='cell{' first' if i == 0 else ''}'><span class='lbl'>{esc(p[k]['name'])}</span>"
                        f"{verdict_pill(p[k], href)}<div class='sc'>{esc(p[k]['score_label'].replace('Grade ', ''))}</div></div>"
                        for i, k in enumerate(("aum", "annuity", "life")))
        opener = r["brief"]["opener"]
        why = (f"<div class='lead'>{esc(opener[0])}</div>" + "".join(f"<div class='more'>{esc(x)}</div>" for x in opener[1:2])
               if opener else "<div class='more'>Nothing on the return points to a conversation</div>")
        body.append(f"<div class='row'><span class='rank'>{row['rank']}</span>"
                    f"<div class='who'><a href='{href}' title='{esc(row['client'])}'>{esc(row['names'] or row['client'])}</a>"
                    f"<span class='muted'>{' &middot; '.join(m if m.startswith('<') else esc(m) for m in meta if m)}</span></div>"
                    f"{cells}<div class='why-c'><span class='lbl'>What stood out</span>{why}</div></div>")
    body.append("</div><div class='export noprint'><div><b>Export these results</b><span>Every client&rsquo;s brief on one "
                "printable page, or the whole run as an Excel workbook.</span></div><div class='ex-btns'>"
                "<a class='btn primary' href='export.html'>Printable page</a>"
                "<a class='btn' href='results.xlsx' download>Download Excel</a></div></div>")
    (out_dir / "summary.html").write_text(page("Client ranking", "".join(body), wide=True), encoding="utf-8")
