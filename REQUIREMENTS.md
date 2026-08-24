# The Weighing Machine: Requirements (first pass)

Part of Zero Alerts (`alert-north-star/README.md`, section 3). The framing of record: What Must Be True v4 (`appendix/what-must-be-true.html`).

**This machine is for ANY alert.** Dwelling age is config #1 (the worked example). Water claims is config #2 (the backtest: a case we already lived through, used to prove the machine's honesty). The alert queue below is who goes next. One config format, one loader, one report; a new alert is a new JSON file (a plain text file of inputs), not new code.

## Purpose

- One instrument that prices whether an underwriting alert is worth keeping.
- It answers, for any alert: how many more binds, how many more NOCs and NOEs, GWP gained or lost (gross written premium: the total premium dollars), loss-ratio impact.
- Today every alert debate stalls the same way: the two sides of the ledger share no unit. UW answers for every NOC, growth answers for every bind, both are right from their seat. The machine turns that argument into a number.
- Per David: the bind lift is already proven. The machine is really a cost-pricing machine.
- Partner: David Curry (or the new data scientist). Reference seed: `tradeoff.py` in scratch-darren.

## The two directions

- **Remove**: an existing alert proposed for retirement (dwelling age 101+ is the worked example).
- **Add**: a proposed new alert, priced BEFORE it ships. Same math, mirrored signs: adding a gate loses the binds, saves the NOCs, creates the reviews, captures the premium.
- Rule: no alert ships unweighed, none retires unweighed.

## Inputs inventory

Two halves: 6 COUNTS (forecast what removal changes) and 6 WEIGHTS (convert counts to dollars). Every input is a Quantity: a point value (the single best guess), a low/high range, a status, a source, and the Metabase recipe it comes from (`consult-the-book/references/data-recipes.md`, db 235 unless noted).

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
| A bind | dollars over a lifetime: year-one premium, retention, segment loss cost, compounded GWP | UNPRICED beyond year one | year-one premium is a finance pull; LTV (lifetime value) is the finance/actuarial ask |
| A NOC | agent side: cure split. 74% cure; cured costs ~0 to -2% of that agent's next-year binds per event; uncured cancellation ~ -20%, front-loaded (most of the damage lands early). Two cured prices are in circulation: Darren's emails use 3-7%, the curves say ~0 to -2%; a config must name which it uses (the gap moves his 8/23 breakeven from ~12 to ~19-23 of 55 notices). Darren's dollar napkin (8/19): a first uncured NOC ≈ 7 future policies ≈ $12K annual premium (4-6 policies/yr, ~7 yr tenure) | agent side partially priced; customer side UNPRICED | scratch-darren `2026-08-noc-impact-inde-agent/` (REPORT.md + tradeoff.py); Darren's "Post bind cancellation" email thread 8/18-8/23 |
| A corrective NOE | ~$0 premium relief to the customer (measured); removed-coverage experience side not | half priced | ANALYSIS-2026-08-16.md; DEEPDIVE catch-count 6.8% vs 3.3% |
| A freed review | UW labor per forced review | partial | UW expense model anchors: $1.50/quote, $6.82/bound; our pool-to-review division gives $4.5-7.5/review, flagged as an assumption |
| Premium from UW corrections | bound-only premium their fixes add | measured ($26K/mo for dwelling age) | `damr_prem_flags_20260807` (values in CENTS); $3,034 per 100 bound, ~0% recovered at renewal |
| The loss join | actual losses tied back to the alert's population | MISSING entirely | plan: an actuarial backtest of the twin's on-book losses (look up what losses those policies actually produced) (What Must Be True v4, section 5) |

## Outputs: the ledger

- Per month, at a stated scale, signed as the change the action causes:
  - Bound policies (with range)
  - Forced UW reviews
  - NOCs, split into "book shifts to twin rate" plus "new binds at twin rate"
  - UW corrective NOEs, same split
  - GWP: premium from UW corrections (measured) plus GWP from new binds (a what-if range until the bind weight lands)
  - Loss-ratio impact: a placeholder that stays "unknown" until the loss join exists. It never silently drops off the page.
- Every line carries an uncertainty range and a status chip: MEASURED, PARTIAL, or UNPRICED.
- Plus one shared threshold: the exchange rate, binds bought per NOC added. That is the number the tolerance bar gets compared against.

## Denomination and the presentation rule

- "Denominated in" means the unit the machine keeps score in. The machine is denominated in COUNTS (binds, NOCs, NOEs, reviews), because loss ratio takes about a year to show up and counts move first, so they stand in for it.
- The counts-plus-dollars rule: every output shows the counts first, then dollars only where a weight exists. A dollar figure never replaces its count. The priced subtotal is labeled "not the verdict" as long as any weight is unpriced.
- Unpriced means UNPRICED, not zero. Unpriced weights get a visible chip and an explicit sensitivity grid (a what-if table across plausible values). A guess never hides inside a priced line (the code enforces this: arithmetic on an unpriced input yields an unpriced output).

## UI options

