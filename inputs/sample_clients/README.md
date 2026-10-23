# Test clients (FICTIONAL)

24 synthetic clients for building and testing the grader. **None of this is real data.** Every page carries the
footer `SAMPLE — FICTIONAL TEST DATA — NOT A REAL RETURN`.

- SSNs are `000-00-####` (never issued). Pattern: `000-00-NNPP`, where NN = client number, PP = 01 taxpayer,
  02 spouse, 03 prior-year spouse (C07 Harold, C21 Craig), 11+ dependents.
- EINs are `00-000####`, phones are `555-01##`, emails are `@example.com`.
- Employers, banks, brokerages, and businesses are invented. Towns and ZIPs are real Minnesota places; streets are made up.
- Two issuers are generic by necessity: the SSA-1099 shows "Social Security Administration," and the 1099-G payer
  is a made-up "North Star State Unemployment Insurance Office (fictional)."

## How it was made

```
cd app
..\.venv\Scripts\python scripts\testgen\generate.py
```

The script is deterministic: the same inputs produce the same files, and the scan noise uses a fixed seed.
It deletes and rewrites the PDFs in `C??_*` folders each time.

| File | What it is |
|---|---|
| `app/scripts/testgen/specs.py` | The 24 client definitions (income, people, payers, designed signals, intended fit) |
| `app/scripts/testgen/returns.py` | Turns engine output into rounded form lines; draws the 1040 and schedules |
| `app/scripts/testgen/sources.py` | Draws the W-2s, 1099s, SSA-1099, K-1, 3921, 1098, and the profile page |
| `app/scripts/testgen/generate.py` | Runs everything, checks reconciliation, makes the scans, writes the answer key |

Figures come from `starter/tax_engine.py` (`compute()` then `assign_payments()`). Each schedule line is rounded
once and every total is the sum of the printed lines, so each return foots. `reconciliation_report.txt` lists
the checks for every client-year (e.g. W-2 box 1 total = 1040 line 1a, Schedule D line 16 = line 7, line 11 =
line 9 − line 10, and printed totals within $3 of the engine). All 618 checks pass.

## Folder contents

Each `Cnn_Last_First/` folder holds:

- `00_Client_Profile_Summary.pdf`: names, DOBs, filing status, dependents with DOBs, occupations, contact info,
  and documents on file. It is marked as a fictional test client, so the §7216 consent rule does not apply.
- `2025_Form_1040_and_Schedules.pdf`: the 1040 plus only the schedules and forms the client needs.
- `2024_Form_1040_and_Schedules.pdf`: only for C05, C07, C10, C13, C16, C20, C21, and C22.
- One PDF per 2025 source document, named `2025_<form>_<payer>_<recipient first name>.pdf`. There are no
  2024 source documents, only the 2024 return.

**Scans** (image-only, no text layer): every PDF for C06, C09, C14, C18, and C23. For C11, only the source
documents are scanned; its profile and 1040 are text PDFs. Scans were made at 150 dpi in grayscale with
a ±0.4–1.5° rotation, gray paper tone, Gaussian noise, and a slight blur. A quick Tesseract test reads most
values, with some misreads (e.g. `131,160` read as `134,160`). The grader's validation step should catch these.

141 PDFs in total: 109 text and 32 scans.

## Answer key

`answer_key.csv` has one row per client: id, names, ages, filing status, AGI (2025 and 2024 where present),
scan type, refund or balance due, designed signals, intended fit levels, and a short narrative.

`answer_key.json` has the same fields plus a `truth` block per year with:
- every printed 1040 line (`form_1040`), each attached schedule's lines (`schedules`), and `forms_attached`
- filing status, the "born before" checkboxes, spouse (including the deceased date for C07 2024), and
  dependents with ages
- key source-document boxes: W-2 box 1, box 2, box 12 codes D/W, box 13; 1099-R boxes 1, 2a, 4, 7, IRA/SEP;
  SSA-1099 box 5; K-1 box 1; 1099-S box 2; 1099-G; Form 3921 spread
- the raw engine figures, for reference

Phase 2 extraction tests should compare against `truth`.

### Signal IDs

`designed_signals` lists the rules each client was **designed** to trigger. IDs are `product.rule`:

- AUM: `aum.agi_150k`, `aum.agi_250k`, `aum.agi_500k`, `aum.invest_income_5k`, `aum.invest_income_25k`,
  `aum.interest_2k`, `aum.interest_10k`, `aum.retirement_distribution`, `aum.rollover_100k`, `aum.inheritance`,
  `aum.asset_sale_gain_100k`, `aum.niit`, `aum.stock_comp_amt`, `aum.no_retirement_savings`, `aum.income_drop`,
  `aum.early_withdrawal`
- Annuity: `annuity.age_55`, `annuity.age_65`, `annuity.pension_ira_income`, `annuity.interest_2k`,
  `annuity.interest_10k`, `annuity.bracket_24`, `annuity.transition`, `annuity.rmd_age`
- Life: `life.dependents`, `life.single_earner`, `life.business_owner`, `life.income_150k`, `life.income_300k`,
  `life.life_event_marriage`, `life.life_event_new_baby`, `life.life_event_divorce`, `life.life_event_widowhood`,
  `life.age_over_75`

The list is the designed story, not every rule a client will trip. Some incidental hits are expected and
correct under the rules:
- C07's survivor pension is 1099-R code 4 (death), so `aum.inheritance` fires.
- C10 and C12 pay NIIT (`aum.niit`).
- C24's backdoor Roth conversions put $14,000 on line 4a, so `aum.retirement_distribution` fires.
- Most high earners hit `annuity.bracket_24`.

### Intended fit levels

These are advisor-judgment targets, set before any grading rules were run.
- **AUM:** high (score ≥ 60), med (30–59), low (< 30).
- **Annuity and Life:** a band of acceptable grades, e.g. `A-B` or `D-F`. Grades are A ≥ 70, B ≥ 50,
  C ≥ 35, D ≥ 20, otherwise F.

Per the brief, Phase 2 must not tune the rules to match these targets. Where the default rules disagree with
a target, the mismatch gets listed for a decision.

## Simplifications to know about

- `tax_engine.py` is simplified. QBI ignores the W-2 wage and SSTB limits, and Form 8995 is used even where
  8995-A would apply (C12). EIC, Form 8812, Form 2210, and state returns are not computed. Line 38's
  estimated tax penalty is a flat 4.5% of the balance due.
- Line numbers follow the 2025 Form 1040 (11a/11b, 13a/13b) and the 2024 Form 1040 (11, 13). See
  `app/docs/research/form_line_reference.md`.
- The 1099-B is a one-page summary from a composite statement, with no transaction detail.
- Box 3 of the 1099-R is blank. W-2 state tax is a flat 5.45% of wages.
