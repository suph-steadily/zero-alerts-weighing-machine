# weighing-machine

First pass of the Weighing Machine: price ANY underwriting alert for removal (or a proposed one for adding), and score automations we already lived through. Counts first, dollars where a weight exists, UNPRICED chips where one does not. Dwelling age is config #1, water claims is the backtest (config #2), and `configs/alert_queue.json` is who goes next. A new alert is a new JSON file, not new code. See `REQUIREMENTS.md` for the full spec, the alert queue, and the intake checklist.

## Run it

No dependencies, plain built-in Python 3 only (nothing to install). From this folder:

```
# text ledger printed to the terminal (stdout) + self-contained HTML report
python3 -m weighing_machine configs/dwelling_age.json -o examples/dwelling_age_report.html

# top-7-states cut, or a 50% holdout (weigh only half the volume)
python3 -m weighing_machine configs/dwelling_age.json --scale 0.93

# once LaNae names her binds-per-NOC tolerance
python3 -m weighing_machine configs/dwelling_age.json --tolerance-bar 100

# the water backtest: did the automation duplicate the underwriter?
python3 -m weighing_machine configs/water_claims_backtest.json
```

Every config declares which of the five estimation methods produced its numbers (sister cohort, pre-alert era, state rollout, boundary, the 10% test); the loader (the code that reads the config) refuses one that does not, and the ledger prints the method so two alerts priced different ways are never compared as equals.

## Tests

```
python3 -m unittest discover -s tests
```

41 tests: the dwelling-age config must reproduce the published v0 ledger (+115 binds, +25 NOCs, +30 book-shift NOEs, -2,200 reviews, -$26K premium, loss unknown) within documented tolerances, plus sanity checks: ranges carry through the math, scaling works, and the add and remove directions mirror each other. The any-alert suite (`tests/test_any_alert.py`) covers the estimation-method declaration, the water backtest scorecard (4 held / 0 missed / 1 not yet readable), the mode guardrails, and the alert queue file.

## Layout

- `configs/dwelling_age.json` - config #1, the worked example; every value carries a point value (the single best guess), a range, a status, a source, and the Metabase recipe it comes from
- `configs/water_claims_backtest.json` - config #2, the backtest: the July water automation scored claim by claim
- `configs/alert_queue.json` - the queue: top alert families by UW touches per month, with data readiness
- `weighing_machine/quantity.py` - the Quantity type; ranges combine by worst case, so they only widen; unpriced never gains a point value
- `weighing_machine/model.py` - the forecast math and the NOC cure-split weight
- `weighing_machine/backtest.py` - the lived-case scorecard (held / missed / not yet readable)
- `weighing_machine/config.py` - the config format, documented at the top of the file; works for any alert
- `weighing_machine/ledger.py` - the two-panel ledger (counts, dollars) and text rendering
- `weighing_machine/report.py` - self-contained HTML report, no external assets
- `examples/dwelling_age_report.html` - generated output, safe to regenerate

## What is stubbed / honest gaps

- **Four weights are UNPRICED** (bind LTV (lifetime value), NOC customer side, NOE experience side, the loss join). They render as chips plus explicit sensitivity grids (what-if tables across plausible values); the illustrative grid values are placeholders, not estimates.
- **Freed-review rate ($4.5-7.5/review)** is our division of the UW expense-model pool ($1.50/quote, $6.82/bound) by review volume; the division is an assumption and says so in the config.
- **NOC weight simplifications**: the -20% uncured cost is treated as level per event (really most of it lands early), and each NOC is assumed to land on a distinct agent.
- **v0 NOE convention**: the published +30 counted only the existing book's rate shift; the machine reports that component (for v0 comparability) and the coherent total (~+40) that includes new-bind NOEs.
- **No queries**: the machine encodes structure; numbers enter through the config files by hand, each with its source and recipe named.
- **The backtest verdicts are recorded, not computed**: each claim's held/missed comes from the analysis that measured it; the loader only enforces honesty (an unreadable number can never claim "held"). A later pass could auto-judge claims where prediction and actual are both numeric.
- **Queue readiness is as-known-today**: "unknown" in the alert queue means nobody pulled it yet, not that it cannot be pulled.
