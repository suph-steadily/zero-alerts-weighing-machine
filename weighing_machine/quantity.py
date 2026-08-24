"""Quantity: a number that carries its range, source, and pricing status.

Every input to the weighing machine is a Quantity, never a bare float.
The rules:

  * `point` is the best estimate. `low`/`high` are scenario bounds. They are
    only confidence intervals when the `source` note says so (the dwelling-age
    rates carry Byar approximate 95% CIs; most other ranges are hand brackets).
  * Propagation is worst-case interval arithmetic (sums add ends, products
    multiply matching ends for non-negative inputs, subtraction crosses ends).
    Ranges therefore only ever WIDEN: a machine-propagated range should
    CONTAIN the corresponding hand-computed range, not match it. The
    dwelling-age validation test asserts containment, not equality.
  * `status` is one of "measured" / "partial" / "unpriced". An unpriced
    Quantity has point=None and may carry a `sensitivity` grid of explicitly
    labeled what-if values. Arithmetic on an unpriced Quantity yields an
    unpriced Quantity: a hidden guess can never leak into a priced line.
  * Rates must name their denominator ("per 100 WHAT, over WHAT window").
    See the "name your NOC denominator" rule in REQUIREMENTS.md.

Stdlib only, in the spirit of tradeoff.py in scratch-darren
(github.com/landlordhq/scratch-darren, 2026-08-noc-impact-inde-agent/).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import List, Optional

MEASURED = "measured"
PARTIAL = "partial"
UNPRICED = "unpriced"
_STATUSES = (MEASURED, PARTIAL, UNPRICED)

# Ordering used when deriving a value from several inputs: the result is only
# as priced as its weakest input.
_STATUS_RANK = {MEASURED: 0, PARTIAL: 1, UNPRICED: 2}


@dataclass(frozen=True)
class Quantity:
    point: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    unit: str = ""
    denominator: str = ""  # required on any *_per_100* rate
    source: str = ""
    recipe: str = ""       # where the number is pulled from (Metabase recipe/table)
    confidence: str = ""   # high / medium / low / none
    status: str = MEASURED
    notes: str = ""
    sensitivity: List[float] = field(default_factory=list)
    sensitivity_labels: List[str] = field(default_factory=list)

    # ---------------------------------------------------------------- basics
    def __post_init__(self):
        if self.status not in _STATUSES:
            raise ValueError("status must be one of %s, got %r" % (_STATUSES, self.status))
        if self.status == UNPRICED:
            if self.point is not None:
                raise ValueError("an UNPRICED quantity must not carry a point value "
                                 "(that would be a hidden guess): %r" % (self.source,))
            return
        if self.point is None:
            raise ValueError("a priced quantity needs a point value: %r" % (self.source,))
        lo = self.point if self.low is None else self.low
        hi = self.point if self.high is None else self.high
        if not (lo <= self.point <= hi):
            raise ValueError("range must bracket the point: %s <= %s <= %s (%s)"
                             % (lo, self.point, hi, self.source))

    @property
    def is_priced(self) -> bool:
        return self.status != UNPRICED

    @property
    def lo(self) -> float:
        return self.point if self.low is None else self.low

    @property
    def hi(self) -> float:
        return self.point if self.high is None else self.high

    @property
    def has_range(self) -> bool:
        return self.is_priced and (self.lo != self.point or self.hi != self.point)

    # ------------------------------------------------------------ arithmetic
    @staticmethod
    def _combine_status(*qs: "Quantity") -> str:
        return max((q.status for q in qs), key=lambda s: _STATUS_RANK[s])

    @staticmethod
    def _unpriced_result(*qs: "Quantity") -> "Quantity":
        srcs = "; ".join(q.source for q in qs if q.status == UNPRICED)
        return Quantity(status=UNPRICED, source="derived from unpriced input(s): " + srcs)

    def add(self, other: "Quantity") -> "Quantity":
        if not (self.is_priced and other.is_priced):
            return self._unpriced_result(self, other)
        return Quantity(point=self.point + other.point,
                        low=self.lo + other.lo, high=self.hi + other.hi,
                        unit=self.unit, status=self._combine_status(self, other),
                        source="derived (sum)")

    def sub(self, other: "Quantity") -> "Quantity":
        """Worst-case interval subtraction: low crosses my low with their high."""
        if not (self.is_priced and other.is_priced):
            return self._unpriced_result(self, other)
        return Quantity(point=self.point - other.point,
                        low=self.lo - other.hi, high=self.hi - other.lo,
                        unit=self.unit, status=self._combine_status(self, other),
                        source="derived (difference)")

    def mul(self, other: "Quantity") -> "Quantity":
        """Interval product. Handles sign-crossing ranges the general way."""
        if not (self.is_priced and other.is_priced):
            return self._unpriced_result(self, other)
        ends = [self.lo * other.lo, self.lo * other.hi,
                self.hi * other.lo, self.hi * other.hi]
        return Quantity(point=self.point * other.point,
                        low=min(ends), high=max(ends),
                        unit=(self.unit + "*" + other.unit).strip("*"),
                        status=self._combine_status(self, other),
                        source="derived (product)")

    def scaled(self, k: float) -> "Quantity":
        """Simple linear scaling (e.g. a 7-state cut, or a 50% holdout)."""
        if not self.is_priced:
            return self
        lo, hi = self.lo * k, self.hi * k
        if k < 0:
            lo, hi = hi, lo
        return replace(self, point=self.point * k, low=lo, high=hi)

    def negate(self) -> "Quantity":
        """Sign flip (used for direction='add'). Bounds swap."""
        return self.scaled(-1.0)

    # ------------------------------------------------------------------- io
    @classmethod
    def from_json(cls, d: dict, key: str = "") -> "Quantity":
        known = {"point", "low", "high", "unit", "denominator", "source", "recipe",
                 "confidence", "status", "notes", "sensitivity", "sensitivity_labels"}
        extra = set(d) - known
        if extra:
            raise ValueError("unknown Quantity fields %s on %r" % (sorted(extra), key))
        q = cls(**d)
        # The "name your NOC denominator" rule, enforced at load time.
        # Keyed on the unit as well as the key name, so a rate cannot dodge
        # the rule by being named something other than *_per_100*.
        is_rate = "_per_100" in key or "per 100" in (q.unit or "").lower()
        if is_rate and not q.denominator:
            raise ValueError("rate %r must name its denominator "
                             "(per 100 WHAT, over WHAT window)" % key)
        return q

    def fmt(self, decimals: int = 1, signed: bool = False, prefix: str = "") -> str:
        if not self.is_priced:
            return "UNPRICED"
        s = "+" if signed else ""

        def one(v):
            if decimals == 0:
                return "%s%s%s" % (s if v > 0 else ("-" if v < 0 else ""), prefix,
                                   format(abs(round(v)), ","))
            return "%s%s%s" % (s if v > 0 else ("-" if v < 0 else ""), prefix,
                               format(abs(v), ",.%df" % decimals))

        if self.has_range:
            return "%s  [%s .. %s]" % (one(self.point), one(self.lo), one(self.hi))
        return one(self.point)
