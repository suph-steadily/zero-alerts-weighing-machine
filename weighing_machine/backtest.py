"""Backtest scorecard: score a case we already lived through.

A weigh-mode config forecasts. A backtest-mode config looks backwards at an
automation that already ran (playbook steps 5-6) and asks: did the system
duplicate the underwriter? Each claim pairs what faithful duplication
predicted with what actually happened, and carries a verdict:

  held    - the prediction survived contact with the data
  missed  - it did not; the machine (or the automation) needs fixing
  pending - the actual number is not readable yet (e.g. NOCs need ~90 days)

The config loader enforces honesty: an unreadable actual can only be
"pending", and every claim states its expectation in plain words. A machine
that cannot recover a case we already lived through does not get to forecast
new ones (REQUIREMENTS.md, validation plan).

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .config import AlertConfig, BacktestClaim


@dataclass
class BacktestScore:
    alert_id: str
    alert_name: str
    as_of: str
    estimator_label: str
    comparison: str
    claims: List[BacktestClaim] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def held(self) -> int:
        return sum(1 for c in self.claims if c.verdict == "held")

    @property
    def missed(self) -> int:
        return sum(1 for c in self.claims if c.verdict == "missed")

    @property
    def pending(self) -> int:
        return sum(1 for c in self.claims if c.verdict == "pending")

    def to_text(self) -> str:
        out = []
        out.append("THE WEIGHING MACHINE  (backtest scorecard)")
        out.append("Case: %s (%s)" % (self.alert_name, self.alert_id))
        out.append("Measured via: %s" % self.estimator_label)
        out.append("Comparison: %s" % self.comparison)
        out.append("As of %s" % self.as_of)
        out.append("")
        out.append("Did the automation duplicate the underwriter?  "
                   "%d held / %d missed / %d not yet readable"
                   % (self.held, self.missed, self.pending))
        out.append("")
        for c in self.claims:
            out.append("[%s] %s" % (c.verdict.upper(), c.label))
            out.append("    expectation: %s" % c.expectation)
            if c.baseline is not None and c.baseline.is_priced:
                out.append("    before: %s %s" % (c.baseline.fmt(1), c.baseline.unit))
            if c.actual.is_priced:
                out.append("    actual: %s %s" % (c.actual.fmt(1), c.actual.unit))
            else:
                out.append("    actual: NOT YET READABLE (%s)" % (c.actual.source or "no source note"))
            if c.read:
                out.append("    read: %s" % c.read)
            out.append("")
        if self.notes:
            out.append("NOTES")
            for n in self.notes:
                out.append("  * %s" % n)
        return "\n".join(out)


def score(cfg: AlertConfig) -> BacktestScore:
    if cfg.mode != "backtest":
        raise ValueError("score() takes a backtest-mode config; "
                         "use weigh() for mode 'weigh'")
    return BacktestScore(
        alert_id=cfg.alert_id,
        alert_name=cfg.name,
        as_of=cfg.as_of,
        estimator_label=cfg.estimator_label,
        comparison=cfg.estimator.get("comparison", ""),
        claims=list(cfg.backtest_claims),
        notes=list(cfg.notes),
    )
