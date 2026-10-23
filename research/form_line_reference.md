# Form and line references used by the test data

The fictional returns use these line numbers. The Phase 2 extractor keys on them.

## Form 1040: 2025 vs. 2024

| Item | 2025 | 2024 |
|---|---|---|
| W-2 wages | 1a (1z total) | 1a (1z total) |
| Tax-exempt / taxable interest | 2a / 2b | 2a / 2b |
| Qualified / ordinary dividends | 3a / 3b | 3a / 3b |
| IRA distributions / taxable | 4a / 4b | 4a / 4b |
| Pensions and annuities / taxable | 5a / 5b | 5a / 5b |
| Social Security / taxable | 6a / 6b | 6a / 6b |
| Capital gain or loss | 7 | 7 |
| Schedule 1 income / adjustments | 8 / 10 | 8 / 10 |
| Total income | 9 | 9 |
| **AGI** | **11a** (page 1), repeated as **11b** (page 2) | **11** |
| Standard or itemized deduction | 12 | 12 |
| QBI deduction | 13a | 13 |
| Schedule 1-A deductions (incl. senior deduction) | 13b | n/a |
| Taxable income | 15 | 15 |
| Tax / Schedule 2 line 3 (AMT) | 16 / 17 | 16 / 17 |
| Child tax credit | 19 | 19 |
| Other taxes (SE, 5329, NIIT) | 23 | 23 |
| Total tax | 24 | 24 |
| Withholding: W-2 / 1099 / total | 25a / 25b / 25d | same |
| Estimated payments | 26 | 26 |
| Total payments | 33 | 33 |
| Refund / amount owed / penalty | 34, 35a / 37 / 38 | same |
| "Born before" checkbox | January 2, 1961 | January 2, 1960 |

**Check before Phase 2 goes live on real returns:** the 2025 split into 11a/11b and 13a/13b (and Schedule 1-A
line 38 feeding 13b) follows my understanding of the redesigned 2025 Form 1040. Confirm it against the final
IRS form and a real Canopy export. To be safe, the extractor should accept either `11` or `11a`/`11b` for AGI.

## Schedules (lines the grader cares about)

- **Schedule 1:** 3 business income, 5 Schedule E income, 7 unemployment, 10 total; 13 HSA, 15 half of SE tax,
  16 SEP/SIMPLE/qualified plans, 20 IRA deduction, 26 total adjustments.
- **Schedule 2:** 2 AMT, 3 total → 1040 line 17; 4 SE tax, 8 Form 5329 tax, 12 NIIT, 21 total → 1040 line 23.
- **Schedule A:** 5a–5e SALT (2025 cap $40,000, phased down 30% of MAGI over $500k, floor $10,000), 8a mortgage
  interest, 11/12/14 charity, 17 total.
- **Schedule B:** 1/2/4 interest, 5/6 dividends.
- **Schedule C:** 1 gross receipts, 28 total expenses, 31 net profit.
- **Schedule D:** 1a short-term 1099-B, 7 net short-term, 8a long-term 1099-B, 10 Form 8949 box F, 13 capital gain
  distributions, 15 net long-term, 16 → 1040 line 7.
- **Schedule E:** per-property 3 rents, 20 expenses, 21 net; 23a–26 totals; 28 S-corp row (column k), 32, 41 total.
- **Schedule SE:** 2 net profit, 4a, 6, 8a W-2 SS wages, 10, 11, 12 SE tax, 13 deduction.
- **Form 8949 Part II box F:** home sale (code H, exclusion as a negative column g) and the S-corp stock sale.
- **Form 8960:** 1, 2, 4a, 5a, 5b, 5d, 8, 12–17 (17 = NIIT).
- **Form 6251:** 1, 2a, 2i (ISO), 4 AMTI, 5 exemption, 9 tentative minimum tax, 10 regular tax, 11 AMT.
- **Form 5329 Part I:** 1, 3, 4 (10% additional tax).
- **Form 8606:** 1 nondeductible contribution, 8 converted, 11 nontaxable portion, 16–18 conversion (18 taxable).
- **Form 8889:** 2 own contributions, 9 employer contributions (W-2 code W), 13 deduction.
- **Form 8995:** 1 businesses, 2/4/5, 10–15 (15 → 1040 line 13a).

## Source documents

- **W-2:** a SSN, b EIN, c employer, e/f employee; 1 wages, 2 federal withholding, 3/4 Social Security, 5/6 Medicare,
  12a–d codes (D = 401(k) deferral, W = employer HSA), 13 checkboxes (statutory / retirement plan / sick pay),
  15–17 state.
- **1099-R:** 1 gross, 2a taxable, 2b checkboxes, 4 withholding, 7 code, IRA/SEP/SIMPLE checkbox. Codes used:
  1 early (C09), 2 early with exception / Roth conversion (C24), 4 death (C07 survivor pension, C10 inherited IRA),
  7 normal (C06, C07, C15), G direct rollover (C08).
- **SSA-1099:** 3 benefits paid, 4 repaid, 5 net, 6 voluntary withholding.
- **Others:** 1099-INT 1; 1099-DIV 1a/1b/2a; 1099-B summary (1d proceeds, 1e basis); 1099-G 1/4; 1099-S 1/2/3;
  1099-NEC 1; 1099-K 1a; K-1 (1120-S) box 1, 16D, 17V, Final K-1 checkbox; Form 3921 1–5; Form 1098 1, 2, 10.
