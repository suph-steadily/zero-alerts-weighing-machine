# The Weighing Machine: Requirements (first pass)

Part of Zero Alerts (`alert-north-star/README.md`, section 3). Canonical framing: What Must Be True v4 (`appendix/what-must-be-true.html`).

## Purpose

- One instrument that prices whether an underwriting alert is worth keeping.
- It answers, for any alert: how many more binds, how many more NOCs and NOEs, GWP gained or lost, loss-ratio impact.
- Today every alert debate stalls the same way: the two sides of the ledger share no unit. UW answers for every NOC, growth answers for every bind, both are right from their seat. The machine turns that argument into a number.
- Per David: the bind lift is already proven. The machine is really a cost-pricing machine.
- Partner: David Curry (or the new data scientist). Reference seed: `tradeoff.py` in scratch-darren.

## The two directions

- **Remove**: an existing alert proposed for retirement (dwelling age 101+ is the worked example).
- **Add**: a proposed new alert, priced BEFORE it ships. Same math, mirrored signs: adding a gate loses the binds, saves the NOCs, creates the reviews, captures the premium.
- Rule: no alert ships unweighed, none retires unweighed.

## Inputs inventory

Two halves: 6 COUNTS (forecast what removal changes) and 6 WEIGHTS (convert counts to dollars). Every input is a Quantity: point, low/high range, status, source, and the Metabase recipe it comes from (`consult-the-book/references/data-recipes.md`, db 235 unless noted).

### The 6 counts

| Count | What it is | Status | Where it comes from |
|---|---|---|---|
| Alert funnel volumes | quotes/mo hitting the alert, share referred, share that dies unlooked | measured | eventstore `underwriting_review_note` joined to `dbt.ipod_smga_uw_alerts_per_quote_version` at the submitted version, family-tagged ("UW touches per alert family" recipe) |
| No-alert twin cohort | a comparable population without the alert, for bind and cancel rates | measured (91-100 twin) | funnel-twin recipe (2026-08-13): DAMR-only vs just-under 0-alert vs under-91 |
| Risk gradient | how outcomes climb past the twin, keeps the projection honest | measured | age re-band of `dbt_dev.damr_uarnoe_{cohort,final}_20260816`; NOC ramps +22.8%/decade ("No-alert age gradient" recipe) |
| Post-bind outcomes | NOCs and UW corrective NOEs per 100 bound, 90 days | measured | `dbt_dev.damr_uarnoe_*_20260816` snapshots, MB cards 142904-142907; NOC sub-reasons via `tap_veruna.wt_insurance_policy__c.steadily_uw_cancellation_reason__c` |
| UW action log | what reviewers actually change on approvals, how often | measured | DAMR six-field chain, MB cards 17-24 (collection 6787), `dbt_dev.damr_field_diffs_20260723`, `damr_prem_flags_20260807` |
| Automation coverage | which review jobs already have a system, so "after the fixes" can be weighed | roof only | auto-RSE: `roof_condition_score_decision` + flag column (BUC-5011 states); pre-bind RSE re-cut in `damr_prebind_rse_20260816` |

### The 6 weights

| Weight | Definition | Status | Where it comes from |
|---|---|---|---|
| A bind | dollars over a lifetime: year-one premium, retention, segment loss cost, compounded GWP | UNPRICED beyond year one | year-one premium is a finance pull; LTV is the finance/actuarial ask |
| A NOC | agent side: cure split. 74% cure; cured costs ~0 to -2% of that agent's next-year binds per event; uncured cancellation ~ -20%, front-loaded | agent side partially priced; customer side UNPRICED | scratch-darren `2026-08-noc-impact-inde-agent/` (REPORT.md + tradeoff.py); Darren's early data via LaNae 8/18 |
| A corrective NOE | ~$0 premium relief to the customer (measured); removed-coverage experience side not | half priced | ANALYSIS-2026-08-16.md; DEEPDIVE catch-count 6.8% vs 3.3% |
| A freed review | UW labor per forced review | partial | UW expense model anchors: $1.50/quote, $6.82/bound; our pool-to-review division gives $4.5-7.5/review, flagged as an assumption |
| Premium from UW corrections | bound-only premium their fixes add | measured ($26K/mo for dwelling age) | `damr_prem_flags_20260807` (values in CENTS); $3,034 per 100 bound, ~0% recovered at renewal |
| The loss join | actual losses tied back to the alert's population | MISSING entirely | plan: actuarial backtest of the twin's on-book losses (What Must Be True v4, section 5) |

## Outputs: the ledger

