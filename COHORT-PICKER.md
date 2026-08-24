# The cohort picker: how to find a comparison group for any alert

As of 2026-08-24. The machine weighs cohorts; it does not find them. This page makes finding one a 5-minute classification instead of a bespoke analysis, so putting alert #3, #4, #5 on the scale is an afternoon each (REQUIREMENTS.md, intake checklist).

## The decision rule

Classify the alert by HOW IT FIRES. That decides which of the five estimation methods (REQUIREMENTS.md, Estimation methods) can produce its counts:

| The alert fires on... | The cohort | Method |
|---|---|---|
| A numeric threshold (age 101+, Coverage A over a limit) | The just-under group: quotes right below the trigger never faced the alert | `sister_cohort` (wide band) or `boundary` (tight at the line) |
| A model score (roof condition, VELMA) | Quotes scoring just under the cutoff | `boundary` at the score line |
| A rollout (shipped by state or by date) | Launch vs control states, or before vs after with a control | `state_rollout` or `pre_alert_era` |
| A yes/no fact (open claim exists, occupancy type, duplicate) | No natural neighbor exists. Use the same population before the rule shipped, or turn the alert off for a random slice | `pre_alert_era` or `ten_percent_test` |

Rules that ride along, from the dwelling-age work:

- **State-match, never pool.** The pooled national twin pointed the wrong way for dwelling age (Simpson bias); the state-matched counterfactual (MB 141815 pattern: apply each state's twin rate to that state's gated volume) is the sizing of record. Book recipe: data-recipes.md, funnel-twin 8/13 + 8/19 recut.
- **Exclude the zero-alert-rows quotes** (they bind at 79.3%, special paths, n small) and remember "clean gated" is structurally empty: a quote that trips the predicate always carries the alert.
- **The twin is a floor.** It never faced the alert, so it cannot see who would start applying once the alert is gone. Say so in the config's estimator notes; carry a gradient/projection input when one exists.
- **Never quote a verdict from a single method.** Sister cohort default, era and boundary as cross-checks, the 10% test settles it.

## The 8 queue families, classified

| Alert family (UW touches/mo) | Fires on | Method | The cohort, concretely | Readiness |
|---|---|---|---|---|
| Dwelling age (5,044) | age threshold (101+) | sister_cohort | 91-100 clean band, state-matched (MB 141815) | DONE (config #1) |
| Excessive claims (1,692) | claim counts by peril; automation rolled out by state | state_rollout | water: 26 launch states vs the rest, Jul 15 (config #2, backtest); removal questions: claim-count boundary (n claims vs n-1) | water/theft measured; fire/liability not built |
| Roof condition (1,156) | roof model score | boundary | quotes scoring just under the alert cutoff. Traps from roof-dial (data-recipes.md): 'exclude' spans scores 1-97 so the live decision is NOT a pure score cut; scores only exist Apr 2026+; model versions coexist (pin or stratify) | config #3, this pass |
| Coverage A threshold (1,094) | dollar threshold on Coverage A | sister_cohort / boundary | quotes just under the limit. Weigh carefully: highest reject rate of the majors (16.3%), this gate may be doing real work | cohort findable, not pulled |
| Open claims (820) | binary: an open claim exists | pre_alert_era or 10% test | same population before the rule (era-adjust; era effects are large) or a 10% slice | needs the era dig |
| Duplicates / declines (772) | binary/categorical match | pre_alert_era or 10% test | as above | needs the era dig |
| Occupancy (575) | categorical | pre_alert_era or 10% test | as above | needs the era dig |
| VELMA high risk (~220) | model score | boundary | quotes just under the VELMA score line; possible cheapest first kill (81.2% approve at 45.1% referral) | cohort findable, not pulled |

## The parameterized pull (the funnel-twin pattern, any threshold/score alert)

The verified dwelling-age predicates and every trap live in the book (consult-the-book `references/data-recipes.md`: funnel-twin 2026-08-13 + 8/19 recut, "UW touches per alert family", roof-dial facts). The shape, parameterized by alert family:

```sql
-- db 235 (Metabase = the ClickHouse warehouse). Quote-level, NB,
-- requires_uw_review basis, evaluated-only, Jan-May-2026-style window.
-- 1) Tag each submitted quote version with its blocking alerts:
--    dbt.ipod_smga_uw_alerts_per_quote_version at the submitted
--    (quote_id, quote_version), family predicate e.g.
--    alert_id LIKE 'DWELLING_AGE%'  -- <- the family parameter
-- 2) Build three lanes per state:
--    gated lane:   family alert present, no other substantive alert
--    twin lane:    just-under the trigger (age band / score band /
--                  amount band), zero substantive alerts
--    clean lane:   far side (the healthy-funnel yardstick)
-- 3) Bind = quote_issued_timestamp IS NOT NULL (exact).
-- 4) Size removal state-matched: apply each state's twin bind rate to that
--    state's gated volume (the MB 141815 move), never the pooled average.
-- 5) Post-bind outcomes: rebuild the census pattern
--    (dbt_dev.damr_uarnoe_* recipe) on both lanes: NOCs
--    (cancellation_reason='Inspection'), UW corrective NOEs
--    (f_ev_class IN ('attribute_correction','exclusion_change') AND
--    f_actor_class='uw'), per 100 bound, 90 days, with reason codes.
```

Per-family parameters to fill: the alert_id predicate, the just-under band definition, and the window. Everything else is the same query. For score alerts, the band is a score range and the score-coverage window applies (roof: Apr 2026+ only).

## What this does NOT solve

- **Binary alerts have no twin.** The era comparison needs its own careful cut (era effects halved inspection cancels between eras; always diff-in-diff, never raw before/after), and the 10% test needs a decision to run it.
- **Selection effects stay invisible** to every method except the 10% test. Every cohort-based cost line is a floor.
- **The weights don't come from cohorts.** Bind LTV, NOC/NOE prices, labor, and the loss join are shared, priced once (INPUTS.md gap list has the owners).
