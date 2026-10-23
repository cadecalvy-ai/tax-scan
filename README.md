# Tax Return Grader

Reads a client's tax return and supporting documents (PDFs exported from Canopy, text or scanned) and grades
the client's fit for three services:

- **AUM:** a score from 0 to 100, banded high, med or low
- **Annuity:** a grade from A to F
- **Life insurance:** a grade from A to F

Each client gets a one-page HTML report. It shows every signal that fired, with the document and line or box it
came from, plus validation warnings and talking points. A ranked `summary.html` / `summary.csv` covers the whole
batch.

**Everything runs on this computer.** No client data is sent to any outside service, and there is no LLM in the
loop. SSNs are masked to the last 4 digits in every report and output file.

---

## 1. Setup (Windows, one time)

Run these in PowerShell or Command Prompt from this folder.

1. **Python 3.11 or newer**
   ```
   winget install -e --id Python.Python.3.12 --scope user
   ```
2. **Poppler** (renders scanned PDF pages to images)
   ```
   winget install -e --id oschwartz10612.Poppler
   ```
3. **Tesseract OCR** (reads scanned pages)
   ```
   winget install -e --id UB-Mannheim.TesseractOCR
   ```
   It installs to `C:\Program Files\Tesseract-OCR\`. The grader finds it there automatically.
4. **Python packages** (into a project-local virtual environment)
   ```
   py -3.12 -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   ```

The grader looks for Poppler and Tesseract on `PATH`, then in the default winget and Program Files locations.
If you installed them somewhere else, set `POPPLER_PATH` to the folder that contains `pdftoppm.exe` and
`TESSERACT_CMD` to the full path of `tesseract.exe`.

## 2. Grading clients

### The easy way: double-click `Start Grader.bat`

Your browser opens to the grader page.

1. Drag a folder of client folders onto it, with one sub-folder per client (or drop a single client's folder
   or PDFs).
2. Click **Grade**.
3. The ranking opens. Click a client for their full report.

Past runs are listed on the home page and saved (SSNs masked) under `outputs\web\`. Keep the black window open
while you use the grader, and close it to stop.

### Command line

Put each client's PDFs in their own folder, for example `inputs/2026_batch/Smith_John/`, then run:

```
.venv\Scripts\python -m src.grader inputs\2026_batch --out outputs\2026_batch
```

- The input can be one client folder or a folder of client folders.
- Open `outputs\2026_batch\summary.html` for the ranking. Each client's report is under `clients\`.
- `summary.csv` opens in Excel. `results.json` has everything in machine-readable form, with SSNs masked.
- `--workers 4` grades four clients at once, which helps when there are many scans.
- `--cache <folder>` keeps OCR results between runs, so repeat runs on scans are fast. The cache contains text
  read from client documents. Point it only at a private local folder, and delete it when you're done.

Try it on the fictional test clients:

```
.venv\Scripts\python -m src.grader inputs\test_clients --out outputs\test_clients --workers 6
```

### About the web page

`Start Grader.bat` runs `.venv\Scripts\python -m src.webapp`, which serves <http://127.0.0.1:5057>. It binds to
`127.0.0.1` only, so other computers can't reach it. Uploaded PDFs go to a temporary folder that is deleted
as soon as grading finishes. The **consent checkbox** applies to every client in that upload. Leave it
unchecked to rely on each folder's own `client.yaml`.

## 3. IRC §7216: client consent (read this)

If your firm prepared these returns, using return information to market non-tax services (investment
management, annuities, insurance) generally requires the client's **prior written consent** under IRC §7216
and Treas. Reg. §301.7216-3. Talk to your compliance team about the consent form and its wording.

The grader enforces this:

- A client folder is graded only if it contains `client.yaml` with:
  ```yaml
  consent_7216: true
  ```
  Add it only after the signed consent is on file.
- With no `client.yaml`, or with `consent_7216: false`, the client is **not graded**. The summary lists it as
  "not graded" with the reason. The return and source documents are not read. With no `client.yaml`, only a
  file named like `*profile*.pdf` is opened, to check for the fictional-test-client marker.
- The fictional test clients are exempt. Their profile summary is marked "FICTIONAL TEST CLIENT". A
  `client.yaml` with `consent_7216: false` still blocks them.
- On the upload page, a checkbox records that consent is on file.

## 4. Tuning the rules

Every threshold, weight, band, and talking-point template is in **`config/grader.yaml`**, and nothing is
hard-coded. Edit it and re-run. The report always shows which rule fired and why, so you can see the effect
of a change. For example, to make large rollovers count more:

```yaml
aum:
  rollover:
    min: 100000
    points: 40
