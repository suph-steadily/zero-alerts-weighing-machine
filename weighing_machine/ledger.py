"""The ledger: what the weighing machine outputs for one alert.

Two panels, per the counts-plus-dollars presentation rule (REQUIREMENTS.md):

  * COUNTS  - binds, NOCs, NOEs, forced reviews. The leading indicators.
              These are always shown, always first. Loss ratio lags ~1 year,
              so the machine is denominated in counts.
  * DOLLARS - each count converted through its weight, WHERE a weight exists.
              Unpriced weights stay visibly UNPRICED; sensitivity grids show
              what-ifs without ever hiding a guess inside a priced line.

Sign convention: every line is the CHANGE caused by the proposed action
(direction "remove" or "add"), signed in the metric's own terms. So for a
removal: binds +115, forced reviews -2,200, NOCs +25. Good or bad is a label,
not a sign flip.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .quantity import Quantity

COUNT = "count"
DOLLARS = "dollars"


@dataclass
class LedgerLine:
    key: str
    label: str
    quantity: Quantity          # the signed delta per month
    kind: str = COUNT           # COUNT or DOLLARS
    good_when: str = "up"       # "up" / "down" / "unknown": which sign is a win
    components: Dict[str, Quantity] = field(default_factory=dict)
    notes: str = ""

    @property
    def status(self) -> str:
        return self.quantity.status


@dataclass
class SensitivityRow:
    label: str                  # e.g. "agent writes 15 binds/yr (median book)"
    value: float
    unit: str


@dataclass
class SensitivityBlock:
    key: str
    title: str
    driver: str                 # which UNPRICED weight this grid varies
    rows: List[SensitivityRow] = field(default_factory=list)
    notes: str = ""


@dataclass
class Ledger:
    alert_id: str
    alert_name: str
    direction: str              # "remove" or "add"
    as_of: str
    scale: float
    lines: List[LedgerLine] = field(default_factory=list)
    sensitivities: List[SensitivityBlock] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)
    # binds bought per NOC added (gross exchange rate); the decision rule
    # compares this against the tolerance bar once one exists.
    bind_to_noc_ratio: Optional[Quantity] = None
    tolerance_bar: Optional[float] = None   # LaNae's number; None = never asked
    # which estimation method produced the counts, and against what comparison
    # population; printed so ledgers from different methods are never mixed up.
    estimator_label: str = ""
    comparison: str = ""

    # ------------------------------------------------------------- helpers
    def line(self, key: str) -> LedgerLine:
        for ln in self.lines:
            if ln.key == key:
                return ln
        raise KeyError(key)

    def counts(self) -> List[LedgerLine]:
        return [ln for ln in self.lines if ln.kind == COUNT]

    def dollars(self) -> List[LedgerLine]:
        return [ln for ln in self.lines if ln.kind == DOLLARS]

    def unpriced(self) -> List[LedgerLine]:
        return [ln for ln in self.lines if not ln.quantity.is_priced]

    # ---------------------------------------------------------------- text
    def to_text(self) -> str:
        w = 34
        out = []
        out.append("THE WEIGHING MACHINE  (first pass)")
        out.append("Alert: %s (%s)" % (self.alert_name, self.alert_id))
        out.append("Direction: %s | scale: %.2f | as of %s"
                   % (self.direction, self.scale, self.as_of))
        if self.estimator_label:
            out.append("Counts estimated via: %s" % self.estimator_label)
        if self.comparison:
            out.append("Comparison: %s" % self.comparison)
        out.append("")
        out.append("COUNTS, per month at this scale")
        for ln in self.counts():
            dec = 0 if abs(ln.quantity.point or 0) >= 100 else 1
            out.append("  %-*s %s   [%s]" % (w, ln.label,
                                             ln.quantity.fmt(dec, signed=True),
                                             ln.status))
            for ck, cq in ln.components.items():
                out.append("  %-*s   . %s: %s" % (w, "", ck, cq.fmt(1, signed=True)))
        out.append("")
        out.append("DOLLARS, per month, where a weight exists")
        for ln in self.dollars():
            if ln.quantity.is_priced:
                out.append("  %-*s %s   [%s]" % (w, ln.label,
                                                 ln.quantity.fmt(0, signed=True, prefix="$"),
                                                 ln.status))
            else:
                out.append("  %-*s UNPRICED" % (w, ln.label))
            if ln.notes:
                out.append("  %-*s   . %s" % (w, "", ln.notes))
        if self.bind_to_noc_ratio is not None:
            out.append("")
            out.append("Exchange rate: %s binds bought per NOC added (gross)"
                       % self.bind_to_noc_ratio.fmt(1))
            bar = ("tolerance bar: NOT SET (never asked)" if self.tolerance_bar is None
                   else "tolerance bar: %.1f" % self.tolerance_bar)
            out.append("  %s" % bar)
        if self.sensitivities:
            out.append("")
            out.append("SENSITIVITY (unpriced weights, explicit what-ifs; not estimates)")
            for blk in self.sensitivities:
                out.append("  %s  (varies: %s)" % (blk.title, blk.driver))
                for row in blk.rows:
                    out.append("    %-40s %s %s"
                               % (row.label, format(row.value, ",.1f"), row.unit))
        if self.caveats:
            out.append("")
            out.append("CAVEATS")
            for c in self.caveats:
                out.append("  * %s" % c)
        return "\n".join(out)
