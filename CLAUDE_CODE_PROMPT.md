# Tax Return Grader — Claude Code Handoff

## Who this is for and what it does
I'm a financial advisor. My firm offers three services:
- **AUM** (investment management)
- **Annuities**
- **Life insurance** (smaller line)

Build a **local tool** that ingests client tax returns and supporting documents (PDFs exported from **Canopy**, our practice-management system; some are text PDFs, some are image-only scans). It extracts the key figures, grades each client's fit for our services, and produces a report showing who deserves a meeting and why.

Work in this folder (`Tax Scanner`), which lives on my Windows PC (OneDrive Desktop):

```
Tax Scanner/
  CLAUDE_CODE_PROMPT.md   <- this file
  starter/tax_engine.py   <- simplified 2024/2025 federal tax math (use for Phase 1)
  inputs/                 <- client document packages, one subfolder per client
  outputs/                <- grader reports
  research/               <- notes, threshold rationale, form/line references
  src/                    <- create: the grader code
  tests/                  <- create: tests that check grader output vs. the answer key
```

Do the work in two phases, in order. **Stop after Phase 1 and show me the results before starting Phase 2.**

---

## Phase 1 — Generate 24 FICTIONAL test clients

No real client data is used at this stage. Generate 24 fake clients with varied income, age, family situation, and investments. Put them in `inputs/test_clients/`.

### Rules for the fake data
- Every page carries a footer: `SAMPLE — FICTIONAL TEST DATA — NOT A REAL RETURN`.
- SSNs use the never-issued `000-00-####` format. EINs use `00-000####`. Phones use `555-01##`. Emails use `@example.com`.
- Employers, payers, and businesses must be fictional; no real company names. Addresses can use real Minnesota towns and ZIPs with invented streets.
- The tax year is **2025**. Eight clients also get a **2024** return so the grader can detect year-over-year changes.
- Use `starter/tax_engine.py` (`compute()` then `assign_payments()`) so the figures add up: AGI, taxable income, tax, withholding, and refund or balance due must reconcile across the 1040, the schedules, and the source documents. It's simplified, not real tax software, and that's fine.

### What goes in each client folder (e.g. `C06_Haugen_Gerald/`)
- `00_Client_Profile_Summary.pdf`: name(s), dates of birth, filing status, dependents with DOBs, occupation, fake contact info, and a list of documents on file.
- `2025_Form_1040_and_Schedules.pdf`: a 1040 laid out with real 2025 line numbers, plus only the schedules or forms the client needs. Available: Sch 1, 1-A, 2, A, B, C, D, E, SE, Forms 8949, 8960, 6251, 5329, 8606, 8889, 8995. The 1040 must show the "born before January 2, 1961" checkboxes and the dependents table.
- `2024_Form_1040_and_Schedules.pdf` for the 8 multi-year clients.
- One PDF per source document, with realistic box layouts:
  - W-2: show boxes 1–6, box 12 codes D and W, the box 13 retirement-plan checkbox, and boxes 16–17.
  - Also as needed: 1099-INT, 1099-DIV, 1099-B (summary), 1099-R (box 1, 2a, 4, 7 code, IRA/SEP checkbox), SSA-1099, 1099-G, 1099-S, 1099-NEC, Schedule K-1 (1120-S), Form 3921, and Form 1098.
- **Scans:** for clients C06, C09, C14, C18, and C23, render every PDF as an image-only scan. Use `pdftoppm` at about 150 dpi, grayscale, a slight rotation (±1.5°), light noise or blur, then save back to PDF with no text layer. For C11, only the source documents are scans. This tests the OCR path.