- **v0 (built)**: a self-contained static HTML report generated by the tool, plus a plain-text ledger printed to the terminal. No dependencies, opens anywhere, screenshots into any doc.
- **Later (recommend, do not build yet)**: maybe a small Streamlit app (a simple point-and-click web page) with sliders for the sensitivity grids, once the machine has been run manually on 2-3 alerts. Per the project doc: decide doc vs script vs tool after running it by hand, not before.

## Validation plan

- **Reproduce dwelling-age v0** (automated, `tests/test_dwelling_age_v0.py`): the machine fed the dwelling-age config must reproduce +115 binds/mo (+50..+175), +25 NOCs/mo (+10..+40), +30 UW corrective NOEs/mo, -2,200 forced reviews/mo, -$26K/mo correction premium, loss unknown. Pinned lines exact; derived points within 5-10%; derived ranges must CONTAIN the published brackets (ranges combine by worst case, so they can only get wider, never narrower).
- **Backtest a known case (BUILT)** (replay history and check the machine gets it right): `configs/water_claims_backtest.json`, mode "backtest". The water-claims automation launch (Jul 15) scored as a five-claim scorecard: what faithful duplication predicted vs what actually happened. Current read: 4 held (referral rate 36.5% to 11.9%; bind rate flat, exactly as "automation defends, removal unlocks" says; alert firing flat by design; time-to-bind 44h to 24h) / 0 missed / 1 not yet readable (NOC and fix rates on automated binds need ~90 days after bind; first honest read ~mid Oct 2026). A machine that cannot recover a case we already lived through does not get to forecast new ones. Run it: `python3 -m weighing_machine configs/water_claims_backtest.json`.
- **Reproduce Darren's breakeven napkin** (his 8/23 reply to the LHRH update): 55 notices/mo, cured priced at 5%, uncured at 20%, 25 future policies per agent, solve for the cancellation share that eats 115 binds. His answer: 22%, ~12 of 55 notices. The machine fed his assumptions must land on his number; fed the curve prices instead (~0 to -2% cured), the breakeven loosens to ~19-23 of 55. An independent hand calculation the machine cannot recover means one of the two is wrong.
- **Sensitivity analysis on the unpriced weights** (what-if runs): for each UNPRICED weight, show the ledger across a grid of plausible values and find the flip point, the value at which the recommendation changes. If the flip point is far outside any plausible value, the missing price does not block the decision.
- **Name your NOC denominator** (the "out of what"): every NOC rate states per 100 of WHAT, over WHAT window. The config loader (the part of the code that reads the input file) rejects a rate without one. Two rates are in circulation (the twin's 6.5 inspection-lane per 100 bound within 90 days, and Darren's 11.7% book-wide all-UW-NOC); quoting one against the other is how a room gets lost.

## Build phases

- **Phase 0, done (this pass, ~2 days)**: Quantity type with range propagation (low/high ranges carry through the math), the config format, the forecast model, NOC cure-split weight, text + HTML reports, dwelling-age validation suite.
- **Phase 1 (~1-2 weeks, with David Curry)**: run it manually on 2-3 more alerts (water backtest first, then a census leader like roof or Coverage A); harden the config format against what those runs break; wire the automation-coverage input so "alert off after the levers land" is a weighable scenario, not just "alert off".
- **Phase 2 (weeks, finance + actuarial partnership, not a data pull)**: price the four unpriced weights; replace the sensitivity grids with real numbers one at a time.
- **Phase 3 (only if 2-3 manual runs demand it)**: promote to a tool (Streamlit or similar). Recommendation stands: do not build this yet.

## Open questions

- **The four unpriced weights**: bind LTV, the freed-review hour, the customer side of a NOC, and the loss join. Each is an owner conversation (finance, UW ops, finance, actuarial), not a query.
- **The gate**: LaNae's tolerance number is the decision rule input. The machine outputs binds-per-NOC; nobody has asked her what exchange rate she accepts. Until asked, the report prints "tolerance bar: NOT SET". The conversation is now live: Christine asked the exact exchange-rate question on the Post bind cancellation thread (8/19), and Darren implicitly proposed a bar in his 8/23 LHRH reply (net-positive under ~12 cancellations/mo of 55 notices, at his prices).
- **Two cured-NOC prices**: reconcile Darren's 3-7% (his 8/18 rerun, self-labeled directional) with the curve's ~0 to -2% per cured event before Phase 2 prices the NOC weight. Until then, a config names its cure price the same way it names its NOC denominator.
- **Selection-effect floor** (the alert also changes who applies): the twin never faced the alert, so twin rates are a floor for true un-reviewed 101+ (book averages 117 years; projection 7-11 NOCs per 100). The machine carries this as a labeled scenario. Open: how to price the gap between floor and projection, and whether the A/B test (section 8 of the project doc) should size it directly.

## Estimation methods (how the counts get forecast)

The sister cohort is the default way to forecast, not the only one. Five ways to forecast removal impact, in rising order of strength:

