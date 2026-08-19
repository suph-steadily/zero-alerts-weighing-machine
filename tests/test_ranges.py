"""Range-propagation sanity: intervals bracket their points, scaling is
linear, direction 'add' is the exact mirror, and unpriced never leaks."""

import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from weighing_machine import Quantity, UNPRICED, load, weigh
from weighing_machine.config import AlertConfig
from weighing_machine.ledger import COUNT

CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "configs", "dwelling_age.json")


class TestQuantityArithmetic(unittest.TestCase):
    def test_range_must_bracket_point(self):
        with self.assertRaises(ValueError):
            Quantity(point=5, low=6, high=7)

    def test_unpriced_must_not_carry_point(self):
        with self.assertRaises(ValueError):
            Quantity(point=5, status=UNPRICED)

    def test_add_sub_are_worst_case(self):
        a = Quantity(point=10, low=8, high=12)
        b = Quantity(point=3, low=2, high=5)
        s = a.add(b)
        self.assertEqual((s.point, s.lo, s.hi), (13, 10, 17))
        d = a.sub(b)
        # low crosses: 8 - 5, high crosses: 12 - 2
        self.assertEqual((d.point, d.lo, d.hi), (7, 3, 10))

    def test_mul_handles_sign_crossing(self):
        a = Quantity(point=10, low=8, high=12)
        g = Quantity(point=1, low=-1, high=2)   # a gap whose CI crosses zero
        m = a.mul(g)
        self.assertEqual((m.point, m.lo, m.hi), (10, -12, 24))

    def test_negate_swaps_bounds(self):
        a = Quantity(point=10, low=8, high=12)
        n = a.negate()
        self.assertEqual((n.point, n.lo, n.hi), (-10, -12, -8))

    def test_unpriced_propagates_and_never_gains_a_point(self):
        a = Quantity(point=10, low=8, high=12)
        u = Quantity(status=UNPRICED, source="the missing weight")
        for out in (a.mul(u), a.add(u), u.sub(a), u.scaled(3), u.negate()):
            self.assertEqual(out.status, UNPRICED)
            self.assertIsNone(out.point)

    def test_denominator_required_on_rates(self):
        with self.assertRaises(ValueError):
            Quantity.from_json({"point": 5.0}, key="something_per_100_bound")


class TestLedgerRanges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load(CONFIG)
        cls.ledger = weigh(cls.cfg)

    def test_every_priced_line_brackets_its_point(self):
        for ln in self.ledger.lines:
            q = ln.quantity
            if q.is_priced:
                self.assertLessEqual(q.lo, q.point, ln.key)
                self.assertLessEqual(q.point, q.hi, ln.key)

    def test_scaling_is_linear_on_counts(self):
        half = weigh(self.cfg, scale=0.5)
        double = weigh(self.cfg, scale=2.0)
        for key in ("binds", "forced_reviews", "nocs", "noes"):
            base = self.ledger.line(key).quantity
            self.assertAlmostEqual(half.line(key).quantity.point, base.point * 0.5)
            self.assertAlmostEqual(double.line(key).quantity.point, base.point * 2.0)
            self.assertAlmostEqual(double.line(key).quantity.lo, base.lo * 2.0)
            self.assertAlmostEqual(double.line(key).quantity.hi, base.hi * 2.0)

    def test_scaling_is_linear_on_priced_dollars(self):
        double = weigh(self.cfg, scale=2.0)
        for key in ("uw_correction_premium", "review_labor_saved"):
            base = self.ledger.line(key).quantity
            self.assertAlmostEqual(double.line(key).quantity.point, base.point * 2.0)

    def test_seven_state_cut_matches_readme(self):
        # Zero Alerts README s4: top-7-states cut = +107 binds (115 x ~0.93)
        cut = weigh(self.cfg, scale=107.0 / 115.0)
        self.assertAlmostEqual(cut.line("binds").quantity.point, 107.0)

    def test_direction_add_is_exact_mirror(self):
        raw = copy.deepcopy(self.cfg.raw)
        raw["alert"]["direction"] = "add"
        tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "_tmp_add_config.json")
        with open(tmp, "w") as f:
            json.dump(raw, f)
        try:
            added = weigh(load(tmp))
        finally:
            os.remove(tmp)
        for ln in self.ledger.lines:
            mirror = added.line(ln.key).quantity
            q = ln.quantity
            if not q.is_priced:
                self.assertFalse(mirror.is_priced, ln.key)
                continue
            self.assertAlmostEqual(mirror.point, -q.point, msg=ln.key)
            self.assertAlmostEqual(mirror.lo, -q.hi, msg=ln.key)   # bounds swap
            self.assertAlmostEqual(mirror.hi, -q.lo, msg=ln.key)

    def test_count_lines_are_counts_dollar_lines_are_dollars(self):
        counts = {ln.key for ln in self.ledger.counts()}
        self.assertEqual(counts, {"binds", "forced_reviews", "nocs", "noes"})
        for ln in self.ledger.dollars():
            self.assertNotIn(ln.key, counts)

    def test_machine_range_wider_than_hand_range_by_construction(self):
        # Worst-case propagation must contain the hand bracket, see the
        # module docstring in quantity.py.
        pub = self.cfg.validation["published_v0_ledger"]["nocs_per_month"]
        q = self.ledger.line("nocs").quantity
        self.assertLessEqual(q.lo, pub["low"])
        self.assertGreaterEqual(q.hi, pub["high"])


if __name__ == "__main__":
    unittest.main()
