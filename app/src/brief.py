"""Turn scored signals into a client conversation brief.

For each product: a plain-English verdict, a meter showing where the score sits
against the grade cut-offs, the top reasons, and talking points (headline, why it
matters, a question to ask). All wording comes from config/grader.yaml
("display" and "conversation"), so it can be edited without touching code.
"""

TONE = {"Strong fit": "good", "Good fit": "good", "Worth a conversation": "mid"}
ORDER = {"good": 0, "mid": 1, "low": 2}
# Talking-point order: concrete events first (best conversation openers), background facts last.
EVENT_GROUPS = {"aum.rollover", "aum.asset_sale", "aum.inheritance", "aum.early_withdrawal", "aum.income_drop",
                "aum.stock_comp_amt", "annuity.transition", "life.life_event", "aum.no_retirement_savings"}
CONTEXT_GROUPS = {"aum.agi", "life.income", "annuity.bracket_24", "annuity.age"}


def _rank(group, points):
    return (0 if group in EVENT_GROUPS else 2 if group in CONTEXT_GROUPS else 1, -points)


def _lead_rank(t, pos):
    """Order for "what stood out": the strongest product first (pos = its place in the ranking), then
    concrete events, then points backed by a dollar figure from the return, then rule weight."""
    kind, pts = _rank(t["group"], t["points"])
    return (pos[t["group"].split(".")[0]], kind, 0 if _amounts(t["headline"]) else 1, pts)


def _lead_order(products, ranked):
    """Each worthwhile product's best point, strongest product first; then everything else."""
    pos = {p["key"]: i for i, p in enumerate(ranked)}
    tps = sorted((t for p in products for t in p["points"]), key=lambda t: _lead_rank(t, pos))
    firsts = []
    for p in ranked:
        if p["tone"] != "low":
            firsts += [t for t in tps if t["group"].split(".")[0] == p["key"]][:1]
    return firsts + [t for t in tps if not any(t is f for f in firsts)]
SNAPSHOT = [("agi", "Household income (AGI)"), ("interest", "Interest (cash & CDs)"),
            ("dividends", "Dividends"), ("cap_gain", "Capital gains"),
            ("retirement", "Retirement distributions"), ("ss", "Social Security"),
            ("sch_c_net", "Business income (Sch C)"), ("sch_f_net", "Farm income (Sch F)"),
            ("k1_ordinary", "S-corp income (K-1)")]


class _Blank(dict):
    def __missing__(self, key):
        return ""


def _fill(text, s, year):
    detail = s.detail or s.value
    out = (text or "").format_map(_Blank(value=s.value, detail=detail, year=year)).strip()
    return out.replace("(s)", "" if s.value == 1 else "s")      # "1 dependent", "2 dependents"


def _talking_point(s, conv, year):
    c = conv.get(s.id) or conv.get(s.group)      # a specific tier (e.g. annuity.age_65) can override the group
    if not c:
        return None
    return {"headline": _fill(c.get("headline"), s, year), "why": _fill(c.get("why"), s, year),
            "ask": _fill(c.get("ask"), s, year), "points": s.points, "group": s.group}


def _meter(points, cuts, scale_max, tick_label):
    """Fill fraction and tick marks (label, position 0-1) for a score bar."""
    top = max(scale_max, points, 1)
    ticks = [(tick_label(lbl, cut), cut / top) for lbl, cut in cuts]
    return {"fill": max(0.0, min(1.0, points / top)), "ticks": ticks}


def _next_step(points, cuts, labels):
    """'12 points from Good fit': only toward a level worth talking about."""
    for lbl, cut in sorted(cuts, key=lambda c: c[1]):
        name = labels.get(lbl, lbl)
        if points < cut and TONE.get(name, "low") != "low":
            return f"{cut - points:.0f} points from {name}"
    return ""


def _amounts(text):
    import re
    return set(re.findall(r"\$[\d,]+", text))


def _note_items(notes):
    """Client notes as short strings: free-text sentences, then answered questions with comments."""
    if not notes:
        return []
    items = list(notes.get("notes", []))
    for a in notes.get("answers", []):
        if a["answer"] == "Yes" or a["comment"]:
            items.append(f"{a['question']} {a['answer']}" + (f" ({a['comment']})" if a["comment"] else ""))
    return items


def _mentions(text, keyword):
    import re
    return re.search(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])", text.lower()) is not None


def link_notes(products, order, notes, links):
    """Attach each client note to the first talking point (strongest product first) whose topic it mentions."""
    for item in _note_items(notes):
        groups = [g for topic in links.values() if any(_mentions(item, k) for k in topic["keywords"])
                  for g in topic["groups"]]
        if not groups:
            continue
        for key in order:
            tp = next((t for t in products[key]["points"] if t["group"] in groups), None)
            if tp is not None:
                tp.setdefault("client_notes", []).append(item)
                break


