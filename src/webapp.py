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

from flask import Flask, abort, jsonify, redirect, request, send_from_directory
from werkzeug.utils import secure_filename

from .grader import run
from .report import CSS, esc

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
def _page(title, body):
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width, initial-scale=1'><title>{esc(title)}</title><style>{CSS}{EXTRA_CSS}"
            f"</style></head><body><main>{body}</main></body></html>")


EXTRA_CSS = """
.drop { border: 2px dashed #b9c0cc; border-radius: 12px; background: #fff; padding: 40px 16px; text-align: center; }
.drop.over { border-color: #2b5bb8; background: #f0f5ff; }
.drop .big { font-size: 17px; font-weight: 600; margin-bottom: 6px; }
.btn { font: inherit; padding: 9px 18px; border-radius: 8px; border: 1px solid #2b5bb8; background: #2b5bb8;
       color: #fff; cursor: pointer; text-decoration: none; display: inline-block; }
.btn.ghost { background: #fff; color: #2b5bb8; }
.btn:disabled { opacity: .5; cursor: default; }
.row { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; margin-top: 12px; }
label.c { display: block; margin: 16px 0; }
#status { margin: 14px 0; }
.spin { display: inline-block; width: 14px; height: 14px; border: 2px solid #b9c0cc; border-top-color: #2b5bb8;
        border-radius: 50%; animation: s 1s linear infinite; vertical-align: -2px; margin-right: 6px; }
@keyframes s { to { transform: rotate(360deg); } }
.nav { display: flex; justify-content: space-between; margin-bottom: 14px; font-size: 13px; }
input[type=file] { display: none; }
"""

HOME_JS = r"""
const drop = document.getElementById('drop'), status = document.getElementById('status'),
      go = document.getElementById('go'), picked = [];
const keep = n => /\.(pdf|ya?ml)$/i.test(n);

function render() {
  const pdfs = picked.filter(p => /\.pdf$/i.test(p.path));
  const folders = new Set(picked.map(p => p.path.split('/').slice(0, -1).join('/')).filter(Boolean));
  status.innerHTML = pdfs.length
    ? `<b>${pdfs.length} PDF${pdfs.length > 1 ? 's' : ''}</b> ready` + (folders.size ? ` from ${folders.size} folder${folders.size > 1 ? 's' : ''}` : '')
      + ` &middot; <a href="#" id="clear">clear</a>`
    : '';
  go.disabled = !pdfs.length;
  const c = document.getElementById('clear');
  if (c) c.onclick = e => { e.preventDefault(); picked.length = 0; render(); };
}
function add(file, path) { if (keep(file.name)) picked.push({file, path: path || file.name}); }

async function walk(entry, prefix) {
  if (entry.isFile) {
    const f = await new Promise((res, rej) => entry.file(res, rej));
    add(f, prefix + f.name);
  } else if (entry.isDirectory) {
    const reader = entry.createReader();
    let batch;
    do {
      batch = await new Promise((res, rej) => reader.readEntries(res, rej));
      for (const e of batch) await walk(e, prefix + entry.name + '/');
    } while (batch.length);
  }
}

['dragover', 'dragenter'].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.add('over'); }));
['dragleave', 'drop'].forEach(t => drop.addEventListener(t, () => drop.classList.remove('over')));
drop.addEventListener('drop', async e => {
  e.preventDefault();
  const entries = [...e.dataTransfer.items].map(i => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  status.innerHTML = '<span class="spin"></span>Reading folders&hellip;';
  if (entries.length) { for (const en of entries) await walk(en, ''); }
  else { [...e.dataTransfer.files].forEach(f => add(f)); }
  render();
});
document.getElementById('pickFolder').onclick = () => document.getElementById('folderIn').click();
document.getElementById('pickFiles').onclick = () => document.getElementById('filesIn').click();
document.getElementById('folderIn').onchange = e => { [...e.target.files].forEach(f => add(f, f.webkitRelativePath)); render(); };
document.getElementById('filesIn').onchange = e => { [...e.target.files].forEach(f => add(f)); render(); };

go.onclick = async () => {
  const fd = new FormData();
  picked.forEach(p => { fd.append('files', p.file, p.path); fd.append('paths', p.path); });
  if (document.getElementById('consent').checked) fd.append('consent', 'yes');
  go.disabled = true;
  const t0 = Date.now();
  const tick = setInterval(() => {
    status.innerHTML = `<span class="spin"></span>Grading&hellip; ${Math.round((Date.now() - t0) / 1000)}s. ` +
      'Text PDFs take a second or two; scanned PDFs take longer.';
  }, 500);
  try {
    const r = await fetch('/grade', {method: 'POST', body: fd});
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || r.statusText);
    window.location = j.url;
  } catch (err) {
    status.innerHTML = `<span class="warn">Could not grade: ${err.message}</span>`;
    go.disabled = false;
  } finally { clearInterval(tick); }
};
"""


