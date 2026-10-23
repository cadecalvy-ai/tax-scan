"""Build the public Tax Scan site for Netlify from the FICTIONAL test clients.

    .venv\\Scripts\\python scripts\\build_netlify_demo.py

Output (netlify_site/):
  index.html            landing page (hero + drop box, demo mode: nothing is uploaded or read)
  anime.min.js          animation library (MIT), served locally
  sample-clients.zip    the 24 fictional clients' PDFs, to try the drop box / the local grader
  demo/index.html       ranking of the sample clients
  demo/clients/*.html   one profile per sample client

Netlify publishes this folder (see netlify.toml); pushing to GitHub redeploys it.

Safety: this only ever publishes fictional data. It grades inputs/test_clients and stops if
any client is not marked as a fictional test client, or if an unmasked SSN appears in a page.
Never point it at real client folders - the site is public.
"""
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.grader import run  # noqa: E402
from src.landing import WEB, build_sample_zip, render_landing, sample_names  # noqa: E402

SRC = ROOT / "inputs" / "test_clients"
SITE = ROOT / "netlify_site"
BANNER = ("<div class='banner'><b>Demo &mdash; fictional test data.</b> These clients, returns, and numbers are "
          "invented to show what Tax Scan produces. No real client data.</div>")
NOINDEX = "<meta name='robots' content='noindex'>"
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
        for old in sorted(SITE.rglob("*"), reverse=True) if SITE.exists() else []:
            if old.is_file():
                old.unlink()
            else:
                try:
                    old.rmdir()
                except OSError:
                    pass
        (SITE / "demo" / "clients").mkdir(parents=True, exist_ok=True)
        out = Path(tmp)

        summary = (out / "summary.html").read_text(encoding="utf-8")
        summary = summary.replace("<!--NAV-->", "<a href='../index.html'>Home</a>"
                                  "<a href='../sample-clients.zip'>Sample files</a><a href='summary.csv'>summary.csv</a>", 1)
        summary = summary.replace("<main>", "<main>" + BANNER, 1).replace("<title>", NOINDEX + "<title>", 1)
        (SITE / "demo" / "index.html").write_text(summary, encoding="utf-8")
        shutil.copy(out / "summary.csv", SITE / "demo" / "summary.csv")
        for f in (out / "clients").glob("*.html"):
            page = f.read_text(encoding="utf-8")
            page = page.replace("<!--NAV-->", "<a href='../../index.html'>Home</a><a href='../index.html'>All clients</a>", 1)
            page = page.replace("<main>", "<main>" + BANNER, 1).replace("<title>", NOINDEX + "<title>", 1)
            (SITE / "demo" / "clients" / f.name).write_text(page, encoding="utf-8")

    landing = render_landing("demo", sample_url="demo/index.html", sample_names=sample_names())
    (SITE / "index.html").write_text(landing.replace("<title>", NOINDEX + "<title>", 1), encoding="utf-8")
    shutil.copy(WEB / "anime.min.js", SITE / "anime.min.js")
    build_sample_zip(SITE / "sample-clients.zip")
    (SITE / "_headers").write_text(HEADERS, encoding="utf-8")

    # last line of defence: no SSN-shaped number may appear in a published page
    for f in list(SITE.rglob("*.html")) + list(SITE.rglob("*.csv")):
        if re.search(r"\b\d{3}-\d{2}-\d{4}\b", f.read_text(encoding="utf-8", errors="ignore")):
            sys.exit(f"Refusing to publish: unmasked SSN found in {f}")
    zip_path = shutil.make_archive(str(SITE), "zip", SITE)
    n = len(list((SITE / "demo" / "clients").glob("*.html")))
    print(f"Built {SITE}: landing page, {n} sample client profiles, sample-clients.zip. Also {zip_path}")


if __name__ == "__main__":
    main()
