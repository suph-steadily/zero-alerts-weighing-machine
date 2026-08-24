"""Validation: reproduce Darren's 8/23 breakeven napkin, then supersede it.

His reply to the 8/22 Bucees LHRH update priced the dwelling-age trade:
55 notices/mo, a cured notice at 5% of the agent's future production, an
uncured cancellation at 20%, 25 future policies per agent (5/yr x 5yr),
against 115 incremental binds/mo. Solve for the cancellation share that eats
the gain: 22%, ~12 of 55 notices. Under 12 cancellations/mo the trade is
net-positive, "ish".

The machine must land on his number when fed his assumptions, and show how
the breakeven moves under the measured curve prices (cured ~0 to -2%/event,
scratch-darren v8): the breakeven loosens to ~19-23 of 55.

Documented inconsistency, on purpose: Darren's 8/19 email prices one uncured
NOC at ~7 future policies ($12K), his 8/23 formula uses 25 future policies
per agent. The two napkins disagree by ~3.5x; v8's own portfolio implies
~3.2 binds/agent/yr on average. The real distribution is the cheapest
unpriced-weight pull (INPUTS.md gap list).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from weighing_machine import Quantity

NOTICES = 55.0          # ~25 NOCs + ~30 NOEs per month
BINDS_GAINED = 115.0    # incremental binds per month
FUTURE_POLICIES = 25.0  # his 8/23 assumption: 5 policies/yr x 5 yr tenure


def breakeven_cancel_share(cured_pct: float, uncured_pct: float) -> float:
    """Solve NOTICES x [(1-x) cured + x uncured] x FUTURE_POLICIES = BINDS.
    Returns x, the share of notices that may end in cancellation before the
    trade goes net-negative (in agent-production binds)."""
    per_notice_budget = BINDS_GAINED / (NOTICES * FUTURE_POLICIES)  # in binds
    cured = cured_pct / 100.0
    uncured = uncured_pct / 100.0
    return (per_notice_budget - cured) / (uncured - cured)


class TestDarrenNapkin(unittest.TestCase):
    def test_reproduces_his_22_pct(self):
        x = breakeven_cancel_share(cured_pct=5.0, uncured_pct=20.0)
        self.assertAlmostEqual(x, 0.2242, places=3)
        self.assertAlmostEqual(x * NOTICES, 12.3, places=1)

    def test_his_own_formula_balances_at_the_breakeven(self):
        # Cross-check with the machine's cure-split arithmetic: at the
        # breakeven, total production cost equals the bind gain exactly.
        x = breakeven_cancel_share(5.0, 20.0)
        cure = Quantity(point=1 - x)
        cured = Quantity(point=5.0)
        uncured = Quantity(point=20.0)
        one_minus_cure = Quantity(point=x)
        per_notice_pct = cure.mul(cured).add(one_minus_cure.mul(uncured))
        cost_binds = NOTICES * (per_notice_pct.point / 100.0) * FUTURE_POLICIES
        self.assertAlmostEqual(cost_binds, BINDS_GAINED, places=6)

    def test_curve_prices_loosen_the_breakeven_to_19_23(self):
        # The measured cured price is ~0 to -2%/event (v8), not 5%. That one
        # substitution moves the breakeven from ~12 to ~19-23 of 55.
        hi = breakeven_cancel_share(cured_pct=0.0, uncured_pct=20.0) * NOTICES
        lo = breakeven_cancel_share(cured_pct=2.0, uncured_pct=20.0) * NOTICES
        self.assertAlmostEqual(hi, 23.0, delta=0.1)
        self.assertAlmostEqual(lo, 19.4, delta=0.1)
        self.assertLess(12.4, lo, "curve prices must loosen his ~12")

    def test_observed_cure_rate_sits_between_the_two_verdicts(self):
        # Book-wide 74% cure -> ~26% cancel -> ~14.3 of 55. Above his 22%
        # breakeven (slightly under water by his prices), below the curve
        # breakeven (comfortably positive by measured prices). This is the
        # whole reason cure_price_basis must be named.
        observed = (1 - 0.74) * NOTICES
        self.assertGreater(observed, 0.2242 * NOTICES)
        self.assertLess(observed, breakeven_cancel_share(2.0, 20.0) * NOTICES)

    def test_the_two_napkins_disagree(self):
        # 8/19: one uncured NOC ~ 7 future policies. 8/23: 25 future policies
        # per agent. Kept failing-loudly-in-writing until he names the unit.
        self.assertNotAlmostEqual(7.0, FUTURE_POLICIES, delta=10.0)


if __name__ == "__main__":
    unittest.main()