```

Signal IDs (like `aum.rollover_100k`) include the threshold, so the reports stay readable after you change
one.

### How the signals are read

| Rule | Where it comes from |
|---|---|
| AGI tiers | 1040 line 11a (2025) or 11 (2024), cross-checked against 11b and against line 9 minus line 10 |
| Dividends + capital gains | lines 3b + 7 (cross-checked with Schedule B, Schedule D, 1099-DIV) |
| Interest | line 2b (Schedule B, 1099-INT) |
| Distributions / rollover / inheritance / early withdrawal | 1099-R box 7 code (G, 4, 1), lines 4a/5a, Form 5329 |
| Dividend jump (inheritance) | 3b this year vs. the prior-year return |
| Home or business sale | Form 8949 rows, Schedule D line 10, 1099-S |
| NIIT / AMT / stock comp | Form 8960 line 17, Schedule 2, Form 6251, Form 3921 |
| No retirement savings | W-2 box 12 deferral codes, Schedule 1 lines 16 and 20 |
| Ages | Profile summary DOBs, then the 1040 "born before" boxes, then SSA-1099 |
| Single earner | W-2 box 1 by employee SSN, plus Schedule C owner |
| Life events | Filing status, spouse deceased marker, and dependents vs. the prior-year return; new baby from dependent DOBs |

## 5. How it works

```
src/ingest.py    read PDFs: pdfplumber for text, Poppler + Tesseract for scans
                 (straighten, erase form rules, two OCR passes merged)
src/classify.py  identify each page: 1040 page 1/2, schedules, W-2, 1099s, SSA-1099, K-1, 3921, 1098, profile
src/extract.py   pull values: form lines matched by their printed wording; information-return boxes by label
src/record.py    assemble one record per client per tax year
src/validate.py  cross-check (AGI = line 9 - line 10, W-2 total = line 1a, ...); use the best-supported value
src/signals.py   evaluate the rules in config/grader.yaml; score and grade
src/report.py    per-client HTML, summary.html, summary.csv
src/grader.py    command line, consent gate
src/webapp.py    optional localhost upload page
```

**Validation.** A return states most figures more than once: the 1040 line, the schedule behind it, the source
documents, and the arithmetic. For each key figure the grader compares every reading and uses the value most
of them agree on. **Every disagreement appears as a warning on the report**, and nothing is changed
silently. This matters most for scans, where OCR occasionally misreads a digit.

**Scans.** Pages with no text layer are OCR'd at 400 dpi. Amounts on scans are re-read from close-up crops,
and the majority of the readings is used. Expect about 2–5 seconds per scanned page.

## 6. Tests

```
.venv\Scripts\python -m pytest tests
```

The tests grade all 24 fictional clients and check:

- **Extraction accuracy:** every 1040 line, filing status, 65+ boxes, dependents, deceased spouse, schedule
  lines, and source-document boxes, for both years and including the scans. Everything currently matches.
- **Designed signals:** every signal in the answer key fires (recall 100%).
- **Fit levels:** each client lands in its intended band, except the six rule disagreements in
  `tests/fit_decisions.yaml` (see below).
- **Other checks:** the consent gate, SSN masking, validation warnings, and the upload page.

`outputs/test_report/signal_precision_recall.md` holds the precision/recall table and the fit-level
comparison.

### Open decisions: `tests/fit_decisions.yaml`

Six clients score a different AUM level than intended. The data is read correctly in every case; the
difference comes from the rules as written (C08, C16, C06, C20, C14, C03). Each entry explains why. Decide
each one by changing `config/grader.yaml` or the intended level, then remove the entry.

## 7. Before using on real returns

- The extractor was developed against the fictional returns in `inputs/test_clients`, which imitate IRS
  layouts. Real Canopy exports will differ in fonts and spacing. Grade a few real (consented) returns first and
  compare the reports to the actual returns. The validation warnings point to anything that didn't line up.
- The 2025 Form 1040 line numbers (11a/11b, 13a/13b) follow the redesigned 2025 form. The extractor accepts
  either 11 or 11a/11b. See `research/form_line_reference.md`.
- Only the most recent return and the year before it are compared. Older returns in the folder are ignored.
- Rental real estate (Schedule E) is extracted but does not drive any AUM rule today.

## 8. Public demo site (Netlify)

`netlify_site/` is the public Tax Scan site, built only from the fictional test clients. It contains:

- the landing page with the drop box (demo mode)
- the sample ranking and profiles in `demo/`
- `sample-clients.zip`: all 24 fictional clients' PDFs, so anyone can try it

On the public site, dropped files are never uploaded or read. Folders named like the sample clients link
to their pre-computed results; anything else gets pointed to running Tax Scan locally. Rebuild after
changing rules or design:

```
.venv\Scripts\python scripts\build_netlify_demo.py
```

Then commit and push. Netlify redeploys from GitHub automatically once the project is linked (Project
configuration → Build & deploy → Link repository → `cadecalvy-ai/tax-scan`, branch `main`; leave the build
command empty, since `netlify.toml` sets the publish folder).

## 9. Fictional test data

`inputs/test_clients` holds 24 fictional clients generated in Phase 1. See `inputs/test_clients/README.md`. To
regenerate them:

```
.venv\Scripts\python scripts\testgen\generate.py
```
