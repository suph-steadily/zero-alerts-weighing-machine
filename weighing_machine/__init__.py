"""The Weighing Machine, first pass.

A standardized way to price whether an underwriting alert should be removed
(or a proposed one added): binds gained vs NOCs, NOEs, lost premium, freed
reviews. Counts first, dollars where a weight exists, UNPRICED chips where
one does not.

Part of the Zero Alerts project (alert-north-star/README.md s3).
Reference seed: tradeoff.py in scratch-darren. Stdlib only.

Usage:
    python3 -m weighing_machine configs/dwelling_age.json -o report.html
"""

from .config import AlertConfig, load
from .ledger import Ledger, LedgerLine
from .model import per_noc_agent_book_loss_pct, weigh
from .quantity import MEASURED, PARTIAL, UNPRICED, Quantity
from .report import render_html

__version__ = "0.1.0"

__all__ = [
    "AlertConfig", "load", "Ledger", "LedgerLine", "weigh",
    "per_noc_agent_book_loss_pct", "Quantity", "render_html",
    "MEASURED", "PARTIAL", "UNPRICED",
]