### The 24 clients (ages as of 12/31/2025)
| ID | Client | Profile | Designed signals |
|---|---|---|---|
| C01 | Tyler Brandvold, 26, Single | W-2 $42.5k, small 401k, refund | Control: low fit everywhere |
| C02 | Marcus & Jenna Okafor, 33/32, MFJ, kids 4 and 1 | Two W-2s, $58k + $41k | Dependents, young family |
| C03 | Daniel & Rachel Lindqvist, 41/39, MFJ, kids 12, 9, 6 | Daniel W-2 $186k with maxed 401k; Rachel no income; small dividends | Single earner, 3 dependents, high income |
| C04 | Priya Raman, 34, Single | W-2 $238k; ISO exercise with $145k spread (3921) causing AMT; 1099-B ST $18.4k, LT $31.2k; dividends $4.8k | Stock comp, AMT, cap gains, high AGI |
| C05 | Dr. Aaron & Megan Feld, 46/44, MFJ, kids 14 and 11 | Sch C dental practice nets $310k with **no SEP or Solo 401k**; Megan W-2 $28k; interest $2.9k; estimated payments | Business owner with no retirement plan, high income, dependents. **Has 2024 return.** |
| C06 | Gerald & Linda Haugen, 68/66, MFJ | Pension $48k; SS $31.2k + $20.4k; IRA distribution $30k; interest $6.2k; dividends $3.1k | Retirees, pension and IRA income, CDs. **Scan.** |
| C07 | Margaret Sundberg, 71, Single in 2025 | Widowed in 2024 (2024 return is MFJ with Harold); survivor SS $38.4k; survivor pension $22k; IRA $18k; interest $9.4k; dividends $5.2k; LT gain $12k | **Widowhood (MFJ to Single)**, cash, IRA. **Has 2024 return.** |
| C08 | Kevin Marsh, 61, Single | W-2 $132k (left job in September); **1099-R code G direct rollover $418k** | Rollover, near retirement |
| C09 | Brian & Tasha Kowalczyk, 52/50, MFJ, kid 16 | Brian laid off: W-2 $64k plus unemployment $9.8k (1099-G); **1099-R code 1, $35k early 401k withdrawal**, Form 5329 penalty; Tasha W-2 $47k | Early withdrawal, job loss, 401k left at old employer. **Scan.** |
| C10 | Sarah & Jon Ellison, 45/47, MFJ, kids 13 and 10 | W-2s $121k + $89k; **1099-R code 4 inherited IRA $62k**; dividends jump from $900 (2024) to $16.4k | Inheritance, dividend jump year over year. **Has 2024 return.** |
| C11 | Robert & Diane Tollefson, 58/57, MFJ | **Home sale** (1099-S): price $1.185M, basis $565k, gain $620k, $500k exclusion, $120k taxable on Form 8949; W-2s $142k + $38k; NIIT | Home-sale liquidity, NIIT. **Source documents scanned.** |
| C12 | Thomas & Carol Reinholt, 63/61, MFJ | **Sold their S-corp**: proceeds $2.3M, basis $460k; final K-1 ordinary income $145k; interest $22k; large estimated payments | Business-sale liquidity event, near retirement |
| C13 | Nathan & Elise Brightwater, 44/42, MFJ, kids 15, 12, 8 | W-2s $268k + $142k, both maxing 401k, HSA; dividends $28.4k; interest $5.6k; LT $14.8k; NIIT | High income, NIIT, dependents. **Has 2024 return.** |
| C14 | Dale & Renee Jorgensen, 55/54, MFJ | Sch E with 4 rentals (rents $98.4k, net about $61k); Dale W-2 $71k | Real estate concentration, single W-2 earner. **Scan.** |
| C15 | Eleanor Hartwig, 75, Single | **RMD**: 1099-R gross $52k with $6k QCD, so $46k taxable; SS $34.2k; interest $4.3k; dividends $8.9k | RMD age, charitable giving (QCD) |
| C16 | Paul & Kathleen Strand, 60/59, MFJ | Retired early in 2024; 2025 has no wages, LT $22k, dividends $11.8k, interest $3.2k; low taxable income. 2024 had W-2 $165k. | Gap years (Roth conversion window), income drop year over year. **Has 2024 return.** |
| C17 | Alicia Dahl, 38, HOH, kids 10 and 7 | W-2 $78.5k (nurse) | Single parent, dependents |
| C18 | Jordan Pike, 29, Single | Gig work: Sch C via 1099-NEC/1099-K gross $48.5k, net $35.7k; no estimated payments; balance due plus underpayment penalty | Control: low fit, cash-flow issue. **Scan.** |
| C19 | Ryan & Heather Castellano, 48/46, MFJ, kids 15 and 11 | S-corp owner: K-1 ordinary $224k plus W-2 from his S-corp $95k; Heather no income; estimated payments | Business owner (key person, buy-sell), single earner |
| C20 | Walter Engstrom, 66, Single | **Social Security started in 2025** ($26.4k, first SSA-1099); part-year W-2 $18k; interest $14.2k (about $350k in CDs). 2024: W-2 $61k, no SS. | SS start, heavy cash. **Has 2024 return.** |
| C21 | Michelle Grady, 47, HOH, kid 13 | **Divorced in 2025** (2024 return MFJ with Craig); W-2 $116k | Divorce (filing status change), now single income. **Has 2024 return.** |
| C22 | Ethan & Sophie Lindgren, 31/30, MFJ, **baby born 2025** | Married in 2025; W-2s $92k + $71k. 2024 return is Ethan's Single return. | Marriage, new baby. **Has 2024 return.** |
| C23 | Dorothy Fenske, 78, Single | SS $21.6k only; interest $240 | Control: low fit. **Scan.** |
| C24 | Dr. Samuel & Grace Adeyemi, 52/50, MFJ, kids 16 and 13 | Samuel W-2 $524k with 401k at catch-up limit; Grace no income; backdoor Roth (8606) for both; dividends $31.5k; interest $6.8k; LT $41k; itemizes (charity $40k, mortgage $18.4k, SALT phased down); NIIT | Very high income, NIIT, charitable giving, single earner with dependents |