1. **The sister cohort** (default). The 91-100 year old homes that never had the alert. Cheap, real, reproducible. Blind to selection effects (it cannot see how removal changes who applies); younger than the true book (handled by the risk-gradient projection).
2. **Pre-alert era diff-in-diff** (difference-in-differences: compare our group's change over time against a control group's change, so shifts that hit everyone cancel out). Same 101+ population before March 2025, set against a control group across the same eras. Never a raw before/after: era effects are large (inspection cancels halved between eras).
3. **Staggered geography.** Pre-DAMR gating rolled out state by state. Template already exists: the water-automation bind-rate diff-in-diff (with time windows that keep incomplete data out of the count, plus placebo checks: run the same test where nothing changed and make sure it reads zero). Caveat: gating states were not chosen at random.
4. **Boundary comparison.** 99-100 vs 101-102 at the cutoff, plus the 2024 un-gated escapees. The cleanest cause-and-effect evidence, but narrow: it says nothing about the 117-year average home.
5. **The 10% test** (playbook step 7). Turn the alert off for a random 10%. The only method that can see the selection effect (who starts submitting once the alert is gone). Measured data replaces every model above.

Rule: never quote a verdict from a single method. The sister cohort is the default; the era diff-in-diff and the boundary are cross-checks; when all three agree, present the range; the 10% test settles it. (Playbook step 6, proving it with the alert still on, answers a different question: whether the levers duplicate the UW, not what removal costs.)

**Enforced in the config format**: every config must carry an `estimator` block naming which of the five methods produced its numbers, plus a plain-words description of the comparison. The loader rejects a config without one, and the ledger prints the method. Two alerts priced by different methods are never silently compared as equals.

## The alert queue (playbook step 2's shopping list)

Machine-readable copy: `configs/alert_queue.json`. Volumes are underwriter touches per month (verified census, Jan-Jun 2026). "Unknown" means nobody has pulled it yet.

| Alert family | UW touches/mo | Comparison group | UW action mix | Post-bind outcomes | Levers | Status |
|---|---|---|---|---|---|---|
| Dwelling age | 5,044 | yes: the 91-100 sister cohort | known (46.5 / 25.3 / 28.2 / 8.4) | known, reason codes pulled | roof dial, pre-fill sourcing, attestations | **weighed (config #1)**; weights unpriced |
| Excessive claims (water/theft/fire/liability) | 1,692 | partial: launch vs control states for water | partial (water: approve 87.1 / reject 3.2) | not yet readable for automated binds (~mid Oct) | water live, theft live, fire/liability not built | **backtest (config #2)** |
| Roof condition | 1,156 | unknown | partial (approve 77.0 / reject 8.0) | unknown | the roof score model already exists | good candidate for config #3 |
| Coverage A threshold | 1,094 | unknown | partial (approve 63.2 / **reject 16.3**, highest of the majors) | unknown | unknown | weigh carefully: this gate may be doing real work |
| Open claims | 820 | unknown | partial (approve 67.4 / reject 11.1) | unknown | claim-matching cleanup explored | not weighed |
| Duplicates / declines | 772 | unknown | partial (approve 76.8 / reject 9.2) | unknown | unknown | not weighed |
| Occupancy | 575 | unknown | partial (approve 67.5 / reject 12.7) | unknown | unknown | not weighed |
| VELMA high risk | ~220 | unknown | partial (approve 81.2 / reject 4.6 at 45.1% referral) | unknown | possibly none needed | possible cheapest first kill |

## Intake checklist: putting a NEW alert on the scale

What to gather before an alert gets a config. Each item names where it comes from (`consult-the-book/references/data-recipes.md`, Metabase db 235 unless noted).

1. **Funnel volumes.** Quotes hitting the alert per month, share referred, share that dies with nobody looking, UW touches per month. Recipe: "UW touches per alert family" (eventstore referrals joined to the alerts table at the submitted version, family-tagged).
2. **A comparison group, and which of the five methods it is.** A sister cohort if one exists; otherwise pre-alert era, state rollout, or the boundary. If none works, the alert waits for a 10% test and the config says so.
3. **The UW action mix.** What reviewers do on this alert's referrals: approve untouched, change something (what), reject (why). Recipe: single-alert cohort ("Study A": quotes whose only alert family is this one) plus the action detail pulls.
4. **Post-bind outcomes.** NOCs and UW corrective endorsements per 100 bound, 90 days, for the gated group and the comparison group, with reason codes. Recipe: the post-bind census pattern (`dbt_dev.damr_uarnoe_*` build) plus the NOC sub-reason join (`tap_veruna.wt_insurance_policy__c.steadily_uw_cancellation_reason__c`).
5. **Which levers exist.** For each UW job on this alert: is there a system that already does it, partly does it, or nothing.
6. **The weights.** Mostly shared across alerts (bind value, NOC cost, review labor, loss join live in one place and are priced once); only the premium-from-corrections number is per-alert.

If items 1-4 exist, writing the config is an afternoon. The machine adds no new math per alert; it adds discipline.

- **NOE double-count risk**: the v0 hand ledger's +30 counted only the existing book's rate shift; the machine also adds new-bind NOEs (~+9/mo, total ~+40). Confirm with David which convention the Thursday proposal quotes, and label it either way.