def _past_runs():
    if not RUNS.exists():
        return []
    out = []
    for d in sorted((p for p in RUNS.iterdir() if p.is_dir() and RUN_RE.match(p.name)), reverse=True):
        if (d / "summary.csv").exists():
            n = sum(1 for _ in open(d / "summary.csv", encoding="utf-8")) - 1
            out.append((d.name, n))
    return out


@app.get("/")
def index():
    runs = _past_runs()
    past = ("<h2>Past runs</h2><div class='wrap'><table><tr><th>When</th><th>Clients</th><th></th></tr>"
            + "".join(f"<tr><td>{esc(datetime.strptime(r, '%Y-%m-%d_%H%M%S').strftime('%b %d, %Y %I:%M %p'))}</td>"
                      f"<td class='num'>{n}</td><td><a href='/runs/{r}/summary.html'>Open ranking</a></td></tr>"
                      for r, n in runs[:30])
            + "</table></div>") if runs else ""
    body = f"""
<h1>Tax Return Grader</h1>
<div class='sub'>Runs on this computer only. Drop a folder of client folders to grade a whole batch,
or one client's folder or PDFs.</div>
<div class='drop' id='drop'>
  <div class='big'>Drag client folders here</div>
  <div class='sub' style='margin:0'>Each sub-folder is one client (return, W-2s, 1099s, profile summary)</div>
  <div class='row'>
    <button class='btn ghost' id='pickFolder' type='button'>Choose a folder&hellip;</button>
    <button class='btn ghost' id='pickFiles' type='button'>Choose PDFs&hellip;</button>
  </div>
  <input type='file' id='folderIn' webkitdirectory multiple>
  <input type='file' id='filesIn' accept='.pdf' multiple>
</div>
<div id='status'></div>
<label class='c'><input type='checkbox' id='consent'> Written IRC &sect;7216 consent is on file for
  <b>every</b> client in this upload. Leave this unchecked to rely on each folder's <code>client.yaml</code>.
  The fictional test clients don't need it.</label>
<button class='btn' id='go' disabled>Grade</button>
{past}
<p class='sub' style='margin-top:24px'>Reports are saved (SSNs masked) in <code>outputs\\web</code>.
Uploaded PDFs are deleted after grading.</p>
<script>{HOME_JS}</script>"""
    return _page("Tax Return Grader", body)


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
    up = "summary.html" if fname.startswith("clients/") else None
    nav = ("<div class='nav'><a href='/'>&larr; Grade more clients</a>"
           + (f"<a href='/runs/{run_id}/{up}'>All clients in this run &rarr;</a>" if up else
              f"<a href='/runs/{run_id}/summary.csv'>Download summary.csv</a>") + "</div>")
    return f.read_text(encoding="utf-8").replace("<main>", "<main>" + nav, 1)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m src.webapp")
    ap.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    a = ap.parse_args(argv)
    url = f"http://{HOST}:{PORT}"
    print(f"Tax Return Grader is running at {url}  (this computer only)")
    print("Keep this window open while you use it. Close it, or press Ctrl+C, to stop.")
    if not a.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
