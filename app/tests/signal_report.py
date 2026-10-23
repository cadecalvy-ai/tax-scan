"""Precision / recall of fired signals versus the answer key's designed signals.

    python -m tests.signal_report            (writes outputs/test_report/signal_precision_recall.md)

"Designed" signals are the story each test client was built to tell. A fired
signal that isn't in the designed list counts as a false positive here, but
many of those are correct under the rules (e.g. a high earner is in the 24%
bracket) - the table lists them so you can judge.
"""
from collections import defaultdict
from pathlib import Path

from tests.harness import ROOT, answer_key, grade_all, in_band

OUT = ROOT / "outputs" / "test_report"


def build(results, key):
    tp, fp, fn = defaultdict(int), defaultdict(int), defaultdict(int)
    fp_who, fn_who = defaultdict(list), defaultdict(list)
    for cid, c in key.items():
        fired = {s["id"] for s in results[cid].get("signals", [])}
        want = set(c["designed_signals"])
        for s in fired & want:
            tp[s] += 1
        for s in fired - want:
            fp[s] += 1
            fp_who[s].append(cid)
        for s in want - fired:
            fn[s] += 1
            fn_who[s].append(cid)
    ids = sorted(set(tp) | set(fp) | set(fn))
    T, F, N = sum(tp.values()), sum(fp.values()), sum(fn.values())
    lines = ["# Signal precision / recall vs. designed signals", "",
             f"Overall: {T} true positives, {F} fired-but-not-designed, {N} missed. "
             f"Precision {T / max(T + F, 1):.0%}, recall {T / max(T + N, 1):.0%}.", "",
             "Recall is what matters for correctness: every designed signal should fire. "
             "'Not designed' hits are often correct under the rules; check the clients listed.", "",
             "| Signal | TP | Fired, not designed | Missed | Precision | Recall | Not-designed clients | Missed clients |",
             "|---|---:|---:|---:|---:|---:|---|---|"]
    for s in ids:
        p = tp[s] / max(tp[s] + fp[s], 1)
        r = tp[s] / max(tp[s] + fn[s], 1) if (tp[s] + fn[s]) else float("nan")
        lines.append(f"| `{s}` | {tp[s]} | {fp[s]} | {fn[s]} | {p:.0%} | "
                     f"{'n/a' if r != r else f'{r:.0%}'} | {', '.join(fp_who[s])} | {', '.join(fn_who[s])} |")
    lines += ["", "## Fit levels vs. intended", "",
              "| Client | AUM score | AUM fit | Intended | Annuity | Intended | Life | Intended |",
              "|---|---:|---|---|---|---|---|---|"]
    for cid, c in sorted(key.items()):
        s, want = results[cid]["scores"], c["intended"]
        mark = lambda ok: "" if ok else " ✗"
        lines.append(f"| {cid} | {s['aum_score']:.0f} | {s['aum_fit']}{mark(s['aum_fit'] == want['aum_fit'])} | "
                     f"{want['aum_fit']} | {s['annuity_grade']} ({s['annuity_points']:.0f})"
                     f"{mark(in_band(s['annuity_grade'], want['annuity_band']))} | {want['annuity_band']} | "
                     f"{s['life_grade']} ({s['life_points']:.0f}){mark(in_band(s['life_grade'], want['life_band']))} | "
                     f"{want['life_band']} |")
    return "\n".join(lines) + "\n", (T, F, N)


def write(results, key):
    text, counts = build(results, key)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "signal_precision_recall.md").write_text(text, encoding="utf-8")
    return text, counts


if __name__ == "__main__":
    text, _ = write(grade_all(), answer_key())
    print(text)
