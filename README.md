# Tax Scan: client tax-return grader

Reads a client's tax return and supporting documents (PDFs exported from Canopy, text or scanned) and grades
the client's fit for three services:

- **AUM:** a score from 0 to 100, banded high, med or low
- **Annuity:** a grade from A to F
- **Life insurance:** a grade from A to F

Each client gets a profile page showing every signal that fired, with the document and line or box it came
from, plus validation results and talking points. A ranked `summary.html` / `summary.csv` covers the batch.

**Everything runs on this computer.** No client data is sent to any outside service, and there is no LLM in the
loop. SSNs are masked to the last 4 digits in every report and output file.

## What's in this folder

```
Tax Scanner/
  Start Grader.bat          double-click: opens the drag-and-drop page in your browser
  Grade My Clients.bat      double-click: grades every client folder in inputs\clients
  inputs/
    clients/                put REAL client folders here (one per client, private)
    sample_clients/         24 FICTIONAL clients to try it with
  outputs/                  every graded run is saved here
  netlify_site/             the public demo website (tax-scan.netlify.app)
    site/                     the website files
    tax-scan-site.zip         the file to upload to Netlify
    Build Website.bat         rebuilds the site and the zip
  app/                      the program: code, config/grader.yaml, tests, docs
```

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
4. **Python packages** (into a virtual environment in this folder)
   ```
   py -3.12 -m venv .venv
   .venv\Scripts\python -m pip install -r app\requirements.txt
   ```

The grader looks for Poppler and Tesseract on `PATH`, then in the default winget and Program Files locations.
If you installed them somewhere else, set `POPPLER_PATH` to the folder that contains `pdftoppm.exe` and
`TESSERACT_CMD` to the full path of `tesseract.exe`.

## 2. Grading clients

### Drag and drop: `Start Grader.bat`

Your browser opens to the Tax Scan page.

1. Drag a folder of client folders onto the drop box, or a single client's folder or PDFs. To try it, drag
   `inputs\sample_clients`.
2. Click **Scan & grade**.
3. The ranking opens. Click a name, or any score pill, to open that client's profile.

Past runs are listed on the page and saved under `outputs\web\`. Keep the black window open while you use it.
The page only accepts connections from this computer. Uploaded PDFs go to a temporary folder that is deleted
as soon as grading finishes.

### Folder based: `Grade My Clients.bat`

1. Put each client's PDFs in their own folder under `inputs\clients\`, for example `inputs\clients\Smith_John\`.
2. Add `client.yaml` with `consent_7216: true` to each folder (see section 3).
3. Double-click `Grade My Clients.bat`. The ranking opens, and the run is saved as `outputs\clients_<date_time>\`.

### Command line (optional)

From the `app` folder:

```
..\.venv\Scripts\python -m src.grader ..\inputs\clients --out ..\outputs\my_run --workers 4
```

- `export.html` puts the ranking and every client's brief on one printable page (Print / save as PDF), and `results.xlsx` has the same results as an Excel workbook (Ranking, Talking points, Key figures, Evidence, Warnings). Both are linked from the bottom of `summary.html`.
- `summary.csv` is the ranking as plain CSV. `results.json` has everything in machine-readable form, with SSNs masked.
- `--cache <folder>` keeps OCR results between runs. The cache contains text read from client documents, so
  point it only at a private local folder.

## 3. IRC §7216: client consent (read this)

If your firm prepared these returns, using return information to market non-tax services (investment
management, annuities, insurance) generally requires the client's **prior written consent** under IRC §7216
and Treas. Reg. §301.7216-3. Talk to your compliance team about the consent form and its wording.

The grader enforces this:

- A client folder is graded only if it contains `client.yaml` with `consent_7216: true`. Add it only after the
  signed consent is on file.
- With no `client.yaml`, or with `consent_7216: false`, the client is **not graded** and the summary says why.
  The return and source documents are not read. With no `client.yaml`, only a file named like `*profile*.pdf`
  is opened, to check for the fictional-sample-client marker.
- The fictional sample clients are exempt. A `client.yaml` with `consent_7216: false` still blocks them.
- On the drag-and-drop page, a switch records that consent is on file for every client in that upload.

## 4. Tuning the rules

Every threshold, weight, band, and talking-point template is in **`app\config\grader.yaml`**, and nothing is
hard-coded. Edit it and re-run. The profile always shows which rule fired and why. For example, to make large
rollovers count more:

```yaml
aum:
  rollover:
    min: 100000
    points: 40