Vary refund versus balance due through `pay_ratio`. Most clients get a small refund. C04, C05, C11, and C18 owe.

### Answer key
Write `inputs/test_clients/answer_key.csv` and `answer_key.json` with one row per client:
- id, names, ages, filing status, AGI (from the engine), and the list of designed signals.
- Intended fit levels: AUM high/med/low, and expected annuity and life grade bands.

Phase 2 tests check against this file. Also write `inputs/test_clients/README.md` explaining the data set.

**After Phase 1, verify before reporting:** open several PDFs, including scans, as images and check the layout. Confirm the 1040 math reconciles, and confirm the scans have no text layer. Then stop and show me.

---

## Phase 2 — Build the grader

### Usage
- **CLI:** `python -m src.grader inputs/<folder> --out outputs/<run>` grades every client subfolder.
- **Local upload page (optional, after the CLI works):** a small Flask app on `localhost`. I drag in a client's PDFs and get the report. It must bind to localhost only.

### Pipeline
1. **Ingest:** read each PDF with `pdfplumber`. If a page has little or no text, fall back to OCR (`pytesseract` plus `pdftoppm`/`pdf2image`; document the Windows Tesseract install in the README).
2. **Classify** each document: 1040 (and its year), each schedule or form, W-2, 1099-INT, -DIV, -B, -R, -G, -S, -NEC, K-1, SSA-1099, 3921, 1098, or the client profile summary.
3. **Extract** into one structured record per client per year, keyed by form and line. The record includes:
   - Filing status, 65+ checkboxes, dependents with ages, and DOBs from the profile summary.
   - Every 1040 line from 1a through 37.
   - W-2 box 12 codes D and W, and box 13.
   - 1099-R box 7 codes and amounts.
   - SSA-1099 box 5.
   - Schedule C net, K-1 box 1, Schedule E rental nets.
   - Form 8960, 6251, 5329, and 8606 presence and amounts.
   - Itemized charity.
4. **Validate:** AGI should equal total income minus adjustments; source-document totals should match the 1040 lines (W-2 box 1 sum vs. line 1a, and so on). Record mismatches as warnings on the report, never silently.
5. **Signals:** evaluate the rules below. Each signal records its source document, the line or box, and the value.
6. **Score:** AUM gets **0–100**. Annuity and Life each get an **A–F** grade.
7. **Report:** one page per client (HTML, plus PDF if easy) showing the three results, the signals that fired with their source lines, validation warnings, and suggested talking points. Also produce a batch `summary.csv` and `summary.html` ranking all clients by AUM score with their annuity and life grades.

