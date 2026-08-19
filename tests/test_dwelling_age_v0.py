"""Validation: the machine, fed the dwelling-age inputs, must reproduce the
published v0 ledger (What Must Be True v4 s2 / Zero Alerts README s4):

    +115 binds/mo (range +50..+175)
    +25 NOCs/mo (+10..+40)
    +30 UW corrective endorsements/mo   <- the hand ledger counted only the
                                           book's rate shift; the machine
                                           reports that component AND the
                                           coherent total (~+40, adds the
                                           new binds' own NOEs)
    -2,200 forced UW reviews/mo
    -$26K/mo premium from UW corrections
    loss impact = unknown

Tolerances, and why:
  * pinned lines (binds, reviews) reproduce exactly.
  * derived points within 10% (premium within 5%; it is near-arithmetic).
  * derived ranges use worst-case interval propagation, so they are WIDER
    than the hand brackets by construction. The test asserts the machine
    range CONTAINS the published range and is not absurdly wide (<= 2.5x
    the published width).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from weighing_machine import load, per_noc_agent_book_loss_pct, weigh

CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "configs", "dwelling_age.json")


class TestDwellingAgeV0(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load(CONFIG)
        cls.ledger = weigh(cls.cfg)
        cls.pub = cls.cfg.validation["published_v0_ledger"]

    # ---------------------------------------------------------- pinned lines
    def test_binds_reproduce_exactly(self):
        q = self.ledger.line("binds").quantity
        pub = self.pub["binds_per_month"]
        self.assertEqual(q.point, pub["point"])
        self.assertEqual(q.lo, pub["low"])
        self.assertEqual(q.hi, pub["high"])

    def test_forced_reviews_reproduce_exactly(self):
        q = self.ledger.line("forced_reviews").quantity
        self.assertEqual(q.point, self.pub["forced_reviews_per_month"]["point"])

    # --------------------------------------------------------- derived lines
    def test_noc_point_within_10pct(self):
        q = self.ledger.line("nocs").quantity
        target = self.pub["nocs_per_month"]["point"]          # 25
        self.assertLessEqual(abs(q.point - target), 0.10 * target,
                             "NOC point %.2f vs published %d" % (q.point, target))

    def test_noc_range_contains_published(self):
        q = self.ledger.line("nocs").quantity
        pub = self.pub["nocs_per_month"]                       # [10, 40]
        self.assertLessEqual(q.lo, pub["low"])
        self.assertGreaterEqual(q.hi, pub["high"])
        pub_width = pub["high"] - pub["low"]
        self.assertLessEqual(q.hi - q.lo, 2.5 * pub_width,
                             "machine range implausibly wide")

    def test_noe_book_shift_reproduces_v0_within_10pct(self):
        # v0's "+30" = the existing book shifting from the reviewed to the
        # twin NOE rate (~850 x 3.66/100 ~= 31). Source of the identity:
        # ANALYSIS-2026-08-16.md ("31-47 extra events/mo at ~850 binds/mo").
        comps = self.ledger.line("noes").components
        book = [v for k, v in comps.items() if "v0" in k and "omitted" not in k][0]
        target = self.pub["noes_per_month_book_shift_only"]["point"]   # 30
        self.assertLessEqual(abs(book.point - target), 0.10 * target,
                             "NOE book shift %.2f vs published %d"
                             % (book.point, target))

    def test_noe_total_exceeds_book_shift(self):
        # The coherent total adds the new binds' own NOEs (~+9/mo), which the
        # hand ledger omitted. Documented design decision, not drift.
        ln = self.ledger.line("noes")
        comps = ln.components
        book = [v for k, v in comps.items() if "v0" in k and "omitted" not in k][0]
        self.assertGreater(ln.quantity.point, book.point)
        self.assertTrue(35 <= ln.quantity.point <= 45,
                        "coherent NOE total drifted: %.1f" % ln.quantity.point)

    def test_premium_within_5pct(self):
        q = self.ledger.line("uw_correction_premium").quantity
        target = self.pub["uw_correction_premium_usd_per_month"]["point"]  # -26000
        self.assertLessEqual(abs(q.point - target), 0.05 * abs(target),
                             "premium %.0f vs published %d" % (q.point, target))
        self.assertLess(q.point, 0, "foregone premium must be a loss")

    def test_loss_impact_is_unknown(self):
        q = self.ledger.line("loss_impact").quantity
        self.assertFalse(q.is_priced)
        self.assertIsNone(q.point)

    # ------------------------------------------------------------ NOC weight
    def test_per_noc_agent_weight_cure_split(self):
        # 0.74 x 1.0 + 0.26 x 20 = 5.94% of the agent's next-year binds,
        # range [5.2, 6.68] from the cured 0..2% band (scratch-darren).
        q = per_noc_agent_book_loss_pct(self.cfg)
        self.assertAlmostEqual(q.point, 5.94, places=2)
        self.assertAlmostEqual(q.lo, 5.20, places=2)
        self.assertAlmostEqual(q.hi, 6.68, places=2)

    # --------------------------------------------------------- exchange rate
    def test_bind_to_noc_exchange_rate(self):
        r = self.ledger.bind_to_noc_ratio
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r.point, 115 / self.ledger.line("nocs").quantity.point,
                               places=6)
        self.assertTrue(4.0 <= r.point <= 5.5,
                        "gross exchange rate drifted: %.2f" % r.point)
        self.assertIsNone(self.ledger.tolerance_bar)   # never asked, stays unset

    # ------------------------------------------------------ unpriced honesty
    def test_unpriced_lines_never_carry_a_number(self):
        for key in ("gwp_new_binds", "noc_agent_attrition", "noe_cost",
                    "loss_impact"):
            q = self.ledger.line(key).quantity
            self.assertFalse(q.is_priced, key)
            self.assertIsNone(q.point, key)

    def test_priced_subtotal_is_labeled_not_verdict(self):
        ln = self.ledger.line("priced_subtotal")
        # labor saved (+13.2k) + foregone premium (-25.8k) ~= -12.6k
        self.assertTrue(-14000 <= ln.quantity.point <= -11000,
                        "priced subtotal drifted: %.0f" % ln.quantity.point)
        self.assertIn("NOT the verdict", ln.notes)


if __name__ == "__main__":
    unittest.main()
