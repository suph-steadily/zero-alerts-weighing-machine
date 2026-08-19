# weighing-machine

First pass of the Weighing Machine: price an underwriting alert for removal (or a proposed one for adding). Counts first, dollars where a weight exists, UNPRICED chips where one does not. See `REQUIREMENTS.md` for the full spec.

## Run it

No dependencies, stdlib Python 3 only. From this folder:

```
# text ledger to stdout + self-contained HTML report
python3 -m weighing_machine configs/dwelling_age.json -o examples/dwelling_age_report.html

# top-7-states cut, or a 50% holdout
python3 -m weighing_machine configs/dwelling_age.json --scale 0.93

# once LaNae names her binds-per-NOC tolerance
python3 -m weighing_machine configs/dwelling_age.json --tolerance-bar 100
```

## Tests

```
python3 -m unittest discover -s tests
```

26 tests: the dwelling-age config must reproduce the published v0 ledger (+115 binds, +25 NOCs, +30 book-shift NOEs, -2,200 reviews, -$26K premium, loss unknown) within documented tolerances, plus range-propagation, scaling, and direction-mirror sanity checks.

## Layout

- `configs/dwelling_age.json` - the worked example; every value carries point, range, status, source, and the Metabase recipe it comes from
- `weighing_machine/quantity.py` - Quantity type; worst-case interval propagation; unpriced never gains a point value
- `weighing_machine/model.py` - the forecast math and the NOC cure-split weight
- `weighing_machine/ledger.py` - the two-panel ledger (counts, dollars) and text rendering
- `weighing_machine/report.py` - self-contained HTML report, no external assets
- `examples/dwelling_age_report.html` - generated output, safe to regenerate

## What is stubbed / honest gaps

- **Four weights are UNPRICED** (bind LTV, NOC customer side, NOE experience side, the loss join). They render as chips plus explicit sensitivity grids; the illustrative grid values are placeholders, not estimates.
- **Freed-review rate ($4.5-7.5/review)** is our division of the UW expense-model pool ($1.50/quote, $6.82/bound) by review volume; the division is an assumption and says so in the config.
- **NOC weight simplifications**: the -20% uncured cost is treated as level per event (really front-loaded), and each NOC is assumed to land on a distinct agent.
- **v0 NOE convention**: the published +30 counted only the existing book's rate shift; the machine reports that component (for v0 comparability) and the coherent total (~+40) that includes new-bind NOEs.
- **No queries**: the machine encodes structure; numbers enter through configs by hand, each with its source and recipe named.
- **Water-claims backtest config** not written yet (Phase 1).
