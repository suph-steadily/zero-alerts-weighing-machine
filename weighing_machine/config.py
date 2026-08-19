"""Load and validate an alert config (a plain JSON file, see configs/).

A config carries the 6 COUNTS and 6 WEIGHTS from the "What Must Be True" v4
framing (alert-north-star/appendix/what-must-be-true.html), each as a
Quantity with point, range, status, source, and (for rates) a denominator.

The counts half supports two paths per line:
  * pinned:  the number was already measured/derived by hand (v0 style),
             stored directly (e.g. binds_gained_per_month).
  * derived: the machine computes it from cohort rates (NOCs, NOEs, premium).

Nothing here queries anything. The `recipe` field on each Quantity names the
Metabase recipe/table (consult-the-book data-recipes.md) the number was, or
would be, pulled from.
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


@dataclass
class AlertConfig:
    alert_id: str
    name: str
    direction: str                       # "remove" or "add"
    as_of: str
    description: str = ""
    notes: List[str] = field(default_factory=list)
    counts: Dict[str, Quantity] = field(default_factory=dict)
    weights: Dict[str, Dict[str, Quantity]] = field(default_factory=dict)
    validation: dict = field(default_factory=dict)   # published targets, optional
    raw: dict = field(default_factory=dict)

    def count(self, key: str) -> Quantity:
        return self.counts[key]

    def weight(self, group: str, key: str) -> Quantity:
        return self.weights[group][key]


def _quantities(block: dict, prefix: str) -> Dict[str, Quantity]:
    out = {}
    for key, val in block.items():
        if isinstance(val, dict):
            out[key] = Quantity.from_json(val, key="%s.%s" % (prefix, key))
        else:
            raise ValueError("%s.%s must be a Quantity object, got %r"
                             % (prefix, key, type(val).__name__))
    return out


def load(path: str) -> AlertConfig:
    with open(path) as f:
        raw = json.load(f)

    alert = raw.get("alert", {})
    for k in ("id", "name", "direction", "as_of"):
        if k not in alert:
            raise ValueError("config missing alert.%s" % k)
    if alert["direction"] not in ("remove", "add"):
        raise ValueError("alert.direction must be 'remove' or 'add'")

    counts = _quantities(raw.get("counts", {}), "counts")
    missing = [k for k in REQUIRED_COUNTS if k not in counts]
    if missing:
        raise ValueError("config missing counts: %s" % ", ".join(missing))

    weights: Dict[str, Dict[str, Quantity]] = {}
    for group, block in raw.get("weights", {}).items():
        weights[group] = _quantities(block, "weights.%s" % group)
    missing = [g for g in REQUIRED_WEIGHT_GROUPS if g not in weights]
    if missing:
        raise ValueError("config missing weight groups: %s" % ", ".join(missing))

    return AlertConfig(
        alert_id=alert["id"],
        name=alert["name"],
        direction=alert["direction"],
        as_of=alert["as_of"],
        description=alert.get("description", ""),
        notes=alert.get("notes", []),
        counts=counts,
        weights=weights,
        validation=raw.get("validation", {}),
        raw=raw,
    )