```

Signal IDs (like `aum.rollover_100k`) include the threshold, so the reports stay readable after a change.

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
| Farm income (shown, not scored) | Schedule F lines 3a, 4a, 6a and 34, cross-checked against 1099-PATR, the USDA 1099-G (box 7) and 1099-MISC crop insurance (box 9) |
| Business books (shown, not scored) | A profit and loss statement's total income vs. Schedule C line 1; its net income and any equipment purchase (bill of sale) appear in the brief |
| Life events | Filing status, spouse deceased marker, and dependents vs. the prior-year return; new baby from dependent DOBs |

## 5. How it works

```
app/src/paths.py     where every folder lives (change locations here only)
app/src/ingest.py    read PDFs: pdfplumber for text, Poppler + Tesseract for scans
                     (straighten, erase form rules, two OCR passes merged)
app/src/classify.py  identify each page: 1040 page 1/2, schedules, W-2, 1099s (INT, DIV, B, R, G, S, NEC, K, PATR,
                     MISC), SSA-1099, K-1, 3921, 1098, profile; P&L statements and bills of sale as context
app/src/extract.py   pull values: form lines matched by their printed wording; information-return boxes by label
app/src/record.py    assemble one record per client per tax year
app/src/validate.py  cross-check (AGI = line 9 - line 10, W-2 total = line 1a, ...); use the best-supported value
app/src/signals.py   evaluate the rules in grader.yaml; score and grade
app/src/report.py    ranking and client profiles (HTML), summary.csv
app/src/export.py    printable export page and results.xlsx
app/src/grader.py    command line, consent gate
app/src/webapp.py    the local drag-and-drop page;  app/src/web/landing.html is its design
```

**Validation.** A return states most figures more than once: the 1040 line, the schedule behind it, the source
documents, and the arithmetic. For each key figure the grader compares every reading and uses the value most
of them agree on. **Every disagreement appears as a warning on the profile**, and nothing is changed
silently. This matters most for scans, where OCR occasionally misreads a digit.

**Scans.** Pages with no text layer are OCR'd at 400 dpi. Amounts on scans are re-read from close-up crops, and
the majority of the readings is used. Expect about 2–5 seconds per scanned page.

## 6. Tests

From the `app` folder:

```
..\.venv\Scripts\python -m pytest tests
```

The tests grade all 24 sample clients and check:

- **Extraction accuracy:** every 1040 line, filing status, 65+ boxes, dependents, deceased spouse, schedule
  lines, and source-document boxes, for both years and including the scans.
- **Designed signals:** every signal in the answer key fires (recall 100%).
- **Fit levels:** each client lands in its intended band, except the six rule disagreements in
  `app\tests\fit_decisions.yaml`.
- **Other checks:** the consent gate, SSN masking, validation warnings, and the drag-and-drop page.

`outputs\test_report\signal_precision_recall.md` holds the precision/recall table and the fit-level comparison.

**Open decisions.** Six clients score a different AUM level than intended (C08, C16, C06, C20, C14, C03). The
data is read correctly; the difference comes from the rules as written. `app\tests\fit_decisions.yaml`
explains each one. Decide each by changing `grader.yaml` or the intended level, then remove the entry.

## 7. Before using on real returns

- The extractor was developed against the fictional returns in `inputs\sample_clients`, which imitate IRS
  layouts. Real Canopy exports will differ in fonts and spacing. Grade a few real (consented) returns first and
  compare the profiles to the actual returns. The validation warnings point to anything that didn't line up.
- The 2025 Form 1040 line numbers (11a/11b, 13a/13b) follow the redesigned 2025 form. The extractor accepts
  either 11 or 11a/11b. See `app\docs\research\form_line_reference.md`.
- Only the most recent return and the year before it are compared. Older returns are ignored.
- Rental real estate (Schedule E) is extracted but does not drive any AUM rule today.

## 8. Public demo site (Netlify)

`netlify_site\site\` is the public Tax Scan site (tax-scan.netlify.app), built only from the fictional sample
clients. On the public site, dropped files are never uploaded or read. Folders named like the sample clients
link to their pre-computed results; anything else gets pointed to running Tax Scan locally.

To update it after changing the rules or design:

1. Double-click `netlify_site\Build Website.bat`. File Explorer opens with `tax-scan-site.zip` selected.
2. In Netlify, open the tax-scan project, go to **Deploys**, and drag the zip onto the page.

## 9. Sample clients

`inputs\sample_clients` holds the 24 fictional clients and their answer key. See its `README.md`. To regenerate
them, from the `app` folder:

```
..\.venv\Scripts\python scripts\testgen\generate.py
```