### Configuration
Put every threshold and weight in `config/grader.yaml`. I will tune them, so nothing may be hard-coded.

### Starting signal rules and weights (defaults to put in the YAML)

**AUM score (sum of points, capped at 100):**
| Signal | Source | Points |
|---|---|---|
| AGI ≥ $150k / ≥ $250k / ≥ $500k | 1040 line 11 | 15 / 20 / 25 |
| Dividends + capital gains ≥ $5k / ≥ $25k | lines 3b + 7 | 15 / 20 |
| Interest ≥ $2k (about $50k+ in cash) / ≥ $10k | line 2b | 10 / 15 |
| IRA or 401k distributions present | lines 4a/5a, 1099-R | 15 |
| Rollover ≥ $100k | 1099-R code G | 25 (replaces the line above) |
| Inheritance: 1099-R code 4, or dividends ≥ 3× the prior year | 1099-R, YoY | 15 |
| Home or business sale gain ≥ $100k | 1099-S, 8949, Sch D | 20 |
| Net Investment Income Tax paid | Form 8960 | 10 |
| Stock compensation or AMT | Form 3921/3922, 6251 | 10 |
| Income ≥ $100k with no retirement savings visible | no W-2 code D, no SEP/IRA deduction | 10 |
| Income drop ≥ 40% YoY, or early retirement | YoY | 10 |
| Early withdrawal (code 1 / Form 5329) | 1099-R | 10 |

**Annuity points**, graded A ≥ 70, B ≥ 50, C ≥ 35, D ≥ 20, otherwise F:
| Signal | Points |
|---|---|
| Age 55+ / 65+ (from DOB, 65+ checkbox, or SSA-1099) | 25 / 30 |
| Pension or IRA income | 20 |
| Interest ≥ $2k / ≥ $10k | 15 / 25 |
| Taxable income in the 24% bracket or higher | 10 |
| Transition: SS started, rollover, widowhood, income drop | 15 |
| RMD age (73+) with IRA distributions | 10 |

**Life points**, using the same grade cutoffs:
| Signal | Points |
|---|---|
| Dependents claimed | 25, +5 per dependent up to 3 |
| Single-earner MFJ (one spouse has ≥ 80% of earned income) | 20 |
| Business owner (Sch C or K-1 ≥ $50k) | 20 |
| Income ≥ $150k / ≥ $300k | 15 / 20 |
| Life event YoY: marriage, new baby, divorce, widowhood | 15 |
| Age over 75 | −20 |

Life events need two years: compare filing status, dependents, and DOBs across the 2024 and 2025 returns.

### Tests
Write `tests/` covering three things:
- Extraction accuracy on every test client, including the scans.
- That every designed signal in the answer key fires.
- That fit levels land in the intended bands.

Report a precision/recall table of signals versus the answer key. Iterate until the extraction is right. **Do not tune the rules to fit the answer key.** If a designed fit level seems wrong given the rules, list it for me to decide.

---

## Non-negotiables
- **Privacy:** real client returns will go through this later, so everything runs locally. No client data is sent to any external API or service by default, and nothing is logged with full SSNs (mask to the last 4 in reports). If you want an LLM-assisted extraction option, make it opt-in and off by default, and tell me before adding it.
- **Transparency:** every score must be explainable from the report: which signal fired, from which line, and with what value.
- **Compliance reminder for the README:** if we prepared these returns, using return information to market non-tax services generally requires the client's prior written consent under IRC §7216. The tool should support a per-client `consent_7216: true/false` flag and refuse to grade a real client without it. The fictional test clients are exempt.
- The target environment is **Windows**, with Python 3.11 or newer. Provide a `requirements.txt` and a README with setup steps, including Tesseract and Poppler on Windows.
- Keep the code simple and readable. I will be maintaining it.
