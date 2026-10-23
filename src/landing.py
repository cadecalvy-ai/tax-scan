"""The Tax Scan landing page (hero + drop box), shared by the local web app and the Netlify demo.

mode "local": dropped files are graded on this computer (POST /grade).
mode "demo":  public site; dropped files are never uploaded or read. Folders named like the
              fictional sample clients link to their pre-computed reports.
"""
import json
import zipfile
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web"
ROOT = WEB.parents[1]
SAMPLE_CLIENTS = ROOT / "inputs" / "test_clients"


def render_landing(mode, runs=(), sample_url="", sample_names=()):
    html = (WEB / "landing.html").read_text(encoding="utf-8")
    return (html.replace("__MODE__", mode)
                .replace("__RUNS__", json.dumps(list(runs)))
                .replace("__SAMPLE__", sample_url)
                .replace("__SAMPLES__", json.dumps(list(sample_names))))


def sample_names():
    return sorted(p.name for p in SAMPLE_CLIENTS.iterdir() if p.is_dir() and p.name[:1] == "C")


def build_sample_zip(dest):
    """Zip the fictional sample clients' PDFs as sample-clients/<client>/<file>.pdf."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("sample-clients/README.txt",
                   "FICTIONAL TEST DATA - not real people or returns.\n"
                   "Unzip, then drag the sample-clients folder (or any client folder inside it) onto Tax Scan.\n")
        for name in sample_names():
            for pdf in sorted((SAMPLE_CLIENTS / name).glob("*.pdf")):
                z.write(pdf, f"sample-clients/{name}/{pdf.name}")
    return dest
