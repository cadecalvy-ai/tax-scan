"""Read the true 1040 line values from real tax-software returns (ground truth for the RIA test returns).

    ..\.venv\Scripts\python scripts\real_return_truth.py "..\test clients from ria\clients"

Writes truth.json next to the clients folder; app/tests/test_real_returns.py compares against it.
import json
import re
import sys
from pathlib import Path

import pdfplumber

LABELS = ["1a", "1e", "1z", "2a", "2b", "3a", "3b", "4a", "4b", "5a", "5b", "6a", "6b", "7", "8", "9", "10", "11a",
          "11b", "12e", "13a", "13b", "14", "15", "16", "17", "18", "19", "22", "23", "24", "25a", "25b", "25d", "26",
          "28", "33", "34", "35a", "37"]
AMT = r"(\(?[\d,]+\.?\)?)"


def truth(pdf):
    with pdfplumber.open(pdf) as d:
        pages = [p.extract_text() or "" for p in d.pages]
    idx = [i for i, t in enumerate(pages) if "U.S. Individual Income Tax Return" in t and "Form" in t[:200]]
    idx = [i for i in idx if "8879" not in pages[i][:80]]
    p1 = idx[0]
    text = pages[p1] + "\n" + pages[p1 + 1]
    out = {}
    for lab in LABELS:
        m = re.findall(rf"(?:^|\s){lab}\s+{AMT}(?=\s|$)", text, flags=re.M)
        if m:
            v = m[-1].strip("().").replace(",", "")
            if v.isdigit():
                out[lab] = int(v)
    status = re.search(r"X\s+(Single|Married filing jointly|Head of household|Married filing separately)", text)
    out["status"] = status.group(1) if status else None
    out["_pages"] = [p1 + 1, p1 + 2]
    return out


if __name__ == "__main__":
    root = Path(sys.argv[1])
    res = {}
    for d in sorted(root.iterdir()):
        r = next(d.glob("2025_Prepared_Return_*.pdf"))
        res[d.name] = truth(r)
        print(d.name, json.dumps(res[d.name]))
    (root.parent / "truth.json").write_text(json.dumps(res, indent=1))