def context_values(ctx):
    """Plain values from the preparer pages (tax rates, state summary, Form 2441); {} when absent."""
    if not ctx:
        return {}
    v = {k: f.value for k, f in ctx.items() if hasattr(f, "value") and f.value not in (None, "")}
    fmt_pct = lambda x: f"{x:g}"  # noqa: E731
    out = {}
    for k in ("federal_marginal", "federal_effective", "state_marginal", "state_effective"):
        if k in v:
            out[k] = fmt_pct(v[k])
    if v.get("state_name"):
        out["state_name"] = v["state_name"]
    if v.get("state_tax"):
        out["state_tax"] = f"${v['state_tax']:,.0f}"
    provs = ctx.get("care_providers") or []
    paid = sum(p["paid"].value or 0 for p in provs)
    if paid:
        out["care_paid"] = f"${paid:,.0f}"
        out["care_provider"] = ", ".join(p["name"] for p in provs if p["name"]) or "provider"
    pnl = [d for d in ctx.get("pnl") or [] if d["net"].value is not None or d["income"].value is not None]
    if pnl:
        d = pnl[0]
        out["pnl_business"] = d["business"] or "the business"
        if d["income"].value is not None:
            out["pnl_income"] = f"${d['income'].value:,.0f}"
        if d["net"].value is not None:
            out["pnl_net"] = f"${d['net'].value:,.0f}"
    buys = [d for d in ctx.get("asset_purchases") or [] if d["price"].value]
    if buys:
        d = buys[0]
        out["asset_desc"] = d["description"] or "business equipment"
        out["asset_price"] = f"${d['price'].value:,.0f}"
        out["asset_date"] = _long_date(d["date"]) if d["date"] else ""
        out["asset_financed"] = f"${d['financed'].value:,.0f}" if d["financed"].value else ""
        out["asset_financed_note"] = f", {out['asset_financed']} of it financed" if d["financed"].value else ""
    return out


def _long_date(iso):
    """'2025-03-22' -> 'March 22, 2025'."""
    import datetime
    try:
        return datetime.date.fromisoformat(iso).strftime("%B %d, %Y").replace(" 0", " ")
    except ValueError:
        return iso


def tax_picture(vals, forms):
    """Short label/value chips for the brief's Tax picture strip."""
    chips = []
    if "federal_marginal" in vals:
        chips.append({"label": "Federal marginal rate", "value": f"{vals['federal_marginal']}%",
                      "sub": f"{vals.get('federal_effective', '?')}% effective"})
    if "state_tax" in vals:
        chips.append({"label": f"{vals.get('state_name', 'State')} income tax", "value": vals["state_tax"],
                      "sub": f"{vals.get('state_marginal', '?')}% marginal"})
    elif "state_name" in vals:
        chips.append({"label": "State", "value": vals["state_name"], "sub": "no state tax due"})
    if "care_paid" in vals:
        b = (forms.get("2441") or {}).get("12")
        chips.append({"label": "Child care paid", "value": vals["care_paid"],
                      "sub": vals["care_provider"] + (f" · ${b.value:,.0f} employer benefits" if b and b.value else "")})
    if "pnl_net" in vals or "pnl_income" in vals:
        sc = (forms.get("Sch C") or {}).get("31")
        sub = f"{vals['pnl_business']} P&L"
        if "pnl_income" in vals:
            sub += f" · {vals['pnl_income']} of sales"
        if sc is not None and sc.value is not None:
            sub += f" · Schedule C net ${sc.value:,.0f}"
        chips.append({"label": "Business books (net income)", "value": vals.get("pnl_net", vals.get("pnl_income")),
                      "sub": sub})
    if "asset_price" in vals:
        sub = vals["asset_desc"]
        if vals["asset_date"]:
            sub += f" · {vals['asset_date']}"
        if vals["asset_financed"]:
            sub += f" · {vals['asset_financed']} financed"
        chips.append({"label": "Equipment purchase", "value": vals["asset_price"], "sub": sub})
    return chips


def link_context(products, order, vals, lines):
    for spec in lines.values():
        if spec.get("only_if") and not vals.get(spec["only_if"]):
            continue
        try:
            text = spec["text"].format(**vals)
        except KeyError:
            continue                     # the documents didn't include what this line needs
        if "federal_marginal" in spec["text"] and vals.get("federal_marginal") in ("0", None) \
                and vals.get("federal_effective") in ("0", None):
            continue                     # nothing to say about a 0% bracket
        # groups are listed in order of preference; strongest product first within each
        tp = next((t for g in spec["groups"] for key in order for t in products[key]["points"] if t["group"] == g), None)
        if tp is not None:
            tp.setdefault("context", []).append(text)


