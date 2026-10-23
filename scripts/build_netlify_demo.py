"""Build a static demo site of the FICTIONAL test-client reports, ready for Netlify.

    .venv\\Scripts\\python scripts\\build_netlify_demo.py

Output: netlify_site/ (index.html = ranking, clients/*.html = reports) and
netlify_site.zip. Deploy by dragging the folder or zip onto https://app.netlify.com/drop.

Safety: this only ever publishes fictional data. It grades inputs/test_clients and
stops if any client is not marked as a fictional test client in its profile.
Never point it at real client folders - Netlify sites are public.
"""
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.grader import run  # noqa: E402

SRC = ROOT / "inputs" / "test_clients"
SITE = ROOT / "netlify_site"
BANNER = ("<div style='background:#fff4d6;border:1px solid #e8c766;border-radius:8px;padding:8px 12px;"
          "margin-bottom:16px;font-size:13px'><b>Demo &mdash; fictional test data.</b> These clients, returns, "
          "and numbers are invented to show what the Tax Return Grader produces. No real client data.</div>")
HEADERS = """/*
  X-Robots-Tag: noindex
  X-Frame-Options: DENY
  Referrer-Policy: no-referrer
"""


def main():
    with tempfile.TemporaryDirectory() as tmp:
        results = run(SRC, tmp, workers=6)
        not_test = [r["client"] for r in results
                    if r.get("status") != "graded" or not str(r.get("consent", "")).startswith("fictional test client")]
        if not_test:
            sys.exit(f"Refusing to build: these are not graded fictional test clients: {not_test}")
        # clear old files but keep the folders (OneDrive can lock a folder being deleted)
        for old in SITE.rglob("*") if SITE.exists() else []:
            if old.is_file():
                old.unlink()
        (SITE / "clients").mkdir(parents=True, exist_ok=True)
        out = Path(tmp)
        index = (out / "summary.html").read_text(encoding="utf-8")
        index = index.replace("<h1>Client ranking</h1>",
                              BANNER + "<h1>Client ranking</h1>", 1)
        index = index.replace("<title>", "<meta name='robots' content='noindex'><title>", 1)
        (SITE / "index.html").write_text(index, encoding="utf-8")
        shutil.copy(out / "summary.csv", SITE / "summary.csv")
        for f in (out / "clients").glob("*.html"):
            page = f.read_text(encoding="utf-8")
            page = page.replace("<main>", "<main><p style='font-size:13px'><a href='../index.html'>&larr; All clients"
                                "</a></p>" + BANNER, 1)
            page = page.replace("<title>", "<meta name='robots' content='noindex'><title>", 1)
            (SITE / "clients" / f.name).write_text(page, encoding="utf-8")
    (SITE / "_headers").write_text(HEADERS, encoding="utf-8")
    # last line of defence: nothing SSN-shaped may be published
    for f in SITE.rglob("*"):
        if f.is_file() and re.search(r"\b\d{3}-\d{2}-\d{4}\b", f.read_text(encoding="utf-8", errors="ignore")):
            sys.exit(f"Refusing to publish: unmasked SSN found in {f}")
    zip_path = shutil.make_archive(str(SITE), "zip", SITE)
    print(f"Built {SITE} ({len(list((SITE / 'clients').glob('*.html')))} client reports) and {zip_path}")
    print("Deploy: drag the netlify_site folder (or the zip) onto https://app.netlify.com/drop")


if __name__ == "__main__":
    main()
