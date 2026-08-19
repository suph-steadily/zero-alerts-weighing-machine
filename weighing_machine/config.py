"""Load and validate an alert config (a plain JSON file, see configs/).

THE SCHEMA, in one place. A config is one alert, and it works for ANY alert:

  alert:      id, name, direction, as_of, mode, description, notes
              - mode "weigh"    -> price the alert for removal or adding
                (direction "remove" or "add")
              - mode "backtest" -> score an automation case we already lived
                through (direction "automate"), via backtest.claims
  estimator:  REQUIRED on every config. Which of the five methods produced
              the numbers (see ESTIMATORS below) plus a plain-words
              "comparison" describing the population or setup. Two configs
              built on different estimators must never be compared as equals;
              the ledger prints the method so nobody can forget.
  counts:     (weigh mode) the volume and rate inputs. "twin_*" keys mean
              "the rate for the comparison group the estimator chose",
              whatever that group is: sister cohort, pre-alert era, rollout
              control states, boundary slice, or the 10% test slice.
  weights:    (weigh mode) the price tags: bind, noc, noe, review, loss.
  backtest:   (backtest mode) claims list: what faithful duplication
              predicted, what actually happened, verdict held/missed/pending.
  validation: optional published targets a test can pin against.

Every number is a Quantity: point, low/high range, status
(measured/partial/unpriced), source, and the Metabase recipe it comes from
(consult-the-book data-recipes.md). Rates must name their denominator.

Nothing here queries anything; numbers enter by hand with their sources.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .quantity import Quantity

REQUIRED_COUNTS = [
    "forced_reviews_per_month",
    "current_binds_per_month",
    "binds_gained_per_month",
    "reviewed_noc_per_100_bound_90d",
    "twin_noc_per_100_bound_90d",
    "reviewed_noe_per_100_bound_90d",
    "twin_noe_per_100_bound_90d",
    "foregone_uw_correction_premium_per_100_bound_usd",
]

REQUIRED_WEIGHT_GROUPS = ["bind", "noc", "noe", "review", "loss"]

# The two things a config can be.
MODE_WEIGH = "weigh"          # price an alert for removal (or adding)
MODE_BACKTEST = "backtest"    # score a case we already lived through
MODES = (MODE_WEIGH, MODE_BACKTEST)

# The five ways the count inputs can be estimated (REQUIREMENTS.md,
# "Estimation methods"). Every config MUST say which one produced its
# numbers, so two alerts priced by different methods are never silently
# compared as equals.
ESTIMATORS = {
    "sister_cohort": "a nearby group that never had the alert",
    "pre_alert_era": "the same group before the alert existed, era-adjusted",
    "state_rollout": "states that got it earlier vs states that got it later",
    "boundary": "quotes right at the cutoff line",
    "ten_percent_test": "the 10% test: alert actually off for a slice, measured",
}

BACKTEST_VERDICTS = ("held", "missed", "pending")


@dataclass
class BacktestClaim:
    """One line of a lived-case scorecard: what faithful duplication
    predicted, what actually happened, and whether the prediction held."""
    key: str
    label: str
    expectation: str            # what duplication implies, in plain words
    actual: Quantity            # UNPRICED = not yet readable
    verdict: str                # held / missed / pending
    read: str = ""              # one plain sentence on the result
    baseline: Optional[Quantity] = None   # the before number, when one exists


@dataclass
class AlertConfig:
    alert_id: str
    name: str
    direction: str                       # "remove" / "add" / "automate"
    as_of: str
    mode: str = MODE_WEIGH
    estimator: dict = field(default_factory=dict)   # method + comparison
    description: str = ""
    notes: List[str] = field(default_factory=list)
    counts: Dict[str, Quantity] = field(default_factory=dict)
    weights: Dict[str, Dict[str, Quantity]] = field(default_factory=dict)
    backtest_claims: List[BacktestClaim] = field(default_factory=list)
    validation: dict = field(default_factory=dict)   # published targets, optional
    raw: dict = field(default_factory=dict)

    def count(self, key: str) -> Quantity:
        return self.counts[key]

    def weight(self, group: str, key: str) -> Quantity:
        return self.weights[group][key]

    @property
    def estimator_method(self) -> str:
        return self.estimator.get("method", "")

    @property
    def estimator_label(self) -> str:
        m = self.estimator_method
        return "%s (%s)" % (m, ESTIMATORS.get(m, "?"))


def _quantities(block: dict, prefix: str) -> Dict[str, Quantity]:
    out = {}
    for key, val in block.items():
        if isinstance(val, dict):
            out[key] = Quantity.from_json(val, key="%s.%s" % (prefix, key))
        else:
            raise ValueError("%s.%s must be a Quantity object, got %r"
                             % (prefix, key, type(val).__name__))
    return out


def _load_estimator(raw: dict) -> dict:
    est = raw.get("estimator")
    if not isinstance(est, dict) or "method" not in est:
        raise ValueError(
            "config missing the estimator block: every config must say which "
            "method produced its numbers, e.g. "
            '{"estimator": {"method": "sister_cohort", "comparison": "..."}}. '
            "Methods: %s" % ", ".join(sorted(ESTIMATORS)))
    if est["method"] not in ESTIMATORS:
        raise ValueError("estimator.method must be one of %s, got %r"
                         % (sorted(ESTIMATORS), est["method"]))
    if not est.get("comparison"):
        raise ValueError("estimator.comparison must describe the comparison "
                         "population or setup in plain words")
    return est


def _load_backtest_claims(raw: dict) -> List[BacktestClaim]:
    block = raw.get("backtest", {})
    claims_raw = block.get("claims")
    if not claims_raw:
        raise ValueError("mode 'backtest' needs backtest.claims (a list)")
    claims = []
    for i, c in enumerate(claims_raw):
        where = "backtest.claims[%d]" % i
        for k in ("key", "label", "expectation", "actual", "verdict"):
            if k not in c:
                raise ValueError("%s missing %r" % (where, k))
        if c["verdict"] not in BACKTEST_VERDICTS:
            raise ValueError("%s.verdict must be one of %s, got %r"
                             % (where, BACKTEST_VERDICTS, c["verdict"]))
        actual = Quantity.from_json(c["actual"], key="%s.actual" % where)
        if not actual.is_priced and c["verdict"] != "pending":
            raise ValueError(
                "%s: the actual number is not readable yet, so the verdict "
                "must be 'pending', not %r" % (where, c["verdict"]))
        baseline = None
        if "baseline" in c:
            baseline = Quantity.from_json(c["baseline"], key="%s.baseline" % where)
        claims.append(BacktestClaim(
            key=c["key"], label=c["label"], expectation=c["expectation"],
            actual=actual, verdict=c["verdict"], read=c.get("read", ""),
            baseline=baseline))
    return claims


def load(path: str) -> AlertConfig:
    with open(path) as f:
        raw = json.load(f)

    alert = raw.get("alert", {})
    for k in ("id", "name", "direction", "as_of"):
        if k not in alert:
            raise ValueError("config missing alert.%s" % k)

    mode = alert.get("mode", MODE_WEIGH)
    if mode not in MODES:
        raise ValueError("alert.mode must be one of %s, got %r" % (MODES, mode))

    if mode == MODE_WEIGH:
        if alert["direction"] not in ("remove", "add"):
            raise ValueError("alert.direction must be 'remove' or 'add'")
    else:
        if alert["direction"] != "automate":
            raise ValueError("a backtest config scores an automation case; "
                             "alert.direction must be 'automate'")

    estimator = _load_estimator(raw)

    counts: Dict[str, Quantity] = {}
    weights: Dict[str, Dict[str, Quantity]] = {}
    backtest_claims: List[BacktestClaim] = []

    if mode == MODE_WEIGH:
        counts = _quantities(raw.get("counts", {}), "counts")
        missing = [k for k in REQUIRED_COUNTS if k not in counts]
        if missing:
            raise ValueError("config missing counts: %s" % ", ".join(missing))
        for group, block in raw.get("weights", {}).items():
            weights[group] = _quantities(block, "weights.%s" % group)
        missing = [g for g in REQUIRED_WEIGHT_GROUPS if g not in weights]
        if missing:
            raise ValueError("config missing weight groups: %s" % ", ".join(missing))
    else:
        backtest_claims = _load_backtest_claims(raw)

    return AlertConfig(
        alert_id=alert["id"],
        name=alert["name"],
        direction=alert["direction"],
        as_of=alert["as_of"],
        mode=mode,
        estimator=estimator,
        description=alert.get("description", ""),
        notes=alert.get("notes", []),
        counts=counts,
        weights=weights,
        backtest_claims=backtest_claims,
        validation=raw.get("validation", {}),
        raw=raw,
    )