def build_brief(signals, scores, cfg, year, figures, notes=None, context=None, forms=None):
    disp = cfg.get("display", {})
    conv = cfg.get("conversation", {})
    names = disp.get("product_names", {"aum": "Investment management", "annuity": "Annuity", "life": "Life insurance"})
    v_aum = disp.get("verdicts", {}).get("aum", {})
    v_grade = disp.get("verdicts", {}).get("grades", {})
    per_product = disp.get("max_points_per_product", 3)
    bands = cfg["bands"]

    products = []
    for key in ("aum", "annuity", "life"):
        if key == "aum":
            value, verdict = scores["aum_score"], v_aum.get(scores["aum_fit"], scores["aum_fit"])
            cuts = [("med", bands["aum"]["med"]), ("high", bands["aum"]["high"])]
            meter = _meter(value, cuts, 100, lambda lbl, cut: str(cut))
            score_label = f"{value:.0f}/100"
            nxt = _next_step(value, cuts, v_aum)
        else:
            value, grade = scores[f"{key}_points"], scores[f"{key}_grade"]
            verdict = v_grade.get(grade, grade)
            cuts = [(g, bands["grades"][g]) for g in ("D", "C", "B", "A")]
            meter = _meter(value, cuts, bands["grades"]["A"] * 1.3, lambda lbl, cut: lbl)
            score_label = f"Grade {grade} · {value:.0f} pts"
            nxt = _next_step(value, cuts, v_grade)
        tone = TONE.get(verdict, "low")
        sigs = sorted((s for s in signals if s.product == key and s.points > 0), key=lambda s: _rank(s.group, s.points))
        tps, seen, amts_used = [], set(), set()
        for s in sigs:
            tp = _talking_point(s, conv, year)
            if not tp or (s.group, tp["headline"]) in seen:
                continue
            amts = _amounts(tp["headline"])
            if amts and amts <= amts_used:
                continue                 # e.g. "$1.84M of capital gains" after "Large sale gain of $1.84M"
            seen.add((s.group, tp["headline"]))
            amts_used |= amts
            tps.append(tp)
        # life events after the first carry 0 points but are still worth mentioning
        for s in signals:
            if s.product == key and s.points == 0 and s.group == "life.life_event":
                tp = _talking_point(s, conv, year)
                if tp and (s.group, tp["headline"]) not in seen:
                    seen.add((s.group, tp["headline"]))
                    tps.append(tp)
        products.append({"key": key, "name": names.get(key, key), "verdict": verdict, "tone": tone,
                         "score_label": score_label, "value": value, "meter": meter, "next": nxt,
                         "reasons": [t["headline"] for t in tps[:3]], "points": tps[:per_product],
                         "more": max(0, len(tps) - per_product)})

    ranked = sorted(products, key=lambda p: (ORDER[p["tone"]], -p["value"] / (100 if p["key"] == "aum" else
                                                                             bands["grades"]["A"])))
    all_tps = _lead_order(products, ranked)
    # A "transition" restates other signals (widowhood, income drop, rollover). When those signals are
    # there, say them in their own words ("Rolled $418,000 out of a workplace plan") at the transition's
    # place, which reflects the stronger product.
    covered = {"widowhood": "life.life_event", "income drop": "aum.income_drop", "early retirement": "aum.income_drop",
               "rollover": "aum.rollover"}
    opener, used = [], set()
    for t in all_tps:
        lines = [t["headline"]]
        if t["group"] == "annuity.transition":
            reasons = [x.strip().lower() for x in t["headline"].split(":", 1)[-1].split(";")]
            subs = []
            for r in reasons:
                k = next((k for k in covered if r.startswith(k)), None)
                same = [x for x in all_tps if k and x["group"] == covered[k]]
                sub = next((x for x in same if k in x["headline"].lower()), same[0] if same else None)
                if sub is None:
                    break
                subs.append(sub["headline"])
            else:
                lines = subs
        for line in lines:
            amts = _amounts(line)
            if line in opener or (amts and amts <= used):
                continue                 # same fact told twice (e.g. a rollover as AUM and as a transition)
            opener.append(line)
            used |= amts
        if len(opener) >= disp.get("opener_points", 3):
            opener = opener[:disp.get("opener_points", 3)]
            break

    fig = {f["key"]: f["value"] for f in figures}
    fig["retirement"] = (fig.get("ira_gross") or 0) + (fig.get("pen_gross") or 0)
    snapshot = [{"label": lbl, "value": fig[k]} for k, lbl in SNAPSHOT if fig.get(k)]
    order = [p["key"] for p in ranked]
    if notes:
        link_notes({p["key"]: p for p in products}, order, notes, disp.get("note_links", {}))
    vals = context_values(context)
    if vals:
        link_context({p["key"]: p for p in products}, order, vals, disp.get("context_lines", {}))
    return {"products": products, "order": order, "opener": opener, "snapshot": snapshot[:6],
            "client_notes": notes, "tax_picture": tax_picture(vals, forms or {})}
