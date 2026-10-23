"""Local web app: drag in a folder of client folders (or one client's PDFs), get the ranked reports.

    Double-click "Start Grader.bat", or run:  python -m src.webapp

Binds to 127.0.0.1 only, so it can't be reached from other computers.
Uploaded PDFs go to a temporary folder that is deleted as soon as grading
finishes. The reports (SSNs masked) are saved under outputs/web/<date_time>/
so past runs stay available from the home page. Nothing is sent anywhere.
"""
import argparse
import os
import re
import tempfile
import threading
import webbrowser
from datetime import datetime
from pathlib import Path, PurePosixPath

from flask import Flask, abort, jsonify, redirect, request, send_file, send_from_directory
from werkzeug.utils import secure_filename

from .grader import run
from .landing import WEB, build_sample_zip, render_landing

HOST, PORT = "127.0.0.1", 5057
ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "outputs" / "web"
KEEP = {".pdf", ".yaml", ".yml"}          # PDFs plus client.yaml (consent flag)
RUN_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 ** 3      # 2 GB per upload


# ---------------------------------------------------------------------
# Grouping uploaded files into clients
# ---------------------------------------------------------------------
def group_uploads(paths):
    """Map uploaded relative paths to client folders.

    - Files with no folder (picked individually)       -> one client
    - One folder containing PDFs directly              -> one client (that folder)
    - A folder of client folders, or several folders   -> one client per sub-folder
    Returns {client_name: [path, ...]}; files that sit beside client folders are skipped.
    """
    paths = [PurePosixPath(p.replace("\\", "/")) for p in paths]
    parents = {p.parent for p in paths}
    if len(parents) == 1:
        only = next(iter(parents))
        name = only.name or "Uploaded_Client"
        return {name: [str(p) for p in paths]}
    parts = [p.parent.parts for p in paths]
    common = 0
    while all(len(x) > common for x in parts) and len({x[common] for x in parts}) == 1:
        common += 1
    groups = {}
    for p, pp in zip(paths, parts):
        if len(pp) > common:
            groups.setdefault(pp[common], []).append(str(p))
    return groups


def _safe_rel(path):
    parts = [secure_filename(x) for x in PurePosixPath(path.replace("\\", "/")).parts]
    return [x for x in parts if x]


# ---------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------
def _past_runs():
    if not RUNS.exists():
        return []
    out = []
    for d in sorted((p for p in RUNS.iterdir() if p.is_dir() and RUN_RE.match(p.name)), reverse=True):
        if (d / "summary.csv").exists():
            n = sum(1 for _ in open(d / "summary.csv", encoding="utf-8")) - 1
            when = datetime.strptime(d.name, "%Y-%m-%d_%H%M%S").strftime("%b %d, %Y · %I:%M %p")
            out.append({"id": d.name, "when": when, "n": n, "url": f"/runs/{d.name}/summary.html"})
    return out


@app.get("/")
def index():
    return render_landing("local", runs=_past_runs()[:20])


@app.get("/anime.min.js")
def anime_js():
    return send_from_directory(WEB, "anime.min.js")


@app.get("/sample-clients.zip")
def sample_zip():
    z = RUNS.parent / "sample-clients.zip"
    if not z.exists():
        build_sample_zip(z)
    return send_file(z, as_attachment=True, download_name="sample-clients.zip")


@app.get("/grade")
def grade_page():
    # Refreshing or reopening the grading address lands here; send the user to the upload page.
    return redirect("/")


@app.post("/grade")
def grade():
    files = request.files.getlist("files")
    paths = request.form.getlist("paths")
    if len(paths) != len(files):                  # folder structure is sent alongside; fall back to file names
        paths = [f.filename for f in files]
    pairs = [(str(PurePosixPath(p.replace("\\", "/"))), f) for p, f in zip(paths, files)
             if Path(p).suffix.lower() in KEEP]
    if not any(p.lower().endswith(".pdf") for p, _ in pairs):
        return jsonify(error="No PDF files were uploaded."), 400
    groups = group_uploads([p for p, _ in pairs])
    by_path = dict(pairs)
    run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_dir = RUNS / run_id
    with tempfile.TemporaryDirectory(prefix="grader_") as tmp:
        base = Path(tmp) / "clients"
        for client, paths in groups.items():
            folder = base / (secure_filename(client) or "Client")
            folder.mkdir(parents=True, exist_ok=True)
            for p in paths:
                parts = _safe_rel(p)
                if parts:
                    by_path[p].save(folder / parts[-1])
            if request.form.get("consent") == "yes":
                (folder / "client.yaml").write_text("consent_7216: true\n", encoding="utf-8")
        folders = [d for d in base.iterdir() if any(d.glob("*.pdf"))]
        if not folders:
            return jsonify(error="No client folders with PDFs were found."), 400
        try:
            workers = max(1, min(len(folders), (os.cpu_count() or 2) // 2))
            # one folder -> grade it directly; several -> grade each sub-folder
            run(folders[0] if len(folders) == 1 else base, out_dir, workers=workers)
        except Exception as e:
            return jsonify(error=f"grading failed: {e}"), 500
    target = "summary.html"
    if len(folders) == 1:
        page = next((out_dir / "clients").glob("*.html"), None)
        target = f"clients/{page.name}" if page else target
    return jsonify(url=f"/runs/{run_id}/{target}")


@app.get("/runs/<run_id>/<path:fname>")
def run_file(run_id, fname):
    if not RUN_RE.match(run_id):
        abort(404)
    folder = RUNS / run_id
    if not fname.endswith(".html"):
        return send_from_directory(folder, fname)
    f = (folder / fname).resolve()
    if folder.resolve() not in f.parents or not f.exists():
        abort(404)
    links = ["<a href='/'>Grade more</a>"]
    if fname.startswith("clients/"):
        links.append(f"<a href='/runs/{run_id}/summary.html'>All clients</a>")
    else:
        links.append(f"<a href='/runs/{run_id}/summary.csv'>summary.csv</a>")
    return f.read_text(encoding="utf-8").replace("<!--NAV-->", "".join(links), 1)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m src.webapp")
    ap.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    a = ap.parse_args(argv)
    url = f"http://{HOST}:{PORT}"
    print(f"Tax Scan is running at {url}  (this computer only)")
    print("Keep this window open while you use it. Close it, or press Ctrl+C, to stop.")
    if not a.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