- Per month, at a stated scale, signed as the change the action causes:
  - Bound policies (with range)
  - Forced UW reviews
  - NOCs, split into "book shifts to twin rate" plus "new binds at twin rate"
  - UW corrective NOEs, same split
  - GWP: premium from UW corrections (measured) plus GWP from new binds (sensitivity until the bind weight lands)
  - Loss-ratio impact: a placeholder that stays "unknown" until the loss join exists. It never silently drops off the page.
- Every line carries an uncertainty range and a status chip: MEASURED, PARTIAL, or UNPRICED.
- Plus one shared threshold: the exchange rate, binds bought per NOC added. That is the number the tolerance bar gets compared against.

## Denomination and the presentation rule

- "Denominated in" means the unit the machine keeps score in. The machine is denominated in COUNTS (binds, NOCs, NOEs, reviews), because loss ratio lags about a year and counts are the leading proxies.
- The counts-plus-dollars rule: every output shows the counts first, then dollars only where a weight exists. A dollar figure never replaces its count. The priced subtotal is labeled "not the verdict" as long as any weight is unpriced.
- Unpriced means UNPRICED, not zero. Unpriced weights get a visible chip and an explicit sensitivity grid. A guess never hides inside a priced line (the code enforces this: arithmetic on an unpriced input yields an unpriced output).

## UI options

- **v0 (built)**: a self-contained static HTML report generated by the tool, plus a plain-text ledger on stdout. No dependencies, opens anywhere, screenshots into any doc.
- **Later (recommend, do not build yet)**: maybe a small Streamlit app with sliders for the sensitivity grids, once the machine has been run manually on 2-3 alerts. Per the project doc: decide doc vs script vs tool after running it by hand, not before.

## Validation plan

- **Reproduce dwelling-age v0** (automated, `tests/test_dwelling_age_v0.py`): the machine fed the dwelling-age config must reproduce +115 binds/mo (+50..+175), +25 NOCs/mo (+10..+40), +30 UW corrective NOEs/mo, -2,200 forced reviews/mo, -$26K/mo correction premium, loss unknown. Pinned lines exact; derived points within 5-10%; derived ranges must CONTAIN the published brackets (worst-case propagation widens, never narrows).
- **Backtest a known case**: the water-claims automation launch (Jul 15). Feed the machine the water inputs (MB 131090 baseline, MB 121562 funnel) and check it predicts what actually happened: referral rate down (36.5% to 11.9%), bind rate flat within noise, time-to-bind down. A machine that cannot recover a case we already lived through does not get to forecast new ones.
- **Sensitivity analysis on the unpriced weights**: for each UNPRICED weight, show the ledger across the grid and find the flip point, the value at which the recommendation changes. If the flip point is far outside any plausible value, the missing price does not block the decision.
- **Name your NOC denominator**: every NOC rate states per 100 of WHAT, over WHAT window. The config loader rejects a rate without a denominator. Two rates are in circulation (the twin's 6.5 inspection-lane per 100 bound 90d, and Darren's 11.7% book-wide all-UW-NOC); quoting one against the other is how a room gets lost.

## Build phases

- **Phase 0, done (this pass, ~2 days)**: Quantity type with range propagation, config schema, the forecast model, NOC cure-split weight, text + HTML reports, dwelling-age validation suite.
- **Phase 1 (~1-2 weeks, with David Curry)**: run it manually on 2-3 more alerts (water backtest first, then a census leader like roof or Coverage A); harden the config schema against what those runs break; wire the automation-coverage input so "alert off after the levers land" is a weighable scenario, not just "alert off".
- **Phase 2 (weeks, finance + actuarial partnership, not a data pull)**: price the four unpriced weights; replace the sensitivity grids with real numbers one at a time.
- **Phase 3 (only if 2-3 manual runs demand it)**: promote to a tool (Streamlit or similar). Recommendation stands: do not build this yet.

## Open questions

- **The four unpriced weights**: bind LTV, the freed-review hour, the customer side of a NOC, and the loss join. Each is an owner conversation (finance, UW ops, finance, actuarial), not a query.
- **The gate**: LaNae's tolerance number is the decision rule input. The machine outputs binds-per-NOC; nobody has asked her what exchange rate she accepts. Until asked, the report prints "tolerance bar: NOT SET".
- **Selection-effect floor**: the twin never faced the alert, so twin rates are a floor for true un-reviewed 101+ (book averages 117 years; projection 7-11 NOCs per 100). The machine carries this as a labeled scenario. Open: how to price the gap between floor and projection, and whether the A/B test (section 8 of the project doc) should size it directly.
- **NOE double-count risk**: the v0 hand ledger's +30 counted only the existing book's rate shift; the machine also adds new-bind NOEs (~+9/mo, total ~+40). Confirm with David which convention the Thursday proposal quotes, and label it either way.
